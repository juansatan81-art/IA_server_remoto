'use strict';
/*
 * Avatar 2D animado, montado con las piezas dibujadas (ver herramientas/preparar_piezas.py).
 *
 * Capas, de atrás hacia delante:
 *   pelo_largo  -> por franjas: arriba sigue a la cabeza, abajo se balancea con retraso
 *   cuerpo      -> torso y brazos, por franjas: la cabeza "arrastra" los hombros
 *   pecho       -> encima del torso, con su propio muelle
 *   (el pelo de la cabeza va entre el pelo largo y el cuerpo)
 *   cabeza      -> cara, flequillo, ojos, boca, rubor, cejas, efectos
 *
 * Las piezas de la cabeza y todo lo vectorial usan las coordenadas del busto
 * original (1254 x 1200); BUSTO las lleva al lienzo.
 */

let W = 1300, H = 1140;
let BUSTO = { escala: 1, dx: 0, dy: 0 };
let PEGATINAS = {};
let PECHO = { arriba: 0, abajo: 1 };
let CUELLO_Y = 610;       // pivote de la inclinación de la cabeza (lienzo)
let CORTE = 607;          // por encima, el pelo largo se mueve rígido con la cabeza
let CUERPO_ARRIBA = 595;
const EJE = 631.5;        // eje de simetría de la cara (busto)
const FRANJA = 2;
// Cómo se comporta el pecho. Por defecto "suave"; para comparar:
//   ?pecho=gelatina (más exagerado)   ?pecho=firme (sin deformarse)
const ESTILOS_PECHO = {
  //          rigidez freno ganancia máx  tirón retraso(s) aplastar
  gelatina: { rigidez: 38, freno: 1.3, ganancia: 3.6, max: 18, tiron: 0.7, retraso: 0.15, aplastar: 0.0018 },
  suave: { rigidez: 55, freno: 2.4, ganancia: 2.4, max: 12, tiron: 0.4, retraso: 0.09, aplastar: 0.0015 },
  firme: { rigidez: 70, freno: 4.5, ganancia: 2.4, max: 12, tiron: 0.4, retraso: 0, aplastar: 0 },
};
const ESTILO_PECHO = ESTILOS_PECHO[new URLSearchParams(location.search).get('pecho')] || ESTILOS_PECHO.suave;

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
  curva: 1, ancho: 1, asim: 0,          // boca vectorial (presumida, pensativa)
  rubor: 0, lagrimas: 0, enojo: 0, sudor: 0, chispas: 0,
  inclinacion: 0, cabezaY: 0,
  miradaX: 0, miradaY: 0, miradaFija: 0,
};

const EXPRESIONES = {
  neutral: {},
  feliz: { feliz: 1, chispas: 1, rubor: 0.35, cejaVis: 0.8, cejaY: -12, cejaAng: -6 },
  enojada: { lidIn: 48, lidOut: 4, cejaVis: 1, cejaY: 10, cejaAng: 26, enojo: 1, cabezaY: 4 },
  triste: { lidOut: 34, lidIn: 6, brillo: 1, cejaVis: 1, cejaAng: -22, cabezaY: 10,
    inclinacion: 0.02, miradaY: 0.6, miradaFija: 0.6 },
  llorando: { lidOut: 38, lidIn: 8, brillo: 1, cejaVis: 1, cejaAng: -26, lagrimas: 1,
    cabezaY: 12, inclinacion: 0.015 },
  sorprendida: { redondo: 1, brillo: 1, cejaVis: 1, cejaY: -24, cabezaY: -6 },
  avergonzada: { lidOut: 22, lidIn: 22, rubor: 1, sudor: 1, cejaVis: 0.9, cejaAng: -14,
    brillo: 0.6, miradaX: -1, miradaY: 0.5, miradaFija: 1, inclinacion: -0.02 },
  presumida: { lidOut: 36, lidIn: 26, curva: 1, asim: 1, cejaVis: 1, cejaY: -4,
    cejaAsim: 16, inclinacion: -0.018 },
  pensativa: { lidOut: 14, lidIn: 8, curva: 0.1, ancho: 0.6, asim: 0.5, cejaVis: 0.9,
    cejaAsim: 12, miradaX: 0.9, miradaY: -0.9, miradaFija: 1, inclinacion: 0.025 },
};

