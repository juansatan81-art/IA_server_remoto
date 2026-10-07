'use strict';
/*
 * Avatar 2D animado.
 *
 * La ilustración está separada en tres capas (pelo, cuerpo, cara). La cabeza
 * se mueve con una transformación (desplazamiento + inclinación) y el pelo
 * largo se dibuja por franjas horizontales que se desplazan cada una un poco
 * distinto: así se dobla sin cortes y se balancea con retraso.
 * Ojos, cejas, boca y efectos se dibujan en vectorial encima.
 */

const W = 1254, H = 1200;
const CUELLO_Y = 760;   // pivote de la inclinación de la cabeza
const CORTE = 756;      // por encima todo se mueve con la cabeza
const EJE = 631.5;      // eje de simetría de la cara
const FRANJA = 2;

const lienzo = document.getElementById('lienzo');
const ctx = lienzo.getContext('2d');
const parametros = new URLSearchParams(location.search);

// ---------------------------------------------------------------- emociones
const NEUTRAL = {
  lidOut: 0, lidIn: 0,        // cuánto bajan los párpados (borde exterior / interior)
  feliz: 0,                   // ojos en ^ ^
  redondo: 0,                 // ojos redondos (sorpresa)
  brillo: 0,                  // reflejos blancos en los ojos
  cejaVis: 0, cejaY: 0, cejaAng: 0, cejaAsim: 0,
  curva: 1, ancho: 1, asim: 0, redonda: 0, abierta: 0, dientes: 0,
  rubor: 0, lagrimas: 0, enojo: 0, sudor: 0, chispas: 0,
  inclinacion: 0, cabezaY: 0,
  miradaX: 0, miradaY: 0, miradaFija: 0,
};

const EXPRESIONES = {
  neutral: {},
  feliz: { feliz: 1, curva: 1.25, ancho: 1.15, abierta: 0.3, dientes: 1, chispas: 1,
    rubor: 0.35, cejaVis: 0.8, cejaY: -12, cejaAng: -6 },
  enojada: { lidIn: 48, lidOut: 4, cejaVis: 1, cejaY: 10, cejaAng: 26, curva: -0.7,
    ancho: 0.85, enojo: 1, cabezaY: 4 },
  triste: { lidOut: 34, lidIn: 6, brillo: 1, cejaVis: 1, cejaAng: -22, curva: -0.8,
    ancho: 0.8, cabezaY: 10, inclinacion: 0.02, miradaY: 0.6, miradaFija: 0.6 },
  llorando: { lidOut: 38, lidIn: 8, brillo: 1, cejaVis: 1, cejaAng: -26, curva: -1,
    ancho: 0.9, abierta: 0.25, lagrimas: 1, cabezaY: 12, inclinacion: 0.015 },
  sorprendida: { redondo: 1, brillo: 1, cejaVis: 1, cejaY: -24, redonda: 1,
    abierta: 0.35, cabezaY: -6 },
  avergonzada: { lidOut: 22, lidIn: 22, rubor: 1, sudor: 1, curva: 0.35, ancho: 0.65,
    asim: -0.4, cejaVis: 0.9, cejaAng: -14, brillo: 0.6, miradaX: -1, miradaY: 0.5,
    miradaFija: 1, inclinacion: -0.02 },
  presumida: { lidOut: 36, lidIn: 26, curva: 1, asim: 1, cejaVis: 1, cejaY: -4,
    cejaAsim: 16, inclinacion: -0.018 },
  pensativa: { lidOut: 14, lidIn: 8, curva: 0.1, ancho: 0.6, asim: 0.5, cejaVis: 0.9,
    cejaAsim: 12, miradaX: 0.9, miradaY: -0.9, miradaFija: 1, inclinacion: 0.025 },
};

const actual = { ...NEUTRAL };
let objetivo = { ...NEUTRAL };
let emocion = 'neutral';
let volverANeutral = 0;   // instante (s) en el que vuelve a neutral; 0 = nunca

// ---------------------------------------------------------------- estado de animación
let t = 0;
const anim = {
  parpadeo: -1, proximoParpadeo: 2,
  mirada: { x: 0, y: 0 }, miradaObj: { x: 0, y: 0 }, proximaMirada: 1,
  pelo: 0, peloV: 0,
  cuerpo: { x: 0, vx: 0, y: 0, vy: 0, incl: 0 },   // el torso sigue a la cabeza con retraso
  impulso: null,
  apertura: 0,
  cabeza: { x: 0, y: 0, incl: 0 }, cabezaObj: { x: 0, y: 0, incl: 0 },   // postura pedida desde fuera
};
const lagrimas = [];

