"""Etiquetas de emoción dentro del texto de la IA: "[feliz] ¡Hola! [sorprendida] ¿En serio?"."""
import re

EMOCIONES = ["neutral", "feliz", "enojada", "triste", "llorando",
             "sorprendida", "avergonzada", "presumida", "pensativa"]

# Lo que un modelo suele escribir en lugar del nombre exacto
SINONIMOS = {
    "normal": "neutral", "seria": "neutral", "tranquila": "neutral", "calmada": "neutral",
    "contenta": "feliz", "alegre": "feliz", "riendo": "feliz", "risa": "feliz",
    "emocionada": "feliz", "happy": "feliz", "sonriente": "feliz",
    "enojado": "enojada", "enfadada": "enojada", "enfadado": "enojada", "molesta": "enojada",
    "furiosa": "enojada", "angry": "enojada",
    "triste": "triste", "sad": "triste", "decepcionada": "triste",
    "llorar": "llorando", "llanto": "llorando", "crying": "llorando",
    "sorpresa": "sorprendida", "sorprendido": "sorprendida", "asombrada": "sorprendida",
    "surprised": "sorprendida",
    "verguenza": "avergonzada", "vergüenza": "avergonzada", "timida": "avergonzada",
    "tímida": "avergonzada", "nerviosa": "avergonzada", "sonrojada": "avergonzada",
    "presumido": "presumida", "orgullosa": "presumida", "chulita": "presumida", "smug": "presumida",
    "pensando": "pensativa", "pensativo": "pensativa", "dudando": "pensativa", "confundida": "pensativa",
}

_ETIQUETA = re.compile(r"\[([^\[\]]{1,24})\]")
_ACCIONES = re.compile(r"\*[^*]{1,80}\*")          # *se ríe*  -> no se lee en voz alta
_PENSAMIENTO = re.compile(r"<think>.*?</think>", re.S | re.I)
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️]")


def normalizar(nombre):
    n = nombre.strip().lower()
    if n in EMOCIONES:
        return n
    return SINONIMOS.get(n)


def limpiar(texto):
    texto = _PENSAMIENTO.sub("", texto)
    texto = _ACCIONES.sub("", texto)
    texto = _EMOJI.sub("", texto)
    return re.sub(r"\s+", " ", texto).strip()


def dividir(texto, por_defecto=None):
    """Divide el texto en tramos [(emocion o None, frase), ...].

    Las etiquetas desconocidas se eliminan del texto para que no se lean.
    """
    texto = _PENSAMIENTO.sub("", texto)
    tramos, actual, pos = [], por_defecto, 0
    for m in _ETIQUETA.finditer(texto):
        anterior = limpiar(texto[pos:m.start()])
        if anterior:
            tramos.append((actual, anterior))
        emo = normalizar(m.group(1))
        if emo:
            actual = emo
        pos = m.end()
    resto = limpiar(texto[pos:])
    if resto:
        tramos.append((actual, resto))
    elif not tramos and actual:
        tramos.append((actual, ""))   # solo una etiqueta, sin texto
    return tramos
