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
function anotar(quien, texto, id) {
  const div = document.createElement('div');
  div.className = `linea ${quien}`;
  const b = document.createElement('b');
  b.textContent = NOMBRES[quien] || quien;
  div.append(b, texto);
  if (id) div.append(botonesValorar(id));
  $('registro').append(div);
  $('registro').scrollTop = $('registro').scrollHeight;
}

// 👍 = así habla Lara (sirve para el entrenamiento) · 👎 = así no. Otro clic en el mismo, lo quita.
function botonesValorar(id) {
  const caja = document.createElement('span');
  caja.className = 'valorar';
  for (const [valor, icono, titulo] of [[1, '👍', 'Así habla Lara'], [-1, '👎', 'Así no']]) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.textContent = icono;
    btn.title = titulo;
    btn.onclick = async () => {
      const nuevo = btn.classList.contains('elegido') ? 0 : valor;
      try {
        const r = await api('valorar', { id, valor: nuevo });
        caja.querySelectorAll('button').forEach((x) => x.classList.remove('elegido'));
        if (nuevo) btn.classList.add('elegido');
        $('cuentaValoradas').textContent = `👍 ${r.buenas} · 👎 ${r.malas}`;
      } catch (err) {
        anotar('error', `No se pudo guardar la valoración: ${err.message}`);
      }
    };
    caja.append(btn);
  }
  return caja;
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
    pintarSemaforos(e);
    if (e.valoradas) $('cuentaValoradas').textContent = `👍 ${e.valoradas.buenas} · 👎 ${e.valoradas.malas}`;
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
    pintarSemaforos(null);
  }
}

// semáforos de la barra de arriba: verde = bien, ámbar = funciona a medias, rojo = falla
function luz(id, color, texto, detalle) {
  const el = $(id);
  el.className = `luz ${color}`;
  el.textContent = texto;
  el.title = detalle;
}

function pintarSemaforos(e) {
  if (!e) {
    for (const id of ['luzIa', 'luzVoz', 'luzObs', 'luzYt']) luz(id, 'rojo', $(id).textContent.split(':')[0], 'Sin conexión con el servidor: ¿está abierta la ventana negra de iniciar.bat?');
    return;
  }
  luz('luzIa', e.ia.ok ? 'verde' : 'rojo', e.ia.ok ? 'IA lista' : 'IA: falla', e.ia.detalle);
  const fish = e.voz.startsWith('Fish');
  const voces = {
    fish: ['verde', 'Voz: Fish', 'La última frase salió con la voz de Fish.'],
    respaldo: ['ambar', 'Voz: respaldo', 'Fish no respondió y la última frase salió con la voz de respaldo (Ximena).'],
    edge: ['verde', 'Voz lista', 'Voz de Microsoft (edge-tts).'],
    error: ['rojo', 'Voz: falla', 'La última frase no tuvo voz. Mira el registro de la conversación.'],
  };
  const [c, txt, det] = voces[e.voz_ultima] || ['verde', fish ? 'Voz: Fish' : 'Voz lista', `Aún no ha hablado. Voz: ${e.voz}.`];
  luz('luzVoz', c, txt, det);
  luz('luzObs', e.obs > 0 ? 'verde' : '', e.obs > 0 ? 'OBS conectado' : 'OBS: no',
    e.obs > 0 ? `Avatar abierto fuera del panel (${e.obs}).` : 'Ningún OBS u otra pestaña tiene abierto /avatar.');
  const yt = e.youtube || {};
  luz('luzYt', !yt.configurado ? '' : /conectad|leyendo|escuch/i.test(yt.estado || '') ? 'verde' : 'ambar',
    !yt.configurado ? 'YouTube: sin clave' : 'YouTube', yt.configurado ? (yt.estado || '') : 'Falta la clave de la API en config.local.json.');
}

// pestañas (se recuerda la última abierta)
function abrirPestana(nombre) {
  document.querySelectorAll('nav [data-pestana]').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.pestana === nombre)));
  document.querySelectorAll('.pestana').forEach((p) => { p.hidden = p.id !== `pestana-${nombre}`; });
  try { localStorage.setItem('pestanaPanel', nombre); } catch {}
}
document.querySelectorAll('nav [data-pestana]').forEach((b) => { b.onclick = () => abrirPestana(b.dataset.pestana); });
try { const guardada = localStorage.getItem('pestanaPanel'); if (guardada) abrirPestana(guardada); } catch {}

