"""Texto a voz: Fish Audio (la voz de Lara del canal) y, de respaldo, edge-tts.

Con "motor": "fish" se pide primero a Fish; si falla, devuelve un audio vacío o tarda
más de "espera_max" segundos, esa frase sale con la voz de edge-tts (Ximena). Así Lara
nunca se queda muda. La clave de Fish va en config.local.json, que git no sube.
"""
import asyncio
import logging
import uuid
from pathlib import Path

import aiohttp
import edge_tts
import edge_tts.communicate as _edge_com
from edge_tts.constants import TRUSTED_CLIENT_TOKEN

# Octubre de 2026: Microsoft está pasando Read Aloud a una dirección nueva y la antigua
# devuelve 403 a todo en Europa (edge-tts issue #490). Se prueba primero la nueva, con
# el mismo token y versión de siempre, y si falla, la antigua. Va aquí y no en la
# librería porque iniciar.bat actualiza edge-tts en cada arranque.
SERVIDORES = [
    f"wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1?Ocp-Apim-Subscription-Key={TRUSTED_CLIENT_TOKEN}",
    _edge_com.WSS_URL,
]


log = logging.getLogger("vtuber")
FISH_URL = "https://api.fish.audio/v1/tts"


class Voz:
    def __init__(self, cfg, carpeta: Path, max_archivos=60):
        self.voz = cfg.get("voz", "es-ES-ElviraNeural")
        fish = cfg.get("fish", {})
        self.fish_clave = fish.get("api_key", "")
        self.fish_modelo = fish.get("modelo", "s2.1-pro-free")
        self.fish_voz = fish.get("voz_id", "")
        self.fish_espera = fish.get("espera_max", 8)
        self.usar_fish = cfg.get("motor") == "fish" and bool(self.fish_clave and self.fish_voz)
        self.descripcion = (f"Fish {self.fish_modelo} (respaldo: {self.voz})" if self.usar_fish
                            else self.voz)
        self.ultimo = ""      # qué voz salió en la última frase: fish, respaldo, edge o error
        self.velocidad = cfg.get("velocidad", "+0%")
        self.tono = cfg.get("tono", "+0Hz")
        self.carpeta = carpeta
        self.max_archivos = max_archivos
        carpeta.mkdir(parents=True, exist_ok=True)
        for viejo in carpeta.glob("*.mp3"):
            viejo.unlink()

    async def sintetizar(self, texto, intentos=2):
        """Genera un mp3 y devuelve su nombre de archivo: Fish primero, edge-tts si falla."""
        if self.usar_fish:
            try:
                nombre = await self._fish(texto)
                self.ultimo = "fish"
                return nombre
            except Exception as err:  # caída, límite, clave mala o lentitud: frase con Ximena
                log.warning("Fish no respondió (%s); esta frase va con %s", err, self.voz)
        try:
            nombre = await self._edge(texto, intentos)
        except Exception:
            self.ultimo = "error"
            raise
        self.ultimo = "respaldo" if self.usar_fish else "edge"
        return nombre

    async def _fish(self, texto):
        nombre = f"{uuid.uuid4().hex}.mp3"
        cuerpo = {"text": texto, "reference_id": self.fish_voz, "format": "mp3",
                  "latency": "balanced", "normalize": True}
        cabeceras = {"Authorization": f"Bearer {self.fish_clave}", "model": self.fish_modelo}
        tiempo = aiohttp.ClientTimeout(total=self.fish_espera)
        async with aiohttp.ClientSession(timeout=tiempo) as ses:
            async with ses.post(FISH_URL, json=cuerpo, headers=cabeceras) as r:
                if r.status != 200:
                    raise RuntimeError(f"HTTP {r.status}: {(await r.text())[:120]}")
                datos = await r.read()
        if len(datos) < 800:
            raise RuntimeError("audio vacío")
        (self.carpeta / nombre).write_bytes(datos)
        self._limpiar()
        return nombre

    async def _edge(self, texto, intentos=2):
        """Genera un mp3 con edge-tts y devuelve su nombre de archivo.

        El servicio de Microsoft a veces tarda, corta la conexión o devuelve un audio vacío
        (sobre todo con muchas frases seguidas). Antes eso pasaba en silencio: el avatar
        recibía un mp3 vacío y se lo saltaba sin que se oyera nada. Ahora se reintenta y,
        si sigue fallando, se avisa con el motivo.
        """
        error = None
        for intento in range(intentos * len(SERVIDORES)):
            # cada intento prueba los servidores por turnos, empezando por el nuevo
            _edge_com.WSS_URL = SERVIDORES[intento % len(SERVIDORES)]
            nombre = f"{uuid.uuid4().hex}.mp3"
            ruta = self.carpeta / nombre
            try:
                com = edge_tts.Communicate(texto, self.voz, rate=self.velocidad, pitch=self.tono)
                await asyncio.wait_for(com.save(str(ruta)), timeout=20)
                if ruta.exists() and ruta.stat().st_size > 800:
                    self._limpiar()
                    return nombre
                error = RuntimeError("Microsoft ha devuelto un audio vacío (suele ser un bloqueo "
                                     "temporal por muchas peticiones seguidas)")
            except asyncio.TimeoutError:
                error = RuntimeError("el servicio de voz ha tardado demasiado en contestar")
            except Exception as err:
                error = err
            ruta.unlink(missing_ok=True)
            if intento % len(SERVIDORES) == len(SERVIDORES) - 1:  # tras probar todos, espera
                await asyncio.sleep(1 + intento // len(SERVIDORES))
        raise error

    def _limpiar(self):
        archivos = sorted(self.carpeta.glob("*.mp3"), key=lambda p: p.stat().st_mtime)
        for viejo in archivos[:-self.max_archivos]:
            viejo.unlink(missing_ok=True)


async def voces_espanol(solo_femeninas=True):
    voces = await edge_tts.list_voices()
    return [v for v in voces
            if v["Locale"].startswith("es-") and (not solo_femeninas or v["Gender"] == "Female")]


if __name__ == "__main__":
    for v in asyncio.run(voces_espanol()):
        print(f'{v["ShortName"]:28} {v["Locale"]}')