// Boca de cada emoción cuando no habla: una de tus piezas o la vectorial
const BOCAS = {
  neutral: 'sonrisa', feliz: 'a', enojada: 'triste', triste: 'triste', llorando: 'o',
  sorprendida: 'o', avergonzada: 'sonrisa', presumida: 'vector', pensativa: 'vector',
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
  pecho: { x: 0, vx: 0, y: 0, vy: 0 },             // y el pecho al torso
  impulso: null,
  apertura: 0,
  cabeza: { x: 0, y: 0, incl: 0 }, cabezaObj: { x: 0, y: 0, incl: 0 },   // postura pedida desde fuera
};
const lagrimas = [];

// Ritmo: deformaciones al compás, medidas en el vídeo de referencia del motion graphic
// (cada zona con su retraso: el flequillo y el pelo siguen a la cabeza, los mechones se
// abren y se cierran, el cuerpo respira ensanchándose, los brazos suben y bajan...).
// avatar.ritmo({ bpm: 120, fuerza: 1, tiempo }) — tiempo: el del vídeo, para ir a compás.
const ritmo = { bpm: 0, fuerza: 0, tiempo: null, ancla: 1.0 };
function ponerRitmo(o = {}) {
  if (o.bpm !== undefined) ritmo.bpm = o.bpm;
  if (o.fuerza !== undefined) ritmo.fuerza = o.fuerza;
  if (o.tiempo !== undefined) ritmo.tiempo = o.tiempo;
  if (o.ancla !== undefined) ritmo.ancla = o.ancla;   // segundo en que cae un golpe
}
// 1 justo en el golpe (más `retraso` s), -1 a mitad de compás. lado=true: la componente
// lateral (un cuarto de compás desfasada), para que no se mueva todo a la vez
function onda(retraso = 0, lado = false) {
  if (!ritmo.fuerza || !ritmo.bpm) return 0;
  const tt = ritmo.tiempo ?? t;
  const fase = 2 * Math.PI * (tt - ritmo.ancla - retraso) * ritmo.bpm / 60;
  return (lado ? Math.sin(fase) : Math.cos(fase)) * ritmo.fuerza;
}

// dibuja una capa del busto en franjas, cada una desplazada por fn(y) -> {dx, dy}
function franjasBusto(img, fn) {
  if (!ritmo.fuerza) { ctx.drawImage(img, 0, 0); return; }
  const paso = 3;
  for (let y = 0; y < img.height; y += paso) {
    const d = fn(y + paso / 2);
    ctx.drawImage(img, 0, y, img.width, paso, d.dx, y + d.dy, img.width, paso + 1);
  }
}

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
  avisarEstado();
  return true;
}

// ---------------------------------------------------------------- utilidades
const lerp = (a, b, k) => a + (b - a) * k;
const limitar = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const suave = (a, b, x) => { const k = limitar((x - a) / (b - a)); return k * k * (3 - 2 * k); };
const azar = (a, b) => a + Math.random() * (b - a);
const aLienzoY = (y) => BUSTO.escala * y + BUSTO.dy;

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
  return { x, y, incl, respira };
}

// muelle del pelo: sigue a la cabeza con retraso
function moverPelo(cabezaX, dt) {
  const fuerza = (cabezaX - anim.pelo) * 55 - anim.peloV * 5;
  anim.peloV += fuerza * dt;
  anim.pelo += anim.peloV * dt;
}

// La cabeza "arrastra" al cuerpo: un muelle más lento y pesado que el del pelo,
// y el pecho sigue al torso con otro muelle más rápido y blando.
function moverCuerpo(p, dt) {
  const c = anim.cuerpo;
  c.vx += ((p.x - c.x) * 18 - c.vx * 6) * dt;
  c.x += c.vx * dt;
  c.vy += ((p.y - c.y) * 22 - c.vy * 7) * dt;
  c.y += c.vy * dt;
  c.incl = lerp(c.incl, p.incl, 1 - Math.exp(-dt * 3));

  // el pecho persigue al torso con un muelle blando: se queda atrás en los
  // movimientos bruscos y luego oscila un poco hasta asentarse
  const q = anim.pecho;
  const e = ESTILO_PECHO;
  const objY = c.y * 0.5 - p.respira * 1.5 + (p.y - c.y) * e.tiron + 8 * onda(0.04),
    objX = c.x * 0.5 + 3 * onda(0.08, true);
  q.vy += ((objY - q.y) * e.rigidez - q.vy * e.freno) * dt;
  q.y += q.vy * dt;
  q.vx += ((objX - q.x) * 60 - q.vx * 6) * dt;
  q.x += q.vx * dt;
  q.objY = objY;
}

