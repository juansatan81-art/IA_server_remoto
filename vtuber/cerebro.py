"""El "cerebro": un modelo de lenguaje local.

Con Ollama se usa su API propia (/api/chat), que permite apagar el modo "pensar"
de modelos como gemma4 o qwen3, mandar imágenes y usar herramientas (buscar en
internet). Con otros programas (LM Studio, llama.cpp, vLLM...) se usa la API
compatible con OpenAI: basta con poner su dirección en config.json -> cerebro.url
"""
import base64
import json
import re
from datetime import datetime

import aiohttp

import internet
from emociones import EMOCIONES

PLANTILLA = """Eres {nombre}, una VTuber que hace directos y charla con su público.
{personalidad}

Tienes un cuerpo de avatar 2D que tú controlas. Para cambiar tu cara escribe una etiqueta
entre corchetes justo antes de la frase. Emociones disponibles: {emociones}.
Ejemplo: [feliz] ¡Hola a todos! [pensativa] Mmm, ¿de qué hablamos hoy?

Reglas:
- Empieza SIEMPRE con una etiqueta de emoción y cámbiala cuando cambie tu emoción.
- Usa SOLO esas etiquetas, escritas exactamente así; no inventes otras.
- Respuestas cortas y habladas: 1 a 3 frases, nada de listas, código, enlaces ni markdown.
- No describas acciones entre asteriscos; tu voz se genera a partir de tu texto.
- Habla SIEMPRE y SOLO en español: nunca escribas en chino, inglés ni con otros alfabetos."""

EXTRA_INTERNET = """- Puedes buscar en internet con tus herramientas. Úsalas cuando te pregunten por algo
  actual o algo que no sepas seguro; no te inventes datos. Cuéntalo con tus palabras."""

EXTRA_VISTA = """- A veces te enseñarán una imagen o lo que se ve en la pantalla (un juego, una web...).
  Míralo de verdad y coméntalo con naturalidad, como si lo estuvieras viendo en directo."""

_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre"]

# Caracteres de chino, japonés y coreano: los modelos pequeños a veces
# cambian de idioma a mitad de frase
_OTRO_ALFABETO = re.compile("[぀-ヿ㐀-鿿가-힯＀-￯]")
_RECORDATORIO = ("Tu respuesta anterior mezclaba otro idioma. Repite la respuesta entera "
                 "solo en español, con la misma etiqueta de emoción al principio.")
_PENSAMIENTO = re.compile(r"<think>.*?</think>", re.S | re.I)
MAX_RONDAS = 3   # búsquedas seguidas que puede encadenar antes de contestar


def _fecha():
    a = datetime.now()
    return (f"Hoy es {_DIAS[a.weekday()]}, {a.day} de {_MESES[a.month - 1]} de {a.year}, "
            f"y son las {a:%H:%M}.")


def _base64(imagen):
    """Acepta 'data:image/jpeg;base64,...' o base64 a secas; devuelve base64 a secas."""
    datos = imagen.split(",", 1)[1] if imagen.startswith("data:") else imagen
    base64.b64decode(datos[:64] + "=" * (-len(datos[:64]) % 4))   # falla si no es base64
    return datos


