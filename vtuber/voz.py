"""Texto a voz con edge-tts (voces neuronales de Microsoft Edge, gratis y sin clave)."""
import asyncio
import uuid
from pathlib import Path

import edge_tts


class Voz:
    def __init__(self, cfg, carpeta: Path, max_archivos=60):
        self.voz = cfg.get("voz", "es-ES-ElviraNeural")
        self.velocidad = cfg.get("velocidad", "+0%")
        self.tono = cfg.get("tono", "+0Hz")
        self.carpeta = carpeta
        self.max_archivos = max_archivos
        carpeta.mkdir(parents=True, exist_ok=True)
        for viejo in carpeta.glob("*.mp3"):
            viejo.unlink()

    async def sintetizar(self, texto, intentos=2):
        """Genera un mp3 y devuelve su nombre de archivo.

        El servicio de Microsoft a veces tarda, corta la conexión o devuelve un audio vacío
        (sobre todo con muchas frases seguidas). Antes eso pasaba en silencio: el avatar
        recibía un mp3 vacío y se lo saltaba sin que se oyera nada. Ahora se reintenta y,
        si sigue fallando, se avisa con el motivo.
        """
        error = None
        for intento in range(intentos):
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
            await asyncio.sleep(1 + intento)
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