// ---------------------------------------------------------------- dibujo
let capas = null;

function transformarCabeza(p) {
  ctx.translate(p.x, p.y);
  ctx.transform(1, 0, -p.incl, 1, p.incl * CUELLO_Y, 0);
}

function aBusto(g = ctx) {
  g.transform(BUSTO.escala, 0, 0, BUSTO.escala, BUSTO.dx, BUSTO.dy);
}

function dibujarPeloLargo(p) {
  // parte alta: rígida con la cabeza (2 px de solape para que no quede rendija)
  ctx.save();
  transformarCabeza(p);
  ctx.drawImage(capas.pelo_largo, 0, 0, W, CORTE + 2, 0, 0, W, CORTE + 2);
  ctx.restore();
  // parte baja: franjas que se doblan y se balancean
  for (let y = CORTE; y < H; y += FRANJA) {
    const m = y + FRANJA / 2;
    const libre = suave(CORTE, H, m);
    const peso = 1 - libre * 0.88;
    const viento = 2.5 * Math.sin(t * 1.3 - m * 0.012);
    const dx = p.x * peso + (anim.pelo - p.x) * libre * 1.3 + viento * libre;
    const dy = p.y * peso;
    if (!ritmo.fuerza) {
      ctx.drawImage(capas.pelo_largo, 0, y, W, FRANJA, dx, y + dy, W, FRANJA + 1);
      continue;
    }
    // al compás, cada lado del pelo se abre y se cierra (los mechones se ensanchan)
    const abrir = 10 * onda(0.16) * libre, lado = 6 * onda(0.2, true) * libre;
    const mitad = W / 2;
    ctx.drawImage(capas.pelo_largo, 0, y, mitad, FRANJA, dx - abrir + lado, y + dy, mitad, FRANJA + 1);
    ctx.drawImage(capas.pelo_largo, mitad, y, mitad, FRANJA, mitad + dx + abrir + lado, y + dy, mitad, FRANJA + 1);
  }
}

// El torso se dibuja por franjas: arriba (hombros) sigue mucho a la cabeza y
// abajo casi nada, así se dobla como una columna en vez de moverse en bloque.
// extra(m): desplazamiento adicional de la franja de la fila m -> { dx, dy, sx }
function franjasCuerpo(img, p, extra = null) {
  const c = anim.cuerpo;
  const crecer = p.respira * 0.006;           // respiración: se estira desde abajo
  for (let y = CUERPO_ARRIBA; y < H; y += FRANJA) {
    const m = y + FRANJA / 2;
    const abajo = suave(CUERPO_ARRIBA, H, m);
    const peso = lerp(0.7, 0.06, abajo);
    let dx = c.x * peso + c.incl * (H - m) * 0.35;
    let dy = c.y * peso * 0.8 - (H - m) * crecer;
    let sx = 1;
    if (ritmo.fuerza) {
      // respira con el compás: se ensancha y se estira un 3 %, más cuanto más abajo
      const r = onda(0.12);
      sx = 1 + 0.03 * r * abajo;
      dy -= (H - m) * 0.016 * r;
    }
    if (extra) {
      const e = extra(m);
      if (e === null) continue;                // fila sin pecho: nada que dibujar
      dx += e.dx; dy += e.dy; sx *= e.sx;
    }
    // sx estrecha o ensancha la franja alrededor del centro del lienzo
    ctx.drawImage(img, 0, y, W, FRANJA, dx + W / 2 * (1 - sx), y + dy, W * sx, FRANJA + 1);
  }
}

// Historial corto del rebote: las filas de abajo usan valores de hace un
// instante, así la onda baja por el pecho como en una gelatina.
const historialRebote = [];
function reboteHace(segundos) {
  const objetivo = t - segundos;
  for (let i = historialRebote.length - 1; i >= 0; i--) {
    if (historialRebote[i].t <= objetivo) return historialRebote[i];
  }
  return historialRebote[0] || { x: 0, y: 0 };
}

