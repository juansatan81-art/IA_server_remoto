"""Lee el chat de un directo de YouTube con la API oficial (YouTube Data API v3).

Solo hace falta una clave de API (gratis, en Google Cloud) y el directo debe ser público
o no listado. La API tiene un límite diario (10.000 "unidades"; cada lectura del chat
gasta unas 5), así que se lee cada `intervalo` segundos: con 8 s llega para unas 4 horas
de directo al día.

Si no le das el vídeo, busca el directo que esté emitiendo tu canal (eso gasta 100 unidades).
"""
import asyncio
import logging
import re

import aiohttp

log = logging.getLogger("vtuber")
API = "https://www.googleapis.com/youtube/v3"


def id_de_video(texto):
    """Acepta el id o un enlace (youtube.com/watch?v=..., youtu.be/..., /live/...)."""
    texto = (texto or "").strip()
    m = re.search(r"(?:v=|youtu\.be/|/live/|/shorts/)([\w-]{11})", texto)
    return m.group(1) if m else texto


class YouTube:
    def __init__(self, cfg, recibir, registrar):
        self.clave = cfg.get("api_key", "").strip()
        self.canal = cfg.get("canal_id", "").strip()
        self.intervalo = max(3, float(cfg.get("intervalo", 8)))
        self.api = cfg.get("api_base", API).rstrip("/")
        self.recibir = recibir         # función(autor, texto, tipo, **extra) del modo directo
        self.registrar = registrar
        self.video = ""
        self.estado = "desconectado"
        self.mensajes = 0
        self._tarea = None

    @property
    def configurado(self):
        return bool(self.clave)

    async def conectar(self, video=""):
        await self.desconectar()
        self.video = id_de_video(video)
        self._tarea = asyncio.create_task(self._leer())

    async def desconectar(self):
        if self._tarea:
            self._tarea.cancel()
            try:
                await self._tarea
            except (asyncio.CancelledError, Exception):
                pass
        self._tarea = None
        self.estado = "desconectado"

    async def _get(self, s, ruta, **params):
        async with s.get(f"{self.api}/{ruta}", params={**params, "key": self.clave}) as r:
            datos = await r.json(content_type=None)
            if r.status != 200:
                error = datos.get("error", {}) if isinstance(datos, dict) else {}
                motivo = (error.get("errors") or [{}])[0].get("reason", "")
                raise RuntimeError(f"YouTube respondió {r.status}: {error.get('message', '')} {motivo}".strip())
            return datos

    async def _buscar_chat(self, s):
        if not self.video:
            if not self.canal:
                raise RuntimeError("Pon el enlace del directo o el canal_id en config.json")
            datos = await self._get(s, "search", part="id", channelId=self.canal, eventType="live", type="video")
            if not datos.get("items"):
                raise RuntimeError("Tu canal no está emitiendo ahora mismo")
            self.video = datos["items"][0]["id"]["videoId"]
        datos = await self._get(s, "videos", part="liveStreamingDetails,snippet", id=self.video)
        if not datos.get("items"):
            raise RuntimeError(f"No encuentro el vídeo {self.video}")
        detalles = datos["items"][0].get("liveStreamingDetails", {})
        chat = detalles.get("activeLiveChatId")
        if not chat:
            raise RuntimeError("Ese vídeo no tiene un chat en directo activo (¿ha empezado el directo?)")
        return chat, datos["items"][0]["snippet"].get("title", "")

    async def _leer(self):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
                self.estado = "buscando el directo…"
                chat, titulo = await self._buscar_chat(s)
                self.estado = f"conectado: {titulo}"
                await self.registrar("sistema", f"Leyendo el chat de YouTube: {titulo}")
                pagina, primera = None, True
                while True:
                    params = {"liveChatId": chat, "part": "snippet,authorDetails", "maxResults": 200}
                    if pagina:
                        params["pageToken"] = pagina
                    try:
                        datos = await self._get(s, "liveChat/messages", **params)
                    except RuntimeError as err:
                        if "liveChatEnded" in str(err) or "liveChatNotFound" in str(err):
                            await self.registrar("sistema", "El chat de YouTube se ha cerrado (fin del directo)")
                            break
                        raise
                    pagina = datos.get("nextPageToken")
                    # lo que ya estaba escrito al conectarse no se responde
                    if not primera:
                        for item in datos.get("items", []):
                            self._entrar(item)
                    primera = False
                    espera = datos.get("pollingIntervalMillis", 5000) / 1000
                    await asyncio.sleep(max(espera, self.intervalo))
        except asyncio.CancelledError:
            raise
        except Exception as err:
            self.estado = f"error: {err}"
            await self.registrar("error", f"YouTube: {err}")
            return
        self.estado = "desconectado"

    def _entrar(self, item):
        sn, autor = item.get("snippet", {}), item.get("authorDetails", {})
        nombre = autor.get("displayName", "Alguien").lstrip("@")
        extra = {"miembro": autor.get("isChatSponsor", False),
                 "moderador": autor.get("isChatModerator", False),
                 "dueño": autor.get("isChatOwner", False)}
        tipo = sn.get("type")
        self.mensajes += 1
        if tipo == "textMessageEvent":
            self.recibir(nombre, sn.get("textMessageDetails", {}).get("messageText", ""), "mensaje", **extra)
        elif tipo == "superChatEvent":
            d = sn.get("superChatDetails", {})
            self.recibir(nombre, d.get("userComment", ""), "superchat", cantidad=d.get("amountDisplayString", ""))
        elif tipo == "superStickerEvent":
            d = sn.get("superStickerDetails", {})
            self.recibir(nombre, "", "superchat", cantidad=d.get("amountDisplayString", ""))
        elif tipo in ("newSponsorEvent", "memberMilestoneChatEvent"):
            texto = sn.get("memberMilestoneChatDetails", {}).get("userComment", "")
            self.recibir(nombre, texto, "miembro")
        elif tipo == "membershipGiftingEvent":
            self.recibir(nombre, "", "regalo de suscripciones")