function forma(e) {
  return e.feliz > 0.5 ? 'feliz' : e.redondo > 0.5 ? 'redondo' : 'normal';
}

function ponerEmocion(nombre, duracion = 0) {
  const e = EXPRESIONES[nombre];
  if (!e) return false;
  const antes = forma(objetivo);
  objetivo = { ...NEUTRAL, ...e };
  if (forma(objetivo) !== antes) anim.parpadeo = t;   // el parpadeo oculta el cambio de forma
  if (nombre !== emocion) anim.impulso = { tipo: nombre, inicio: t };
  emocion = nombre;
  volverANeutral = duracion > 0 ? t + duracion : 0;
  return true;
}

// ---------------------------------------------------------------- utilidades
const lerp = (a, b, k) => a + (b - a) * k;
const limitar = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const suave = (a, b, x) => { const k = limitar((x - a) / (b - a)); return k * k * (3 - 2 * k); };
const azar = (a, b) => a + Math.random() * (b - a);

function cargarImagen(src) {
  return new Promise((ok, mal) => {
    const i = new Image();
    i.onload = () => ok(i);
    i.onerror = mal;
    i.src = src;
  });
}

// ---------------------------------------------------------------- actualización
function actualizar(dt) {
  const k = 1 - Math.exp(-dt * 9);
  for (const c in actual) actual[c] = lerp(actual[c], objetivo[c], k);

  if (volverANeutral && t >= volverANeutral && !hablando()) ponerEmocion('neutral');

  // parpadeo automático
  if (t >= anim.proximoParpadeo) {
    anim.parpadeo = t;
    anim.proximoParpadeo = t + (Math.random() < 0.15 ? 0.25 : azar(2, 5.5));
  }

  // mirada: pequeños saltos aleatorios, salvo que la emoción la fije
  if (t >= anim.proximaMirada) {
    anim.miradaObj = { x: azar(-0.7, 0.7), y: azar(-0.4, 0.4) };
    if (Math.random() < 0.4) anim.miradaObj = { x: 0, y: 0 };
    anim.proximaMirada = t + azar(1.2, 4);
  }
  const fija = actual.miradaFija;
  const mx = lerp(anim.miradaObj.x, actual.miradaX, fija);
  const my = lerp(anim.miradaObj.y, actual.miradaY, fija);
  const km = 1 - Math.exp(-dt * 14);
  anim.mirada.x = lerp(anim.mirada.x, mx, km);
  anim.mirada.y = lerp(anim.mirada.y, my, km);

  // boca: volumen del audio
  const nivel = nivelAudio();
  const ka = 1 - Math.exp(-dt * (nivel > anim.apertura ? 28 : 14));
  anim.apertura = lerp(anim.apertura, nivel, ka);

  const kc = 1 - Math.exp(-dt * 5);
  for (const c of ['x', 'y', 'incl']) anim.cabeza[c] = lerp(anim.cabeza[c], anim.cabezaObj[c], kc);

  // lágrimas
  if (actual.lagrimas > 0.3 && Math.random() < dt * 3.5 * actual.lagrimas) {
    const lado = Math.random() < 0.5 ? 1 : -1;
    lagrimas.push({ lado, x: azar(432, 452), y: 596, v: azar(20, 50), r: azar(7, 11) });
  }
  for (const l of lagrimas) { l.v += 260 * dt; l.y += l.v * dt; l.x -= 8 * dt; }
  while (lagrimas.length && lagrimas[0].y > 760) lagrimas.shift();
}