// brazos en otra pose (herramientas/poses.py): se cambia el cuerpo por el torso sin brazos
// y los brazos se dibujan encima del pecho, moviéndose con el cuerpo
let poseBrazos = null;

async function ponerBrazos(nombre) {
  if (!nombre) { poseBrazos = null; return; }
  const clave = `brazos_${nombre}`;
  if (!capas.cuerpo_sin_brazos) capas.cuerpo_sin_brazos = await cargarImagen('capas/cuerpo_sin_brazos.png');
  if (!capas[clave]) capas[clave] = await cargarImagen(`capas/${clave}.png`);
  poseBrazos = clave;
}

function dibujarCuerpo(p) {
  franjasCuerpo(poseBrazos ? capas.cuerpo_sin_brazos : capas.cuerpo, p);
  // el pecho rebota respecto al torso: diferencia entre su muelle y el del torso
  const c = anim.cuerpo, q = anim.pecho;
  const e = ESTILO_PECHO;
  const rebY = limitar((q.y - (q.objY ?? q.y)) * e.ganancia, -e.max, e.max);
  const rebX = limitar((q.x - c.x * 0.5) * 1.5, -6, 6);
  anim.rebote = { x: rebX, y: rebY };
  historialRebote.push({ t, x: rebX, y: rebY });
  while (historialRebote.length > 2 && historialRebote[0].t < t - 0.5) historialRebote.shift();

  const arriba = PECHO.arriba, abajo = PECHO.abajo;
  franjasCuerpo(capas.pecho, p, (m) => {
    if (m < arriba - 4 || m > abajo + 4) return null;
    if (!e.retraso) {
      // firme: arriba, donde se une al torso, no se mueve; el rebote crece hasta la mitad
      const k = suave(arriba, (arriba + abajo) / 2, m);
      return { dx: rebX * k, dy: rebY * k, sx: 1 };
    }
    // gelatina: cuanto más abajo, más se mueve y con más retraso; al estirarse
    // se estrecha un poco y al encogerse se ensancha
    const k = suave(arriba, abajo, m);
    const r = reboteHace(k * e.retraso);
    return { dx: r.x * k, dy: r.y * k * 1.15, sx: 1 - r.y * k * e.aplastar };
  });
  if (poseBrazos && capas[poseBrazos]) {
    const sube = 11 * onda(0.1), estira = 0.045 * onda(0.14), mece = 5 * onda(0.1, true);
    // el hombro queda pegado al cuerpo; el movimiento crece hacia los codos y las manos
    franjasCuerpo(capas[poseBrazos], p, (m) => {
      const k = suave(760, 1060, m);
      return { dx: mece * k, dy: (sube + (m - 900) * estira) * k, sx: 1 + 0.022 * onda(0.14) * k };
    });
  }
}

function trazo(ancho, color = '#000', g = ctx) {
  g.lineWidth = ancho;
  g.strokeStyle = color;
  g.lineCap = 'round';
  g.lineJoin = 'round';
}

function pegatina(nombre, alfa = 1, sx = 1, sy = 1, g = ctx) {
  const p = PEGATINAS[nombre], img = capas[nombre];
  if (!p || !img || alfa < 0.01) return;
  const cx = p.x + p.w / 2, cy = p.y + p.h / 2;
  g.globalAlpha = alfa;
  g.drawImage(img, cx - p.w * sx / 2, cy - p.h * sy / 2, p.w * sx, p.h * sy);
  g.globalAlpha = 1;
}

// --- ojos: tu contorno blanco + la forma negra, que se mueve para mirar
const OJOS = { x: 340, y: 420, w: 590, h: 210 };   // zona de los ojos (busto)
const lienzoOjos = document.createElement('canvas');
lienzoOjos.width = OJOS.w; lienzoOjos.height = OJOS.h;
const gOjos = lienzoOjos.getContext('2d');

