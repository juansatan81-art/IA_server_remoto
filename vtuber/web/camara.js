'use strict';
/*
 * Cámara del avatar, como en VTube Studio: el personaje está entero (hasta los pies) y
 * se elige qué parte se ve.
 *   - Por defecto, el busto llenando la ventana (como siempre, también en OBS).
 *     Con ?vista=entero se empieza viendo el cuerpo entero.
 *   - Rueda del ratón o pellizco del touchpad: acercar / alejar hacia el cursor.
 *   - Arrastrar: mover la vista.  Doble clic: volver a la vista inicial.
 *   - Teclas: B = busto, E = cuerpo entero, 0 = vista inicial.
 * La vista se recuerda en este navegador (por página: el panel y OBS no se pisan).
 */
const camara = (() => {
  const lienzo = document.getElementById('lienzo');
  const clave = 'camaraAvatar:' + location.search;
  let W = 1300, H = 1140, HT = 1140;
  let s = 1, cx = 0, cy = 0;          // escala (px de pantalla por px del lienzo) y centro visible

  const ancho = () => window.innerWidth, alto = () => window.innerHeight;
  const ajusteBusto = () => Math.min(ancho() / W, alto() / H);
  const ajusteEntero = () => Math.min(ancho() / W, alto() / HT);

  function busto() {           // el busto llena la ventana, apoyado abajo como antes
    s = ajusteBusto(); cx = W / 2; cy = H - alto() / s / 2;
    aplicar();
  }
  function entero() {
    s = ajusteEntero(); cx = W / 2; cy = HT / 2;
    aplicar();
  }
  const inicial = () => (new URLSearchParams(location.search).get('vista') === 'entero' ? entero() : busto());

  function aplicar(guardar = true) {
    const min = ajusteEntero() * 0.6, max = ajusteBusto() * 6;
    s = Math.min(max, Math.max(min, s));
    lienzo.style.width = `${W * s}px`;
    lienzo.style.height = `${HT * s}px`;
    lienzo.style.left = `${ancho() / 2 - cx * s}px`;
    lienzo.style.top = `${alto() / 2 - cy * s}px`;
    if (guardar) {
      try { localStorage.setItem(clave, JSON.stringify({ rel: s / ajusteBusto(), cx, cy })); } catch {}
    }
  }

  function zoom(factor, mx, my) {
    const px = cx + (mx - ancho() / 2) / s, py = cy + (my - alto() / 2) / s;   // punto bajo el cursor
    s *= factor;
    aplicar(false);
    cx = px - (mx - ancho() / 2) / s; cy = py - (my - alto() / 2) / s;          // que siga bajo el cursor
    aplicar();
  }

  function iniciar(w, h, ht) {
    W = w; H = h; HT = ht;
    let guardada = null;
    try { guardada = JSON.parse(localStorage.getItem(clave) || 'null'); } catch {}
    if (guardada) { s = guardada.rel * ajusteBusto(); cx = guardada.cx; cy = guardada.cy; aplicar(false); }
    else inicial();

    // rueda y pellizco (en el touchpad el pellizco llega como rueda con Ctrl)
    window.addEventListener('wheel', (e) => {
      e.preventDefault();
      const paso = e.ctrlKey ? 0.01 : 0.0015;
      zoom(Math.exp(-e.deltaY * paso), e.clientX, e.clientY);
    }, { passive: false });

    let arrastre = null;
    window.addEventListener('pointerdown', (e) => {
      if (e.button !== 0 || e.target.id === 'aviso') return;
      arrastre = { x: e.clientX, y: e.clientY };
    });
    window.addEventListener('pointermove', (e) => {
      if (!arrastre) return;
      cx -= (e.clientX - arrastre.x) / s; cy -= (e.clientY - arrastre.y) / s;
      arrastre = { x: e.clientX, y: e.clientY };
      aplicar();
    });
    window.addEventListener('pointerup', () => { arrastre = null; });
    window.addEventListener('dblclick', inicial);
    window.addEventListener('keydown', (e) => {
      if (e.key === 'b' || e.key === 'B') busto();
      else if (e.key === 'e' || e.key === 'E') entero();
      else if (e.key === '0') inicial();
    });
    // al cambiar el tamaño de la ventana se mantiene el encuadre
    window.addEventListener('resize', () => {
      let g = null;
      try { g = JSON.parse(localStorage.getItem(clave) || 'null'); } catch {}
      if (g) { s = g.rel * ajusteBusto(); cx = g.cx; cy = g.cy; aplicar(false); } else inicial();
    });
  }

  return { iniciar, busto, entero, inicial };
})();

window.camara = camara;   // para usarla desde la consola o desde pruebas