function postura() {
  const respira = Math.sin(t * Math.PI * 2 / 3.6);
  let x = 7 * Math.sin(t * 0.53) + 4 * Math.sin(t * 1.31 + 1);
  let y = 3 * Math.sin(t * 0.9 + 2) - respira * 2.5 + actual.cabezaY;
  let incl = 0.012 * Math.sin(t * 0.41) + 0.006 * Math.sin(t * 1.7) + actual.inclinacion;

  x += anim.cabeza.x; y += anim.cabeza.y; incl += anim.cabeza.incl;

  // al hablar asiente un poco
  y += anim.apertura * 5;
  incl += 0.008 * Math.sin(t * 2.7) * limitar(anim.apertura * 3);

  // sollozos
  y += 3.5 * Math.max(0, Math.sin(t * 7)) * actual.lagrimas;

  const imp = anim.impulso;
  if (imp) {
    const d = t - imp.inicio;
    if (imp.tipo === 'feliz') y -= Math.abs(Math.sin(d * 9)) * 10 * Math.exp(-d * 2);
    if (imp.tipo === 'enojada') x += Math.sin(d * 45) * 7 * Math.exp(-d * 3);
    if (imp.tipo === 'sorprendida') y -= 16 * Math.exp(-d * 5) * Math.min(1, d * 12);
    if (imp.tipo === 'avergonzada') x -= 10 * Math.exp(-d * 2) * Math.min(1, d * 6);
    if (d > 3) anim.impulso = null;
  }

  // muelle del pelo: sigue a la cabeza con retraso
  return { x, y, incl, respira };
}

function moverPelo(cabezaX, dt) {
  const fuerza = (cabezaX - anim.pelo) * 55 - anim.peloV * 5;
  anim.peloV += fuerza * dt;
  anim.pelo += anim.peloV * dt;
}

// La cabeza "arrastra" al cuerpo: un muelle más lento y pesado que el del pelo.
function moverCuerpo(p, dt) {
  const c = anim.cuerpo;
  c.vx += ((p.x - c.x) * 18 - c.vx * 6) * dt;
  c.x += c.vx * dt;
  c.vy += ((p.y - c.y) * 22 - c.vy * 7) * dt;
  c.y += c.vy * dt;
  c.incl = lerp(c.incl, p.incl, 1 - Math.exp(-dt * 3));
}

// ---------------------------------------------------------------- dibujo
let capas = null;

function transformarCabeza(p) {
  ctx.translate(p.x, p.y);
  ctx.transform(1, 0, -p.incl, 1, p.incl * CUELLO_Y, 0);
}

function dibujarPelo(p) {
  // parte alta: rígida con la cabeza
  ctx.save();
  transformarCabeza(p);
  // 2 px de solape con las franjas para que no quede una rendija
  ctx.drawImage(capas.pelo, 0, 0, W, CORTE + 2, 0, 0, W, CORTE + 2);
  ctx.restore();
  // parte baja: franjas que se doblan y se balancean
  for (let y = CORTE; y < H; y += FRANJA) {
    const m = y + FRANJA / 2;
    const libre = suave(CORTE, H, m);
    const peso = 1 - libre * 0.88;
    const viento = 2.5 * Math.sin(t * 1.3 - m * 0.012);
    const dx = p.x * peso + (anim.pelo - p.x) * libre * 1.3 + viento * libre;
    const dy = p.y * peso;
    ctx.drawImage(capas.pelo, 0, y, W, FRANJA, dx, y + dy, W, FRANJA + 1);
  }
}

// El torso se dibuja por franjas: arriba (hombros) sigue mucho a la cabeza y
// abajo casi nada, así se dobla como una columna en vez de moverse en bloque.
const CUERPO_ARRIBA = 742;
function dibujarCuerpo(p) {
  const c = anim.cuerpo;
  const crecer = p.respira * 0.006;           // respiración: se estira desde abajo
  for (let y = CUERPO_ARRIBA; y < H; y += FRANJA) {
    const m = y + FRANJA / 2;
    const abajo = suave(CUERPO_ARRIBA, H, m);
    const peso = lerp(0.7, 0.06, abajo);
    const dx = c.x * peso + c.incl * (H - m) * 0.35;
    const dy = c.y * peso * 0.8 - (H - m) * crecer;
    ctx.drawImage(capas.cuerpo, 0, y, W, FRANJA, dx, y + dy, W, FRANJA + 1);
  }
}

function trazo(ancho, color = '#000') {
  ctx.lineWidth = ancho;
  ctx.strokeStyle = color;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
}

