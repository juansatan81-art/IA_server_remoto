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

const NOMBRES = { usuario: 'Chat / tú', ia: 'IA', error: 'Error', sistema: 'Sistema',
  pensamiento: 'Piensa (no se oye)', filtro: 'Filtro' };
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
      `Cerebro: ${e.cerebro.modelo} (${e.cerebro.url})${e.cerebro.internet ? ' · con internet' : ''}`
      + ` · Filtros: ${e.ayudante ? `reglas + ${e.ayudante}` : 'solo reglas'}`
      + ` · Voz: ${e.voz} · Avatares conectados: ${e.avatares_conectados}`;
    pintarDirecto(e.directo, e.youtube);
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
    if (m.tipo === 'glosario') cargarGlosario();
    if (m.tipo === 'estado_avatar') {
      $('emocionActual').textContent = m.emocion;
      $('diciendo').textContent = m.texto ? `— «${m.texto}»` : '';
    }
  };
  ws.onopen = () => { cargarEstado(); cargarGlosario(); };
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

// ------------------------------------------------------------ modo directo
let directoActivo = false;

function pintarDirecto(d, yt) {
  directoActivo = d.activo;
  $('iniciarDirecto').disabled = d.activo;
  $('terminarDirecto').disabled = !d.activo;
  const el = $('estadoDirecto');
  if (d.activo) {
    el.innerHTML = '';
    const b = document.createElement('b');
    b.className = 'encendido';
    b.textContent = `● En directo (${d.minutos} min)`;
    el.append(b, ` · En cola: ${d.en_cola} · Ignorados por el filtro: ${d.ignorados} · ${d.animo}`
      + (d.viendo_pantalla ? ' · Viendo tu pantalla' : ''));
  } else {
    el.textContent = 'Apagado. Con el directo encendido, Lara elige a quién responder del chat y habla sola cuando el chat está tranquilo.';
  }
  $('ytEstado').textContent = yt.configurado ? `YouTube: ${yt.estado}`
    : 'YouTube: falta la clave de la API en config.local.json (mira el README).';
}

$('iniciarDirecto').onclick = async () => {
  try {
    await api('directo/iniciar', { plan: $('plan').value, video: $('ytVideo').value });
    cargarEstado();
  } catch (err) { anotar('error', err.message); }
};
$('terminarDirecto').onclick = async () => {
  $('terminarDirecto').disabled = true;
  $('bots').checked = false;
  try { await api('directo/terminar'); } catch (err) { anotar('error', err.message); }
  cargarEstado();
};
$('panico').onclick = () => api('directo/panico').catch((e) => anotar('error', e.message));

formulario('formSimular', 'simTexto', 'enviarSimular', async (texto) => {
  const tipo = $('simTipo').value;
  await api('directo/chat', {
    autor: $('simAutor').value.trim() || 'Espectador', texto, tipo,
    cantidad: tipo === 'superchat' ? '5,00 €' : '',
  });
});

$('formYoutube').addEventListener('submit', async (e) => {
  e.preventDefault();
  try { await api('youtube/conectar', { video: $('ytVideo').value }); } catch (err) { anotar('error', err.message); }
  cargarEstado();
});
$('ytDesconectar').onclick = async () => {
  try { await api('youtube/desconectar'); } catch (err) { anotar('error', err.message); }
  cargarEstado();
};

// espectadores de mentira para probar cómo elige a quién responder
const BOTS = ['Pablo', 'Marta_gamer', 'xXDarkXx', 'Lucía', 'Andrés', 'NoobMaster', 'Sofi', 'Kevin2009'];
const FRASES = ['hola Lara!!', '¿Qué juego vas a jugar hoy?', 'jajaja', 'Lara, ¿cuál es tu comida favorita?',
  'primera vez que vengo, saludos desde México', 'me encanta tu voz', 'xd', '¿Sabes qué es un agujero negro?',
  'Lara ¿te gusta Minecraft?', 'buenas noches a todos', 'qué guapa estás hoy', '¿Cuántos años tienes?',
  'hoy tengo examen de mates 😭', 'saludos!!', '¿Lara puedes cantar algo?', 'gg'];
setInterval(() => {
  if (!$('bots').checked || !directoActivo) return;
  const n = 1 + Math.floor(Math.random() * 3);
  for (let i = 0; i < n; i++) {
    api('directo/chat', {
      autor: BOTS[Math.floor(Math.random() * BOTS.length)],
      texto: FRASES[Math.floor(Math.random() * FRASES.length)],
    }).catch(() => {});
  }
}, 6000);

// con el directo encendido y la pantalla compartida, Lara ve una captura cada 8 s
setInterval(() => {
  if (!directoActivo) return;
  const captura = capturaPantalla();
  if (captura) api('directo/vista', { imagen: captura }).catch(() => {});
}, 8000);

// ------------------------------------------------------------ glosario
function boton(texto, accion, clase = '') {
  const b = document.createElement('button');
  b.type = 'button';
  b.textContent = texto;
  if (clase) b.className = clase;
  b.onclick = async () => {
    b.disabled = true;
    try { await accion(); await cargarGlosario(); } catch (err) { anotar('error', err.message); b.disabled = false; }
  };
  return b;
}

async function cargarGlosario() {
  let terminos = [];
  try { terminos = (await (await fetch('/api/glosario')).json()).terminos; } catch { return; }
  const pendientes = terminos.filter((t) => t.estado === 'pendiente');
  const aprobados = terminos.filter((t) => t.estado === 'aprobado');
  $('pendientes').replaceChildren(...pendientes.map((t) => {
    const d = document.createElement('div');
    d.className = 'termino';
    const titulo = document.createElement('b');
    titulo.textContent = `${t.termino} (pendiente)`;
    const fuente = document.createElement('small');
    fuente.textContent = t.fuente || '';
    const texto = document.createElement('textarea');
    texto.value = t.significado;
    const fila = document.createElement('div');
    fila.className = 'fila';
    fila.append(
      boton('Aprobar', () => api('glosario', { termino: t.termino, significado: texto.value, estado: 'aprobado' }), 'principal'),
      boton('Rechazar', () => api('glosario', { termino: t.termino, estado: 'rechazado' })),
    );
    d.append(titulo, fuente, texto, fila);
    return d;
  }));
  $('resumenAprobados').textContent = `Aprobados (${aprobados.length})`;
  $('aprobados').replaceChildren(...aprobados.map((t) => {
    const d = document.createElement('div');
    d.className = 'aprobado';
    const span = document.createElement('span');
    const b = document.createElement('b');
    b.textContent = t.termino;
    span.append(b, `: ${t.significado}`);
    d.append(span, boton('Quitar', () => api('glosario/borrar', { termino: t.termino })));
    return d;
  }));
}

formulario('formTermino', 'nuevoTermino', 'anadirTermino', async (termino) => {
  await api('glosario', { termino, significado: $('nuevoSignificado').value, estado: 'aprobado' });
  $('nuevoSignificado').value = '';
  await cargarGlosario();
});

conectar();
setInterval(cargarEstado, 3000);