function dibujarOjos(parpadeo) {
  const a = actual;
  if (a.feliz > 0.5) {
    pegatina('ojo_feliz_izq'); pegatina('ojo_feliz_der');
    return;
  }
  if (parpadeo > 0.72 && a.redondo < 0.5) {
    pegatina('ojo_cerrado_izq'); pegatina('ojo_cerrado_der');
    return;
  }
  const g = gOjos;
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.clearRect(0, 0, OJOS.w, OJOS.h);
  g.setTransform(1, 0, 0, 1, -OJOS.x, -OJOS.y);
  g.drawImage(capas.ojos_blanco, 0, 0);
  const cierre = a.redondo > 0.5 ? 0 : parpadeo / 0.72 * 0.8;
  for (const lado of [1, -1]) pupila(g, lado, cierre, parpadeo);
  // todo queda dentro de tu contorno del ojo
  g.globalCompositeOperation = 'destination-in';
  g.drawImage(capas.ojos_blanco, 0, 0);
  g.globalCompositeOperation = 'source-over';
  ctx.drawImage(lienzoOjos, OJOS.x, OJOS.y);
}

function pupila(g, lado, cierre, parpadeo) {
  const a = actual;
  const gx = anim.mirada.x * lado, gy = anim.mirada.y;
  g.save();
  if (lado < 0) { g.translate(2 * EJE, 0); g.scale(-1, 1); }
  if (a.redondo > 0.5) {
    const cx = 490 + gx * 14, cy = 515 + gy * 8;
    const ry = 60 * Math.max(0.08, 1 - parpadeo);
    g.fillStyle = '#000';
    g.beginPath(); g.ellipse(cx, cy, 54, ry, 0, 0, Math.PI * 2); g.fill();
    if (parpadeo < 0.5) reflejos(g, cx, cy, a.brillo, gx, gy);
    g.restore();
    return;
  }
  const cx = 490 + gx * 14, cy = 490 + gy * 7;
  const yOut = lerp(456 + a.lidOut, 584, cierre);
  const yIn = lerp(468 + a.lidIn, 584, cierre);
  // la línea del párpado va de (377, yOut) a (603, yIn); se prolonga un poco
  const pend = (yIn - yOut) / 226;
  const linea = () => { g.moveTo(350, yOut - 27 * pend); g.lineTo(630, yIn + 27 * pend); };
  g.save();
  g.beginPath(); g.ellipse(cx, cy, 94, 92, 0, 0, Math.PI * 2); g.clip();
  g.beginPath(); linea(); g.lineTo(630, 640); g.lineTo(350, 640); g.closePath();
  g.fillStyle = '#000'; g.fill();
  if (a.brillo > 0.03 && cierre < 0.4) {
    g.clip();
    reflejos(g, cx, Math.max(cy + 20, (yOut + yIn) / 2 + 40), a.brillo, gx, gy);
  }
  g.restore();
  // párpado bajado: lo de encima es piel y la línea del párpado pasa a ser el borde
  if (yOut > 461 || yIn > 473) {
    g.beginPath(); g.moveTo(350, 420); g.lineTo(630, 420); g.lineTo(630, yIn + 27 * pend);
    g.lineTo(350, yOut - 27 * pend); g.closePath();
    g.fillStyle = '#fff'; g.fill();
    trazo(8, '#000', g); g.beginPath(); linea(); g.stroke();
  }
  g.restore();
}

function reflejos(g, cx, cy, fuerza, gx, gy) {
  g.globalAlpha = limitar(fuerza);
  g.fillStyle = '#fff';
  g.beginPath(); g.ellipse(cx - 28 + gx * 8, cy - 18 + gy * 6, 20, 16, -0.4, 0, Math.PI * 2); g.fill();
  g.beginPath(); g.arc(cx + 26 + gx * 8, cy + 20 + gy * 6, 8, 0, Math.PI * 2); g.fill();
  g.globalAlpha = 1;
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
  ctx.globalAlpha = 1;
  ctx.restore();
}

// --- boca: tus piezas; al hablar alterna entre la "O" y la "A" según el volumen
function dibujarBoca() {
  const ap = anim.apertura;
  let forma = BOCAS[emocion] || 'sonrisa';
  if (ap > 0.12) forma = ap > 0.45 ? 'a' : 'o';
  if (forma === 'vector') return dibujarBocaVector();
  if (forma === 'a') {
    const abre = ap > 0.12 ? 0.7 + 0.45 * ap : 0.75;
    pegatina('boca_a', 1, 0.85 + 0.15 * abre, abre);
  } else if (forma === 'o') {
    pegatina('boca_o', 1, 1, ap > 0.12 ? 0.8 + 0.5 * ap : 1);
  } else {
    pegatina('boca_' + forma);
  }
}

