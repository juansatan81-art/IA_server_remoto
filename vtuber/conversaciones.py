"""Registro de todo lo que dice Lara, con el contexto exacto que vio el modelo.

Cada frase dicha queda en memoria/conversaciones/AAAA-MM-DD.jsonl (una línea por frase) y
las valoraciones del panel (👍/👎) en valoraciones.jsonl, sin reescribir nada: solo se añade.
El prompt de sistema se guarda aparte (sistemas/<huella>.txt) porque casi nunca cambia.
`herramientas/exportar_dataset.py` junta las tres cosas en un dataset para el fine-tuning.
"""

import hashlib
import json
import time
import uuid
from datetime import datetime
from pathlib import Path


class Conversaciones:
    def __init__(self, carpeta: Path):
        self.carpeta = carpeta / "conversaciones"
        (self.carpeta / "sistemas").mkdir(parents=True, exist_ok=True)
        self.valoraciones = self.carpeta / "valoraciones.jsonl"

    def _anadir(self, archivo, datos):
        with open(archivo, "a", encoding="utf-8") as f:
            f.write(json.dumps(datos, ensure_ascii=False) + "\n")

    def _sistema(self, texto):
        huella = hashlib.sha1(texto.encode("utf-8")).hexdigest()[:12]
        ruta = self.carpeta / "sistemas" / f"{huella}.txt"
        if not ruta.exists():
            ruta.write_text(texto, encoding="utf-8")
        return huella

    def guardar(self, turno, dicho, origen, bloqueada=False):
        """`turno` es lo que dejó el cerebro: {"sistema", "historial", "entrada", "respuesta"}.
        Devuelve el id de la frase (el panel lo usa para valorarla) o "" si no hay turno."""
        if not turno:
            return ""
        id_frase = uuid.uuid4().hex[:12]
        try:
            self._anadir(self.carpeta / f"{datetime.now():%Y-%m-%d}.jsonl", {
                "id": id_frase, "fecha": datetime.now().isoformat(timespec="seconds"),
                "origen": origen,                      # "chat" (le hablan) o "sola" (sin chat)
                "sistema": self._sistema(turno["sistema"]),
                "historial": turno["historial"], "entrada": turno["entrada"],
                "respuesta": turno["respuesta"],       # lo que generó el modelo
                "dicho": dicho, "bloqueada": bloqueada})  # lo que se oyó (el filtro puede cambiarlo)
        except OSError:
            return ""
        return id_frase

    def valorar(self, id_frase, valor):
        """valor: 1 (👍), -1 (👎) o 0 (quitar la valoración). Cuenta la última."""
        self._anadir(self.valoraciones, {"id": id_frase, "valor": int(valor), "cuando": int(time.time())})

    def cuantas(self):
        """Frases valoradas hasta ahora: {"buenas": n, "malas": n}."""
        ultimas = {}
        if self.valoraciones.exists():
            for linea in self.valoraciones.read_text(encoding="utf-8").splitlines():
                try:
                    v = json.loads(linea)
                    ultimas[v["id"]] = v["valor"]
                except (json.JSONDecodeError, KeyError):
                    continue
        valores = list(ultimas.values())
        return {"buenas": valores.count(1), "malas": valores.count(-1)}
