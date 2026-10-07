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
    if (!texto) return;
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

// los mensajes de la charla llegan por el socket (también los de otros programas)
formulario('formChat', 'chat', 'enviarChat', (t) => api('chat', { mensaje: t }));
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
      `Cerebro: ${e.cerebro.modelo} (${e.cerebro.url}) · Voz: ${e.voz} · Avatares conectados: ${e.avatares_conectados}`;
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
  };
  ws.onopen = cargarEstado;
  ws.onclose = () => { $('estado').textContent = 'Reconectando…'; setTimeout(conectar, 1500); };
}

conectar();
setInterval(cargarEstado, 5000);
