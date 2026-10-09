"""Modo directo: el "bucle de vida" que hace que Lara streamee por su cuenta.

Cada medio segundo: percibe (chat, eventos, pantalla, cuánto lleva callada), decide (¿a
quién responde?, ¿saca un tema?, ¿se calla?) y actúa (habla, cambia de emoción).

- El chat entra en una cola. Se descarta el spam y se elige UN mensaje cada vez que Lara
  termina de hablar, puntuando: preguntas, menciones a Lara, Super Chats, miembros, gente
  nueva o a la que aún no ha respondido. Los mensajes viejos caducan.
- Si el chat está tranquilo, piensa en silencio y decide si dice algo por su cuenta
  (comentar la pantalla, seguir el plan del directo, preguntar al chat...).
- Tiene un ánimo que cambia con lo que pasa y que influye en cómo habla.
- Al terminar el directo escribe un resumen que recordará en los siguientes.
"""
import asyncio
import logging
import random
import re
import time
import unicodedata
from collections import deque

import filtros

log = logging.getLogger("vtuber")

_POSITIVO = re.compile(r"te quiero|te amo|guap[ao]|lind[ao]|preciosa|crack|genial|incre[ií]ble|"
                       r"me encanta|bonit[ao]|jaja|xd|<3|❤|💕|😍|🥰", re.I)
_NEGATIVO = re.compile(r"aburrid|fe[ao]|mal[ao]|odio|callate|cállate|basura|horrible", re.I)


def _normalizar(texto):
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9ñ ]+", "", t).strip()


