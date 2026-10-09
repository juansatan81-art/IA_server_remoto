"""Glosario: palabras de internet, memes y personajes que Lara conoce sin tener que buscarlos.

- Empieza con una lista inicial revisada (LISTA_INICIAL).
- Cuando Lara busca en internet qué significa algo, apunta el término como "pendiente".
- Tú los revisas en el panel: los apruebas (y corriges el significado) o los rechazas.
- Solo los aprobados se usan: si alguien los menciona en el chat, Lara recibe el
  significado y ya no necesita buscarlo.

Se guarda en memoria/glosario.json, aparte de la memoria de espectadores y de vídeos.
"""
import json
import logging
import random
import re
import unicodedata
from datetime import datetime
from pathlib import Path

log = logging.getLogger("vtuber")

# (término, otras formas de escribirlo, significado). Revisada a mano; puedes cambiar
# cualquier cosa desde el panel.
LISTA_INICIAL = [
    ("brainrot", ["brain rot"], "Contenido de internet tan absurdo y repetitivo que, en broma, 'pudre el cerebro'; "
     "también el humor que nace de él. Oxford la eligió palabra del año en 2024."),
    ("brainrot italiano", ["italian brainrot"], "Moda de 2025: personajes absurdos hechos con IA, mezcla de "
     "animales y objetos, con nombres que suenan a italiano. Ojo: algunos audios originales tienen "
     "blasfemias o frases ofensivas, así que se habla de los personajes, nunca se repiten esas letras."),
    ("Tralalero Tralala", ["tralalero"], "Personaje del brainrot italiano: un tiburón con tres patas y zapatillas Nike."),
    ("Bombardiro Crocodilo", ["bombardiro", "bombardino cocodrilo"], "Personaje del brainrot italiano: un cocodrilo "
     "que es a la vez un avión bombardero."),
    ("Bombombini Gusini", ["bombardini gusini", "bombombini", "gusini"], "Personaje del brainrot italiano: un ganso "
     "con forma de avión de combate, 'pariente' de Bombardiro Crocodilo."),
    ("Tung Tung Tung Sahur", ["tung tung sahur", "tung tung"], "Personaje del brainrot (de Indonesia): un tronco de "
     "madera con cara que lleva un bate; el nombre imita el tambor que despierta a la gente para el sahur, "
     "la comida de antes del amanecer en Ramadán."),
    ("Ballerina Cappuccina", ["ballerina capuchina", "ballerina cappuccino"], "Personaje del brainrot italiano: una "
     "bailarina de ballet con una taza de capuchino por cabeza."),
    ("Lirilì Larilà", ["lirili larila"], "Personaje del brainrot italiano: un elefante-cactus con sandalias."),
    ("Brr Brr Patapim", ["patapim"], "Personaje del brainrot italiano: un mono-árbol del bosque con pies enormes."),
    ("Chimpanzini Bananini", ["chimpanzini"], "Personaje del brainrot italiano: un chimpancé metido dentro de un plátano."),
    ("Trippi Troppi", [], "Personaje del brainrot italiano: una gamba con cabeza de gato."),
    ("skibidi", ["skibidi toilet"], "Viene de 'Skibidi Toilet', serie de YouTube de cabezas que salen de inodoros; "
     "se usa como palabra comodín sin sentido."),
    ("67", ["six seven", "six-seven", "6 7", "seis siete"], "Meme de 2025: decir 'six seven' (seis siete) moviendo las "
     "manos arriba y abajo; viene de una canción de Skrilla y no significa nada, la gracia es esa."),
    ("rizz", [], "Carisma para ligar o caer bien; 'tener rizz'."),
    ("aura", ["aura points", "puntos de aura"], "Lo guay o digno que pareces: hacer algo épico da '+1000 de aura'; "
     "hacer el ridículo te hace perder aura."),
    ("sigma", [], "Persona solitaria e 'independiente'; se usa casi siempre en broma."),
    ("NPC", [], "Alguien que actúa como un personaje secundario de videojuego, sin pensar por sí mismo."),
    ("cringe", [], "Vergüenza ajena."),
    ("GOAT", [], "El mejor de todos los tiempos (Greatest Of All Time)."),
    ("POV", [], "Punto de vista: vídeos en los que te pones en la piel de alguien."),
    ("mewing", [], "Poner la lengua en el paladar para marcar la mandíbula; en memes, el gesto de mandar callar "
     "tocándose la mandíbula."),
    ("looksmaxxing", ["looksmaxing"], "Intentar mejorar al máximo tu aspecto físico; se usa mucho en broma."),
    ("delulu", [], "Que vive en su fantasía o se hace ilusiones irreales (de 'delusional')."),
    ("slay", [], "Hacerlo genial, arrasar."),
    ("simp", [], "Persona que hace demasiado por alguien que le gusta."),
    ("ratio", [], "Cuando una respuesta tiene más 'me gusta' que el mensaje original."),
    ("no cap", ["cap"], "'En serio, sin mentir'; 'cap' significa mentira."),
    ("fanum tax", ["fanum"], "Quitarle comida a un amigo en broma (viene del streamer Fanum)."),
    ("Ohio", ["only in ohio", "solo en ohio"], "'Solo en Ohio': se dice de algo muy raro o absurdo."),
    ("amogus", ["among us"], "Among Us, el juego de descubrir al impostor; de ahí 'sus' = sospechoso."),
    ("clanker", [], "Insulto de broma para robots e inteligencias artificiales (de Star Wars). Si te lo dicen, "
     "tómatelo con humor."),
    ("Labubu", [], "Muñeco de peluche de un monstruito con dientes, de la marca Pop Mart, muy de moda en 2025."),
    ("Block Blast", [], "Juego de puzles de móvil: colocar bloques en un tablero para completar filas y columnas."),
    ("chamba", [], "Trabajo (Latinoamérica). 'Mucha chamba' = mucho trabajo."),
    ("funar", ["funado", "funa"], "Criticar o 'cancelar' públicamente a alguien en redes (Latinoamérica)."),
    ("tilín", ["le hizo tilin", "me hizo tilin"], "'Le hizo tilín': le gustó alguien."),
    ("red flag", ["green flag"], "Red flag: señal de alarma en una persona. Green flag: buena señal."),
    ("random", [], "Algo aleatorio o sin sentido."),
    ("god", [], "En España, 'genial' o 'buenísimo': 'está god'."),
    ("xd", ["xD"], "Cara riéndose; se usa para indicar risa o que algo es broma."),
    ("GG", [], "'Good game', buena partida; también 'se acabó'."),
    ("F", [], "Escribir 'F' es mostrar respeto o pésame en broma cuando algo sale mal."),
    ("W", ["L"], "W = victoria o algo bueno; L = derrota o algo malo ('una L enorme')."),
    ("noob", [], "Novato en un juego."),
    ("tryhard", [], "Alguien que se esfuerza muchísimo en un juego para ganar."),
    ("AFK", [], "Ausente del teclado: alguien que no está jugando en ese momento."),
    ("lag", [], "Retraso por mala conexión en un juego."),
    ("nerfear", ["nerf", "bufear", "buff"], "Nerfear: hacer más débil algo en un juego. Bufear: hacerlo más fuerte."),
    ("boomer", [], "Persona mayor o con gustos anticuados (se usa en broma)."),
]