function dibujarBocaVector() {
  const a = actual;
  const cx = 632, base = 638;
  const mitad = 40 * a.ancho;
  const xl = cx - mitad, xr = cx + mitad;
  const yl = base + a.asim * 6, yr = base - a.asim * 20;
  trazo(7);
  ctx.beginPath();
  ctx.moveTo(xl, yl);
  ctx.quadraticCurveTo(cx + a.asim * 8, (yl + yr) / 2 + a.curva * 34, xr, yr);
  ctx.stroke();
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
  dibujarPeloLargo(p);

  // el pelo de la cabeza va detrás del cuerpo (los hombros y el cuello lo tapan)
  ctx.save();
  transformarCabeza(p);
  aBusto();
  // el volumen de arriba se aplasta en el golpe y rebota; las puntas se balancean
  const estirar = -0.032 * onda(0.06), balanceo = 16 * onda(0.12, true);
  franjasBusto(capas.pelo_cabeza, (y) => ({
    dx: balanceo * suave(150, 900, y) * suave(150, 900, y),
    dy: (y - 620) * estirar,
  }));
  ctx.restore();

  dibujarCuerpo(p);

  ctx.save();
  transformarCabeza(p);
  aBusto();
  ctx.drawImage(capas.cara, 0, 0);

  // el flequillo se adelanta un poco más que la cara al girar
  ctx.save();
  ctx.translate(p.x * 0.14 + (anim.pelo - p.x) * 0.15, p.y * 0.06);
  // y se mece como si girara un poco desde arriba, con algo de retraso
  const mecer = 13 * onda(0.09, true), botar = 6 * onda(0.05);
  franjasBusto(capas.flequillo, (y) => {
    const k = limitar((y - 270) / 190);
    return { dx: mecer * k, dy: botar * k };
  });
  ctx.restore();

  // los rasgos van delante del flequillo (el ojo derecho tapa parte del pelo)
  ctx.save();
  ctx.translate(p.x * 0.1, p.y * 0.05);
  const d = anim.parpadeo >= 0 ? (t - anim.parpadeo) / 0.18 : 1;
  const parpadeo = d < 1 ? Math.sin(d * Math.PI) : 0;
  pegatina('rubor_izq', actual.rubor);
  pegatina('rubor_der', actual.rubor);
  dibujarOjos(parpadeo);
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
let contexto = null, analizador = null, muestras = null, volumen = null;
let silenciado = parametros.has('mudo');
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
    // volumen aparte: ?mudo=1 analiza la voz (para mover la boca) pero no la reproduce
    volumen = contexto.createGain();
    volumen.gain.value = silenciado ? 0 : 1;
    fuente.connect(analizador);
    analizador.connect(volumen);
    volumen.connect(contexto.destination);
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
    avisarEstado();
    if (emocion !== 'neutral' && !volverANeutral) volverANeutral = t + 3;
    return;
  }
  if (m.emocion) ponerEmocion(m.emocion);
  mostrarSubtitulo(m.texto || '');
  avisarEstado();
  if (!m.audio) { setTimeout(terminar, 1500); return; }
  prepararAudio();
  if (contexto && contexto.state === 'suspended') contexto.resume().catch(() => {});
  audio.src = m.audio;
  m.inicio = performance.now();
  audio.play().catch((err) => {
    if (err.name === 'AbortError') return;   // se cambió de frase antes de empezar: normal
    pedirClic();
    avisarAudio(err.name === 'NotAllowedError'
      ? 'el navegador ha bloqueado el sonido: haz clic en la vista previa del avatar (en OBS, marca "Controlar audio mediante OBS")'
      : `no se pudo reproducir la voz (${err.name}: ${err.message})`);
  });
}

// cuenta al servidor los problemas de sonido (antes se saltaba la frase en silencio)
function avisarAudio(texto) {
  if (typeof enviar === 'function') enviar({ tipo: 'aviso_audio', texto });
}

