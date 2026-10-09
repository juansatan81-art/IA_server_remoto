"""Servidor del VTuber: une cerebro (IA local), voz (edge-tts) y avatar (navegador/OBS).

    python servidor.py              -> http://127.0.0.1:8765/avatar  (OBS)
                                       http://127.0.0.1:8765/panel   (control)

API HTTP (para que cualquier programa o IA controle el avatar):
    POST /api/chat      {"mensaje": "...", "usuario": "opcional", "imagenes": ["data:image/jpeg;base64,..."]}
                        la IA responde y habla (las imágenes son opcionales: fotos, capturas...)
    POST /api/decir     {"texto": "[feliz] Hola", "emocion": "opcional"}  habla sin IA
    POST /api/emocion   {"nombre": "feliz", "duracion": 0}          0 = hasta que cambie
    POST /api/cabeza    {"x": 0, "y": 0, "inclinacion": 0}          postura de la cabeza
    POST /api/mirar     {"x": 0, "y": 0, "duracion": 2}             dirección de la mirada
    POST /api/parar     {}                                          calla y vacía la cola
    POST /api/olvidar   {}                                          borra la memoria de la charla
    GET  /api/estado

Modo directo (Lara streamea sola: elige a quién responder, habla cuando el chat calla...):
    POST /api/directo/iniciar   {"plan": "hoy jugamos a Minecraft..."}
    POST /api/directo/terminar  {}            guarda un resumen para recordarlo
    POST /api/directo/chat      {"autor": "Pablo", "texto": "...", "tipo": "mensaje|superchat|miembro",
                                 "cantidad": "5 €"}   un mensaje del chat (YouTube u otro programa)
    POST /api/directo/panico    {}            calla, vacía la cola y cambia de tema
    POST /api/directo/vista     {"imagen": "data:image/jpeg;base64,..."}   lo que hay en pantalla
    POST /api/youtube/conectar  {"video": "enlace o id (opcional)"}
    POST /api/youtube/desconectar {}

Glosario (palabras y memes que conoce sin buscar; los nuevos esperan tu aprobación):
    GET  /api/glosario
    POST /api/glosario          {"termino": "...", "significado": "...", "estado": "aprobado|pendiente|rechazado"}
    POST /api/glosario/borrar   {"termino": "..."}
"""
import argparse
import asyncio
import atexit
import json
import logging
import random
import sys
import time
import urllib.request
import uuid
from pathlib import Path

from aiohttp import WSMsgType, web

import filtros
from cerebro import Cerebro
from directo import Directo
from emociones import EMOCIONES, dividir, normalizar
from glosario import Glosario
from memoria import Memoria
from voz import Voz
from youtube import YouTube

RAIZ = Path(__file__).resolve().parent
WEB = RAIZ / "web"
AUDIO = RAIZ / "audio_cache"
MEMORIA = RAIZ / "memoria"

log = logging.getLogger("vtuber")

# lo que dice mientras piensa a fondo una respuesta difícil
RELLENOS = ["[pensativa] Mmm, déjame pensarlo un momento.", "[pensativa] Uy, buena pregunta… a ver.",
            "[pensativa] Espera, que esta tiene miga.", "[pensativa] Mmm… dame un segundito."]