class Cerebro:
    def __init__(self, cfg, personaje):
        self.url = cfg.get("url", "http://localhost:11434/v1").rstrip("/")
        self.modelo = cfg.get("modelo", "qwen2.5:7b")
        self.clave = cfg.get("api_key", "local")
        self.temperatura = cfg.get("temperatura", 0.8)
        self.max_tokens = cfg.get("max_tokens", 300)
        self.max_historial = cfg.get("historial", 20)
        self.contexto = cfg.get("contexto", 8192)
        self.mantener = cfg.get("mantener_cargado", "24h")
        self.pensar = bool(cfg.get("pensar", False))
        self.internet = bool(cfg.get("internet", True))
        # "ollama" (API propia) u "openai"; por defecto se deduce de la dirección
        self.api = cfg.get("api") or ("ollama" if ":11434" in self.url else "openai")
        self.base_ollama = re.sub(r"/v1$", "", self.url)
        self.sistema = cfg.get("prompt_sistema") or "\n".join([
            PLANTILLA.format(nombre=personaje.get("nombre", "la VTuber"),
                             personalidad=personaje.get("personalidad", ""),
                             emociones=", ".join(EMOCIONES)),
            EXTRA_INTERNET if self.internet else "",
            EXTRA_VISTA]).strip()
        self.historial = []

    # ------------------------------------------------------------------ charla
    async def responder(self, mensaje, usuario=None, imagenes=None, aviso=None):
        """Devuelve la respuesta (con etiquetas). `imagenes`: lista de base64 o data URL.

        `aviso(texto)` es una corrutina opcional para contar qué hace (buscar en internet...).
        """
        contenido = f"{usuario}: {mensaje}" if usuario else mensaje
        imagenes = [_base64(i) for i in (imagenes or [])]
        actual = {"role": "user", "content": contenido, "imagenes": imagenes}
        mensajes = [{"role": "system", "content": f"{self.sistema}\n\n{_fecha()}"},
                    *self.historial, actual]

        respuesta = await self._conversar(mensajes, aviso)
        # si se ha colado otro idioma, se le pide una vez que lo repita en español
        if _OTRO_ALFABETO.search(respuesta):
            respuesta = await self._conversar(
                mensajes + [{"role": "assistant", "content": respuesta},
                            {"role": "user", "content": _RECORDATORIO}], aviso, herramientas=False)
        # y si aún así queda algo, se corta ahí: mejor una frase más corta que oírla en chino
        corte = _OTRO_ALFABETO.search(respuesta)
        if corte:
            respuesta = respuesta[:corte.start()].rstrip(" ,;:-")
            if respuesta and respuesta[-1] not in ".!?…":
                respuesta += "…"
        if not respuesta:
            respuesta = "[avergonzada] Perdón, me he liado."

        # las imágenes no se guardan en la memoria (ocupan mucho); queda la nota
        if imagenes:
            contenido += f"\n(Aquí te enseñaron {'una imagen' if len(imagenes) == 1 else 'unas imágenes'}.)"
        self.historial += [{"role": "user", "content": contenido},
                           {"role": "assistant", "content": respuesta}]
        self.historial = self.historial[-self.max_historial:]
        return respuesta

    async def _conversar(self, mensajes, aviso=None, herramientas=True):
        """Pide respuesta; si el modelo quiere usar herramientas, las usa y vuelve a pedir."""
        mensajes = list(mensajes)
        for ronda in range(MAX_RONDAS + 1):
            usar = herramientas and self.internet and ronda < MAX_RONDAS
            texto, llamadas = await self._pedir(mensajes, usar)
            if not llamadas:
                return texto
            mensajes.append({"role": "assistant", "content": texto, "llamadas": llamadas})
            for llamada in llamadas:
                if aviso:
                    await aviso(internet.describir(llamada["nombre"], llamada["argumentos"]))
                resultado = await internet.usar(llamada["nombre"], llamada["argumentos"])
                mensajes.append({"role": "tool", "content": resultado, **llamada})
        return texto

    # ------------------------------------------------------------- peticiones
    async def _pedir(self, mensajes, herramientas):
        if self.api == "ollama":
            ruta, cuerpo = f"{self.base_ollama}/api/chat", self._cuerpo_ollama(mensajes, herramientas)
        else:
            ruta, cuerpo = f"{self.url}/chat/completions", self._cuerpo_openai(mensajes, herramientas)
        datos = await self._post(ruta, cuerpo)
        if self.api == "ollama":
            msg = datos.get("message", {})
        else:
            msg = datos["choices"][0]["message"]
        llamadas = []
        for n, l in enumerate(msg.get("tool_calls") or []):
            args = l["function"].get("arguments") or {}
            if isinstance(args, str):   # OpenAI lo manda como texto JSON; Ollama, como objeto
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            llamadas.append({"id": l.get("id") or f"llamada{n}", "nombre": l["function"]["name"],
                             "argumentos": args if isinstance(args, dict) else {}})
        # los modelos "razonadores" que no saben apagarlo piensan dentro de <think>
        return _PENSAMIENTO.sub("", msg.get("content") or "").strip(), llamadas

    async def _post(self, ruta, cuerpo):
        cabeceras = {"Authorization": f"Bearer {self.clave}"}
        tiempo = aiohttp.ClientTimeout(total=180)
        async with aiohttp.ClientSession(timeout=tiempo) as s:
            for _ in range(3):
                async with s.post(ruta, json=cuerpo, headers=cabeceras) as r:
                    if r.status == 200:
                        return await r.json(content_type=None)
                    error = (await r.text())[:300]
                # si el modelo no sabe pensar o no admite herramientas, se quita y se reintenta
                if r.status == 400 and "think" in error and "think" in cuerpo:
                    cuerpo.pop("think")
                elif r.status == 400 and "tools" in error and "tools" in cuerpo:
                    cuerpo.pop("tools")
                    self.internet = False
                else:
                    break
        if "image" in error.lower() or "vision" in error.lower():
            error += " (este modelo no puede ver imágenes)"
        raise RuntimeError(f"El modelo respondió {r.status}: {error}")

    def _cuerpo_ollama(self, mensajes, herramientas):
        salida = []
        for m in mensajes:
            nuevo = {"role": m["role"], "content": m["content"]}
            if m.get("imagenes"):
                nuevo["images"] = m["imagenes"]
            if m.get("llamadas"):
                nuevo["tool_calls"] = [{"function": {"name": l["nombre"], "arguments": l["argumentos"]}}
                                       for l in m["llamadas"]]
            if m["role"] == "tool":
                nuevo["tool_name"] = m["nombre"]
            salida.append(nuevo)
        cuerpo = {"model": self.modelo, "messages": salida, "stream": False,
                  "think": self.pensar, "keep_alive": self.mantener,
                  "options": {"temperature": self.temperatura, "num_predict": self.max_tokens,
                              "num_ctx": self.contexto}}
        if herramientas:
            cuerpo["tools"] = internet.HERRAMIENTAS
        return cuerpo

    def _cuerpo_openai(self, mensajes, herramientas):
        salida = []
        for m in mensajes:
            nuevo = {"role": m["role"], "content": m["content"]}
            if m.get("imagenes"):
                nuevo["content"] = [{"type": "text", "text": m["content"]}] + [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{i}"}}
                    for i in m["imagenes"]]
            if m.get("llamadas"):
                nuevo["tool_calls"] = [{"id": l["id"], "type": "function",
                                        "function": {"name": l["nombre"],
                                                     "arguments": json.dumps(l["argumentos"])}}
                                       for l in m["llamadas"]]
            if m["role"] == "tool":
                nuevo["tool_call_id"] = m["id"]
            salida.append(nuevo)
        cuerpo = {"model": self.modelo, "messages": salida, "temperature": self.temperatura,
                  "max_tokens": self.max_tokens, "stream": False}
        if herramientas:
            cuerpo["tools"] = internet.HERRAMIENTAS
        return cuerpo

    def olvidar(self):
        self.historial.clear()
