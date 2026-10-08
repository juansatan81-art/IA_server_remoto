"""Herramientas de internet para el cerebro: buscar en la web y leer una página.

No necesitan clave: la búsqueda usa la versión HTML de DuckDuckGo y, si falla,
la búsqueda de Wikipedia en español.
"""
import html
import re
from urllib.parse import parse_qs, unquote, urlparse

import aiohttp

NAVEGADOR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
             "Accept-Language": "es-ES,es;q=0.9"}
TIEMPO = aiohttp.ClientTimeout(total=15)

# Lo que el modelo ve de cada herramienta (formato de "tools" de Ollama / OpenAI)
HERRAMIENTAS = [
    {"type": "function", "function": {
        "name": "buscar_en_internet",
        "description": "Busca en internet información actual o datos que no sepas seguro "
                       "(noticias, fechas, precios, resultados, juegos, personas, el tiempo...).",
        "parameters": {"type": "object", "properties": {
            "consulta": {"type": "string", "description": "Qué buscar, en pocas palabras"}},
            "required": ["consulta"]}}},
    {"type": "function", "function": {
        "name": "leer_pagina",
        "description": "Lee el texto de una página web (por ejemplo, un resultado de la búsqueda) "
                       "cuando los resúmenes no bastan.",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string", "description": "Dirección completa de la página"}},
            "required": ["url"]}}},
]

_ETIQUETAS = re.compile(r"<[^>]+>")
_RESULTADO = re.compile(r'<a\b([^>]*class="result__a"[^>]*)>(.*?)</a>(.*?)(?=class="result__a"|$)', re.S)
_HREF = re.compile(r'href="([^"]+)"')
_RESUMEN = re.compile(r'class="result__snippet"[^>]*>(.*?)</a>', re.S)


def _texto(fragmento):
    return re.sub(r"\s+", " ", html.unescape(_ETIQUETAS.sub("", fragmento))).strip()


def _enlace_real(href):
    """DuckDuckGo envuelve los enlaces: //duckduckgo.com/l/?uddg=<url de verdad>."""
    href = html.unescape(href)
    if "uddg=" in href:
        return unquote(parse_qs(urlparse(href).query).get("uddg", [href])[0])
    return "https:" + href if href.startswith("//") else href


async def _duckduckgo(s, consulta, cuantos):
    async with s.post("https://html.duckduckgo.com/html/",
                      data={"q": consulta, "kl": "es-es"}) as r:
        pagina = await r.text()
    resultados = []
    for atributos, titulo, resto in _RESULTADO.findall(pagina):
        href = _HREF.search(atributos)
        href = href.group(1) if href else ""
        if not href or "y.js?" in href or "ad_provider" in href:   # anuncios
            continue
        resumen = _RESUMEN.search(resto)
        resultados.append({"titulo": _texto(titulo), "url": _enlace_real(href),
                           "resumen": _texto(resumen.group(1)) if resumen else ""})
        if len(resultados) >= cuantos:
            break
    return resultados


async def _wikipedia(s, consulta, cuantos):
    params = {"action": "query", "list": "search", "srsearch": consulta,
              "format": "json", "srlimit": cuantos}
    async with s.get("https://es.wikipedia.org/w/api.php", params=params) as r:
        datos = await r.json(content_type=None)
    return [{"titulo": a["title"],
             "url": "https://es.wikipedia.org/wiki/" + a["title"].replace(" ", "_"),
             "resumen": _texto(a.get("snippet", ""))}
            for a in datos.get("query", {}).get("search", [])]


async def buscar(consulta, cuantos=5):
    resultados = []
    async with aiohttp.ClientSession(timeout=TIEMPO, headers=NAVEGADOR) as s:
        for fuente in (_duckduckgo, _wikipedia):
            try:
                resultados = await fuente(s, consulta, cuantos)
            except Exception:   # sin red, bloqueado, formato cambiado... se prueba la otra
                resultados = []
            if resultados:
                break
    if not resultados:
        return "No se ha encontrado nada (o no hay conexión a internet)."
    return "\n\n".join(f"{i}. {r['titulo']}\n{r['url']}\n{r['resumen']}"
                       for i, r in enumerate(resultados, 1))


async def leer(url, maximo=3000):
    if not url.startswith(("http://", "https://")):
        return "La dirección debe empezar por http:// o https://"
    try:
        async with aiohttp.ClientSession(timeout=TIEMPO, headers=NAVEGADOR) as s:
            async with s.get(url) as r:
                if "html" not in r.headers.get("Content-Type", "html"):
                    return "Esa dirección no es una página de texto."
                pagina = await r.text(errors="replace")
    except Exception as err:
        return f"No se pudo abrir la página: {err}"
    pagina = re.sub(r"<(script|style|noscript|svg|nav|footer|header)\b.*?</\1>", " ", pagina,
                    flags=re.S | re.I)
    texto = _texto(pagina)
    return texto[:maximo] + ("…" if len(texto) > maximo else "") or "La página está vacía."


async def usar(nombre, argumentos):
    """Ejecuta la herramienta que ha pedido el modelo y devuelve el texto para él."""
    if nombre == "buscar_en_internet":
        return await buscar(str(argumentos.get("consulta", "")).strip() or "noticias de hoy")
    if nombre == "leer_pagina":
        return await leer(str(argumentos.get("url", "")).strip())
    return f"La herramienta '{nombre}' no existe."


def describir(nombre, argumentos):
    """Texto corto para el panel: qué está haciendo la IA."""
    if nombre == "buscar_en_internet":
        return f"Buscando en internet: {argumentos.get('consulta', '')}"
    if nombre == "leer_pagina":
        return f"Leyendo: {argumentos.get('url', '')}"
    return f"Usando {nombre}"
