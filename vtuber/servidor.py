"""Servidor del VTuber: une cerebro (IA local), voz (edge-tts) y avatar (navegador/OBS).

    python servidor.py              -> http://127.0.0.1:8765/avatar  (OBS)
                                       http://127.0.0.1:8765/panel   (control)

API HTTP (para que cualquier programa o IA controle el avatar):
    POST /api/chat      {"mensaje": "...", "usuario": "opcional"}   la IA responde y habla
    POST /api/decir     {"texto": "[feliz] Hola", "emocion": "opcional"}  habla sin IA
    POST /api/emocion   {"nombre": "feliz", "duracion": 0}          0 = hasta que cambie
    POST /api/cabeza    {"x": 0, "y": 0, "inclinacion": 0}          postura de la cabeza
    POST /api/mirar     {"x": 0, "y": 0, "duracion": 2}             dirección de la mirada
    POST /api/parar     {}                                          calla y vacía la cola
    POST /api/olvidar   {}                                          borra la memoria de la charla
    GET  /api/estado
"""
import argparse
import asyncio
import json
import logging
import uuid
from pathlib import Path

from aiohttp import WSMsgType, web

from cerebro import Cerebro
from emociones import EMOCIONES, dividir, normalizar
from voz import Voz

RAIZ = Path(__file__).resolve().parent
WEB = RAIZ / "web"
AUDIO = RAIZ / "audio_cache"

log = logging.getLogger("vtuber")


class VTuber:
    def __init__(self, cfg):
        self.cfg = cfg
        self.cerebro = Cerebro(cfg.get("cerebro", {}), cfg.get("personaje", {}))
        self.voz = Voz(cfg.get("voz", {}), AUDIO)
        self.avatares = set()
        self.paneles = set()
        self.turno = asyncio.Lock()   # una respuesta detrás de otra, en orden

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
        await self._enviar(self.paneles, {"tipo": "registro", "quien": quien, "texto": texto})

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
            except Exception as err:  # sin voz, el avatar al menos muestra la emoción y el texto
                await self.registrar("error", f"No se pudo generar la voz: {err}")
            await self.al_avatar(mensaje)

    async def chat(self, mensaje, usuario=None):
        async with self.turno:
            await self.registrar("usuario", f"{usuario}: {mensaje}" if usuario else mensaje)
            await self.al_avatar({"tipo": "emocion", "nombre": "pensativa", "duracion": 30})
            try:
                respuesta = await self.cerebro.responder(mensaje, usuario)
            except Exception as err:
                await self.al_avatar({"tipo": "emocion", "nombre": "neutral"})
                await self.registrar("error", f"El cerebro no responde: {err}")
                raise
            await self.registrar("ia", respuesta)
            await self.decir(respuesta, "neutral")
            return respuesta


# -------------------------------------------------------------------- rutas
def crear_app(vt: VTuber):
    app = web.Application()
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
        finally:
            grupo.discard(ws)
        return ws

    @rutas.get("/api/estado")
    async def estado(_):
        c = vt.cerebro
        return web.json_response({
            "emociones": EMOCIONES,
            "avatares_conectados": len(vt.avatares),
            "cerebro": {"url": c.url, "modelo": c.modelo, "mensajes_en_memoria": len(c.historial)},
            "voz": vt.voz.voz,
        })

    @rutas.post("/api/chat")
    async def chat(req):
        datos = await json_de(req)
        mensaje = str(datos.get("mensaje", "")).strip()
        if not mensaje:
            raise web.HTTPBadRequest(text="Falta 'mensaje'")
        try:
            respuesta = await vt.chat(mensaje, datos.get("usuario"))
        except Exception as err:
            return web.json_response({"error": str(err)}, status=502)
        return web.json_response({"respuesta": respuesta})

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

    @rutas.post("/api/olvidar")
    async def olvidar(_):
        vt.cerebro.olvidar()
        await vt.registrar("sistema", "Memoria de la conversación borrada")
        return web.json_response({"ok": True})

    app.add_routes(rutas)
    app.router.add_static("/audio", AUDIO)
    app.router.add_static("/", WEB)   # avatar.js, panel.js, capas/...
    return app


def main():
    ap = argparse.ArgumentParser(description="Servidor del VTuber")
    ap.add_argument("--config", default=str(RAIZ / "config.json"))
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)
    srv = cfg.get("servidor", {})
    host, puerto = srv.get("host", "127.0.0.1"), srv.get("puerto", 8765)
    vt = VTuber(cfg)
    print(f"\n  Avatar (OBS):  http://{host}:{puerto}/avatar"
          f"\n  Panel:         http://{host}:{puerto}/panel"
          f"\n  Cerebro:       {vt.cerebro.modelo} en {vt.cerebro.url}"
          f"\n  Voz:           {vt.voz.voz}\n")
    web.run_app(crear_app(vt), host=host, port=puerto, print=None)


if __name__ == "__main__":
    main()