function conectar() {
  const esquema = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${esquema}://${location.host}/ws?rol=panel`);
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    if (m.tipo === 'registro') anotar(m.quien, m.texto, m.id);
    if (m.tipo === 'glosario') cargarGlosario();
    if (m.tipo === 'juego') pintarJuego(m);
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
const BOTS = ['Pablo', 'Marta_gamer', 'xXDarkXx', 'Lucía', 'Andrés', 'NoobMaster', 'Sofi', 'Kevin2009',
  'VenezolanoRandom7', 'ElCapibaraFeliz', 'Dani_MX', 'NoSoyUnBot', 'Valeria.art', 'Toño_04', 'GatoConSueño', 'Ari'];
// Las de abajo están inspiradas en los comentarios reales del canal (octubre 2026): saludos,
// ánimos, bromas cortas, la voz, Xiaro (en broma y en serio) y peticiones de temas.
const FRASES = ['hola Lara!!', '¿Qué juego vas a jugar hoy?', 'jajaja', 'Lara, ¿cuál es tu comida favorita?',
  'primera vez que vengo, saludos desde México', 'me encanta tu voz', 'xd', '¿Sabes qué es un agujero negro?',
  'Lara ¿te gusta Minecraft?', 'buenas noches a todos', 'qué guapa estás hoy', '¿Cuántos años tienes?',
  'hoy tengo examen de mates 😭', 'saludos!!', '¿Lara puedes cantar algo?', 'gg',
  'llegué temprano 🗣️', 'seee', 'que onda Lara', '¿De qué país eres?', 'saludos desde Venezuela 🇻🇪',
  'pan con café ☕', 'XD', 'chat, ¿la apoyamos? 🔥', 'le veo potencial al canal, sigue así',
  'buen vídeo el de los hongos, genia', '¿tu voz es real o es inteligencia artificial?',
  '¿por qué tienes la voz de Alya?', 'eres Xiaro', 'la versión buena de Xiaro jaja',
  'te pareces mucho a Xiaro, ¿por qué?', 'Lara, ¿te gusta la astronomía? a mí me encanta el espacio',
  'haz un vídeo de Cicada 3301 porfa', '¿qué opinas de los hongos zombi?', 'que ganas de comer un capibara jsjs',
  'perfecto para poner mientras descanso', 'quiero que seas famosa', 'ya me suscribí, ojalá te vaya bien',
  '¿eres una persona o una IA?', '¿quién te creó?', 'me espanté con lo de la hormiga 😰', 'ono :v',
  'yo me uniría como miembro pero no hay money 😢', '¿cuál es tu libro favorito?', 'hola desde España',
  'Lara, ¿qué es lo que más te gusta hacer?', 'jsjsjs', '¿cada cuánto subes vídeos?', 'te amo Lara ❤',
  '¿te puedo hacer un fanart?', 'la edición de tus vídeos es cine'];
// En cada tanda escriben personas DISTINTAS, y cada una espera al menos 25 s antes de
// volver a escribir (antes un mismo bot soltaba varias frases sin relación seguidas y
// Lara las recibía pegadas en un solo mensaje).
const ultimoBot = {};
setInterval(() => {
  if (!$('bots').checked || !directoActivo) return;
  const ahora = Date.now();
  const libres = BOTS.filter((b) => ahora - (ultimoBot[b] || 0) > 25000).sort(() => Math.random() - 0.5);
  const n = Math.min(libres.length, 1 + Math.floor(Math.random() * 3));
  for (const autor of libres.slice(0, n)) {
    ultimoBot[autor] = ahora;
    api('directo/chat', { autor, texto: FRASES[Math.floor(Math.random() * FRASES.length)] }).catch(() => {});
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

// ---------------------------------------------------------------- tres en raya
function pintarJuego(j) {
  const tablero = $('tableroPanel');
  if (!tablero.children.length) {
    for (let i = 1; i <= 9; i++) {
      const b = document.createElement('button');
      b.type = 'button';
      b.onclick = async () => {
        try { await api('juego/jugar', { casilla: i }); } catch (err) { anotar('error', `Tres en raya: ${err.message}`); }
      };
      tablero.append(b);
    }
  }
  const votando = j.quedan !== null && j.quedan !== undefined;
  const recuento = votando ? j.votos : (j.ultima_votacion ? j.ultima_votacion.votos : {});
  [...tablero.children].forEach((b, i) => {
    const ficha = j.tablero[i];
    const votos = recuento[i + 1];
    b.className = ficha;
    b.textContent = ficha || '';
    if (votos && (!ficha || (j.ultima_votacion && j.ultima_votacion.casilla === i + 1))) { const s = document.createElement('small'); s.textContent = `${votos} voto${votos > 1 ? 's' : ''}`; b.append(s); }
    b.disabled = Boolean(ficha) || !j.activo || j.turno !== 'X' || j.rival !== 'panel';
  });
  const rival = j.rival === 'chat' ? 'el chat' : 'ti';
  const fin = { O: '¡Ha ganado Lara!', X: `Ha ganado ${j.rival === 'chat' ? 'el chat' : 'tu X'}.`, empate: 'Empate.' };
  $('estadoJuego').textContent = j.resultado ? fin[j.resultado]
    : !j.activo ? 'Sin partida.'
    : j.turno === 'O' ? 'Lara está pensando su jugada…'
    : j.rival === 'chat' ? (j.quedan !== null ? `El chat está votando: quedan ${j.quedan} s.` : 'Turno del chat: esperando el primer voto (un número del 1 al 9).')
    : `Te toca a ${rival}: eres la X.`;
  $('marcadorJuego').textContent = `Lara ${j.marcador.lara} · rival ${j.marcador.rival} · empates ${j.marcador.empates}`;
}
$('urlJuego').textContent = `${location.origin}/juego`;
$('nuevoJuego').onclick = async () => {
  try { pintarJuego(await api('juego/nuevo', { rival: $('rivalJuego').value, empieza: $('empiezaJuego').value })); }
  catch (err) { anotar('error', `Tres en raya: ${err.message}`); }
};
$('terminarJuego').onclick = async () => { pintarJuego(await api('juego/terminar')); };
fetch('/api/estado').then((r) => r.json()).then((e) => e.juego && pintarJuego(e.juego)).catch(() => {});

conectar();
setInterval(cargarEstado, 3000);