_PEDIR = """Una VTuber acaba de buscar en internet «{consulta}». Estos son los resultados:
{resultado}

¿La búsqueda era para entender una palabra, expresión, meme, personaje o tendencia de internet?
Si sí, da el término tal cual se escribe y su significado en 1 o 2 frases sencillas en español,
basándote solo en los resultados. Si no (era otra cosa, como una noticia o un dato), es_termino = false."""
ESQUEMA = {"type": "object", "properties": {
    "es_termino": {"type": "boolean"}, "termino": {"type": "string", "maxLength": 60},
    "significado": {"type": "string", "maxLength": 300}}, "required": ["es_termino", "termino", "significado"]}


def _norm(texto):
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9ñ ]+", " ", t)).strip()


class Glosario:
    def __init__(self, carpeta: Path):
        self.archivo = Path(carpeta) / "glosario.json"
        try:
            self.terminos = json.loads(self.archivo.read_text(encoding="utf-8"))
        except FileNotFoundError:
            hoy = datetime.now().strftime("%Y-%m-%d")
            self.terminos = [{"termino": t, "alias": a, "significado": s, "estado": "aprobado",
                              "fuente": "lista inicial", "fecha": hoy} for t, a, s in LISTA_INICIAL]
            self._guardar()
        except (json.JSONDecodeError, OSError) as err:
            log.warning("No se pudo leer %s (%s); uso un glosario vacío sin borrarlo.", self.archivo, err)
            self.terminos = []

    def _guardar(self):
        self.archivo.parent.mkdir(exist_ok=True)
        temporal = self.archivo.with_suffix(".tmp")
        temporal.write_text(json.dumps(self.terminos, ensure_ascii=False, indent=2), encoding="utf-8")
        temporal.replace(self.archivo)

    def _buscar(self, termino):
        n = _norm(termino)
        for t in self.terminos:
            if _norm(t["termino"]) == n or n in (_norm(a) for a in t.get("alias", [])):
                return t
        return None

    def mencionados(self, texto, maximo=4):
        """Términos aprobados que aparecen en el texto (palabras completas)."""
        n = f" {_norm(texto)} "
        vistos = []
        for t in self.terminos:
            if t["estado"] != "aprobado":
                continue
            formas = [t["termino"], *t.get("alias", [])]
            if any(f" {_norm(f)} " in n for f in formas if len(_norm(f)) >= 2):
                vistos.append(t)
                if len(vistos) >= maximo:
                    break
        return vistos

    def nota(self, texto):
        """Frase para el modelo con el significado de lo que se menciona."""
        vistos = self.mencionados(texto)
        if not vistos:
            return ""
        return ("Significados que ya conoces (no hace falta buscarlos): "
                + " | ".join(f"{t['termino']}: {t['significado']}" for t in vistos))

    def al_azar(self, n=3):
        aprobados = [t for t in self.terminos if t["estado"] == "aprobado"]
        return random.sample(aprobados, min(n, len(aprobados)))

    async def aprender(self, cerebro, consulta, resultado):
        """Tras una búsqueda: si era para entender un término, se apunta como pendiente."""
        if resultado.startswith("No se ha encontrado"):
            return None
        try:
            datos = await cerebro.json([{"role": "user", "content": _PEDIR.format(
                consulta=consulta, resultado=resultado[:2500])}], ESQUEMA, max_tokens=200, temperatura=0)
        except Exception:
            return None
        termino = str(datos.get("termino", "")).strip()
        significado = str(datos.get("significado", "")).strip()
        if not datos.get("es_termino") or not termino or not significado:
            return None
        if self._buscar(termino):
            return None   # ya estaba (aprobado, pendiente o rechazado: no se repite)
        nuevo = {"termino": termino, "alias": [], "significado": significado, "estado": "pendiente",
                 "fuente": f"búsqueda: {consulta}", "fecha": datetime.now().strftime("%Y-%m-%d")}
        self.terminos.append(nuevo)
        self._guardar()
        return nuevo

    # ---------------------------------------------------------- panel
    def poner(self, termino, significado=None, estado=None, alias=None):
        termino = termino.strip()
        if not termino:
            raise ValueError("Falta el término")
        t = self._buscar(termino)
        if t is None:
            t = {"termino": termino, "alias": [], "significado": "", "estado": "aprobado",
                 "fuente": "añadido a mano", "fecha": datetime.now().strftime("%Y-%m-%d")}
            self.terminos.append(t)
        if significado is not None:
            t["significado"] = significado.strip()
        if estado in ("aprobado", "pendiente", "rechazado"):
            t["estado"] = estado
        if alias is not None:
            t["alias"] = [a.strip() for a in alias if a.strip()]
        self._guardar()
        return t

    def borrar(self, termino):
        t = self._buscar(termino)
        if t:
            self.terminos.remove(t)
            self._guardar()
        return bool(t)
