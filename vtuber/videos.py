"""Fichas de los vídeos publicados del canal, para que Lara hable de ellos sin inventar.

Las fichas se escriben en memoria/videos.json (legible: se puede corregir a mano). Al
arrancar se vuelcan a memoria/videos.db, una base SQLite con búsqueda de texto (FTS5),
que se rehace sola si el JSON es más nuevo. Cuando un mensaje habla de un vídeo, la
ficha entra en la nota para el modelo con la orden de no inventar ni buscar fuera.
"""
import json
import logging
import re
import sqlite3
import unicodedata
from pathlib import Path

log = logging.getLogger("vtuber")

PISTAS = ("video", "videos", "canal", "subiste", "hiciste", "contaste", "hablaste", "publicaste")
VACIAS = set("""a al algo como con cual cuando de del donde el ella ellos en era es esa ese eso esta
este esto fue ha has hay la las le les lo los mas me mi muy no nos o para pero por que se si sin
sobre su sus te tu tus un una uno y ya yo qué cómo cuál dónde porque tiene tienes""".split())


def _norm(texto):
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9ñ ]+", " ", t)).strip()


class Videos:
    def __init__(self, carpeta: Path):
        self.json = Path(carpeta) / "videos.json"
        self.db = Path(carpeta) / "videos.db"
        self.fichas = []
        try:
            self.fichas = json.loads(self.json.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (json.JSONDecodeError, OSError) as err:
            log.warning("No se pudo leer %s (%s); Lara no tendrá fichas de vídeos.", self.json, err)
            return
        if not self.db.exists() or self.db.stat().st_mtime < self.json.stat().st_mtime:
            self._construir()

    def _construir(self):
        self.db.unlink(missing_ok=True)
        con = sqlite3.connect(self.db)
        con.execute("CREATE VIRTUAL TABLE videos USING fts5(titulo, claves, texto, n UNINDEXED)")
        for i, f in enumerate(self.fichas):
            texto = " ".join([f.get("resumen", ""), *f.get("datos_clave", []), *f.get("capitulos", [])])
            con.execute("INSERT INTO videos VALUES (?, ?, ?, ?)",
                        (_norm(f["titulo"]), _norm(" ".join(f.get("palabras_clave", []) + f.get("temas", []))), _norm(texto), i))
        con.commit()
        con.close()
        log.info("Base de vídeos rehecha: %d fichas", len(self.fichas))

    def buscar(self, mensaje, maximo=2):
        """Fichas que tienen que ver con el mensaje. Hace falta que nombre algo concreto
        de un vídeo (título o palabra concreta), o que hable de sus vídeos y coincida un tema
        general (luna, música, voz...). Así «hola» no trae el vídeo de los saludos."""
        if not self.fichas or not self.db.exists():
            return []
        palabras = [p for p in _norm(mensaje).split() if len(p) > 2 and p not in VACIAS and p not in PISTAS]
        if not palabras:
            return []
        consulta = " OR ".join(f'"{p}"' for p in palabras)
        con = sqlite3.connect(self.db)
        try:
            filas = con.execute(
                "SELECT n, bm25(videos, 3.0, 4.0, 1.0) AS r, titulo, claves FROM videos "
                "WHERE videos MATCH ? ORDER BY r LIMIT ?", (consulta, maximo * 3)).fetchall()
        except sqlite3.OperationalError:
            return []
        finally:
            con.close()
        habla_de_videos = any(p in _norm(mensaje).split() for p in PISTAS)
        n = f" {_norm(mensaje)} "
        dentro = lambda formas: any(f" {_norm(c)} " in n for c in formas if _norm(c))
        concretas, por_tema = [], []
        for i, _, titulo, claves in filas:
            f = self.fichas[i]
            titulo_n = _norm(f["titulo"])
            nombra_titulo = f" {titulo_n} " in n and (len(titulo_n.split()) > 1 or habla_de_videos)
            if dentro(f.get("palabras_clave", [])) or nombra_titulo:
                concretas.append(f)          # nombra algo propio de ese vídeo: basta
            elif habla_de_videos and dentro(f.get("temas", [])):
                por_tema.append(f)           # tema general: solo si habla de sus vídeos
        elegidas = (concretas or por_tema)[:maximo]
        return elegidas

    def lista(self):
        return " | ".join(f"«{f['titulo']}» ({f['fecha']})" for f in self.fichas)

    def nota(self, mensaje):
        """Texto para el modelo con las fichas relevantes (vacío si el mensaje no va de vídeos)."""
        fichas = self.buscar(mensaje)
        n = _norm(mensaje).split()
        pide_lista = any(p in n for p in ("videos", "video")) and \
            any(p in n for p in ("cuales", "cuantos", "lista", "todos", "ultimo", "primero", "favorito"))
        if pide_lista and not any(_norm(f["titulo"]) in _norm(mensaje) for f in fichas):
            fichas = [f for f in fichas if any(f" {_norm(c)} " in f" {_norm(mensaje)} "
                                                for c in f.get("palabras_clave", []))]
        if not fichas and not pide_lista:
            return ""
        partes = ["Fichas de TUS vídeos publicados que tienen que ver con esto. Para hablar de "
                  "ellos usa SOLO lo que pone aquí: no inventes detalles ni los busques en internet. "
                  "Si te preguntan algo que no está, di con naturalidad que no lo recuerdas bien."]
        if pide_lista:
            partes.append(f"Tus vídeos publicados, del más antiguo al más nuevo: {self.lista()}.")
        for f in fichas:
            datos = " ".join(f.get("datos_clave", []))
            partes.append(f"«{f['titulo']}» ({f['fecha']}, {f.get('tipo', '')}): {f['resumen']} {datos}")
        return " ".join(partes)
