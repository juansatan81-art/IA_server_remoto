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
_DESPEDIDA = re.compile(r"\b(me voy|me tengo que ir|me despido|adi[oó]s|chao|chau|bye|hasta (luego|ma[nñ]ana|la pr[oó]xima)|"
                        r"nos vemos|buenas noches|a dormir|me desconecto)\b", re.I)
_RELLENO = {"que", "del", "las", "los", "una", "uno", "por", "para", "con"}


_ADORNO = re.compile(r"^(?:[xX]+[xX_.\-]*)(?=[A-Z0-9])|(?<=[a-z0-9])(?:[_.\-]*[xX]+)$")
_SUFIJO = re.compile(r"\.(?:art|exe|tv|yt|vt|png|jpg|gg)$", re.I)
_SOBRAN = {"mx", "ar", "es", "cl", "co", "pe", "ve", "us", "uy", "ec", "yt", "tv", "vt", "ttv", "oficial",
           "official", "yt", "live", "gaming", "games", "uwu", "owo", "xd", "gamer", "player",
           "user", "usuario"}


def nombre_hablado(autor):
    """El apodo como se puede decir en voz alta: «xXDarkXx» -> «Dark», «Dani_MX» -> «Dani»,
    «Valeria.art» -> «Valeria», «Kevin2009» -> «Kevin», «VenezolanoRandom7» -> «Venezolano Random».
    La memoria sigue usando el apodo real; esto es solo lo que ve (y dice) Lara."""
    n = (autor or "").strip().lstrip("@")
    n = _SUFIJO.sub("", n)
    if re.match(r"^[xX]{1,2}[A-Z]", n) and re.search(r"[a-z][xX]{1,2}$", n):
        n = _ADORNO.sub("", n)                                     # «xXDarkXx» -> «Dark»
    n = re.sub(r"(?<=[a-záéíóúñ])(?=[A-ZÁÉÍÓÚÑ])", " ", n)        # «NoSoyUnBot» -> «No Soy Un Bot»
    n = re.sub(r"[\d_.\-|~*#]+", " ", n)
    # fuera las «x» de adorno sueltas («XX Juan XX», «xX_Sombra_Xx») y las coletillas
    palabras = [p for p in n.split() if p.lower() not in _SOBRAN and not re.fullmatch(r"[xX]+", p)]
    palabras = [p.capitalize() if p.isupper() and len(p) > 3 else p for p in palabras]
    if len(palabras) > 4:
        palabras = palabras[:2]
    hablado = " ".join(palabras).strip()
    return hablado if len(re.sub(r"[^a-zA-ZáéíóúñÁÉÍÓÚÑ]", "", hablado)) >= 2 else "alguien del chat"


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
        self.negativos = {}           # autor -> mensajes negativos (los trolls bajan en la cola)
        self.seguidas_sola = 0        # veces seguidas que ha hablado sola sin que nadie escriba
        self.dichos = deque(maxlen=12)  # temas recientes de lo que ha dicho ella sola
        self.registro = []            # lo que pasa en el directo, para el resumen final
        self.animo = {"humor": 0.3, "energia": 0.8}
        self.cambiar_tema = False
        self.proximo_espontaneo = 0
        self.vista = None             # (momento, imagen) última captura de pantalla
        self.ignorados = 0
        self.saludado = False
        self._tarea = None
        # memoria del directo entero: un resumen que se reescribe cada ~15 min (el historial
        # literal solo guarda los últimos mensajes)
        self.cada_resumen = cfg.get("resumen_cada", 900)
        self.resumen_vivo = ""
        self.ultimo_resumen = 0.0
        self.ultimo_recordatorio = 0.0
        self.sin_respuesta = {}       # autor -> mensajes suyos seguidos sin respuesta
        # algo que Lara dijo no conocer: si en ese tiempo nadie lo explica, lo busca ella
        self.espera_explicacion = cfg.get("espera_explicacion", 50)
        self.por_explicar = None      # {"tema", "t"}
        self.explicados = set()       # palabras de lo que el chat ya le explicó en este directo

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
        self.resumen_vivo, self.sin_respuesta, self.por_explicar, self.explicados = "", {}, None, set()
        self.ultimo_resumen = self.ultimo_recordatorio = time.monotonic()
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
        if self.vt.juego.votar(autor, texto):   # «5» durante una partida es un voto, no charla
            return True
        if not texto or filtros.es_spam(texto):
            return False
        self.cola.append({"autor": autor, "texto": texto, "t": time.monotonic(),
                          "clave": _normalizar(texto), **extra})
        self.sin_respuesta[autor] = self.sin_respuesta.get(autor, 0) + 1
        return True

    def _palabras_tema(self):
        if not self.por_explicar:
            return set()
        return {w for w in _normalizar(self.por_explicar["tema"]).split() if len(w) >= 3 and w not in _RELLENO}

    def _explica(self, m):
        """¿Este mensaje habla de lo que Lara dijo no conocer?"""
        palabras = self._palabras_tema()
        return bool(palabras) and bool(palabras & set(m["clave"].split()))

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
            p -= 2.5 * self.negativos.get(m["autor"], 0)  # el que solo viene a molestar, al final
            if self.sin_respuesta.get(m["autor"], 0) >= 2:
                p += 3                                    # lleva varios mensajes sin respuesta
            if self._explica(m):
                p += 4                                    # le están explicando lo que no conocía
            if _DESPEDIDA.search(m["texto"]):
                p += 2                                    # que nadie se vaya sin despedida
            hace = ahora - self.respondidos.get(m["autor"], -1e9)
            if hace < 300:
                p -= 4 * (1 - hace / 300)                 # ya le respondió hace poco
            largo = len(m["texto"])
            p += 1 if 12 <= largo <= 160 else -1
            p += min(repeticiones[m["clave"]] - 1, 3)     # muchos dicen lo mismo
            p -= (ahora - m["t"]) / self.caducidad * 2    # los recientes, antes
            return p + random.random() * 0.5              # un poco de azar, como una persona

        elegido = dict(max(self.cola, key=puntos))
        # se quitan el elegido y los que dicen lo mismo
        iguales = [m for m in self.cola if m["clave"] == elegido["clave"]]
        for m in iguales:
            self.cola.remove(m)
        elegido["varios"] = len(iguales)
        # si esa persona ha escrito varias cosas SEGUIDAS (menos de 20 s entre una y otra,
        # como quien parte una frase en varios mensajes), se responden juntas; como mucho 3.
        # Lo que escribió en otro momento se queda en la cola como otro mensaje.
        # Van en líneas separadas, sin barras (antes se juntaba todo con " / ", y con los
        # bots salían frases sueltas sin relación pegadas en un solo mensaje).
        suyos = sorted((m for m in self.cola if m["autor"] == elegido["autor"]), key=lambda m: m["t"])
        juntos = [(elegido["t"], elegido["texto"])]
        for m in suyos:
            if len(juntos) >= 3:
                break
            if min(abs(m["t"] - t) for t, _ in juntos) <= 20:
                juntos.append((m["t"], m["texto"]))
                self.cola.remove(m)
        juntos.sort()
        elegido["seguidos"] = len(juntos)
        elegido["texto"] = "\n".join(t for _, t in juntos)
        ambiente = [f"{nombre_hablado(m['autor'])}: {m['texto']}" for m in list(self.cola)[-5:]]
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
        if self.resumen_vivo:
            partes.append(f"Lo que va de directo: {self.resumen_vivo}")
        partes.append(self._texto_animo())
        if self.activo:
            partes.append("Ya has saludado a todo el chat al empezar: NO vuelvas a decir «hola a todos»."
                          if self.saludado else
                          "Aún no has saludado al empezar el directo: saluda a todos una vez, brevemente.")
        if self.vt.juego.activo:
            partes.append(self.vt.juego.nota())
        if self._vista():
            partes.append("La imagen que ves es tu pantalla del directo ahora mismo.")
        else:
            partes.append("Ahora mismo NO ves la pantalla: no digas lo que hay en ella.")
        if extra:
            partes.append(extra)
        if self.cambiar_tema:
            partes.append("Acaba de pasar algo incómodo: cambia de tema por completo, con naturalidad.")
        return " ".join(partes)

    # ------------------------------------------------------------ bucle
    async def _bucle(self):
        while True:
            await asyncio.sleep(0.5)
            # sin avatar abierto (ni panel ni OBS) no hay por dónde hablar: se espera
            if not self.activo or self.vt.ocupada() or not self.vt.avatares:
                continue
            if time.monotonic() - self.vt.fin_habla < self.pausa:
                continue
            try:
                ahora = time.monotonic()
                if self.por_explicar and ahora - self.por_explicar["t"] > self.espera_explicacion:
                    await self._buscar_desconocido()
                elif ahora - self.ultimo_resumen > self.cada_resumen and len(self.registro) >= 6:
                    await self._actualizar_resumen()
                elif self.eventos:
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
        # cuanto más rato lleva hablando sola, más espacia las intervenciones (hasta x4)
        factor *= min(4.0, 1.35 ** self.seguidas_sola)
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
        nuevo_hoy = m["autor"] not in self.respondidos
        apodo = nombre_hablado(m["autor"])   # Lara ve (y dice) el nombre limpio; la memoria usa el real
        extra = [self.vt.memoria.sobre(m["autor"], apodo), self.vt.glosario.nota(m["texto"])]
        self.sin_respuesta.pop(m["autor"], None)
        if _DESPEDIDA.search(m["texto"]):
            extra.append(f"Parece que {apodo} se despide del directo: si de verdad se va, despídelo "
                         f"por su nombre con un deseo concreto según lo que haya contado.")
        if self._explica(m):
            tema = self.por_explicar["tema"]
            extra.append(f"{apodo} te está explicando qué es «{tema}», que antes no conocías: "
                         f"dale las gracias y repítelo con tus palabras («ah, o sea que…»).")
            self.vt._por_aprender.append((tema, f"Explicación de un espectador del chat: {m['texto']}"))
            self.explicados |= self._palabras_tema()
            self.por_explicar = None
        elif nuevo_hoy and self.inicio and time.monotonic() - self.inicio > 600 and (self.resumen_vivo or self.plan):
            extra.append(f"{apodo} acaba de llegar al directo: si viene a cuento, cuéntale en una "
                         f"frase de qué va.")
        if m["varios"] > 1:
            extra.append(f"{m['varios']} personas han escrito esto mismo: puedes responder a todos a la vez.")
        if m.get("seguidos", 1) > 1:
            extra.append(f"{apodo} ha escrito {m['seguidos']} mensajes seguidos: respóndele a todo junto, con naturalidad.")
        if ambiente:
            extra.append(f"Otros mensajes recientes del chat, solo para que sepas el ambiente: NO los "
                         f"leas, NO los nombres y NO les respondas ahora (ya les tocará); responde "
                         f"SOLO a {apodo}: " + " | ".join(ambiente))
        self.vt.memoria.visto(m["autor"])
        self.respondidos[m["autor"]] = time.monotonic()
        self.seguidas_sola = 0
        if _POSITIVO.search(m["texto"]):
            self._cambiar_animo(humor=0.08)
        elif _NEGATIVO.search(m["texto"]):
            self._cambiar_animo(humor=-0.06)
            self.negativos[m["autor"]] = self.negativos.get(m["autor"], 0) + 1
        imagenes = self._vista() if self.ver_en_respuestas else []
        respuesta = await self.vt.responder_y_hablar(m["texto"], apodo, imagenes,
                                                     self._nota(" ".join(e for e in extra if e)),
                                                     real=m["autor"])
        self._recoger_desconocido()
        if respuesta:
            self.saludado = True      # con el chat lleno desde el principio, saluda en su primera respuesta
            self.cambiar_tema = False
            self._cambiar_animo(energia=-0.004)
            self._programar_espontaneo()
            asyncio.create_task(self._apuntar_espectador(m["autor"], m["texto"], apodo))

    def _recoger_desconocido(self):
        """Si al responder dijo no conocer algo, queda a la espera de que el chat lo explique."""
        tema, self.vt.cerebro.no_lo_conozco = self.vt.cerebro.no_lo_conozco, ""
        # lo que el chat ya le explicó en este directo no vuelve a quedar pendiente (al responder
        # a la explicación, el modelo todavía lo marca como desconocido)
        if tema and self.activo and not ({w for w in _normalizar(tema).split() if len(w) >= 3} & self.explicados):
            self.por_explicar = {"tema": tema, "t": time.monotonic()}

    async def _buscar_desconocido(self):
        """Nadie le ha explicado lo que no conocía: lo busca ella (y el glosario lo aprende)."""
        tema, self.por_explicar = self.por_explicar["tema"], None
        await self.vt.responder_y_hablar(
            f"(Nota para ti: hace un rato dijiste que no conocías «{tema}» y nadie del chat te lo ha "
            f"explicado. Búscalo ahora en internet y cuéntalo en 1 o 2 frases, como «bueno, como "
            f"nadie me lo explica, lo he buscado…».)", None, self._vista(), self._nota(), quien="sistema")
        self._programar_espontaneo()

    async def _actualizar_resumen(self):
        """Cada ~15 min: resumen corto de lo que va de directo, que Lara tiene siempre delante."""
        self.ultimo_resumen = time.monotonic()
        lineas = "\n".join(self.registro[-80:])
        anterior = f"Resumen que ya tenías de antes:\n{self.resumen_vivo}\n\n" if self.resumen_vivo else ""
        try:
            async with self.vt.turno:
                datos = await self.vt.cerebro.json(
                    [{"role": "system", "content": "Resumes directos de una VTuber, en español."},
                     {"role": "user", "content":
                      f"{anterior}Lo último que ha pasado en el directo de {self.vt.nombre}:\n{lineas}\n\n"
                      f"Escribe el resumen de TODO lo que va de directo (lo de antes y lo nuevo) en 2 o 3 "
                      f"frases cortas, en segunda persona («has hablado de…»): temas, quién contó qué "
                      f"(con su nombre) y lo que quedó pendiente."}],
                    {"type": "object", "properties": {"resumen": {"type": "string"}}, "required": ["resumen"]},
                    max_tokens=220)
            resumen = str(datos.get("resumen", "")).strip()
        except Exception as err:
            await self.vt.registrar("error", f"No se pudo resumir lo que va de directo: {err}")
            return
        if resumen:
            self.resumen_vivo = resumen
            await self.vt.registrar("sistema", f"Lo que va de directo: {resumen}")

    async def _apuntar_espectador(self, autor, texto, apodo=None):
        try:   # la nota se escribe con el nombre limpio (es lo que luego lee Lara); se guarda con el real
            self.vt.memoria.anotar(autor, await self.vt.ayudante.nota_espectador(apodo or autor, texto))
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
        apodo = nombre_hablado(e["autor"])
        extra += " " + self.vt.memoria.sobre(e["autor"], apodo)
        if await self.vt.responder_y_hablar(mensaje, apodo, self._vista(), self._nota(extra), real=e["autor"]):
            self.saludado = True
        self._programar_espontaneo()

    async def _espontaneo(self):
        callado = int(time.monotonic() - self.vt.fin_habla)
        extra = f"El chat lleva un rato callado ({callado} s sin que nadie te hable)."
        if self.dichos:
            extra += (" Lo que ya has dicho por tu cuenta en este directo (NO lo repitas): "
                      + " | ".join(list(self.dichos)[-8:]))
        if random.random() < 0.25:   # de vez en cuando, alguna expresión de internet que conoce
            terminos = self.vt.glosario.al_azar(2)
            if terminos:
                extra += (" Si encaja de forma natural (sin forzarlo), puedes usar alguna expresión de "
                          "internet que conoces: " + "; ".join(f"{t['termino']} ({t['significado']})" for t in terminos))
        if not self.saludado:
            extra += " Acabas de empezar el directo: saluda a todo el mundo y cuenta qué vais a hacer hoy."
        elif time.monotonic() - self.ultimo_recordatorio > 18 * 60 and (self.resumen_vivo or self.plan):
            extra += (" Hace rato que no recuerdas de qué va el directo: si encaja, dilo en una frase "
                      "para quien acabe de llegar («para quien llega: hoy estamos…»).")
            self.ultimo_recordatorio = time.monotonic()
        dice = await self.vt.hablar_sola(self._nota(), self._vista(), extra)
        self.cambiar_tema = False
        if dice:
            self.saludado = True
            self.seguidas_sola += 1
            self.dichos.append(dice[:150])
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
