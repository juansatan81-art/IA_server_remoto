"""El "cerebro": un modelo de lenguaje local con API compatible con OpenAI.

Sirve con Ollama, LM Studio, llama.cpp (llama-server), vLLM, KoboldCpp...
Solo hay que poner su dirección en config.json -> cerebro.url
"""
import re

import aiohttp

from emociones import EMOCIONES

PLANTILLA = """Eres {nombre}, una VTuber que hace directos y charla con su público.
{personalidad}

Tienes un cuerpo de avatar 2D que tú controlas. Para cambiar tu cara escribe una etiqueta
entre corchetes justo antes de la frase. Emociones disponibles: {emociones}.
Ejemplo: [feliz] ¡Hola a todos! [pensativa] Mmm, ¿de qué hablamos hoy?

Reglas:
- Empieza SIEMPRE con una etiqueta de emoción y cámbiala cuando cambie tu emoción.
- Usa SOLO esas etiquetas, escritas exactamente así; no inventes otras.
- Respuestas cortas y habladas: 1 a 3 frases, nada de listas, código ni markdown.
- No describas acciones entre asteriscos; tu voz se genera a partir de tu texto.
- Habla SIEMPRE y SOLO en español: nunca escribas en chino, inglés ni con otros alfabetos."""

# Caracteres de chino, japonés y coreano: los modelos Qwen pequeños a veces
# cambian de idioma a mitad de frase
_OTRO_ALFABETO = re.compile("[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af\uff00-\uffef]")
_RECORDATORIO = ("Tu respuesta anterior mezclaba otro idioma. Repite la respuesta entera "
                 "solo en español, con la misma etiqueta de emoción al principio.")


class Cerebro:
    def __init__(self, cfg, personaje):
        self.url = cfg.get("url", "http://localhost:11434/v1").rstrip("/")
        self.modelo = cfg.get("modelo", "qwen2.5:7b")
        self.clave = cfg.get("api_key", "local")
        self.temperatura = cfg.get("temperatura", 0.8)
        self.max_tokens = cfg.get("max_tokens", 300)
        self.max_historial = cfg.get("historial", 20)
        self.sistema = cfg.get("prompt_sistema") or PLANTILLA.format(
            nombre=personaje.get("nombre", "la VTuber"),
            personalidad=personaje.get("personalidad", ""),
            emociones=", ".join(EMOCIONES),
        )
        self.historial = []

    async def responder(self, mensaje, usuario=None):
        contenido = f"{usuario}: {mensaje}" if usuario else mensaje
        mensajes = [{"role": "system", "content": self.sistema},
                    *self.historial,
                    {"role": "user", "content": contenido}]
        respuesta = await self._pedir(mensajes)
        # si se ha colado otro idioma, se le pide una vez que lo repita en español
        if _OTRO_ALFABETO.search(respuesta):
            respuesta = await self._pedir(mensajes + [{"role": "assistant", "content": respuesta},
                                                      {"role": "user", "content": _RECORDATORIO}])
        # y si aún así queda algo, se corta ahí: mejor una frase más corta que oírla en chino
        corte = _OTRO_ALFABETO.search(respuesta)
        if corte:
            respuesta = respuesta[:corte.start()].rstrip(" ,;:-") or "[avergonzada] Perdón, me he liado."
            if respuesta[-1] not in ".!?…":
                respuesta += "…"

        self.historial += [{"role": "user", "content": contenido},
                           {"role": "assistant", "content": respuesta}]
        self.historial = self.historial[-self.max_historial:]
        return respuesta

    async def _pedir(self, mensajes):
        cuerpo = {
            "model": self.modelo,
            "messages": mensajes,
            "temperature": self.temperatura,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        cabeceras = {"Authorization": f"Bearer {self.clave}"}
        tiempo = aiohttp.ClientTimeout(total=180)
        async with aiohttp.ClientSession(timeout=tiempo) as s:
            async with s.post(f"{self.url}/chat/completions", json=cuerpo, headers=cabeceras) as r:
                if r.status != 200:
                    raise RuntimeError(f"El modelo respondió {r.status}: {(await r.text())[:300]}")
                datos = await r.json()
        respuesta = datos["choices"][0]["message"]["content"] or ""
        # los modelos "razonadores" (qwen3, deepseek-r1...) piensan dentro de <think>
        return re.sub(r"<think>.*?</think>", "", respuesta, flags=re.S | re.I).strip()

    def olvidar(self):
        self.historial.clear()
