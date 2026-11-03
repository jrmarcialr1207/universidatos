/* Experimento texto a SQL con Claude: mismo esquema, reglas y ejemplos que texto_sql.py (precalculados por pregunta). */
(async () => {
  const $ = id => document.getElementById(id);
  const EXP = JSON.parse($('datos-exp').textContent);   // {reglas, ejemplos, respuesta, preguntas:[{id, pregunta, esquema}]}
  const est = t => { $('estado').textContent = t; };
  const MAX_FILAS = 60, REINTENTOS = 2;
  const res = {};
  let db = null, sql = null, sample = null, ctl = null;

  function b64(id) { const s = atob($(id).textContent.trim()), u = new Uint8Array(s.length); for (let i = 0; i < s.length; i++) u[i] = s.charCodeAt(i); return u; }
  function fila(r) {
    let tr = $('r-' + r.id);
    if (!tr) { tr = document.createElement('tr'); tr.id = 'r-' + r.id; $('tabla').tBodies[0].append(tr); }
    tr.innerHTML = '';
    [r.id, r.pregunta, r.sql || '—', r.error ? 'ERROR: ' + r.error : r.respuesta, r.segundos].forEach(v => { const td = document.createElement('td'); td.textContent = v ?? ''; tr.append(td); });
  }
  const hechas = () => EXP.preguntas.filter(q => res[q.id] && !res[q.id].error).length;
  function json(t) {
    try { return JSON.parse(t); } catch (_) {}
    const m = /\{[\s\S]*\}/.exec(t || ''); if (m) { try { return JSON.parse(m[0]); } catch (_) {} }
    const c = /```(?:sql)?\s*((?:select|with)[\s\S]*?)```/i.exec(t || ''); return c ? { sql: c[1] } : {};
  }
  function ejecutar(q) {
    const s = q.trim().replace(/;\s*$/, '').trim();
    if (!/^\s*(select|with)\b/i.test(s) || s.includes(';')) throw new Error('ValueError: Solo se permite una consulta SELECT.');
    const st = sql.prepare(s); const cols = st.getColumnNames(), filas = [];
    try { while (filas.length <= MAX_FILAS && st.step()) filas.push(st.get()); } finally { st.free(); }
    return { cols, filas };
  }
  // sample no acepta un mensaje de sistema: las reglas van al inicio del primer turno del usuario
  async function preguntar(q) {
    const t0 = performance.now();
    const turnos = [{ role: 'user', content: EXP.reglas + '\n\n' + EXP.ejemplos + '\n\n' + q.esquema + '\n\nPregunta: ' + q.pregunta }];
    const intentos = []; let consulta = null, razon = null, cols = [], filas = [], error = null;
    for (let k = 0; k <= REINTENTOS; k++) {
      const j = json((await sample(turnos, { signal: ctl.signal })).text);
      consulta = j.sql || null; razon = j.razon || null;
      if (!consulta) { intentos.push({ sql: null, razon }); break; }
      try { ({ cols, filas } = ejecutar(consulta)); error = null; }
      catch (e) { error = String(e.message || e).startsWith('ValueError') ? String(e.message) : 'OperationalError: ' + (e.message || e); cols = []; filas = []; }
      intentos.push({ sql: consulta, error, renglones: filas.length });
      if (!error && filas.length && filas[0].some(v => v !== null)) break;
      if (k === REINTENTOS) break;
      const aviso = error ? `La consulta falló con el error: ${error}. Corrígela.` : 'La consulta no devolvió datos. Revisa el espacio_id, el año, las columnas y los filtros, o responde sql null si la base no tiene el dato.';
      turnos.push({ role: 'assistant', content: JSON.stringify({ sql: consulta }) }, { role: 'user', content: aviso });
    }
    let texto;
    if (!consulta) texto = 'No es posible responder con la base de datos: ' + (razon || 'el dato no está registrado.');
    else {
      const r = error ? { error } : { columnas: cols, renglones: filas.slice(0, MAX_FILAS) };
      if (filas.length > MAX_FILAS) r.nota = `Se muestran los primeros ${MAX_FILAS} renglones.`;
      const j = json((await sample([{ role: 'user', content: EXP.respuesta + '\n\nPregunta: ' + q.pregunta + '\n\nConsulta: ' + consulta + '\n\nRESULTADO: ' + JSON.stringify(r) }], { signal: ctl.signal })).text);
      texto = String(j.respuesta || '').trim() || 'No pude redactar la respuesta.';
    }
    return { respuesta: texto, sql: consulta, intentos, segundos: Math.round((performance.now() - t0) / 100) / 10 };
  }

  async function correr() {
    if (!sample) { est('Claude no está disponible en esta vista. Abre la página en claude.ai con tu sesión iniciada.'); return; }
    $('correr').disabled = true; $('detener').hidden = false; ctl = new AbortController();
    for (const q of EXP.preguntas.filter(q => !res[q.id] || res[q.id].error)) {
      if (ctl.signal.aborted) break;
      est(`Pregunta ${hechas() + 1} de ${EXP.preguntas.length} (${q.id}): ${q.pregunta}`);
      try {
        const o = await preguntar(q);
        await guardar({ id: q.id, condicion: 'texto_sql', repeticion: 1, modelo: 'claude', modo_usado: 'texto_sql', pregunta: q.pregunta, error: null, ...o, fecha: new Date().toISOString() });
      } catch (e) {
        const code = e && e.code;
        if (code === 'cancelled') break;
        if (['rate_limited', 'not_granted', 'sampling_disabled', 'session_expired'].includes(code)) {
          est(`Se detuvo en ${q.id} (${code}). Lo hecho quedó guardado; vuelve a pulsar el botón más tarde para continuar.`); break;
        }
        await guardar({ id: q.id, condicion: 'texto_sql', repeticion: 1, modelo: 'claude', modo_usado: 'texto_sql', pregunta: q.pregunta,
          respuesta: '', sql: null, error: (code || 'error') + ': ' + ((e && e.message) || ''), segundos: 0, fecha: new Date().toISOString() });
      }
    }
    $('correr').disabled = false; $('detener').hidden = true; $('bajar').hidden = !hechas();
    if (hechas() === EXP.preguntas.length) est(`Listo: ${hechas()} de ${EXP.preguntas.length} preguntas. Ya puedes avisar en el chat.`);
  }
  async function guardar(r) {
    res[r.id] = r; fila(r);
    try { localStorage.setItem('exp-sql', JSON.stringify(res)); } catch (_) {}
    if (db) { try { await db.collection('resultados_sql').doc(r.id + '_r1').set(r); } catch (e) { console.warn('db', e && e.code); } }
  }

  $('correr').onclick = correr;
  $('detener').onclick = () => ctl && ctl.abort();
  $('bajar').onclick = async () => {
    const blob = new Blob([EXP.preguntas.filter(q => res[q.id]).map(q => JSON.stringify(res[q.id])).join('\n') + '\n'], { type: 'text/plain' });
    try { const d = await window.claude?.use?.('downloads'); if (d) await d.save({ filename: 'resultados_claude_sql.jsonl', data: blob }); } catch (_) {}
  };

  est('Cargando la base de datos…');
  try {
    const SQL = await initSqlJs({ wasmBinary: b64('wasm').buffer });
    sql = new SQL.Database(fflate.gunzipSync(b64('base')));
    const n = sql.exec("SELECT COUNT(*) FROM tablas")[0].values[0][0];
    est(`Base de datos cargada (${n} tablas). Pulsa el botón para empezar.`);
  } catch (e) { est('No se pudo cargar la base de datos: ' + (e.message || e)); return; }
  try { Object.assign(res, JSON.parse(localStorage.getItem('exp-sql') || '{}')); } catch (_) {}
  try {
    db = await window.claude?.use?.('db');
    if (db) (await db.collection('resultados_sql').get()).docs.forEach(d => { const v = d.data(); if (v && v.id) res[v.id] = v; });
  } catch (_) {}
  EXP.preguntas.forEach(q => res[q.id] && fila(res[q.id]));
  if (hechas()) { $('bajar').hidden = false; est(`Llevas ${hechas()} de ${EXP.preguntas.length} preguntas.`); }
  try { sample = await window.claude?.use?.('sample'); } catch (_) { sample = null; }
  $('correr').disabled = false;
})();
