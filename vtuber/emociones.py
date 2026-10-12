"""Etiquetas de emoción dentro del texto de la IA: "[feliz] ¡Hola! [sorprendida] ¿En serio?"."""
import re

EMOCIONES = ["neutral", "feliz", "enojada", "triste", "llorando",
             "sorprendida", "avergonzada", "presumida", "pensativa"]

# Lo que un modelo suele escribir en lugar del nombre exacto
SINONIMOS = {
    # las que salen jugando
    "alivio": "feliz", "aliviada": "feliz", "frustrada": "enojada", "picada": "enojada",
    "agobiada": "sorprendida", "concentrada": "pensativa",
    "normal": "neutral", "seria": "neutral", "tranquila": "neutral", "calmada": "neutral",
    "contenta": "feliz", "alegre": "feliz", "riendo": "feliz", "risa": "feliz",
    "emocionada": "feliz", "happy": "feliz", "sonriente": "feliz", "excitada": "feliz",
    "entusiasmada": "feliz", "animada": "feliz", "divertida": "feliz", "ilusionada": "feliz",
    "curiosa": "pensativa", "curioso": "pensativa", "interesada": "pensativa",
    "intrigada": "pensativa", "dudosa": "pensativa", "reflexiva": "pensativa",
    "timida": "avergonzada", "insegura": "avergonzada", "apenada": "avergonzada",
    "preocupada": "triste", "dolida": "triste", "asustada": "sorprendida",
    "impresionada": "sorprendida", "confiada": "presumida", "orgullosa": "presumida",
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


_EMOTICONOS = re.compile(r"(?<!\w)(?:[xX][dD]+|[:;=]-?[)(DPpOo3]+|<3+|u[wW]u|o[wW]o|\^_*\^|T_T|:v)(?!\w)")
_MARCAS = re.compile(r"[*_#~`|<>\[\]{}]")
_ENLACES = re.compile(r"https?://\S+|www\.\S+")


def para_voz(frase):
    """Lo que se oye: sin emoticonos ni símbolos que la voz leería tal cual («equis de»,
    «dos puntos paréntesis»…). El texto que se ve en el panel no cambia."""
    # Decidido por Juan Luis escuchando pruebas con las dos voces (2026-10-12): las risas largas, «¡¡¡…!!!», «¿¿…??»,
    # mayúsculas y «Mmm» se dejan; «XD» y los emoticonos se quitan (Fish dice «xte» o cosas raras
    # y Ximena lee «emoticono cara riendo»).
    t = _ENLACES.sub("", frase)
    t = _EMOTICONOS.sub("", t)
    t = _MARCAS.sub("", t)
    t = re.sub(r"(\d)\s*-\s*(\d)", r"\1 o \2", t)  # «1-2» -> «1 o 2»
    t = re.sub(r"\s+([,.;:!?…])", r"\1", t)
    t = re.sub(r"[,;:]+([.!?…])", r"\1", t)        # «Jajaja,.» (al quitar un «XD») -> «Jajaja.»
    return re.sub(r"\s+", " ", t).strip(" ,;")


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
