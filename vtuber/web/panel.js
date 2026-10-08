'use strict';

const $ = (id) => document.getElementById(id);

async function api(ruta, datos = {}) {
  const r = await fetch(`/api/${ruta}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(datos),
  });
  const cuerpo = await r.text();
  let json = {};
  try { json = JSON.parse(cuerpo); } catch { json = { error: cuerpo }; }
  if (!r.ok) throw new Error(json.error || cuerpo || `Error ${r.status}`);
  return json;
}

const NOMBRES = { usuario: 'Tú', ia: 'IA', error: 'Error', sistema: 'Sistema' };
function anotar(quien, texto) {
  const div = document.createElement('div');
  div.className = `linea ${quien}`;
  const b = document.createElement('b');
  b.textContent = NOMBRES[quien] || quien;
  div.append(b, texto);
  $('registro').append(div);
  $('registro').scrollTop = $('registro').scrollHeight;
}

function formulario(form, input, boton, accion) {
  $(form).addEventListener('submit', async (e) => {
    e.preventDefault();
    const texto = $(input).value.trim();
    if (!texto && !(form === 'formChat' && adjuntos.length)) return;
    $(boton).disabled = true;
    try {
      await accion(texto);
      $(input).value = '';
    } catch (err) {
      anotar('error', err.message);
    } finally {
      $(boton).disabled = false;
      $(input).focus();
    }
  });
}

// ------------------------------------------------------------ imágenes
const MAX_LADO = 1280;   // más grande no ve mejor y tarda más
let adjuntos = [];       // data URLs en JPEG

function aJpeg(fuente, ancho, alto) {
  const k = Math.min(1, MAX_LADO / Math.max(ancho, alto));
  const c = document.createElement('canvas');
  c.width = Math.round(ancho * k);
  c.height = Math.round(alto * k);
  c.getContext('2d').drawImage(fuente, 0, 0, c.width, c.height);
  return c.toDataURL('image/jpeg', 0.85);
}

function leerImagen(archivo) {
  return new Promise((ok, mal) => {
    const img = new Image();
    img.onload = () => { ok(aJpeg(img, img.naturalWidth, img.naturalHeight)); URL.revokeObjectURL(img.src); };
    img.onerror = () => mal(new Error(`No se pudo leer ${archivo.name || 'la imagen'}`));
    img.src = URL.createObjectURL(archivo);
  });
}

function pintarAdjuntos() {
  $('adjuntos').replaceChildren(...adjuntos.map((url, i) => {
    const d = document.createElement('div');
    d.className = 'adjunto';
    const img = document.createElement('img');
    img.src = url;
    const quitar = document.createElement('button');
    quitar.type = 'button';
    quitar.textContent = '×';
    quitar.title = 'Quitar';
    quitar.onclick = () => { adjuntos.splice(i, 1); pintarAdjuntos(); };
    d.append(img, quitar);
    return d;
  }));
}

async function adjuntar(archivos) {
  for (const a of archivos) {
    if (!a.type.startsWith('image/')) continue;
    try { adjuntos.push(await leerImagen(a)); } catch (err) { anotar('error', err.message); }
  }
  pintarAdjuntos();
}

$('adjuntar').onclick = () => $('archivo').click();
$('archivo').onchange = (e) => { adjuntar([...e.target.files]); e.target.value = ''; };
$('chat').addEventListener('paste', (e) => {
  const imgs = [...e.clipboardData.files].filter((f) => f.type.startsWith('image/'));
  if (imgs.length) { e.preventDefault(); adjuntar(imgs); }
});

// pantalla compartida: se captura un fotograma en el momento de enviar
const video = $('pantalla');
let flujo = null;

function capturaPantalla() {
  if (!flujo || !video.videoWidth) return null;
  return aJpeg(video, video.videoWidth, video.videoHeight);
}

function dejarDeCompartir() {
  if (flujo) flujo.getTracks().forEach((t) => t.stop());
  flujo = null;
  video.srcObject = null;
  video.classList.remove('activa');
  $('compartir').textContent = 'Compartir pantalla';
  $('comentar').disabled = true;
}

$('compartir').onclick = async () => {
  if (flujo) return dejarDeCompartir();
  try {
    flujo = await navigator.mediaDevices.getDisplayMedia({ video: { frameRate: 5 }, audio: false });
  } catch (err) {
    if (err.name !== 'NotAllowedError') anotar('error', `No se pudo compartir la pantalla: ${err.message}`);
    return;
  }
  flujo.getVideoTracks()[0].addEventListener('ended', dejarDeCompartir);
  video.srcObject = flujo;
  await video.play().catch(() => {});
  video.classList.add('activa');
  $('compartir').textContent = 'Dejar de compartir';
  $('comentar').disabled = false;
};

async function enviarChat(mensaje) {
  const imagenes = [...adjuntos];
  const captura = capturaPantalla();
  if (captura) imagenes.push(captura);
  await api('chat', { mensaje, imagenes });
  adjuntos = [];
  pintarAdjuntos();
}

$('comentar').onclick = async () => {
  $('comentar').disabled = true;
  try {
    await enviarChat('Esto es lo que se ve ahora mismo en mi pantalla. ¿Qué ves? Coméntalo.');
  } catch (err) {
    anotar('error', err.message);
  } finally {
    $('comentar').disabled = !flujo;
  }
};

// los mensajes de la charla llegan por el socket (también los de otros programas)
formulario('formChat', 'chat', 'enviarChat', enviarChat);
formulario('formDecir', 'decir', 'enviarDecir', (t) => api('decir', { texto: t }));
$('parar').onclick = () => api('parar').catch((e) => anotar('error', e.message));
$('olvidar').onclick = () => api('olvidar').catch((e) => anotar('error', e.message));

document.querySelectorAll('[data-cabeza]').forEach((b) => {
  const [x, y, inclinacion] = b.dataset.cabeza.split(',').map(Number);
  b.onclick = () => api('cabeza', { x, y, inclinacion });
});

async function cargarEstado() {
  try {
    const e = await (await fetch('/api/estado')).json();
    $('estado').textContent =
      `Cerebro: ${e.cerebro.modelo} (${e.cerebro.url})${e.cerebro.internet ? ' · con internet' : ''} · Voz: ${e.voz} · Avatares conectados: ${e.avatares_conectados}`;
    if (!$('emociones').children.length) {
      for (const nombre of e.emociones) {
        const b = document.createElement('button');
        b.textContent = nombre;
        b.onclick = () => api('emocion', { nombre }).catch((err) => anotar('error', err.message));
        $('emociones').append(b);
      }
    }
  } catch {
    $('estado').textContent = 'Sin conexión con el servidor';
  }
}

function conectar() {
  const esquema = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${esquema}://${location.host}/ws?rol=panel`);
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    if (m.tipo === 'registro') anotar(m.quien, m.texto);
    if (m.tipo === 'estado_avatar') {
      $('emocionActual').textContent = m.emocion;
      $('diciendo').textContent = m.texto ? `— «${m.texto}»` : '';
    }
  };
  ws.onopen = cargarEstado;
  ws.onclose = () => { $('estado').textContent = 'Reconectando…'; setTimeout(conectar, 1500); };
}

// sonido de la vista previa (se recuerda en este navegador)
const casilla = $('sonidoVista');
try { casilla.checked = localStorage.getItem('sonidoVista') !== 'no'; } catch { /* sin almacenamiento */ }
function aplicarSonido() {
  try { localStorage.setItem('sonidoVista', casilla.checked ? 'si' : 'no'); } catch { /* da igual */ }
  const v = $('vista').contentWindow;
  if (v && v.avatar) v.avatar.silenciar(!casilla.checked);
}
casilla.addEventListener('change', aplicarSonido);
$('vista').addEventListener('load', () => setTimeout(aplicarSonido, 500));

conectar();
setInterval(cargarEstado, 5000);