class VTuber:
    def __init__(self, cfg):
        self.cfg = cfg
        self.nombre = cfg.get("personaje", {}).get("nombre", "la VTuber")
        self.cerebro = Cerebro(cfg.get("cerebro", {}), cfg.get("personaje", {}))
        self.ayudante = filtros.Ayudante(cfg.get("ayudante", {}), self.cerebro.base_ollama)
        self.memoria = Memoria(MEMORIA)
        self.glosario = Glosario(MEMORIA)
        self._por_aprender = []       # búsquedas de las que el glosario puede sacar un término
        self.cerebro.al_buscar = lambda consulta, resultado: self._por_aprender.append((consulta, resultado))
        self.fallos_voz = 0
        self._ultimo_aviso = ("", 0)
        self.sin_pantallas_desde = None   # desde cuándo no hay ni panel ni avatar abiertos
        self.modelos_descargados = False
        self.cerebro.recuerdos = self.memoria.recuerdos()
        self.voz = Voz(cfg.get("voz", {}), AUDIO)
        self.directo = Directo(self, cfg.get("directo", {}))
        self.youtube = YouTube(cfg.get("youtube", {}), self.directo.recibir, self.registrar)
        self.avatares = set()
        self.paneles = set()
        self.turno = asyncio.Lock()   # una respuesta detrás de otra, en orden
        self.pendientes = {}          # frases enviadas al avatar que aún no ha terminado de decir
        self.fin_habla = time.monotonic()
        self.generacion = 0           # el botón de pánico la sube: lo que se estaba pensando se tira

    # ---------------------------------------------------------------- difusión
    async def _enviar(self, destinos, mensaje):
        datos = json.dumps(mensaje, ensure_ascii=False)
        for ws in list(destinos):
            try:
                await ws.send_str(datos)
            except (ConnectionResetError, RuntimeError):
                destinos.discard(ws)

    async def al_avatar(self, mensaje):
        await self._enviar(self.avatares, mensaje)

    async def registrar(self, quien, texto):
        log.info("[%s] %s", quien, texto)
        self.directo.apuntar(quien, texto)
        await self._enviar(self.paneles, {"tipo": "registro", "quien": quien, "texto": texto})

    # ---------------------------------------------------------------- ¿está hablando?
    def hablando(self):
        ahora = time.monotonic()
        for i, limite in list(self.pendientes.items()):
            if ahora > limite:            # por si ningún avatar avisa (ninguno abierto, error...)
                del self.pendientes[i]
        return bool(self.pendientes)

    def ocupada(self):
        return self.turno.locked() or self.hablando()

    async def aviso_avatar(self, texto):
        """Problemas de sonido que cuenta el avatar (el mismo aviso, como mucho cada 30 s)."""
        ahora = time.monotonic()
        anterior, cuando = self._ultimo_aviso
        if not texto or (texto == anterior and ahora - cuando < 30):
            return
        self._ultimo_aviso = (texto, ahora)
        await self.registrar("error", f"Avatar: {texto}")

    def termino_frase(self, id_frase):
        if self.pendientes.pop(id_frase, None) is not None and not self.pendientes:
            self.fin_habla = time.monotonic()

    # ---------------------------------------------------------------- acciones
    async def decir(self, texto, emocion=None):
        """Habla un texto que puede llevar etiquetas [emocion]."""
        for emo, frase in dividir(texto, normalizar(emocion) if emocion else None):
            if not frase:
                await self.al_avatar({"tipo": "emocion", "nombre": emo})
                continue
            mensaje = {"tipo": "hablar", "id": uuid.uuid4().hex, "texto": frase, "emocion": emo}
            try:
                mensaje["audio"] = "/audio/" + await self.voz.sintetizar(frase)
                self.fallos_voz = 0
            except Exception as err:  # sin voz, el avatar al menos muestra la emoción y el texto
                self.fallos_voz += 1
                consejo = ""
                if self.fallos_voz == 3:
                    consejo = (" — La voz falla seguido: suele ser un bloqueo temporal de Microsoft o "
                               "una versión vieja de edge-tts. Cierra y vuelve a abrir iniciar.bat (lo "
                               "actualiza solo) y comprueba tu conexión a internet.")
                await self.registrar("error", f"No se pudo generar la voz: {err}{consejo}")
            if self.avatares:
                # margen generoso: unos 15 caracteres por segundo, más la carga del audio
                self.pendientes[mensaje["id"]] = time.monotonic() + 4 + len(frase) / 10
            await self.al_avatar(mensaje)
        if not self.pendientes:
            self.fin_habla = time.monotonic()

    async def _revisar_y_decir(self, respuesta, generacion):
        """Último control antes de la voz: si se pulsó pánico o la frase no es apta, no se dice."""
        if generacion != self.generacion:
            await self.registrar("sistema", f"(descartado por pánico) {respuesta}")
            return None
        apto, motivo = await self.ayudante.revisar_salida(respuesta)
        if not apto:
            await self.registrar("filtro", f"Frase bloqueada ({motivo or 'no apta'}): {respuesta}")
            respuesta = filtros.FRASE_SEGURA
        if generacion != self.generacion:
            return None
        await self.registrar("ia", respuesta)
        await self.decir(respuesta, "neutral")
        return respuesta

    async def responder_y_hablar(self, mensaje, usuario=None, imagenes=None, nota=""):
        async with self.turno:
            generacion = self.generacion
            texto = f"{usuario}: {mensaje}" if usuario else mensaje
            if imagenes:
                texto += f"  [{len(imagenes)} imagen{'es' if len(imagenes) > 1 else ''}]"
            await self.registrar("usuario", texto)
            await self.al_avatar({"tipo": "emocion", "nombre": "pensativa", "duracion": 30})

            async def aviso(que):
                await self.registrar("sistema", que)
                await self.al_avatar({"tipo": "emocion", "nombre": "pensativa", "duracion": 30})
                if que.startswith("Pensando"):   # para que no haya un silencio raro mientras piensa
                    await self.decir(random.choice(RELLENOS))

            self.modelos_descargados = False
            nota = " ".join(p for p in (nota, self.glosario.nota(mensaje)) if p)
            try:
                respuesta = await self.cerebro.responder(mensaje, usuario, imagenes, aviso, nota)
            except Exception as err:
                await self.al_avatar({"tipo": "emocion", "nombre": "neutral"})
                await self.registrar("error", f"El cerebro no responde: {err}")
                raise
            dicho = await self._revisar_y_decir(respuesta, generacion)
        if self._por_aprender:
            asyncio.create_task(self._aprender_terminos())
        return dicho

    async def _aprender_terminos(self):
        """Después de contestar (para no retrasar la respuesta): ¿la búsqueda era un término nuevo?"""
        while self._por_aprender:
            consulta, resultado = self._por_aprender.pop(0)
            async with self.turno:
                nuevo = await self.glosario.aprender(self.cerebro, consulta, resultado)
            if nuevo:
                await self.registrar("sistema", f"Glosario: «{nuevo['termino']}» apuntado; revísalo en el panel")
                await self._enviar(self.paneles, {"tipo": "glosario"})

    async def chat(self, mensaje, usuario=None, imagenes=None):
        """Charla directa desde el panel (tú hablándole). En directo, también sabe el contexto."""
        nota = self.directo._nota() if self.directo.activo else ""
        self.directo.seguidas_sola = 0
        if self.directo.activo and not imagenes:
            imagenes = self.directo._vista()
        return await self.responder_y_hablar(mensaje, usuario, imagenes, nota)

    async def hablar_sola(self, nota, imagenes, extra):
        async with self.turno:
            self.modelos_descargados = False
            generacion = self.generacion
            pensamiento, dice = await self.cerebro.hablar_sola(nota, imagenes, extra)
            if pensamiento:
                await self.registrar("pensamiento", pensamiento)
            if not dice:
                return ""
            return await self._revisar_y_decir(dice, generacion) or ""


    # ---------------------------------------------------------------- apagar los modelos
    def _modelos(self):
        if self.cerebro.api != "ollama":
            return []
        return [(self.cerebro.base_ollama, m) for m in {self.cerebro.modelo, self.ayudante.modelo} if m]

    def descargar_modelos(self):
        """Saca los modelos de la memoria de la gráfica y de la RAM (keep_alive = 0).

        Es síncrono a propósito: se llama también al cerrar la ventana, cuando ya no hay bucle.
        """
        for base, modelo in self._modelos():
            datos = json.dumps({"model": modelo, "keep_alive": 0}).encode()
            peticion = urllib.request.Request(f"{base}/api/generate", data=datos,
                                              headers={"Content-Type": "application/json"})
            try:
                urllib.request.urlopen(peticion, timeout=3).read()
            except Exception:
                pass   # Ollama cerrado o el modelo ya no estaba cargado
        self.modelos_descargados = True

    async def vigilar_pantallas(self, espera):
        """Si se cierran el panel y el avatar (y OBS), se apaga el modelo pasado `espera` s."""
        while True:
            await asyncio.sleep(10)
            if self.avatares or self.paneles:
                self.sin_pantallas_desde = None
                continue
            if self.sin_pantallas_desde is None:
                self.sin_pantallas_desde = time.monotonic()
            if self.modelos_descargados or time.monotonic() - self.sin_pantallas_desde < espera:
                continue
            if self.directo.activo:
                await self.directo.terminar()      # guarda el recuerdo antes de apagar
            await asyncio.to_thread(self.descargar_modelos)
            log.info("No queda ninguna pantalla abierta: modelo apagado (se vuelve a cargar al hablar).")


