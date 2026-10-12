"""Tres en raya: Lara contra ti (desde el panel) o contra el chat (votando del 1 al 9).

Es el primer juego y la plantilla de los siguientes: el juego lleva el tablero y las reglas,
y Lara solo recibe el estado en texto y elige entre las jugadas permitidas. Si elige mal
(una casilla ocupada o nada), el juego juega por ella una casilla libre. Las «pistas» son
lo que un buen adaptador le da a la IA: qué casillas ganan ya y cuáles bloquean al rival.

Casillas:   1 | 2 | 3
            4 | 5 | 6
            7 | 8 | 9
"""

import asyncio
import random
import re
import time

LINEAS = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]
LARA, RIVAL = "O", "X"
_VOTO = re.compile(r"^\s*!?\s*([1-9])\s*!?\s*$")

ESQUEMA = {"type": "object", "properties": {
    "pensamiento": {"type": "string"}, "casilla": {"type": "integer"}, "dice": {"type": "string"}},
    "required": ["pensamiento", "casilla", "dice"]}
ESQUEMA_DECIR = {"type": "object", "properties": {"dice": {"type": "string"}}, "required": ["dice"]}


def ganador(tablero):
    for a, b, c in LINEAS:
        if tablero[a] and tablero[a] == tablero[b] == tablero[c]:
            return tablero[a]
    return "empate" if all(tablero) else ""


def jugadas_que_ganan(tablero, ficha):
    """Casillas (1-9) con las que `ficha` haría tres en raya ahora mismo."""
    return [i + 1 for i in range(9) if not tablero[i] and ganador(tablero[:i] + [ficha] + tablero[i + 1:]) == ficha]


def dibujar(tablero):
    filas = []
    for f in range(3):
        filas.append(" | ".join(tablero[f * 3 + c] or str(f * 3 + c + 1) for c in range(3)))
    return "\n".join(filas)


