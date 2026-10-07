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

    async def sintetizar(self, texto):
        """Genera un mp3 y devuelve su nombre de archivo."""
        nombre = f"{uuid.uuid4().hex}.mp3"
        com = edge_tts.Communicate(texto, self.voz, rate=self.velocidad, pitch=self.tono)
        await com.save(str(self.carpeta / nombre))
        self._limpiar()
        return nombre

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