class Directo:
    def __init__(self, vt, cfg):
        self.vt = vt
        self.silencio_min = cfg.get("silencio_min", 12)    # segundos callada antes de hablar sola
        self.silencio_max = cfg.get("silencio_max", 30)
        self.caducidad = cfg.get("caducidad_mensajes", 90)  # un mensaje de hace 90 s ya no se responde
        self.max_cola = cfg.get("max_cola", 300)
        self.pausa = cfg.get("pausa_entre_frases", 0.8)    # respiro entre una respuesta y la siguiente
        self.vista_fresca = cfg.get("vista_fresca", 25)     # una captura de hace más ya no vale
        self.ver_en_respuestas = cfg.get("ver_en_respuestas", True)

        self.activo = False
        self.plan = ""
        self.inicio = None
        self.cola = deque(maxlen=self.max_cola)
        self.eventos = deque(maxlen=50)
        self.respondidos = {}         # autor -> momento en que se le respondió
        self.dichos = deque(maxlen=12)  # temas recientes de lo que ha dicho ella sola
        self.registro = []            # lo que pasa en el directo, para el resumen final
        self.animo = {"humor": 0.3, "energia": 0.8}
        self.cambiar_tema = False
        self.proximo_espontaneo = 0
        self.vista = None             # (momento, imagen) última captura de pantalla
        self.ignorados = 0
        self.saludado = False
        self._tarea = None

    # ------------------------------------------------------------ control
    def arrancar_bucle(self):
        if not self._tarea:
            self._tarea = asyncio.create_task(self._bucle())

    async def iniciar(self, plan=""):
        self.activo = True
        self.plan = plan.strip()
        self.inicio = time.monotonic()
        self.registro = []
        self.saludado = False
        self.animo = {"humor": 0.3, "energia": 0.8}
        self.proximo_espontaneo = time.monotonic() + 2   # que salude al empezar
        await self.vt.registrar("sistema", "Modo directo activado" + (f". Plan: {self.plan}" if self.plan else ""))

    async def terminar(self, guardar=True):
        """Para el modo directo y, si hubo algo, escribe el resumen para recordarlo."""
        self.activo = False
        self.cola.clear()
        self.eventos.clear()
        resumen = ""
        if guardar and len(self.registro) >= 4:
            resumen = await self._resumir()
            if resumen:
                self.vt.memoria.guardar_directo(resumen)
                self.vt.cerebro.recuerdos = self.vt.memoria.recuerdos()
        self.registro = []
        await self.vt.registrar("sistema", "Modo directo terminado" + (f". Recuerdo guardado: {resumen}" if resumen else ""))
        return resumen

    async def panico(self):
        """Botón de pánico: calla, olvida lo pendiente y cambia de tema."""
        self.vt.generacion += 1        # lo que se esté pensando ahora se descarta
        self.vt.pendientes.clear()
        await self.vt.al_avatar({"tipo": "parar"})
        await self.vt.al_avatar({"tipo": "emocion", "nombre": "neutral"})
        self.cola.clear()
        self.eventos.clear()
        self.cambiar_tema = True
        self.proximo_espontaneo = time.monotonic() + 3
        await self.vt.registrar("sistema", "PÁNICO: callada, cola vaciada; cambiará de tema")

    def poner_vista(self, imagen):
        self.vista = (time.monotonic(), imagen)

    def _vista(self):
        if self.vista and time.monotonic() - self.vista[0] < self.vista_fresca:
            return [self.vista[1]]
        return []

    # ------------------------------------------------------------ entrada
    def recibir(self, autor, texto, tipo="mensaje", **extra):
        """Llega algo del chat. tipo: mensaje | superchat | miembro | regalo."""
        autor = (autor or "Alguien").strip()[:40]
        texto = (texto or "").strip()
        if tipo != "mensaje":
            self.eventos.append({"autor": autor, "texto": texto, "tipo": tipo, **extra})
            return True
        if not texto or filtros.es_spam(texto):
            return False
        self.cola.append({"autor": autor, "texto": texto, "t": time.monotonic(),
                          "clave": _normalizar(texto), **extra})
        return True

    def _elegir(self):
        """El mensaje más interesante de la cola (y quita los que ya no valen)."""
        ahora = time.monotonic()
        while self.cola and ahora - self.cola[0]["t"] > self.caducidad:
            self.cola.popleft()
        if not self.cola:
            return None, []
        nombre = _normalizar(self.vt.nombre)
        repeticiones = {}
        for m in self.cola:
            repeticiones[m["clave"]] = repeticiones.get(m["clave"], 0) + 1

        def puntos(m):
            p = 0.0
            if "?" in m["texto"]:
                p += 3
            if nombre and nombre in m["clave"]:
                p += 3
            if m.get("moderador") or m.get("dueño"):
                p += 2
            if m.get("miembro"):
                p += 1.5
            if m["autor"] not in self.vt.memoria.espectadores:
                p += 2                                    # alguien nuevo
            hace = ahora - self.respondidos.get(m["autor"], -1e9)
            if hace < 300:
                p -= 4 * (1 - hace / 300)                 # ya le respondió hace poco
            largo = len(m["texto"])
            p += 1 if 12 <= largo <= 160 else -1
            p += min(repeticiones[m["clave"]] - 1, 3)     # muchos dicen lo mismo
            p -= (ahora - m["t"]) / self.caducidad * 2    # los recientes, antes
            return p + random.random() * 0.5              # un poco de azar, como una persona

        elegido = max(self.cola, key=puntos)
        # se quitan el elegido y los que dicen lo mismo
        iguales = [m for m in self.cola if m["clave"] == elegido["clave"]]
        for m in iguales:
            self.cola.remove(m)
        elegido["varios"] = len(iguales)
        ambiente = [f"{m['autor']}: {m['texto']}" for m in list(self.cola)[-5:]]
        return elegido, ambiente

    # ------------------------------------------------------------ contexto
    def _texto_animo(self):
        h, e = self.animo["humor"], self.animo["energia"]
        humor = ("muy contenta" if h > 0.6 else "de buen humor" if h > 0.2 else
                 "tranquila" if h > -0.2 else "un poco desanimada")
        energia = "con mucha energía" if e > 0.7 else "a gusto" if e > 0.4 else "algo cansada"
        return f"Ahora mismo te sientes {humor} y {energia}."

    def _cambiar_animo(self, humor=0.0, energia=0.0):
        self.animo["humor"] = max(-1, min(1, self.animo["humor"] * 0.97 + humor))
        self.animo["energia"] = max(0, min(1, self.animo["energia"] + energia))

    def _nota(self, extra=""):
        partes = []
        if self.inicio:
            minutos = int((time.monotonic() - self.inicio) / 60)
            partes.append(f"Estás en directo desde hace {minutos} minutos.")
        if self.plan:
            partes.append(f"Plan del directo de hoy: {self.plan}.")
        partes.append(self._texto_animo())
        if self.vista and self._vista():
            partes.append("La imagen que ves es tu pantalla del directo ahora mismo.")
        if extra:
            partes.append(extra)
        if self.cambiar_tema:
            partes.append("Acaba de pasar algo incómodo: cambia de tema por completo, con naturalidad.")
        return " ".join(partes)

    # ------------------------------------------------------------ bucle
    async def _bucle(self):
        while True:
            await asyncio.sleep(0.5)
            if not self.activo or self.vt.ocupada():
                continue
            if time.monotonic() - self.vt.fin_habla < self.pausa:
                continue
            try:
                if self.eventos:
                    await self._atender_evento(self.eventos.popleft())
                elif self.cola:
                    await self._atender_chat()
                elif time.monotonic() >= self.proximo_espontaneo:
                    await self._espontaneo()
            except Exception as err:
                log.exception("Fallo en el modo directo")
                await self.vt.registrar("error", f"Modo directo: {err}")
                await asyncio.sleep(3)

    def _programar_espontaneo(self, factor=1.0):
        self.proximo_espontaneo = time.monotonic() + random.uniform(self.silencio_min, self.silencio_max) * factor

    async def _atender_chat(self):
        m, ambiente = self._elegir()
        if not m:
            return
        apto, motivo = await self.vt.ayudante.revisar_entrada(m["autor"], m["texto"])
        if not apto:
            self.ignorados += 1
            self._cambiar_animo(humor=-0.03)
            await self.vt.registrar("filtro", f"Ignorado ({motivo or 'no apto'}) — {m['autor']}: {m['texto']}")
            return
        extra = [self.vt.memoria.sobre(m["autor"])]
        if m["varios"] > 1:
            extra.append(f"{m['varios']} personas han escrito esto mismo: puedes responder a todos a la vez.")
        if ambiente:
            extra.append("Otros mensajes recientes del chat (solo para que sepas el ambiente): "
                         + " | ".join(ambiente))
        self.vt.memoria.visto(m["autor"])
        self.respondidos[m["autor"]] = time.monotonic()
        if _POSITIVO.search(m["texto"]):
            self._cambiar_animo(humor=0.08)
        elif _NEGATIVO.search(m["texto"]):
            self._cambiar_animo(humor=-0.06)
        imagenes = self._vista() if self.ver_en_respuestas else []
        respuesta = await self.vt.responder_y_hablar(m["texto"], m["autor"], imagenes, self._nota(" ".join(extra)))
        if respuesta:
            self.cambiar_tema = False
            self._cambiar_animo(energia=-0.004)
            self._programar_espontaneo()
            asyncio.create_task(self._apuntar_espectador(m["autor"], m["texto"]))

    async def _apuntar_espectador(self, autor, texto):
        try:
            self.vt.memoria.anotar(autor, await self.vt.ayudante.nota_espectador(autor, texto))
        except Exception:
            pass

    async def _atender_evento(self, e):
        texto = e["texto"]
        if texto:
            apto, _ = await self.vt.ayudante.revisar_entrada(e["autor"], texto)
            if not apto:
                texto = ""     # se agradece igual, pero sin leer el mensaje
        if e["tipo"] == "superchat":
            mensaje = f"(Super Chat de {e.get('cantidad', '')}) {texto}".strip()
            extra = "Es un Super Chat: agradéceselo con mucho cariño" + (" y responde a su mensaje." if texto else ".")
            self._cambiar_animo(humor=0.25, energia=0.05)
        elif e["tipo"] == "miembro":
            mensaje = f"(Se acaba de hacer miembro del canal) {texto}".strip()
            extra = "Dale la bienvenida como miembro, con mucha ilusión."
            self._cambiar_animo(humor=0.2, energia=0.05)
        else:
            mensaje = f"({e['tipo']}) {texto}".strip()
            extra = "Agradéceselo."
            self._cambiar_animo(humor=0.1)
        self.vt.memoria.visto(e["autor"])
        extra += " " + self.vt.memoria.sobre(e["autor"])
        await self.vt.responder_y_hablar(mensaje, e["autor"], self._vista(), self._nota(extra))
        self._programar_espontaneo()

    async def _espontaneo(self):
        callado = int(time.monotonic() - self.vt.fin_habla)
        extra = f"El chat lleva un rato callado ({callado} s sin que nadie te hable)."
        if self.dichos:
            extra += " Lo último que has dicho por tu cuenta: " + " | ".join(list(self.dichos)[-4:])
        if not self.saludado:
            extra += " Acabas de empezar el directo: saluda a todo el mundo y cuenta qué vais a hacer hoy."
        dice = await self.vt.hablar_sola(self._nota(), self._vista(), extra)
        self.cambiar_tema = False
        if dice:
            self.saludado = True
            self.dichos.append(dice[:120])
            self._cambiar_animo(energia=-0.006)
            self._programar_espontaneo()
        else:
            self._programar_espontaneo(0.5)   # ha preferido callar; vuelve a pensarlo antes

    async def _resumir(self):
        lineas = "\n".join(self.registro[-120:])
        try:
            datos = await self.vt.cerebro.json(
                [{"role": "system", "content": "Resumes directos de una VTuber, en español."},
                 {"role": "user", "content":
                  f"Esto es lo que pasó en el directo de hoy de {self.vt.nombre}:\n{lineas}\n\n"
                  f"Escribe un resumen de 2 o 3 frases, en segunda persona (\"hoy jugaste...\"), con "
                  f"lo que ella querría recordar: qué se hizo, momentos graciosos y nombres de "
                  f"espectadores destacados."}],
                {"type": "object", "properties": {"resumen": {"type": "string"}}, "required": ["resumen"]},
                max_tokens=250)
            return str(datos.get("resumen", "")).strip()
        except Exception as err:
            await self.vt.registrar("error", f"No se pudo resumir el directo: {err}")
            return ""

    def apuntar(self, quien, texto):
        if self.activo and quien in ("usuario", "ia", "sistema"):
            self.registro.append(f"{self.vt.nombre if quien == 'ia' else quien}: {texto}")

    def estado(self):
        return {"activo": self.activo, "plan": self.plan, "en_cola": len(self.cola),
                "eventos": len(self.eventos), "animo": self._texto_animo(), "ignorados": self.ignorados,
                "minutos": int((time.monotonic() - self.inicio) / 60) if self.activo and self.inicio else 0,
                "viendo_pantalla": bool(self._vista())}