def apagar_al_cerrar_ventana(vt):
    """En Windows, cerrar la ventana negra mata el programa sin avisar a Python: se registra un
    manejador para que antes descargue el modelo (Windows da unos segundos para ello)."""
    atexit.register(vt.descargar_modelos)          # Ctrl+C o cierre normal
    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes

    manejador_t = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

    def manejar(evento):
        # 0 Ctrl+C, 1 Ctrl+Break, 2 cerrar ventana, 5 cerrar sesión, 6 apagar el PC
        if evento in (0, 1, 2, 5, 6) and not vt.modelos_descargados:
            vt.descargar_modelos()
        return False   # que Windows siga cerrando como siempre

    vt._manejador_ventana = manejador_t(manejar)   # hay que guardarlo para que no se borre
    ctypes.windll.kernel32.SetConsoleCtrlHandler(vt._manejador_ventana, True)


# -------------------------------------------------------------------- rutas
def crear_app(vt: VTuber):
    app = web.Application(client_max_size=32 * 1024 * 1024)   # caben fotos y capturas
    rutas = web.RouteTableDef()

    async def json_de(req):
        try:
            return await req.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise web.HTTPBadRequest(text="Se esperaba un cuerpo JSON")

    @rutas.get("/")
    async def inicio(_):
        raise web.HTTPFound("/panel")

    @rutas.get("/avatar")
    async def avatar(_):
        return web.FileResponse(WEB / "avatar.html")

    @rutas.get("/panel")
    async def panel(_):
        return web.FileResponse(WEB / "panel.html")

    @rutas.get("/ws")
    async def socket(req):
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(req)
        grupo = vt.paneles if req.query.get("rol") == "panel" else vt.avatares
        grupo.add(ws)
        try:
            async for msg in ws:
                if msg.type == WSMsgType.ERROR:
                    break
                # el avatar avisa de lo que hace de verdad; el panel lo muestra en directo
                if msg.type == WSMsgType.TEXT and grupo is vt.avatares:
                    try:
                        datos = json.loads(msg.data)
                    except json.JSONDecodeError:
                        continue
                    if datos.get("tipo") == "estado":
                        await vt._enviar(vt.paneles, {**datos, "tipo": "estado_avatar"})
                    elif datos.get("tipo") == "fin_audio":
                        vt.termino_frase(datos.get("id"))
                    elif datos.get("tipo") == "aviso_audio":   # el navegador no pudo reproducir la voz
                        await vt.aviso_avatar(str(datos.get("texto", ""))[:300])
        finally:
            grupo.discard(ws)
        return ws

    @rutas.get("/api/estado")
    async def estado(_):
        c = vt.cerebro
        return web.json_response({
            "emociones": EMOCIONES,
            "avatares_conectados": len(vt.avatares),
            "cerebro": {"url": c.url, "modelo": c.modelo, "mensajes_en_memoria": len(c.historial),
                        "internet": c.internet},
            "voz": vt.voz.voz,
            "ayudante": vt.ayudante.modelo if vt.ayudante.disponible else "",
            "directo": vt.directo.estado(),
            "youtube": {"configurado": vt.youtube.configurado, "estado": vt.youtube.estado},
        })

    @rutas.post("/api/chat")
    async def chat(req):
        datos = await json_de(req)
        mensaje = str(datos.get("mensaje", "")).strip()
        imagenes = datos.get("imagenes") or []
        if not isinstance(imagenes, list) or not all(isinstance(i, str) for i in imagenes):
            raise web.HTTPBadRequest(text="'imagenes' debe ser una lista de textos base64")
        if not mensaje and imagenes:
            mensaje = "Mira esto."
        if not mensaje:
            raise web.HTTPBadRequest(text="Falta 'mensaje'")
        try:
            respuesta = await vt.chat(mensaje, datos.get("usuario"), imagenes)
        except Exception as err:
            return web.json_response({"error": str(err)}, status=502)
        return web.json_response({"respuesta": respuesta or ""})

    @rutas.post("/api/decir")
    async def decir(req):
        datos = await json_de(req)
        texto = str(datos.get("texto", "")).strip()
        if not texto:
            raise web.HTTPBadRequest(text="Falta 'texto'")
        async with vt.turno:
            await vt.registrar("ia", texto)
            await vt.decir(texto, datos.get("emocion"))
        return web.json_response({"ok": True})

    @rutas.post("/api/emocion")
    async def emocion(req):
        datos = await json_de(req)
        nombre = normalizar(str(datos.get("nombre", "")))
        if not nombre:
            raise web.HTTPBadRequest(text=f"Emoción desconocida. Opciones: {', '.join(EMOCIONES)}")
        await vt.al_avatar({"tipo": "emocion", "nombre": nombre,
                            "duracion": float(datos.get("duracion", 0))})
        return web.json_response({"ok": True, "emocion": nombre})

    @rutas.post("/api/cabeza")
    async def cabeza(req):
        d = await json_de(req)
        await vt.al_avatar({"tipo": "cabeza", "x": float(d.get("x", 0)), "y": float(d.get("y", 0)),
                            "inclinacion": float(d.get("inclinacion", 0))})
        return web.json_response({"ok": True})

    @rutas.post("/api/mirar")
    async def mirar(req):
        d = await json_de(req)
        await vt.al_avatar({"tipo": "mirar", "x": float(d.get("x", 0)), "y": float(d.get("y", 0)),
                            "duracion": float(d.get("duracion", 2))})
        return web.json_response({"ok": True})

    @rutas.post("/api/parar")
    async def parar(_):
        await vt.al_avatar({"tipo": "parar"})
        return web.json_response({"ok": True})

    @rutas.post("/api/directo/iniciar")
    async def directo_iniciar(req):
        datos = await json_de(req)
        await vt.directo.iniciar(str(datos.get("plan", "")))
        if vt.youtube.configurado and datos.get("youtube", True) and vt.youtube.estado == "desconectado":
            await vt.youtube.conectar(str(datos.get("video", "")))
        return web.json_response({"ok": True, "directo": vt.directo.estado()})

    @rutas.post("/api/directo/terminar")
    async def directo_terminar(_):
        await vt.youtube.desconectar()
        resumen = await vt.directo.terminar()
        return web.json_response({"ok": True, "resumen": resumen})

    @rutas.post("/api/directo/chat")
    async def directo_chat(req):
        d = await json_de(req)
        tipo = str(d.get("tipo", "mensaje"))
        if tipo not in ("mensaje", "superchat", "miembro"):
            raise web.HTTPBadRequest(text="tipo debe ser mensaje, superchat o miembro")
        extra = {"cantidad": str(d.get("cantidad", ""))} if tipo == "superchat" else {}
        aceptado = vt.directo.recibir(str(d.get("autor", "")), str(d.get("texto", "")), tipo, **extra)
        if not vt.directo.activo:
            return web.json_response({"ok": aceptado, "aviso": "El modo directo está apagado: "
                                      "el mensaje espera en la cola hasta que lo inicies."})
        return web.json_response({"ok": aceptado})

    @rutas.post("/api/directo/panico")
    async def directo_panico(_):
        await vt.directo.panico()
        return web.json_response({"ok": True})

    @rutas.post("/api/directo/vista")
    async def directo_vista(req):
        d = await json_de(req)
        imagen = d.get("imagen")
        if not isinstance(imagen, str) or not imagen:
            raise web.HTTPBadRequest(text="Falta 'imagen'")
        vt.directo.poner_vista(imagen)
        return web.json_response({"ok": True})

    @rutas.post("/api/youtube/conectar")
    async def youtube_conectar(req):
        if not vt.youtube.configurado:
            return web.json_response({"error": "Falta youtube.api_key en config.json"}, status=400)
        d = await json_de(req)
        await vt.youtube.conectar(str(d.get("video", "")))
        return web.json_response({"ok": True})

    @rutas.post("/api/youtube/desconectar")
    async def youtube_desconectar(_):
        await vt.youtube.desconectar()
        return web.json_response({"ok": True})

    @rutas.get("/api/glosario")
    async def glosario_ver(_):
        return web.json_response({"terminos": vt.glosario.terminos})

    @rutas.post("/api/glosario")
    async def glosario_poner(req):
        d = await json_de(req)
        try:
            t = vt.glosario.poner(str(d.get("termino", "")),
                                  d.get("significado") if isinstance(d.get("significado"), str) else None,
                                  d.get("estado"), d.get("alias") if isinstance(d.get("alias"), list) else None)
        except ValueError as err:
            raise web.HTTPBadRequest(text=str(err))
        return web.json_response({"ok": True, "termino": t})

    @rutas.post("/api/glosario/borrar")
    async def glosario_borrar(req):
        d = await json_de(req)
        return web.json_response({"ok": vt.glosario.borrar(str(d.get("termino", "")))})

    @rutas.post("/api/olvidar")
    async def olvidar(_):
        vt.cerebro.olvidar()
        await vt.registrar("sistema", "Memoria de la conversación borrada")
        return web.json_response({"ok": True})

    async def al_arrancar(_):
        vt.directo.arrancar_bucle()
        espera = vt.cfg.get("cerebro", {}).get("apagar_sin_pantallas", 120)
        if espera:
            asyncio.create_task(vt.vigilar_pantallas(espera))

    app.on_startup.append(al_arrancar)
    app.add_routes(rutas)
    app.router.add_static("/audio", AUDIO)
    app.router.add_static("/", WEB)   # avatar.js, panel.js, capas/...
    return app