// Ojo izquierdo; el derecho se dibuja reflejado.
function dibujarOjo(lado, parpadeo) {
  const a = actual;
  const gx = anim.mirada.x * lado, gy = anim.mirada.y;
  ctx.save();
  if (lado < 0) { ctx.translate(2 * EJE, 0); ctx.scale(-1, 1); }

  // línea de la cuenca (el arco fino de fuera)
  const arco = 1 - Math.max(a.feliz, a.redondo);
  if (arco > 0.02) {
    ctx.globalAlpha = arco;
    trazo(7);
    ctx.beginPath();
    ctx.ellipse(490, 470, 135, 122, 0, Math.PI * 0.56, Math.PI * 0.985);
    ctx.stroke();
    ctx.globalAlpha = 1;
  }

  if (a.feliz > 0.5) {
    // ^ ^
    trazo(13);
    ctx.beginPath();
    ctx.ellipse(490, 560 + gy * 4, 84, 66, 0, Math.PI * 1.1, Math.PI * 1.9);
    ctx.stroke();
  } else if (a.redondo > 0.5) {
    const cx = 490 + gx * 10, cy = 512 + gy * 8;
    const ry = 72 * Math.max(0.08, 1 - parpadeo);
    ctx.fillStyle = '#000';
    ctx.beginPath();
    ctx.ellipse(cx, cy, 66, ry, 0, 0, Math.PI * 2);
    ctx.fill();
    if (parpadeo < 0.5) reflejos(cx, cy, a.brillo, gx, gy);
  } else {
    const cx = 490 + gx * 6, cy = 482 + gy * 3;
    const cierre = parpadeo;
    const yOut = lerp(456 + a.lidOut, 584, cierre);
    const yIn = lerp(468 + a.lidIn, 584, cierre);
    ctx.save();
    ctx.beginPath();
    ctx.ellipse(cx, cy, 113, 110, 0, 0, Math.PI * 2);
    ctx.clip();
    ctx.beginPath();
    // la línea del párpado va de (377, yOut) a (603, yIn); se prolonga un poco
    const pend = (yIn - yOut) / 226;
    ctx.moveTo(360, yOut - 17 * pend);
    ctx.lineTo(620, yIn + 17 * pend);
    ctx.lineTo(620, 620);
    ctx.lineTo(360, 620);
    ctx.closePath();
    ctx.fillStyle = '#000';
    ctx.fill();
    if (a.brillo > 0.03 && cierre < 0.5) {
      ctx.clip();
      reflejos(cx, Math.max(cy + 20, (yOut + yIn) / 2 + 40), a.brillo, gx, gy);
    }
    ctx.restore();
  }
  ctx.restore();
}

function reflejos(cx, cy, fuerza, gx, gy) {
  ctx.globalAlpha = limitar(fuerza);
  ctx.fillStyle = '#fff';
  ctx.beginPath();
  ctx.ellipse(cx - 28 + gx * 8, cy - 18 + gy * 6, 20, 16, -0.4, 0, Math.PI * 2);
  ctx.fill();
  ctx.beginPath();
  ctx.arc(cx + 26 + gx * 8, cy + 20 + gy * 6, 8, 0, Math.PI * 2);
  ctx.fill();
  ctx.globalAlpha = 1;
}

function dibujarCeja(lado) {
  const a = actual;
  if (a.cejaVis < 0.02) return;
  ctx.save();
  if (lado < 0) { ctx.translate(2 * EJE, 0); ctx.scale(-1, 1); }
  const sube = a.cejaAsim * lado;
  const yOut = 424 + a.cejaY - sube - a.cejaAng * 0.3;
  const yIn = 430 + a.cejaY - sube * 0.6 + a.cejaAng;
  const camino = () => {
    ctx.beginPath();
    ctx.moveTo(418, yOut);
    ctx.quadraticCurveTo(495, Math.min(yOut, yIn) - 16, 572, yIn);
  };
  ctx.globalAlpha = a.cejaVis;
  trazo(22, '#fff'); camino(); ctx.stroke();
  trazo(10); camino(); ctx.stroke();
  ctx.restore();
}

