/* ---------- Modo experimento: corre las preguntas de evaluación con el mismo agente de Claude ---------- */
(() => {
  const PREG = JSON.parse(document.getElementById('preguntas-exp').textContent);
  const caja = document.createElement('section');
  caja.className = 'panel-exp';
  caja.innerHTML = `
    <h2>Experimento: Claude con las herramientas de Universidatos</h2>
    <p>Corre las ${PREG.length} preguntas de evaluación, una por una, con el mismo agente y las mismas herramientas de la página de consulta. Tarda aproximadamente de 30 a 60 minutos; deja esta pestaña abierta. Cada respuesta se guarda al terminar, así que si cierras la página o se alcanza el límite de uso, al volver a abrirla continúa donde se quedó.</p>
    <p class="xpc-botones"><button type="button" id="xpc-correr" class="btn">Correr las preguntas</button>
      <button type="button" id="xpc-detener" class="btn-mini" hidden>Detener</button>
      <button type="button" id="xpc-bajar" class="btn-mini" hidden>Descargar resultados</button></p>
    <p id="xpc-estado" class="estado"></p>
    <div class="xpc-tabla-caja"><table id="xpc-tabla"><thead><tr><th>Id</th><th>Pregunta</th><th>Respuesta de Claude</th><th>s</th></tr></thead><tbody></tbody></table></div>`;
  document.body.prepend(caja);
  const est = t => { document.getElementById('xpc-estado').textContent = t; };
  const res = {};          // id → resultado
  let db = null, ctl = null;

  function fila(r) {
    const tb = document.querySelector('#xpc-tabla tbody');
    let tr = document.getElementById('xpc-' + r.id);
    if (!tr) { tr = document.createElement('tr'); tr.id = 'xpc-' + r.id; tb.append(tr); }
    tr.innerHTML = '';
    [r.id, r.pregunta, r.error ? 'ERROR: ' + r.error : r.respuesta, r.segundos].forEach(v => { const td = document.createElement('td'); td.textContent = v; tr.append(td); });
  }
  function hechas() { return PREG.filter(q => res[q.id]).length; }
  function guardarLocal() { try { localStorage.setItem('xpc-claude', JSON.stringify(res)); } catch (_) {} }

  async function cargar() {
    try { Object.assign(res, JSON.parse(localStorage.getItem('xpc-claude') || '{}')); } catch (_) {}
    try {
      db = await window.claude?.use?.('db');
      if (db) {
        const snap = await db.collection('resultados').get();
        snap.docs.forEach(d => { const v = d.data(); if (v && v.id) res[v.id] = v; });
      }
    } catch (_) {}
    PREG.forEach(q => res[q.id] && fila(res[q.id]));
    est(hechas() ? `Llevas ${hechas()} de ${PREG.length} preguntas.` : '');
    if (hechas()) document.getElementById('xpc-bajar').hidden = false;
    if (hechas() === PREG.length) document.getElementById('xpc-correr').textContent = 'Volver a correr las que fallaron';
  }

  async function guardar(r) {
    res[r.id] = r; guardarLocal(); fila(r);
    if (db) { try { await db.collection('resultados').doc(r.id + '_r1').set(r); } catch (e) { console.warn('db', e && e.code); } }
  }

  async function correr() {
    if (!sample) { est('Claude no está disponible en esta vista. Abre la página en claude.ai e inicia sesión.'); return; }
    const btn = document.getElementById('xpc-correr'), det = document.getElementById('xpc-detener');
    btn.disabled = true; det.hidden = false;
    ctl = new AbortController();
    const pendientes = PREG.filter(q => !res[q.id] || res[q.id].error);
    for (const q of pendientes) {
      if (ctl.signal.aborted) break;
      est(`Pregunta ${hechas() + 1} de ${PREG.length} (${q.id}): ${q.pregunta}`);
      const r0 = buscador.buscar(q.pregunta);
      const b = { t: q.pregunta, q: r0.q, resultados: r0.resultados };
      const t0 = performance.now();
      try {
        const o = await correrClaude(b, ctl.signal, t => est(`${q.id}: ${t}`));
        await guardar({ id: q.id, condicion: 'claude', repeticion: 1, modelo: 'claude (' + (o.res.modelTierApplied || 'default') + ')', modo_usado: 'herramientas',
          pregunta: q.pregunta, respuesta: String(o.res.text || '').replace(/\*\*/g, '').trim(), error: null,
          segundos: Math.round(o.segundos * 10) / 10, pasos: o.pasos.length, truncada: !!o.res.truncated, fecha: new Date().toISOString() });
      } catch (e) {
        const code = e && e.code;
        if (code === 'cancelled') break;
        if (['rate_limited', 'not_granted', 'sampling_disabled', 'tools_unavailable', 'session_expired'].includes(code)) {
          est(`Se detuvo en ${q.id}: ${MENSAJES_IA[code] || code}. Lo hecho quedó guardado; vuelve a pulsar el botón más tarde para continuar.`);
          btn.disabled = false; det.hidden = true; return;
        }
        await guardar({ id: q.id, condicion: 'claude', repeticion: 1, modelo: 'claude', modo_usado: 'herramientas', pregunta: q.pregunta,
          respuesta: e && e.text ? String(e.text) : '', error: (code || 'error') + ': ' + ((e && e.message) || ''),
          segundos: Math.round((performance.now() - t0) / 100) / 10, pasos: 0, truncada: false, fecha: new Date().toISOString() });
      }
      document.getElementById('xpc-bajar').hidden = false;
    }
    btn.disabled = false; det.hidden = true;
    est(hechas() === PREG.length ? `Listo: ${PREG.length} de ${PREG.length} preguntas. Ya puedes avisar en el chat o descargar los resultados.` : `Detenido. Llevas ${hechas()} de ${PREG.length}.`);
  }

  document.getElementById('xpc-correr').onclick = correr;
  document.getElementById('xpc-detener').onclick = () => ctl && ctl.abort();
  document.getElementById('xpc-bajar').onclick = async () => {
    const txt = PREG.filter(q => res[q.id]).map(q => JSON.stringify(res[q.id])).join('\n') + '\n';
    const blob = new Blob([txt], { type: 'text/plain' });
    try { const d = await window.claude?.use?.('downloads'); if (d) { await d.save({ filename: 'resultados_claude.jsonl', data: blob }); return; } } catch (e) { if (e && e.code === 'declined') return; }
    est('No se pudo descargar desde aquí; los resultados quedaron guardados en la página.');
  };
  cargar();
})();