def mezclar(base, encima):
    """config.local.json pisa a config.json, apartado por apartado."""
    for clave, valor in encima.items():
        if isinstance(valor, dict) and isinstance(base.get(clave), dict):
            mezclar(base[clave], valor)
        else:
            base[clave] = valor
    return base


def main():
    ap = argparse.ArgumentParser(description="Servidor del VTuber")
    ap.add_argument("--config", default=str(RAIZ / "config.json"))
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)
    # tus ajustes privados (clave de YouTube...) van aquí: git no lo sube ni lo pisa al actualizar
    local = Path(args.config).with_name("config.local.json")
    if local.exists():
        with open(local, encoding="utf-8") as f:
            mezclar(cfg, json.load(f))
    srv = cfg.get("servidor", {})
    host, puerto = srv.get("host", "127.0.0.1"), srv.get("puerto", 8765)
    vt = VTuber(cfg)
    if cfg.get("cerebro", {}).get("apagar_al_cerrar", True):
        apagar_al_cerrar_ventana(vt)
    print(f"\n  Avatar (OBS):  http://{host}:{puerto}/avatar"
          f"\n  Panel:         http://{host}:{puerto}/panel"
          f"\n  Cerebro:       {vt.cerebro.modelo} en {vt.cerebro.url}"
          f"\n  Ayudante:      {vt.ayudante.modelo or '(ninguno: solo reglas)'}"
          f"{' en el procesador' if vt.ayudante.modelo and vt.ayudante.en_procesador else ''}"
          f"\n  Voz:           {vt.voz.voz}\n")
    try:
        web.run_app(crear_app(vt), host=host, port=puerto, print=None, access_log=None)
    except OSError as err:
        if err.errno in (98, 10048) or "10048" in str(err):
            print(f"\n  ERROR: el puerto {puerto} ya está en uso: hay OTRO servidor del VTuber abierto"
                  f"\n  (una ventana negra anterior, o uno que arrancó otro programa)."
                  f"\n  Ciérralo y vuelve a intentarlo. En PowerShell puedes cerrarlo con:"
                  f"\n    Stop-Process -Id (Get-NetTCPConnection -LocalPort {puerto}).OwningProcess -Force\n")
            raise SystemExit(1)
        raise


if __name__ == "__main__":
    main()