class TresEnRaya:
    def __init__(self, vt, cfg):
        self.vt = vt
        self.pistas = cfg.get("pistas", True)           # decirle qué casillas ganan o bloquean
        self.tiempo_votos = cfg.get("tiempo_votos", 15)  # segundos de votación del chat
        # "cada_mensaje": cada «2» que se escribe es un voto (anima a escribir), con un tope por
        # persona y votación (0 = sin límite) · "por_persona": un voto por persona, vale el último
        self.modo_votos = cfg.get("modo_votos", "cada_mensaje")
        self.tope_votos = cfg.get("tope_votos", 5)
        self.tablero = [""] * 9
        self.activo = False
        self.rival = "panel"      # "panel" (tú) o "chat"
        self.turno = ""           # LARA, RIVAL o "" si ha terminado
        self.resultado = ""       # "", LARA, RIVAL o "empate"
        # solo en memoria y solo la votación en curso: al cerrarse se borra (no se guarda nada)
        self.votos = {}           # voto -> casilla
        self.por_autor = {}       # autor -> votos que lleva en esta votación
        self.cierre_votos = 0.0   # cuándo se cierra la votación (0 = no ha empezado)
        self.marcador = {"lara": 0, "rival": 0, "empates": 0}
        self.ultima_votacion = None   # {"casilla", "votos": {casilla: n}, "personas"}: se ve hasta la siguiente
        self._amenazas_lara = []      # casillas con las que Lara ganaba tras su última jugada
        self._tarea = None

    # ------------------------------------------------------------ estado
    def estado(self):
        cuenta = {}
        for c in self.votos.values():
            cuenta[c] = cuenta.get(c, 0) + 1
        quedan = max(0, round(self.cierre_votos - time.monotonic())) if self.cierre_votos else None
        return {"tipo": "juego", "activo": self.activo, "tablero": self.tablero, "rival": self.rival,
                "turno": self.turno, "resultado": self.resultado, "votos": cuenta,
                "quedan": quedan, "marcador": self.marcador, "ultima_votacion": self.ultima_votacion}

    async def _avisar(self):
        await self.vt._enviar(self.vt.paneles | self.vt.pantallas_juego, self.estado())

    def nota(self):
        """Contexto para el resto de respuestas mientras hay partida (lo usa el modo directo)."""
        if not self.activo:
            return ""
        return (f"Ahora mismo SÍ estás jugando una partida de tres en raya contra {self._contra()}; "
                f"tú eres la O. Tablero:\n{dibujar(self.tablero)}")

    def _contra(self):
        # Lara NO sabe quién juega desde el panel: es «tu rival», sin nombre
        return "el chat (eligen las X votando con números del 1 al 9)" if self.rival == "chat" else "tu rival"

    # ------------------------------------------------------------ partida
    async def nueva(self, rival="panel", empieza="rival"):
        self.tablero = [""] * 9
        self.rival = "chat" if rival == "chat" else "panel"
        self.activo, self.resultado, self.votos, self.por_autor, self.cierre_votos = True, "", {}, {}, 0.0
        self.ultima_votacion, self._amenazas_lara = None, []
        self.turno = LARA if empieza == "lara" else RIVAL
        await self._avisar()
        quien = "el chat" if self.rival == "chat" else "ti (panel)"
        await self.vt.registrar("sistema", f"Tres en raya contra {quien}. Empieza {'Lara' if self.turno == LARA else 'el rival'}.")
        if self.turno == LARA:
            self._lanzar(self._mueve_lara(inicio=True))
        else:
            self._lanzar(self._anunciar_inicio())

    async def terminar(self):
        self.activo, self.turno, self.cierre_votos = False, "", 0.0
        if self._tarea and not self._tarea.done():
            self._tarea.cancel()
        await self._avisar()

    def _lanzar(self, corrutina):
        self._tarea = asyncio.create_task(self._con_errores(corrutina))

    async def _con_errores(self, corrutina):
        try:
            await corrutina
        except asyncio.CancelledError:
            raise
        except Exception as err:
            await self.vt.registrar("error", f"Tres en raya: {err}")

    async def jugar_rival(self, casilla):
        """Jugada del rival (del panel o la ganadora de la votación). Devuelve un error o ""."""
        if not self.activo or self.turno != RIVAL:
            return "No es el turno del rival."
        if not 1 <= casilla <= 9 or self.tablero[casilla - 1]:
            return "Esa casilla no está libre."
        self.tablero[casilla - 1] = RIVAL
        self.votos, self.por_autor, self.cierre_votos = {}, {}, 0.0   # la votación se borra
        self.turno = LARA if not ganador(self.tablero) else ""
        await self._avisar()
        self._lanzar(self._tras_jugada_rival(casilla))   # sin esperar: el panel no se queda colgado
        return ""

    async def _tras_jugada_rival(self, casilla):
        if not await self._comprobar_final():
            await self._mueve_lara(ultima=casilla)

    async def _comprobar_final(self):
        r = ganador(self.tablero)
        if not r:
            return False
        self.resultado, self.turno, self.activo = r, "", False
        self.marcador["lara" if r == LARA else "rival" if r == RIVAL else "empates"] += 1
        await self._avisar()
        quien = "el chat" if self.rival == "chat" else "tu rival"
        texto = {LARA: "Has GANADO tú la partida.", RIVAL: f"Ha ganado {quien}: has perdido la partida.",
                 "empate": "La partida ha acabado en empate."}[r]
        siente = {LARA: "Te hace ilusión: feliz o un pelín presumida, sin burlarte de nadie.",
                  RIVAL: ("Te fastidia perder: un momento de enojada o triste (sin dramatizar) y luego "
                          "deportiva, con ganas de revancha."),
                  "empate": "Según cómo haya ido: alivio, o pique por no haber ganado."}[r]
        await self.vt.registrar("sistema", f"Tres en raya: {texto}")
        await self._hablar(f"(Nota para ti: {texto} {siente} Reacciónalo en 1 o 2 frases, como lo "
                           f"harías tú, con la cara que toque.)")
        return True

    async def _anunciar_inicio(self):
        if self.rival == "chat":
            await self._hablar("(Nota para ti: empieza una partida de tres en raya contra el chat; "
                               "empiezan ellos. Explica en una frase que voten escribiendo un número del 1 "
                               "al 9, como las teclas de un teléfono: 1 arriba a la izquierda, 9 abajo a la "
                               "derecha. Gana la casilla más votada.)")
        else:
            await self._hablar("(Nota para ti: empieza una partida de tres en raya contra tu rival, que "
                               "juega desde el panel, y empieza tu rival. No sabes cómo se llama: no le "
                               "pongas nombre. Dilo en una frase, con ganas.)")

    async def _hablar(self, nota):
        """Lara dice algo sobre la partida (sin que salga en el registro como mensaje del chat)."""
        async with self.vt.turno:
            generacion = self.vt.generacion
            c = self.vt.cerebro
            mensajes = c._mensajes(nota, [], "")
            datos = await c.json(mensajes, ESQUEMA_DECIR, max_tokens=c.max_tokens)
            dice = str(datos.get("dice", "")).strip()
            if dice:
                c._apuntar_turno(mensajes, dice)
                c._recordar(nota, dice)
                await self.vt._revisar_y_decir(dice, generacion, "juego")

    # ------------------------------------------------------------ Lara juega
    async def _mueve_lara(self, ultima=None, inicio=False):
        libres = [i + 1 for i in range(9) if not self.tablero[i]]
        partes = [f"(Nota para ti: estás jugando al tres en raya contra {self._contra()}; tú eres la O "
                  f"y tu rival la X. No sabes cómo se llama tu rival: no le pongas nombre.",
                  f"Tablero (los números son casillas libres):\n{dibujar(self.tablero)}",
                  f"Casillas libres: {', '.join(map(str, libres))}."]
        if ultima:
            quien = "El chat ha votado y ha puesto" if self.rival == "chat" else "Tu rival acaba de poner"
            partes.append(f"{quien} su X en la casilla {ultima}.")
        if inicio:
            partes.append("Empiezas tú: es la primera jugada.")
        ganan, bloquean = jugadas_que_ganan(self.tablero, LARA), jugadas_que_ganan(self.tablero, RIVAL)
        if self.pistas:
            if ganan:
                partes.append(f"Si pones en {' o '.join(map(str, ganan))}, GANAS ya.")
            if bloquean:
                partes.append(f"Ojo: tu rival gana si pone en {' o '.join(map(str, bloquean))}; bloquéalo.")
        partes.append("Cómo te sientes ahora (que se note en la cara y en el tono, sin exagerar): "
                      + self._sentimiento(ultima, ganan, bloquean))
        partes.append('Elige UNA casilla libre ("casilla", un número) y di en voz alta 1 o 2 frases '
                      'cortas con tu jugada ("dice", empezando con la etiqueta de la emoción que toque; '
                      'no siempre pensativa). "pensamiento" es lo que piensas en silencio.)')
        nota = "\n".join(partes)
        async with self.vt.turno:
            generacion = self.vt.generacion
            await self.vt.al_avatar({"tipo": "emocion", "nombre": "pensativa", "duracion": 30})
            c = self.vt.cerebro
            try:
                datos = await c.json(c._mensajes(nota, [], ""), ESQUEMA, max_tokens=c.max_tokens + 100)
            except Exception as err:
                datos = {}
                await self.vt.registrar("error", f"Tres en raya: el cerebro no respondió ({err})")
            if not self.activo:
                return
            mensajes = c._mensajes(nota, [], "")
            casilla = datos.get("casilla")
            if casilla not in libres:
                await self.vt.registrar("sistema", f"Lara eligió una casilla no válida ({casilla}); juega una libre al azar")
                casilla = random.choice(libres)
                datos["dice"] = ""
            if datos.get("pensamiento"):
                await self.vt.registrar("pensamiento", str(datos["pensamiento"]))
            self.tablero[casilla - 1] = LARA
            self._amenazas_lara = jugadas_que_ganan(self.tablero, LARA)
            dice = str(datos.get("dice", "")).strip() or f"[pensativa] Pongo en la {casilla}."
            c._apuntar_turno(mensajes, dice)   # para que la jugada también se pueda valorar 👍/👎
            c._recordar(f"(Tres en raya: te tocaba mover.)", dice)
            await self.vt._revisar_y_decir(dice, generacion, "juego")
        if await self._comprobar_final():
            return
        self.turno = RIVAL
        await self._avisar()

    def _sentimiento(self, ultima, ganan, bloquean):
        """Qué le pasa por dentro según la partida, para que no ponga siempre la misma cara."""
        if ultima and ultima in self._amenazas_lara:
            if ganan:
                return ("te han tapado una jugada, pero aún te queda otra para ganar: un poco "
                        "presumida o feliz.")
            return ("te acaban de tapar la jugada con la que ibas a ganar y te fastidia: un «jo» "
                    "de enojada suave, o avergonzada por haberlo dejado tan claro.")
        if ganan:
            return "puedes ganar ya y lo sabes: un pelín presumida o feliz, sin burlarte."
        if len(bloquean) >= 2:
            return ("tu rival tiene dos formas de ganar y no puedes tapar las dos: agobiada, "
                    "sorprendida o triste; se te escapa la partida.")
        if bloquean:
            return "tu rival te amenaza: algo de tensión (sorprendida), y alivio si lo tapas."
        if sum(1 for c in self.tablero if c) <= 1:
            return "la partida acaba de empezar: con ganas, feliz o curiosa."
        return "partida tranquila e igualada: concentrada o divertida, como te salga."

    # ------------------------------------------------------------ votos del chat
    def votar(self, autor, texto):
        """Lo llama el modo directo con cada mensaje. True si era un voto (y no va a la cola)."""
        m = _VOTO.match(texto or "")
        if not m or not self.activo or self.rival != "chat":
            return False
        if self.turno != RIVAL:
            return True                       # mientras mueve Lara no se vota (el tablero va a cambiar)
        casilla = int(m.group(1))
        if self.tablero[casilla - 1]:
            return True
        # los que llegan sin nombre (la simulación del panel sin rellenar «Nombre») son cada uno
        # una persona distinta
        if not autor or autor == "Alguien":
            autor = f"(sin nombre {len(self.votos) + 1})"
        if self.modo_votos == "por_persona":
            self.votos[autor] = casilla                    # vale el último que escribe
        else:
            llevados = self.por_autor.get(autor, 0)
            if self.tope_votos and llevados >= self.tope_votos:
                return True                                # ya ha gastado sus votos de esta ronda
            self.votos[f"{autor}#{llevados}"] = casilla
        self.por_autor[autor] = self.por_autor.get(autor, 0) + 1
        if not self.cierre_votos:
            self.cierre_votos = time.monotonic() + self.tiempo_votos
            self._lanzar(self._cerrar_votacion())
        else:
            asyncio.create_task(self._avisar())
        return True

    async def _cerrar_votacion(self):
        await self._avisar()
        while time.monotonic() < self.cierre_votos:
            await asyncio.sleep(1)
            await self._avisar()
        cuenta = {}
        for c in self.votos.values():
            cuenta[c] = cuenta.get(c, 0) + 1
        if not cuenta:
            self.cierre_votos = 0.0
            return
        maximo = max(cuenta.values())
        elegida = random.choice([c for c, n in cuenta.items() if n == maximo])   # empate: al azar
        # el recuento se queda a la vista (en el tablero y en OBS) hasta la siguiente votación
        total, personas = len(self.votos), len(self.por_autor)
        self.ultima_votacion = {"casilla": elegida, "votos": cuenta, "personas": personas}
        await self.vt.registrar("sistema", f"Votación del chat: gana la casilla {elegida} ({maximo} de "
                                           f"{total} voto{'s' if total > 1 else ''}, "
                                           f"{personas} persona{'s' if personas > 1 else ''})")
        await self.jugar_rival(elegida)