function dibujarBoca() {
  const a = actual;
  const ab = limitar(anim.apertura + a.abierta);
  const cx = 632, base = 638;

  if (a.redonda > 0.5) {
    const rx = 16 + ab * 10, ry = 18 + ab * 20;
    const cy = 650 + ab * 8;
    ctx.beginPath();
    ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
    ctx.fillStyle = '#262626';
    ctx.fill();
    ctx.save(); ctx.clip();
    ctx.fillStyle = '#8a8a8a';
    ctx.beginPath(); ctx.ellipse(cx, cy + ry * 0.8, rx * 0.8, ry * 0.45, 0, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
    trazo(6); ctx.stroke();
    return;
  }

  const mitad = 40 * a.ancho;
  const xl = cx - mitad, xr = cx + mitad;
  const yl = base + a.asim * 6, yr = base - a.asim * 20;
  const medio = (yl + yr) / 2;

  if (ab < 0.04) {
    trazo(7);
    ctx.beginPath();
    ctx.moveTo(xl, yl);
    ctx.quadraticCurveTo(cx + a.asim * 8, medio + a.curva * 34, xr, yr);
    ctx.stroke();
    return;
  }

  const arriba = medio + a.curva * 12 - ab * 6;
  const abajo = arriba + 16 + ab * 84 + Math.max(0, a.curva) * 14;
  ctx.beginPath();
  ctx.moveTo(xl, yl);
  ctx.quadraticCurveTo(cx, arriba, xr, yr);
  ctx.quadraticCurveTo(cx, abajo, xl, yl);
  ctx.closePath();
  ctx.fillStyle = '#262626';
  ctx.fill();
  ctx.save();
  ctx.clip();
  if (a.dientes > 0.3) {
    ctx.fillStyle = '#fff';
    ctx.fillRect(xl - 5, Math.min(yl, yr) - 40, mitad * 2 + 10, (arriba - Math.min(yl, yr)) / 2 + 48);
  }
  const fondo = (yl + yr) / 4 + (arriba + abajo) / 4 + (abajo - arriba) * 0.3;
  ctx.fillStyle = '#8a8a8a';
  ctx.beginPath();
  ctx.ellipse(cx, fondo + 8, mitad * 0.6, 18, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
  trazo(6);
  ctx.beginPath();
  ctx.moveTo(xl, yl);
  ctx.quadraticCurveTo(cx, arriba, xr, yr);
  ctx.quadraticCurveTo(cx, abajo, xl, yl);
  ctx.closePath();
  ctx.stroke();
}

function dibujarRubor() {
  const r = actual.rubor;
  if (r < 0.02) return;
  for (const lado of [1, -1]) {
    const cx = lado > 0 ? 432 : 2 * EJE - 432, cy = 640;
    ctx.globalAlpha = r * 0.5;
    ctx.fillStyle = '#f2a7b8';
    ctx.beginPath(); ctx.ellipse(cx, cy, 44, 18, 0, 0, Math.PI * 2); ctx.fill();
    ctx.globalAlpha = r;
    trazo(4);
    for (let i = -1; i <= 1; i++) {
      ctx.beginPath();
      ctx.moveTo(cx + i * 22 - 6, cy + 9);
      ctx.lineTo(cx + i * 22 + 6, cy - 9);
      ctx.stroke();
    }
  }
  ctx.globalAlpha = 1;
}

function gota(x, y, r) {
  ctx.beginPath();
  ctx.moveTo(x, y - r * 2.2);
  ctx.bezierCurveTo(x + r * 0.4, y - r * 1.2, x + r, y - r * 0.6, x + r, y);
  ctx.arc(x, y, r, 0, Math.PI);
  ctx.bezierCurveTo(x - r, y - r * 0.6, x - r * 0.4, y - r * 1.2, x, y - r * 2.2);
  ctx.closePath();
}

function dibujarLagrimas() {
  if (actual.lagrimas > 0.05) {
    // agua acumulada bajo los ojos
    ctx.globalAlpha = actual.lagrimas;
    for (const lado of [1, -1]) {
      ctx.save();
      if (lado < 0) { ctx.translate(2 * EJE, 0); ctx.scale(-1, 1); }
      ctx.fillStyle = '#d8ecff';
      ctx.beginPath();
      ctx.ellipse(470, 598, 70, 9, 0.05, 0, Math.PI * 2);
      ctx.fill();
      trazo(3); ctx.stroke();
      ctx.restore();
    }
    ctx.globalAlpha = 1;
  }
  for (const l of lagrimas) {
    const x = l.lado > 0 ? l.x : 2 * EJE - l.x;
    gota(x, l.y, l.r);
    ctx.fillStyle = '#d8ecff';
    ctx.fill();
    trazo(3); ctx.stroke();
  }
}

function dibujarSudor() {
  const s = actual.sudor;
  if (s < 0.02) return;
  const d = (t * 0.35) % 1;
  ctx.globalAlpha = s * (1 - suave(0.7, 1, d));
  gota(950, 455 + d * 40, 16);
  ctx.fillStyle = '#fff'; ctx.fill();
  trazo(5); ctx.stroke();
  trazo(4); ctx.beginPath(); ctx.moveTo(945, 445 + d * 40); ctx.lineTo(942, 460 + d * 40); ctx.stroke();
  ctx.globalAlpha = 1;
}

function dibujarVena() {
  const e = actual.enojo;
  if (e < 0.02) return;
  const esc = (0.9 + 0.12 * Math.max(0, Math.sin(t * 9))) * e;
  ctx.save();
  ctx.translate(800, 330);
  ctx.scale(esc, esc);
  for (let i = 0; i < 4; i++) {
    ctx.save();
    ctx.rotate(i * Math.PI / 2);
    trazo(18, '#fff');
    ctx.beginPath(); ctx.moveTo(10, 34); ctx.quadraticCurveTo(12, 12, 34, 10); ctx.stroke();
    trazo(8);
    ctx.beginPath(); ctx.moveTo(10, 34); ctx.quadraticCurveTo(12, 12, 34, 10); ctx.stroke();
    ctx.restore();
  }
  ctx.restore();
}

function estrella(x, y, r) {
  ctx.beginPath();
  for (let i = 0; i < 8; i++) {
    const ang = i * Math.PI / 4 - Math.PI / 2;
    const rr = i % 2 ? r * 0.3 : r;
    ctx.lineTo(x + Math.cos(ang) * rr, y + Math.sin(ang) * rr);
  }
  ctx.closePath();
}

function dibujarChispas() {
  const c = actual.chispas;
  if (c < 0.02) return;
  const puntos = [[250, 330, 0], [1010, 250, 1.7], [205, 560, 3.1], [1060, 520, 4.4]];
  for (const [x, y, fase] of puntos) {
    const r = (14 + 12 * Math.max(0, Math.sin(t * 3 + fase))) * c;
    estrella(x, y, r);
    ctx.fillStyle = '#fff'; ctx.fill();
    trazo(4); ctx.stroke();
  }
}

function dibujar(p) {
  ctx.clearRect(0, 0, W, H);
  dibujarPelo(p);
  dibujarCuerpo(p);

  ctx.save();
  transformarCabeza(p);
  ctx.drawImage(capas.cara, 0, 0, W, CORTE, 0, 0, W, CORTE);

  // los rasgos se adelantan un poco al girar: sensación de volumen
  ctx.save();
  ctx.translate(p.x * 0.08, p.y * 0.04);
  const d = anim.parpadeo >= 0 ? (t - anim.parpadeo) / 0.16 : 1;
  const parpadeo = d < 1 ? Math.sin(d * Math.PI) : 0;
  dibujarRubor();
  dibujarOjo(1, parpadeo);
  dibujarOjo(-1, parpadeo);
  dibujarLagrimas();
  dibujarBoca();
  ctx.restore();

  dibujarCeja(1);
  dibujarCeja(-1);
  dibujarSudor();
  dibujarVena();
  dibujarChispas();
  ctx.restore();
}

// ---------------------------------------------------------------- audio y voz
const audio = new Audio();
audio.crossOrigin = 'anonymous';
let contexto = null, analizador = null, muestras = null;
const cola = [];
let enCurso = null;

function prepararAudio() {
  if (contexto) return;
  try {
    contexto = new (window.AudioContext || window.webkitAudioContext)();
    const fuente = contexto.createMediaElementSource(audio);
    analizador = contexto.createAnalyser();
    analizador.fftSize = 1024;
    muestras = new Float32Array(analizador.fftSize);
    fuente.connect(analizador);
    analizador.connect(contexto.destination);
  } catch (err) {
    console.warn('Sin análisis de audio; la boca se moverá de forma aproximada.', err);
  }
}

function hablando() {
  return !!enCurso || cola.length > 0;
}

function nivelAudio() {
  if (!enCurso || audio.paused) return 0;
  if (!analizador) return 0.3 + 0.3 * Math.sin(t * 22);
  analizador.getFloatTimeDomainData(muestras);
  let suma = 0;
  for (const v of muestras) suma += v * v;
  const rms = Math.sqrt(suma / muestras.length);
  return limitar((rms - 0.015) * 9);
}

function hablar(mensaje) {
  cola.push(mensaje);
  if (!enCurso) siguiente();
}

function siguiente() {
  const m = cola.shift();
  enCurso = m || null;
  if (!m) {
    mostrarSubtitulo('');
    if (emocion !== 'neutral' && !volverANeutral) volverANeutral = t + 3;
    return;
  }
  if (m.emocion) ponerEmocion(m.emocion);
  mostrarSubtitulo(m.texto || '');
  if (!m.audio) { setTimeout(terminar, 1500); return; }
  prepararAudio();
  if (contexto && contexto.state === 'suspended') contexto.resume().catch(() => {});
  audio.src = m.audio;
  audio.play().catch(() => pedirClic());
}

function terminar() {
  const m = enCurso;
  if (m && m.id) enviar({ tipo: 'fin_audio', id: m.id });
  siguiente();
}
audio.addEventListener('ended', terminar);
audio.addEventListener('error', terminar);

function parar() {
  cola.length = 0;
  audio.pause();
  enCurso = null;
  mostrarSubtitulo('');
}

const aviso = document.getElementById('aviso');
function pedirClic() { aviso.hidden = false; }
aviso.addEventListener('click', () => {
  aviso.hidden = true;
  prepararAudio();
  if (contexto) contexto.resume();
  if (enCurso && enCurso.audio) audio.play().catch(() => {});
});

const subtitulo = document.getElementById('subtitulo');
function mostrarSubtitulo(texto) {
  if (!parametros.has('subtitulos')) return;
  subtitulo.textContent = texto;
  subtitulo.hidden = !texto;
}

// x, y: desplazamiento en píxeles (±30 razonable); inclinacion: -1..1 (ladeo)
function ponerCabeza(x = 0, y = 0, inclinacion = 0) {
  anim.cabezaObj = { x: limitar(x, -40, 40), y: limitar(y, -30, 30), incl: limitar(inclinacion, -1, 1) * 0.06 };
}

// ---------------------------------------------------------------- conexión con el servidor
let socket = null;

function enviar(obj) {
  if (socket && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(obj));
}

function manejar(m) {
  switch (m.tipo) {
    case 'emocion': ponerEmocion(m.nombre, m.duracion || 0); break;
    case 'hablar': hablar(m); break;
    case 'parar': parar(); break;
    case 'mirar': anim.miradaObj = { x: limitar(m.x, -1, 1), y: limitar(m.y, -1, 1) };
      anim.proximaMirada = t + (m.duracion || 2); break;
    case 'cabeza': ponerCabeza(m.x, m.y, m.inclinacion); break;
  }
}

function conectar() {
  if (location.protocol === 'file:') return;
  const esquema = location.protocol === 'https:' ? 'wss' : 'ws';
  socket = new WebSocket(`${esquema}://${location.host}/ws?rol=avatar`);
  socket.onmessage = (e) => { try { manejar(JSON.parse(e.data)); } catch (err) { console.error(err); } };
  socket.onclose = () => setTimeout(conectar, 1500);
}

// ---------------------------------------------------------------- arranque
async function iniciar() {
  const [pelo, cuerpo, cara] = await Promise.all(
    ['pelo', 'cuerpo', 'cara'].map((n) => cargarImagen(`capas/${n}.png`)));
  capas = { pelo, cuerpo, cara };

  if (parametros.get('fondo')) document.body.style.background = parametros.get('fondo');
  if (parametros.get('emocion')) ponerEmocion(parametros.get('emocion'));
  conectar();

  let anterior = performance.now();
  function fotograma(ahora) {
    const dt = Math.min(0.05, (ahora - anterior) / 1000);
    anterior = ahora;
    t += dt;
    actualizar(dt);
    const p = postura();
    moverPelo(p.x, dt);
    moverCuerpo(p, dt);
    dibujar(p);
    requestAnimationFrame(fotograma);
  }
  requestAnimationFrame(fotograma);
}

// Para controlar el avatar desde la consola del navegador o desde pruebas
window.avatar = { emocion: ponerEmocion, hablar, parar, cabeza: ponerCabeza, EXPRESIONES, estado: () => ({ emocion, actual }) };

iniciar().catch((err) => console.error('No se pudo iniciar el avatar', err));