// cuenta al servidor (y de ahí al panel) qué emoción tiene y qué está diciendo
function avisarEstado() {
  if (typeof enviar === 'function') enviar({ tipo: 'estado', emocion, texto: enCurso ? enCurso.texto || '' : '' });
}

function terminar() {
  const m = enCurso;
  if (m && m.id) enviar({ tipo: 'fin_audio', id: m.id });
  siguiente();
}
audio.addEventListener('ended', terminar);
audio.addEventListener('error', () => {
  const codigos = { 1: 'cancelado', 2: 'error de red', 3: 'el audio está dañado o vacío', 4: 'formato no soportado o archivo no encontrado' };
  if (enCurso && enCurso.audio) avisarAudio(`no se pudo reproducir una frase: ${codigos[audio.error && audio.error.code] || 'error desconocido'}`);
  terminar();
});

// vigilante: si el sistema de sonido se ha dormido o la frase se ha atascado, se arregla
let ultimoTiempo = -1, atascadoDesde = 0;
setInterval(() => {
  if (contexto && contexto.state === 'suspended' && enCurso && enCurso.audio) {
    contexto.resume().catch(() => {});
    avisarAudio('el sonido del navegador se había parado; intento reactivarlo (si no se oye, haz clic en la vista previa)');
  }
  if (enCurso && enCurso.audio && !audio.paused) {
    if (audio.currentTime === ultimoTiempo) {
      if (!atascadoDesde) atascadoDesde = performance.now();
      if (performance.now() - atascadoDesde > 8000) {
        avisarAudio('una frase se ha quedado atascada sin sonar; la salto');
        atascadoDesde = 0;
        terminar();
      }
    } else atascadoDesde = 0;
    ultimoTiempo = audio.currentTime;
  } else { atascadoDesde = 0; ultimoTiempo = -1; }
}, 2000);

// si cambia la salida de audio (auriculares, bluetooth, otra pantalla...), se sigue la nueva
if (navigator.mediaDevices && navigator.mediaDevices.addEventListener) {
  navigator.mediaDevices.addEventListener('devicechange', () => {
    if (contexto && contexto.setSinkId) contexto.setSinkId('').catch(() => {});
    if (contexto && contexto.state === 'suspended') contexto.resume().catch(() => {});
  });
}

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
  const modelo = await (await fetch('capas/piezas.json')).json();
  W = modelo.lienzo.ancho; H = modelo.lienzo.alto;
  lienzo.width = W; lienzo.height = H;
  BUSTO = modelo.busto_a_lienzo;
  PEGATINAS = modelo.pegatinas;
  PECHO = modelo.pecho;
  CUELLO_Y = aLienzoY(760); CORTE = Math.round(aLienzoY(756));
  CUERPO_ARRIBA = modelo.cuerpo_arriba ?? Math.round(aLienzoY(742));
  const nombres = ['pelo_largo', 'cuerpo', 'pecho', 'pelo_cabeza', 'cara', 'ojos_blanco', 'flequillo',
    ...Object.keys(PEGATINAS)];
  const imagenes = await Promise.all(nombres.map((n) => cargarImagen(`capas/${n}.png`)));
  capas = Object.fromEntries(nombres.map((n, i) => [n, imagenes[i]]));
  window.avatar.listo = true;

  if (parametros.get('fondo')) document.body.style.background = parametros.get('fondo');
  if (parametros.get('emocion')) ponerEmocion(parametros.get('emocion'));
  if (parametros.get('brazos')) await ponerBrazos(parametros.get('brazos'));
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
// Silenciar o no este avatar (la boca se sigue moviendo igual)
function silenciar(si) {
  silenciado = !!si;
  if (volumen) volumen.gain.value = silenciado ? 0 : 1;
}

window.avatar = {
  emocion: ponerEmocion, hablar, parar, cabeza: ponerCabeza, silenciar, brazos: ponerBrazos, ritmo: ponerRitmo, EXPRESIONES,
  estado: () => ({ emocion, actual, silenciado: volumen ? volumen.gain.value === 0 : silenciado }),
  pecho: () => ({ ...(anim.rebote || { x: 0, y: 0 }) }),   // rebote actual del pecho, en px
};

iniciar().catch((err) => console.error('No se pudo iniciar el avatar', err));
