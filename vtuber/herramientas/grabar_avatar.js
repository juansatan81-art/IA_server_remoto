// Graba el avatar fotograma a fotograma (con reloj virtual: 60 fps exactos, sin saltos).
//
//   node herramientas/grabar_avatar.js <url del avatar> <guion.json> <carpeta de salida>
//
// guion.json: { "fps": 60, "fotogramas": [ { "brazos": "pose1", "cabeza": [x, y, incl],
//                                            "emocion": "avergonzada" }, ... ] }
// Cada fotograma se guarda como PNG transparente (00000.png, 00001.png...).
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

(async () => {
  const [url, archivoGuion, salida] = process.argv.slice(2);
  const guion = JSON.parse(fs.readFileSync(archivoGuion, 'utf8'));
  const fps = guion.fps || 60;
  fs.mkdirSync(salida, { recursive: true });

  const navegador = await chromium.launch();
  const pagina = await navegador.newPage({ viewport: { width: 1300, height: 1140 } });
  pagina.on('pageerror', (e) => console.error('Error en el avatar:', e.message));
  // reloj virtual y azar repetible: el avatar avanza solo cuando se le pide un fotograma
  await pagina.addInitScript(() => {
    let ahora = 0, semilla = 12345;
    const pendientes = [];
    window.__reloj = {
      avanzar(ms) {
        ahora += ms;
        const lista = pendientes.splice(0);
        for (const cb of lista) cb(ahora);
      },
    };
    performance.now = () => ahora;
    window.requestAnimationFrame = (cb) => { pendientes.push(cb); return pendientes.length; };
    Math.random = () => ((semilla = (semilla * 1664525 + 1013904223) % 4294967296) / 4294967296);
  });
  await pagina.goto(url);
  await pagina.waitForFunction(() => window.avatar && window.avatar.listo, null, { polling: 100 });  // rAF está parado
  // unos segundos de "calentamiento" para que muelles y respiración arranquen asentados
  await pagina.evaluate((paso) => { for (let i = 0; i < 120; i++) window.__reloj.avanzar(paso); }, 1000 / fps);

  let poseActual = null, emocionActual = null;
  for (let i = 0; i < guion.fotogramas.length; i++) {
    const f = guion.fotogramas[i];
    if ((f.brazos || null) !== poseActual) {
      poseActual = f.brazos || null;
      await pagina.evaluate((p) => window.avatar.brazos(p), poseActual);
    }
    if (f.emocion && f.emocion !== emocionActual) {
      emocionActual = f.emocion;
      await pagina.evaluate((e) => window.avatar.emocion(e), emocionActual);
    }
    const datos = await pagina.evaluate(({ f, paso }) => {
      if (f.cabeza) window.avatar.cabeza(...f.cabeza);
      window.__reloj.avanzar(paso);
      return document.querySelector('canvas').toDataURL('image/png');
    }, { f, paso: 1000 / fps });
    fs.writeFileSync(path.join(salida, `${String(i).padStart(5, '0')}.png`), Buffer.from(datos.split(',')[1], 'base64'));
    if (i % 60 === 0) process.stdout.write(`  ${i}/${guion.fotogramas.length}\r`);
  }
  await navegador.close();
  console.log(`  ${guion.fotogramas.length} fotogramas en ${salida}`);
})();
