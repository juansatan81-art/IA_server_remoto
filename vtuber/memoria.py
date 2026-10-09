"""Memoria a largo plazo de Lara: quién es cada espectador y qué pasó en directos anteriores.

Se guarda en la carpeta memoria/ como JSON legible (puedes abrirlo y corregirlo a mano).
"""
import json
import logging
import time
from datetime import datetime
from pathlib import Path

log = logging.getLogger("vtuber")

MAX_NOTAS = 6          # cosas que recuerda de cada espectador
RECUERDOS_EN_PROMPT = 3


class Memoria:
    def __init__(self, carpeta: Path):
        self.carpeta = Path(carpeta)
        self.carpeta.mkdir(exist_ok=True)
        self.f_espectadores = self.carpeta / "espectadores.json"
        self.f_directos = self.carpeta / "directos.json"
        self.espectadores = self._leer(self.f_espectadores, {})
        self.directos = self._leer(self.f_directos, [])

    def _leer(self, archivo, vacio):
        try:
            return json.loads(archivo.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return vacio
        except (json.JSONDecodeError, OSError) as err:
            log.warning("No se pudo leer %s (%s); empiezo de cero sin borrarlo.", archivo, err)
            return vacio

    def _guardar(self, archivo, datos):
        self.carpeta.mkdir(exist_ok=True)
        temporal = archivo.with_suffix(".tmp")
        temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
        temporal.replace(archivo)

    # ---------------------------------------------------------- espectadores
    def visto(self, autor):
        """Apunta que ha escrito; devuelve cuántas veces le ha visto antes de hoy."""
        hoy = datetime.now().strftime("%Y-%m-%d")
        e = self.espectadores.setdefault(autor, {"primera_vez": hoy, "dias": [], "mensajes": 0, "notas": []})
        dias_antes = len([d for d in e["dias"] if d != hoy])
        if hoy not in e["dias"]:
            e["dias"] = (e["dias"] + [hoy])[-30:]
        e["mensajes"] += 1
        e["ultima_vez"] = time.time()
        self._guardar(self.f_espectadores, self.espectadores)
        return dias_antes

    def anotar(self, autor, nota):
        if not nota:
            return
        e = self.espectadores.get(autor)
        if e is None or nota in e["notas"]:
            return
        e["notas"] = (e["notas"] + [nota])[-MAX_NOTAS:]
        self._guardar(self.f_espectadores, self.espectadores)

    def sobre(self, autor):
        """Frase para el modelo con lo que sabe de esa persona."""
        e = self.espectadores.get(autor)
        if not e:
            return f"{autor} escribe por primera vez: dale la bienvenida."
        hoy = datetime.now().strftime("%Y-%m-%d")
        otros_dias = len([d for d in e["dias"] if d != hoy])
        partes = []
        if hoy in e["dias"]:
            # ya se le ha respondido hoy: sin volver a darle la bienvenida
            partes.append(f"Ya has hablado hoy con {autor}: NO le des la bienvenida otra vez.")
        if otros_dias:
            partes.append(f"{autor} ya ha venido a {otros_dias} directo(s) anteriores.")
        elif hoy not in e["dias"]:
            partes.append(f"{autor} escribe por primera vez: dale la bienvenida.")
        if e["notas"]:
            partes.append(f"Lo que recuerdas de {autor}: " + "; ".join(e["notas"]) + ".")
        return " ".join(partes)

    # ---------------------------------------------------------- directos
    def guardar_directo(self, resumen):
        self.directos.append({"fecha": datetime.now().strftime("%Y-%m-%d %H:%M"), "resumen": resumen})
        self._guardar(self.f_directos, self.directos)

    def recuerdos(self):
        return "\n".join(f"- {d['fecha'][:10]}: {d['resumen']}" for d in self.directos[-RECUERDOS_EN_PROMPT:])
