/* ---------- IA con Claude: cada persona usa su propia cuenta (capacidad «sample») ---------- */
const Calc = (() => {
  const AMIN = ANIOS[0], AMAX = ANIOS[ANIOS.length - 1];
  class E extends Error {}
  const nombre = id => byId[id].ruta.replace(/ > /g, ' › ');
  const unid = id => {
    const dv = byId[id].derivada;
    if (dv) return (dv.op === 'proporcion' || dv.op === 'variacion_anual') ? '%' : dv.op === 'razon' ? '' : unid(dv.ids[0]);
    const r = byId[id].ruta.toLowerCase();
    if (r.includes('millones de pesos')) return 'millones de pesos';
    if (r.includes('miles de pesos')) return 'miles de pesos';
    if (/por alumn|por computadora|por tutor/.test(r)) return '';
    if (/%|porcentaje|índice|indice|eficiencia|tasa/.test(r)) return '%';
    return '';
  };
  const r = (x, d = 2) => Number.isInteger(x) ? x : Math.round(x * 10 ** d) / 10 ** d;
  const f = (x, d = 2) => r(x, d).toLocaleString('es-MX', { maximumFractionDigits: d });
  const vid = v => { v = String(v ?? '').trim(); if (!SER[v]) asegurarCelda(v); if (!SER[v]) throw new E(`No existe el indicador «${v}». Usa buscar_indicadores para encontrar el id correcto.`); return v; };
  const van = (v, def) => {
    if (v == null || v === '') return def;
    const a = Math.trunc(Number(v));
    if (!(a >= 1990 && a <= 2100)) throw new E(`Año inválido: ${v}`);
    return a;
  };
  const anios = id => Object.keys(SER[id]).map(Number).sort((a, b) => a - b);
  const valor = (id, a) => {
    if (SER[id][a] == null) { const ks = anios(id); throw new E(`${nombre(id)} no tiene dato en ${a}. Años disponibles: ${ks[0]}–${ks[ks.length - 1]}.`); }
    return SER[id][a];
  };
  const tramo = (id, d, h) => {
    d = van(d, AMIN); h = van(h, AMAX); if (d > h) [d, h] = [h, d];
    const out = {}; anios(id).forEach(a => { if (a >= d && a <= h) out[a] = SER[id][a]; });
    if (!Object.keys(out).length) throw new E(`${nombre(id)} no tiene datos entre ${d} y ${h}.`);
    return out;
  };
  const comun = ids => {
    let c = null;
    ids.forEach(i => { const s = new Set(anios(i)); c = c ? new Set([...c].filter(x => s.has(x))) : s; });
    if (!c || !c.size) throw new E('Esos indicadores no tienen ningún año en común.');
    return Math.max(...c);
  };
  const lista = v => (Array.isArray(v) ? v : v ? [v] : []);

  function evaluar(expr) {
    const s = String(expr ?? '').replace(/,/g, '').replace(/×/g, '*').replace(/÷/g, '/').replace(/\*\*/g, '^').replace(/\s+/g, '');
    if (!s || s.length > 200) throw new E('Expresión vacía o demasiado larga.');
    let i = 0;
    const num = () => { const m = s.slice(i).match(/^(\d+(\.\d+)?|\.\d+)/); if (!m) throw new E('Solo se permiten números y + - * / ^ ( ).'); i += m[0].length; return parseFloat(m[0]); };
    const prim = () => {
      if (s[i] === '(') { i++; const v = suma(); if (s[i] !== ')') throw new E('Falta cerrar un paréntesis.'); i++; return v; }
      if (s[i] === '-') { i++; return -prim(); }
      if (s[i] === '+') { i++; return prim(); }
      return num();
    };
    const pot = () => { const b = prim(); if (s[i] === '^') { i++; const e = pot(); if (Math.abs(e) > 100 || Math.abs(b) > 1e12) throw new E('Potencia demasiado grande.'); return b ** e; } return b; };
    const prod = () => { let v = pot(); while (s[i] === '*' || s[i] === '/') { const o = s[i++]; const w = pot(); v = o === '*' ? v * w : v / w; } return v; };
    const suma = () => { let v = prod(); while (s[i] === '+' || s[i] === '-') { const o = s[i++]; const w = prod(); v = o === '+' ? v + w : v - w; } return v; };
    const v = suma();
    if (i !== s.length) throw new E(`No entendí la expresión «${expr}».`);
    if (!Number.isFinite(v)) throw new E('El resultado no es un número válido.');
    return v;
  }

  const OPS = ['valor', 'cambio', 'crecimiento_anual_promedio', 'promedio', 'maximo', 'minimo', 'suma', 'proporcion', 'razon', 'diferencia', 'expresion'];
  const TIPOS = ['linea', 'barras', 'comparar_anio', 'cambio_anios'];
  const OPS_SERIE = ['razon', 'proporcion', 'diferencia', 'suma', 'variacion_anual'];
  let nSeries = 0;
  const sinAcentos = t => String(t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim().replace(/\s+/g, '_');

  const ladoEspacios = (spec, nombreLado) => {
    const nn = Buscador.norm;
        const partes = Array.isArray(spec) ? spec : [spec];
        if (!partes.length || !partes[0]) throw new E(`Indica «${nombreLado}» como lista de {tabla, columnas}.`);
        const out = new Map();
        partes.forEach(pt => {
          const T = TAB[String(pt.tabla || '').trim().toUpperCase()];
          if (!T || T.tipo === 'lista') throw new E(`«${pt.tabla}» no es una tabla numérica. Usa buscar_tablas.`);
          const nombres = T.columnas.map(c => c.join(' › '));
          const js = lista(pt.columnas).map(q => { const qn = nn(q); let j = nombres.findIndex(x => nn(x) === qn); if (j < 0) { const c = nombres.map((x, k) => k).filter(k => nn(nombres[k]).includes(qn)); if (c.length === 1) j = c[0]; }
            if (j < 0) throw new E(`En ${T.id} no hay una columna única «${q}». Columnas: ${nombres.join('; ')}`); return j; });
          const as = Object.keys(T.datos).sort(), a = as[as.length - 1], mat = T.datos[a];
          // tablas con bloques (p. ej. PTC / no PTC): se usa un solo bloque, el primero o el primero que coincida con «bloque»
          const GR = /^(escuela|facultad|plantel|centro|unidad|instituto|dependencia)/;
          const gruposDe = {}; T.filas.forEach(f => { const r = f.ruta; if (r.length > 2 && GR.test(nn(r[1])) && !GR.test(nn(r[0]))) (gruposDe[r[0]] = gruposDe[r[0]] || new Set()).add(nn(r[1])); });
          const bloques = Object.keys(gruposDe), todos = bloques.flatMap(b => [...gruposDe[b]]);
          const juntar = todos.length === new Set(todos).size;  // bloques por nivel educativo (grupos distintos): se usan todos
          const blq = pt.bloque ? nn(pt.bloque) : null, vistos = new Set();
          const elegido = blq ? bloques.find(b => nn(b).includes(blq)) : bloques[0];
          if (blq && bloques.length && !elegido) throw new E(`En ${T.id} no hay un bloque «${pt.bloque}». Bloques: ${bloques.join('; ')}`);
          T.filas.forEach((f, i) => {
            const r = f.ruta; if (r.length < 2) return;
            if (r.length > 2 && bloques.includes(r[0]) && r[0] !== elegido && !(juntar && !blq)) return;
            const g = r[r.length - 2].replace(/\s*\*+$/, '').trim(), e = r[r.length - 1].trim();
            if (!/^(escuela|facultad|plantel|centro|unidad|instituto|dependencia)/.test(nn(g))) return;
            const k = nn(g).split(' ')[0] + '|' + nn(e);
            const kk = T.id + k; if (vistos.has(kk)) return; vistos.add(kk);  // con bloques, solo el primero (o el pedido)
            const ids = js.filter(j => mat[i] && mat[i][j] != null).map(j => `${T.id}.f${i}.c${j}`); if (!ids.length) return;
            const prev = out.get(k) || { ids: [], v: 0, nombre: `${e} (${g})`, grupo: nn(g) };
            prev.ids.push(...ids); prev.v += js.reduce((s2, j) => s2 + ((mat[i] && mat[i][j]) || 0), 0); out.set(k, prev);
          });
        });
        return out;
      };

  const H = {
    buscar_indicadores({ texto = '' }) {
      const res = buscador.buscar(String(texto), 15).resultados;
      if (!res.length) throw new E(`No encontré indicadores con «${texto}». Prueba con otras palabras clave.`);
      return { descripcion: `Buscó indicadores con «${texto}» (${res.length} encontrados)`,
        resultados: res.map(x => ({ id: x.id, indicador: nombre(x.id), eje: byId[x.id].eje })) };
    },
    obtener_valores({ ids, desde, hasta }) {
      const l = lista(ids).map(vid).slice(0, 8);
      if (!l.length) throw new E('Indica al menos un id.');
      const series = l.map(id => {
        const t = tramo(id, desde, hasta);
        return { id, indicador: nombre(id), unidad: unid(id), valores: Object.fromEntries(Object.entries(t).map(([a, v]) => [a, r(v)])) };
      });
      return { descripcion: 'Consultó valores de: ' + series.map(s => s.indicador).join('; '), series };
    },
    calcular({ operacion = '', id, id2, ids, anio, desde, hasta, expresion }) {
      let op = sinAcentos(operacion);
      op = { variacion: 'cambio', tcma: 'crecimiento_anual_promedio', tasa_de_crecimiento: 'crecimiento_anual_promedio', media: 'promedio' }[op] || op;
      if (!OPS.includes(op)) throw new E(`Operación desconocida «${operacion}». Usa una de: ${OPS.join(', ')}.`);
      if (op === 'expresion') { const v = evaluar(expresion); return { descripcion: `Calculó ${expresion} = ${f(v, 4)}`, resultado: r(v, 4) }; }
      if (op === 'suma') {
        const l = (Array.isArray(ids) ? ids : [id, id2].filter(Boolean)).map(vid);
        if (l.length < 2) throw new E('Para sumar indica al menos dos ids en «ids».');
        const a = van(anio) || comun(l);
        const total = l.reduce((t, i) => t + valor(i, a), 0);
        return { descripcion: `Sumó ${l.length} indicadores en ${a} = ${f(total)}`, anio: a,
          partes: Object.fromEntries(l.map(i => [nombre(i), r(valor(i, a))])), resultado: r(total) };
      }
      if (['proporcion', 'razon', 'diferencia'].includes(op)) {
        const A = vid(id), B = vid(id2), a = van(anio) || comun([A, B]);
        const va = valor(A, a), vb = valor(B, a);
        let res, txt;
        if (op === 'diferencia') { res = va - vb; txt = 'Diferencia'; }
        else { if (vb === 0) throw new E('El segundo indicador vale 0 ese año; no se puede dividir.'); res = va / vb * (op === 'proporcion' ? 100 : 1); txt = op === 'proporcion' ? 'Proporción (%)' : 'Razón'; }
        return { descripcion: `${txt} de ${nombre(A)} entre ${nombre(B)} en ${a} = ${f(res)}`, anio: a, valor_1: r(va), valor_2: r(vb), resultado: r(res), ...(op === 'proporcion' ? { unidad: '%' } : {}) };
      }
      const I = vid(id), t = tramo(I, desde, hasta), as = Object.keys(t).map(Number);
      const base = { indicador: nombre(I), unidad: unid(I) };
      const a1 = as[0], a2 = as[as.length - 1], v1 = t[a1], v2 = t[a2];
      if (op === 'valor') { const a = van(anio, a2), v = valor(I, a); return { ...base, descripcion: `${nombre(I)} en ${a} = ${f(v)}`, anio: a, resultado: r(v) }; }
      if (op === 'cambio') {
        const res = { ...base, desde: a1, valor_desde: r(v1), hasta: a2, valor_hasta: r(v2), cambio: r(v2 - v1) };
        if (v1 && base.unidad !== '%') res.cambio_porcentual = r((v2 - v1) / v1 * 100);
        res.descripcion = `Cambio de ${nombre(I)} de ${a1} (${f(v1)}) a ${a2} (${f(v2)}): ${f(v2 - v1)}` + (res.cambio_porcentual != null ? ` (${f(res.cambio_porcentual)}%)` : base.unidad === '%' ? ' puntos' : '');
        return res;
      }
      if (op === 'crecimiento_anual_promedio') {
        if (a1 === a2) throw new E('Se necesitan al menos dos años distintos.');
        if (v1 <= 0 || v2 <= 0) throw new E('El crecimiento compuesto requiere valores positivos en ambos años.');
        const tc = ((v2 / v1) ** (1 / (a2 - a1)) - 1) * 100;
        return { ...base, descripcion: `Crecimiento anual promedio de ${nombre(I)} ${a1}–${a2} = ${f(tc)}% por año`,
          desde: a1, valor_desde: r(v1), hasta: a2, valor_hasta: r(v2), anios_transcurridos: a2 - a1, resultado: r(tc), unidad_resultado: '% anual' };
      }
      if (op === 'promedio') { const m = Object.values(t).reduce((s, v) => s + v, 0) / as.length;
        return { ...base, descripcion: `Promedio de ${nombre(I)} ${a1}–${a2} (${as.length} años con dato) = ${f(m)}`, desde: a1, hasta: a2, anios_con_dato: as.length, resultado: r(m) }; }
      const a = as.reduce((m, k) => (op === 'maximo' ? t[k] > t[m] : t[k] < t[m]) ? k : m, as[0]);
      return { ...base, descripcion: `${op === 'maximo' ? 'Máximo' : 'Mínimo'} de ${nombre(I)} ${a1}–${a2}: ${f(t[a])} en ${a}`, anio: a, resultado: r(t[a]) };
    },
    buscar_tablas({ texto = '' }) {
      const res = rankTablas(String(texto)).slice(0, 5);
      if (!res.length) throw new E(`No encontré tablas con «${texto}». Tablas disponibles: ` + Object.values(TAB).map(T => `${T.id} ${T.titulo}`).join('; '));
      return { descripcion: `Buscó tablas con «${texto}» (${res.length} encontradas)`,
        tablas: res.map(x => { const T = TAB[x.id];
          if (T.tipo === 'lista') { const a = Object.keys(T.renglones).sort().pop();
            return { tabla: T.id, tipo: 'lista de texto', titulo: T.titulo, anios: Object.keys(T.renglones).map(Number), renglones: (T.renglones[a] || []).length,
              columnas: T.encabezados[a], renglones_que_coinciden: x.filas.length }; }
          return {
          tabla: T.id, tipo: 'numérica', titulo: T.titulo, anios: Object.keys(T.datos).map(Number), filas: T.filas.length,
          grupos: T.filas.filter((f, i) => T.filas.some(g => g.ruta.length > f.ruta.length && g.ruta.slice(0, f.ruta.length).join('|') === f.ruta.join('|'))).map(f => f.ruta.join(' › ')).slice(0, 15),
          columnas: T.columnas.map((c, j) => ({ c: j, columna: c.join(' › ') })).slice(0, 40),
          filas_que_coinciden: x.filas.slice(0, 10).map(i => ({ f: i, fila: T.filas[i].ruta.join(' › ') })) }; }) };
    },
    consultar_tabla({ tabla, grupo, filas, columnas, anio }) {
      const T = TAB[String(tabla || '').trim().toUpperCase()];
      if (!T) throw new E(`No existe la tabla «${tabla}». Usa buscar_tablas.`);
      if (T.tipo === 'lista') {
        const as = Object.keys(T.renglones).sort(), a = String(van(anio, +as[as.length - 1]));
        if (!T.renglones[a]) throw new E(`La tabla ${T.id} no tiene datos de ${a}. Años disponibles: ${as.join(', ')}.`);
        const enc = T.encabezados[a], qs = [...lista(filas), ...lista(grupo)].map(Buscador.norm).filter(Boolean);
        let rs = T.renglones[a].filter(r => !qs.length || qs.every(q => Buscador.norm(r.join(' ')).includes(q)));
        const total = rs.length; rs = rs.slice(0, 150);
        return { descripcion: `Consultó la lista ${T.id} «${T.titulos[a]}»: ${total} renglones`, tabla: T.id, tipo: 'lista de texto', titulo: T.titulos[a], anio: +a,
          renglones_encontrados: total, renglones: rs.map(r => Object.fromEntries(enc.map((h, k) => [h, r[k] || '']))),
          aviso: (total > 150 ? 'Se muestran los primeros 150; filtra con «filas» para ver otros. ' : '') + 'Es una lista de texto: no se grafica. Cuenta renglones si necesitas cantidades.',
          notas: (T.notas[a] || []).slice(0, 4), fuente: T.fuente[a] };
      }
      const anios = Object.keys(T.datos).sort();
      const a = String(van(anio, +anios[anios.length - 1]));
      const mat = T.datos[a];
      if (!mat) throw new E(`La tabla ${T.id} no tiene datos de ${a}. Años disponibles: ${anios.join(', ')}.`);
      const nn = Buscador.norm;
      let fs = T.filas.map((x, i) => i);
      if (grupo) {
        const g = nn(grupo);
        fs = fs.filter(i => { const r = T.filas[i].ruta; return r.length > 1 && nn(r[r.length - 2]).includes(g); });
        if (!fs.length) throw new E(`No hay filas dentro del grupo «${grupo}». Grupos de la tabla: ` + [...new Set(T.filas.filter(f => f.ruta.length > 1).map(f => f.ruta[f.ruta.length - 2]))].join('; '));
      }
      if (filas) {
        const fl = lista(filas).map(nn);
        fs = fs.filter(i => fl.some(q => nn(T.filas[i].ruta.join(' ')).includes(q)));
        if (!fs.length) throw new E(`Ninguna fila coincide con ${JSON.stringify(filas)}.`);
      }
      let cs = T.columnas.map((x, j) => j);
      if (columnas) {
        const cl = lista(columnas).map(nn);
        cs = cs.filter(j => cl.some(q => nn(T.columnas[j].join(' ')).includes(q)));
        if (!cs.length) throw new E(`Ninguna columna coincide con ${JSON.stringify(columnas)}. Columnas: ` + T.columnas.map(c => c.join(' › ')).join('; '));
      }
      if (fs.length * cs.length > 240) throw new E(`La consulta tiene ${fs.length * cs.length} celdas; filtra con «grupo», «filas» o «columnas» (máximo 240). Columnas: ` + T.columnas.map(c => c.join(' › ')).join('; '));
      const celdas = [];
      fs.forEach(f => cs.forEach(c => { const v = mat[f] && mat[f][c]; if (v == null) return;
        celdas.push({ id: `${T.id}.f${f}.c${c}`, fila: T.filas[f].ruta.join(' › '), columna: (((T.columnas_anio || {})[a] || {})[c] || T.columnas[c]).join(' › '), valor: v }); }));
      const ns = (T.no_sumables || []).map(j => T.columnas[j].join(' › '));
      return { descripcion: `Consultó la tabla ${T.id} «${T.titulos[a]}»: ${celdas.length} celdas`, tabla: T.id, titulo: T.titulos[a], anio: +a, anios_disponibles: anios.map(Number), celdas,
        notas: (T.notas[a] || []).slice(0, 4), fuente: T.fuente[a],
        aviso: 'Las celdas vacías en la tabla original se leen como 0.' + (ns.length ? ` Estas columnas son promedios y no se suman: ${ns.join('; ')}.` : '') };
    },
    ordenar_filas({ tabla, columna, nivel = 'programa', grupo, sumar_sedes = false, orden = 'mayor', n = 15, anio }) {
      const T = TAB[String(tabla || '').trim().toUpperCase()];
      if (!T) throw new E(`No existe la tabla «${tabla}». Usa buscar_tablas.`);
      if (T.tipo === 'lista') throw new E(`La tabla ${T.id} es una lista de texto; usa consultar_tabla.`);
      const as = Object.keys(T.datos).sort(), a = String(van(anio, +as[as.length - 1])), mat = T.datos[a];
      if (!mat) throw new E(`La tabla ${T.id} no tiene datos de ${a}. Años disponibles: ${as.join(', ')}.`);
      const nn = Buscador.norm, F = T.filas;
      let c = T.columnas.findIndex(x => x.length === 1 && x[0] === 'Total');
      if (columna) {
        const q = nn(columna), cand = T.columnas.map((x, j) => j).filter(j => nn(T.columnas[j].join(' ')).includes(q));
        if (!cand.length) throw new E(`Ninguna columna coincide con «${columna}». Columnas: ` + T.columnas.map(x => x.join(' › ')).join('; '));
        c = cand.find(j => T.columnas[j][T.columnas[j].length - 1] === 'Total') ?? cand[0];
      }
      if (c < 0) c = T.columnas.findIndex(x => x[x.length - 1] === 'Total');
      if (c < 0) c = T.columnas.length - 1;
      const tieneHijos = i => F.some(g => g.ruta.length > F[i].ruta.length && F[i].ruta.every((x, k) => g.ruta[k] === x));
      const GR = /^(escuela|facultad|plantel|centro|unidad|instituto|dependencia)/;
      const kGrupo = r => r.findIndex(x => GR.test(nn(x)));  // posición del grupo (después de un posible bloque por nivel)
      const esEsp = i => { const r = F[i].ruta, k = kGrupo(r); return k >= 0 && r.length === k + 2; };
      let fs = F.map((x, i) => i).filter(i => nivel === 'espacio' ? esEsp(i) : (F[i].ruta.length >= 3 && !tieneHijos(i) && !esEsp(i)));
      if (grupo) { const g = nn(grupo); fs = fs.filter(i => nn(F[i].ruta.slice(0, -1).join(' ')).includes(g)); }
      let ds = fs.map(i => [i, mat[i] && mat[i][c]]).filter(d => d[1] != null);
      if (ds.length < 2) throw new E('No hay suficientes filas con dato para ordenar con esos filtros.');
      const menor = sinAcentos(orden).startsWith('men'), k = Math.max(2, Math.min(30, Math.trunc(n) || 15));
      const cmp = (x, y) => menor ? x - y : y - x;
      const col = T.columnas[c].join(' › ');
      const sede = i => { const r = F[i].ruta, k = kGrupo(r); return k >= 0 && r.length > k + 1 ? r[k + 1].trim() : (r.length > 1 ? r[1].trim() : ''); };  // el espacio académico
      const prog = i => F[i].ruta[F[i].ruta.length - 1].trim().replace(/\s*\(\d+\)$/, '');
      const ns = (T.no_sumables || []).includes(c);
      if (sumar_sedes && !ns && nivel !== 'espacio') {
        const gr = new Map();
        ds.forEach(([i]) => { const key = nn(prog(i)); if (!gr.has(key)) gr.set(key, []); gr.get(key).push(i); });
        const sumas = [...gr.values()].map(idx => {
          const ids = idx.map(i => `${T.id}.f${i}.c${c}`); ids.forEach(asegurarCelda);
          if (ids.length === 1) return { id: ids[0], programa: prog(idx[0]), sedes: [sede(idx[0])], valor: mat[idx[0]][c] };
          return { ids, programa: prog(idx[0]), sedes: idx.map(sede), valor: idx.reduce((s, i) => s + mat[i][c], 0) };
        }).sort((x, y) => cmp(x.valor, y.valor)).slice(0, k);
        sumas.forEach(sm => { if (sm.ids) { const res = H.calcular_serie({ operacion: 'suma', ids: sm.ids, nombre: `${sm.programa} (todas las sedes)` }); sm.id = res.id; delete sm.ids; } });
        return { descripcion: `Ordenó ${gr.size} programas de la tabla ${T.id} sumando sus sedes («${col}», ${a})`, tabla: T.id, titulo: T.titulos[a], anio: +a, columna: col,
          criterio: 'mismo programa sumado en todas las sedes donde se imparte', total_programas: gr.size,
          resultado: sumas.map(sm => ({ id: sm.id, programa: sm.programa, valor: r(sm.valor), numero_de_sedes: sm.sedes.length, sedes: sm.sedes })),
          series: sumas.map(sm => ({ id: sm.id })), fuente: T.fuente[a] };
      }
      ds.sort((x, y) => cmp(x[1], y[1]));
      const top = ds.slice(0, k).map(([i, v]) => { const id = `${T.id}.f${i}.c${c}`; asegurarCelda(id); const rr = F[i].ruta; return nivel === 'espacio' ? { id, espacio: rr[rr.length - 1], grupo: rr[rr.length - 2], valor: r(v) } : { id, programa: prog(i), espacio: sede(i), valor: r(v) }; });
      return { descripcion: `Ordenó ${ds.length} ${nivel === 'espacio' ? 'espacios' : 'programas'} de la tabla ${T.id} por «${col}» (${a})`, tabla: T.id, titulo: T.titulos[a], anio: +a, columna: col,
        criterio: nivel === 'espacio' ? 'cada espacio académico' : 'cada programa contado por separado en cada espacio académico (sin sumar sedes)', filas_ordenadas: ds.length,
        resultado: top, series: top.map(x => ({ id: x.id })), fuente: T.fuente[a],
        aviso: ns ? 'Esta columna es un promedio o índice: no se suma entre sedes.' : undefined };
    },
    cambio_espacios({ partes, desde, hasta, grupo, titulo = '' }) {
      // cambio de un indicador entre dos años en cada espacio académico (las partes se suman: p. ej. matrícula = A26 + A40 + A15)
      const L = ladoEspacios(partes, 'partes'), nn = Buscador.norm, g = grupo ? nn(grupo) : null;
      const filas = [];
      L.forEach((x, k) => {
        if (g && !x.grupo.includes(g)) return;
        x.ids.forEach(asegurarCelda);
        const anios = [...new Set(x.ids.flatMap(i => Object.keys(SER[i] || {})))].map(Number).sort((a, b) => a - b);
        const suma = a => { const vs = x.ids.map(i => SER[i]?.[a]); return vs.some(v => v != null) ? vs.reduce((t, v) => t + (v || 0), 0) : null; };
        filas.push({ x, anios, suma });
      });
      const todos = [...new Set(filas.flatMap(f => f.anios))].sort((a, b) => a - b);
      const h = van(hasta) || todos[todos.length - 1], d = van(desde) || Math.max(...todos.filter(a => a < h));
      if (!isFinite(d) || d === h) throw new E('No hay dos años distintos con datos para comparar; indica «desde» y «hasta».');
      const ok = [], sin = [];
      filas.forEach(f => { const v0 = f.suma(d), v1 = f.suma(h); if (v0 == null || v1 == null) sin.push(f.x.nombre); else ok.push({ ...f, v0, v1 }); });
      if (ok.length < 2) throw new E(`No hay espacios con dato en ${d} y en ${h}.`);
      ok.sort((a, b) => (b.v1 - b.v0) - (a.v1 - a.v0));
      const ids = ok.map(f => {  // una serie por espacio con su nombre completo (un año sin posgrado suma 0, no se pierde)
        const vals = {}; f.anios.forEach(a => { const v = f.suma(a); if (v != null) vals[a] = r(v); });
        const nid = 'S' + (++nSeries); SER[nid] = vals;
        byId[nid] = { id: nid, ruta: f.x.nombre, concepto: f.x.nombre, eje: 'Serie calculada', archivo: 'calc', fila_excel: '', derivada: { op: 'suma', ids: f.x.ids, formula: f.x.ids.join(' + ') } };
        return nid;
      });
      const t0 = ok.reduce((t, f) => t + f.v0, 0), t1 = ok.reduce((t, f) => t + f.v1, 0);
      const sg = v => (v >= 0 ? '+' : '−') + Math.abs(r(v)).toLocaleString('es-MX'), pc = (a, b) => a ? `${b >= a ? '+' : '−'}${Math.abs(r((b - a) / a * 100))}%` : '';
      const tit = (titulo || `Cambio por espacio, ${d}–${h}`).slice(0, 120);
      const tabla = { titulo: tit, encabezados: ['Espacio', String(d), String(h), 'Cambio', '%'],
        filas: ok.map(f => ({ nombre: f.x.nombre, ids: [{ texto: r(f.v0).toLocaleString('es-MX') }, { texto: r(f.v1).toLocaleString('es-MX') }, { texto: sg(f.v1 - f.v0) }, { texto: pc(f.v0, f.v1) }] })),
        fuente: `Fuente: Agenda Estadística ${d} y ${h}, tablas ${[...new Set(lista(partes).map(p => String(p.tabla).toUpperCase()))].join(' + ')}.` };
      return { descripcion: `Comparó ${d} y ${h} en ${ok.length} espacios`, tabla,
        grafica: { tipo: 'cambio_anios', ids: ids.slice(0, 80), desde: d, hasta: h, titulo: tit },
        suma_espacios: { [d]: r(t0), [h]: r(t1), cambio: r(t1 - t0) }, subieron: ok.filter(f => f.v1 > f.v0).length, bajaron: ok.filter(f => f.v1 < f.v0).length,
        mayores_aumentos: ok.slice(0, 6).map(f => [f.x.nombre, r(f.v0), r(f.v1), r(f.v1 - f.v0)]),
        mayores_disminuciones: [...ok].reverse().filter(f => f.v1 < f.v0).slice(0, 6).map(f => [f.x.nombre, r(f.v0), r(f.v1), r(f.v1 - f.v0)]),
        sin_dato_en_un_anio: sin.slice(0, 15), series: ids.map(id => ({ id })),
        aviso: 'La gráfica de cambio y la tabla completa se muestran al usuario. El cuarto número de cada espacio es el cambio: positivo = subió, negativo = bajó.' };
    },
    dato_fichas({ concepto, tipo }) {
      // un mismo dato (p. ej. «Año de fundación») en todas las fichas por espacio
      const nn = Buscador.norm, cq = nn(String(concepto || '')).split(/\s+/).filter(w => w.length >= 3 && !['del', 'las', 'los'].includes(w));
      if (!cq.length) throw new E('Indica el dato, p. ej. «Año de fundación» o «Computadoras».');
      const TIPOS = { O: 'Organismo académico', U: 'Centro universitario UAEM', V: 'Unidad académica profesional', N: 'Instituto o centro de investigación', B: 'Plantel de la Escuela Preparatoria' };
      const tf = tipo ? Object.keys(TIPOS).filter(k => nn(TIPOS[k]).includes(nn(tipo).slice(0, 6)) || (k === 'O' && /facult|escuel/.test(nn(tipo)))) : null;
      const filas = [];
      Object.values(TAB).forEach(T => {
        if (T.seccion !== 'Fichas por espacio' || (tf && tf.length && !tf.includes(T.id[0]))) return;
        const a = Object.keys(T.renglones).sort().pop();
        const r = T.renglones[a].find(x => cq.every(w => nn(x[0] + ' ' + x[1]).includes(w)));
        if (r) filas.push({ ficha: T.id, espacio: T.titulo, tipo: TIPOS[T.id[0]], concepto: r[1], valor: r[2] });
      });
      if (!filas.length) throw new E(`No encontré «${concepto}» en las fichas por espacio.`);
      const anio = v => { const m = String(v).match(/(18|19|20)\d{2}/); return m ? +m[0] : null; };
      if (filas.every(f => anio(f.valor))) filas.sort((x, y) => anio(x.valor) - anio(y.valor) || x.espacio.localeCompare(y.espacio));
      else if (filas.every(f => !isNaN(+f.valor))) filas.sort((x, y) => +y.valor - +x.valor);
      const tabla = { titulo: `${filas[0].concepto} por espacio universitario`, encabezados: ['Espacio', 'Tipo de espacio', filas[0].concepto],
        filas: filas.map(f => ({ nombre: f.espacio, ids: [{ texto: f.tipo }, { texto: String(f.valor) }] })),
        fuente: 'Fuente: Agenda Estadística 2025, fichas por espacio (O, U, V, N y B).' };
      return { descripcion: `Reunió «${filas[0].concepto}» de ${filas.length} fichas por espacio`, tabla, resultado: filas,
        aviso: 'La tabla completa se muestra al usuario. Si un valor trae dos años (p. ej. «1986 / 2008*»), la ficha explica el cambio en sus notas.' };
    },
    donde_se_imparte({ programa, nivel, grupo }) {
      // busca un programa por nombre en la matrícula por espacio y programa (A26 licenciatura, A39 posgrado)
      const nn = Buscador.norm, VAC = new Set('de la el en los las del y e para con a al por su sus un una'.split(' '));
      const toks = x => new Set(nn(x).replace(/\(.*?\)/g, ' ').replace(/^(especialidad|especializacion|maestria|doctorado|licenciatura)\s+((en|de)\s+)?/, '').split(/[^a-z0-9]+/).filter(w => w && !VAC.has(w) && w !== 'licenciatura').map(w => w.slice(0, 5)));
      const nivelDe = x => { const m = nn(x).match(/^(especialidad|especializacion|maestria|doctorado)/); return m ? ({ especializacion: 'especialidad' }[m[1]] || m[1]) : 'licenciatura'; };
      const tq = toks(String(programa || '')); if (!tq.size) throw new E('Indica el nombre del programa, p. ej. «Derecho».');
      const nv = nivel ? sinAcentos(nivel) : null, g = grupo ? nn(grupo) : null;
      const fuentes = ['A26', 'A39'].filter(t => TAB[t] && (!nv || (nv.startsWith('lic') ? t === 'A26' : t === 'A39')));
      const progs = new Map(), nombres = new Map();
      fuentes.forEach(tid => {
        const T = TAB[tid], at = Object.keys(T.datos).sort().pop(), mat = T.datos[at], ct = T.columnas.findIndex(c => c.length === 1 && c[0] === 'Total');
        const rutas = T.filas.map(f => f.ruta);
        rutas.forEach((r, i) => {
          if (r.length < 3 || rutas.some(x => x.length > r.length && r.every((y, k) => x[k] === y))) return;
          let nombre = r[r.length - 1].trim().replace(/\s*\(?\d+\)?$|\*+$/, '').trim();
          if (nv && !nv.startsWith('lic') && nivelDe(nombre) !== nv.slice(0, 5) && !nivelDe(nombre).startsWith(nv.slice(0, 5))) return;
          const tr = toks(nombre); if (![...tq].every(w => tr.has(w))) return;
          const esp = `${r[1].trim()} (${r[0].trim()})`; if (g && !nn(esp).includes(g)) return;
          const clave = nivelDe(nombre) + '|' + [...tr].sort().join(' ') + '|' + (nn(nombre).includes('distancia') ? 'd' : '');
          if (!nombres.has(clave)) nombres.set(clave, nombre); nombre = nombres.get(clave);
          if (!progs.has(nombre)) progs.set(nombre, new Map());
          const d = progs.get(nombre), prev = d.get(esp) || { ids: [], v: 0 };
          if (ct >= 0 && mat[i] && mat[i][ct] != null) { prev.ids.push(`${tid}.f${i}.c${ct}`); prev.v += mat[i][ct]; }
          d.set(esp, prev);
        });
      });
      if (!progs.size) throw new E(`No encontré programas con «${programa}» en la matrícula (A26, A39).`);
      const exactos = [...progs.keys()].filter(n => { const t = toks(n); return t.size === tq.size && [...tq].every(w => t.has(w)); });
      const principal = exactos.length ? exactos : [...progs.keys()], otros = [...progs.keys()].filter(n => !principal.includes(n));
      const filas = [], resumen = [];
      principal.sort((a, b) => progs.get(b).size - progs.get(a).size).forEach(n => {
        const d = [...progs.get(n).entries()].sort((a, b) => b[1].v - a[1].v);
        resumen.push({ programa: n, espacios: d.length, detalle: d.map(([e, x]) => [e, r(x.v)]) });
        d.forEach(([e, x]) => { x.ids.forEach(asegurarCelda); const sid = x.ids.length === 1 ? x.ids[0] : (x.ids.length ? H.calcular_serie({ operacion: 'suma', ids: x.ids, nombre: `${n} en ${e}` }).id : null);
          filas.push({ nombre: e, ids: [{ texto: n }, sid] }); });
      });
      const tabla = { titulo: `Espacios donde se ofrece: ${principal.slice(0, 3).join(', ')}`.slice(0, 140), encabezados: ['Espacio académico', 'Programa', 'Matrícula'], filas,
        fuente: 'Fuente: Agenda Estadística 2025, matrícula por espacio y programa educativo (tablas A26 y A39).' };
      return { descripcion: `Buscó «${programa}» en ${fuentes.join(' y ')}: ${principal.length} programa(s) en ${filas.length} renglones`, tabla,
        programas: resumen.slice(0, 8), otros_relacionados: otros.slice(0, 10).map(n => [n, progs.get(n).size]),
        series: filas.map(f => f.ids[1]).filter(Boolean).map(id => ({ id })), aviso: 'Cuenta los espacios con matrícula registrada en la Agenda 2025. La tabla se muestra al usuario.' };
    },
    matricula_programas_lista({ lista = 'A08', tabla = 'A39', por_espacio = false, espacio }) {
      // cruza una lista de programas (nivel, nombre) con la matrícula por programa, emparejando por nombre y nivel
      const L = TAB[String(lista).toUpperCase()], T = TAB[String(tabla).toUpperCase()];
      if (!L || L.tipo !== 'lista') throw new E(`«${lista}» no es una lista de programas.`);
      if (!T || T.tipo === 'lista') throw new E(`«${tabla}» no es una tabla de matrícula.`);
      const nn = Buscador.norm, VAC = new Set('de la el en los las del y e para con a al por su sus un una'.split(' '));
      const NIV = { especialidad: 'especialidad', especializacion: 'especialidad', maestria: 'maestria', doctorado: 'doctorado' };
      const TXT = { especialidad: 'Especialidad', maestria: 'Maestría', doctorado: 'Doctorado' };
      const toks = x => new Set(nn(x).replace(/\(.*?\)/g, ' ').replace(/^(especialidad|especializacion|maestria|doctorado)\s+(en\s+)?/, '').split(/[^a-z0-9]+/).filter(w => w && !VAC.has(w)));
      const nivel = x => { const m = nn(x).match(/^(especialidad|especializacion|maestria|doctorado)/); return m ? NIV[m[1]] : null; };
      const al = Object.keys(L.renglones).sort().pop(), at = Object.keys(T.datos).sort().pop(), mat = T.datos[at];
      const ct = T.columnas.findIndex(c => c.length === 1 && c[0] === 'Total'); if (ct < 0) throw new E(`${T.id} no tiene columna Total.`);
      const rows = L.renglones[al].filter(r => r.length > 1 && r[1] && !/^\d+$/.test(String(r[1]).trim())).map(r => [NIV[nn(r[0])] || nn(r[0]), r[1]]);
      const hojas = T.filas.map((f, i) => [i, f.ruta]).filter(([i, r]) => nivel(r[r.length - 1]));
      const filas = [], sin = [], aprox = [], idsTot = [], porEsp = [], fe = espacio ? nn(espacio) : null;
      rows.forEach(([nv, nom]) => {
        const tq = toks(nom); let c = [];
        hojas.forEach(([i, r]) => { if (nivel(r[r.length - 1]) !== nv) return; const tr = toks(r[r.length - 1]); if (!tq.size || !tr.size) return;
          const inter = [...tq].filter(w => tr.has(w)).length, uni = new Set([...tq, ...tr]).size, mn = Math.min(tq.size, tr.size);
          c.push([Math.max(inter / uni, mn >= 2 ? 0.95 * inter / mn : 0), i, r]); });
        c.sort((x, y) => y[0] - x[0]);
        let sel = c.filter(x => x[0] >= 0.75), esAprox = false;
        if (!sel.length) { const sub = c.filter(x => [...toks(x[2][x[2].length - 1])].every(w => tq.has(w))); if (new Set(sub.map(x => nn(x[2][x[2].length - 1]))).size === 1) { sel = sub; esAprox = true; } }
        const etq = `${TXT[nv] || nv} en ${nom}`;
        if (!sel.length) { sin.push(etq); return; }
        const ok = nn(sel[0][2][sel[0][2].length - 1]), mejor = sel[0][0];
        const idx = sel.filter(x => (esAprox || x[0] >= mejor - 0.05) && nn(x[2][x[2].length - 1]) === ok).map(x => x[1]).filter(i => mat[i] && mat[i][ct] != null);
        if (!idx.length) { sin.push(etq); return; }
        if (por_espacio || fe) {  // un renglón por espacio donde se imparte
          let alguno = false;
          idx.forEach(i => { const rr = T.filas[i].ruta; if (fe && !nn(rr[1]).includes(fe) && !nn(rr[0]).includes(fe)) return;
            const id = `${T.id}.f${i}.c${ct}`; asegurarCelda(id); alguno = true;
            porEsp.push({ esp: `${rr[1].trim()} (${rr[0].trim()})`, g: rr[0], prog: etq + (esAprox ? ' (aproximado)' : ''), id, v: mat[i][ct] }); });
          if (esAprox && alguno) aprox.push(etq);
          return;
        }
        const ids = idx.map(i => `${T.id}.f${i}.c${ct}`); ids.forEach(asegurarCelda);
        const sid = ids.length === 1 ? ids[0] : H.calcular_serie({ operacion: 'suma', ids, nombre: `${etq}: matrícula` }).id; idsTot.push(sid);
        const sedes = [...new Set(idx.map(i => T.filas[i].ruta[1].trim()))].join(', '), n39 = T.filas[idx[0]].ruta[T.filas[idx[0]].ruta.length - 1].trim();
        filas.push({ nombre: etq, ids: [sid, { texto: sedes }, { texto: n39 + (esAprox ? ' (aproximado)' : '') }], v: idx.reduce((s2, i) => s2 + mat[i][ct], 0) });
        if (esAprox) aprox.push(`${etq} → «${n39}»`);
      });
      if (por_espacio || fe) {
        if (!porEsp.length) throw new E('Ningún programa de la lista se imparte en ese espacio.');
        const og = [...new Set(T.filas.map(f => f.ruta[0]))];
        porEsp.sort((x, y) => og.indexOf(x.g) - og.indexOf(y.g) || nn(x.esp).localeCompare(nn(y.esp)) || x.prog.localeCompare(y.prog));
        const cuenta = {}; porEsp.forEach(x => { cuenta[x.esp] = (cuenta[x.esp] || 0) + 1; });
        const tb = { titulo: `Programas de ${L.id} por espacio académico`, encabezados: ['Espacio académico', `Programa (lista ${L.id})`, `Matrícula (${T.id})`],
          filas: porEsp.map(x => ({ nombre: x.esp, ids: [{ texto: x.prog }, x.id] })), fuente: `Fuente: Agenda Estadística 2025, lista ${L.id} cruzada por nombre y nivel con ${T.id}, que dice en qué espacio se imparte cada programa.` };
        return { descripcion: `Cruzó ${L.id} con ${T.id} por espacio: ${porEsp.length} renglones en ${Object.keys(cuenta).length} espacios`, tabla: tb,
          programas_por_espacio: Object.entries(cuenta).sort((x, y) => y[1] - x[1]), renglones: porEsp.slice(0, 40).map(x => [x.esp, x.prog, x.v]),
          aproximados: aprox, sin_emparejar: fe ? [] : sin, series: porEsp.map(x => ({ id: x.id })),
          aviso: 'La tabla completa se muestra al usuario; un programa que se imparte en varios espacios aparece en cada uno.' };
      }
      if (filas.length < 2) throw new E('No pude emparejar suficientes programas.');
      filas.sort((x, y) => y.v - x.v);
      const tot = idsTot.length > 1 ? H.calcular_serie({ operacion: 'suma', ids: idsTot, nombre: `Matrícula de los programas de ${L.id}` }).id : null;
      const tabla2 = { titulo: `Matrícula de los programas de ${L.titulo}`.slice(0, 140), encabezados: [`Programa (lista ${L.id})`, `Matrícula (${T.id})`, 'Espacio(s)', `Nombre en la tabla ${T.id}`],
        filas: filas.map(f => ({ nombre: f.nombre, ids: f.ids })), totales: [tot, null, null], fuente: `Fuente: Agenda Estadística 2025, lista ${L.id} cruzada por nombre y nivel con la matrícula por programa de ${T.id}.` };
      return { descripcion: `Cruzó por nombre y nivel ${rows.length} programas de ${L.id} con la matrícula de ${T.id}: ${filas.length} emparejados`, tabla: tabla2,
        programas_en_lista: rows.length, emparejados: filas.length, matricula_total: tot ? r(SER[tot][Object.keys(SER[tot]).pop()]) : null,
        mas_alumnos: filas.slice(0, 6).map(f => [f.nombre, f.v, f.ids[1].texto]), menos_alumnos: filas.slice(-4).map(f => [f.nombre, f.v]),
        aproximados: aprox, sin_emparejar: sin, series: [...filas.map(f => ({ id: f.ids[0] })), ...(tot ? [{ id: tot }] : [])],
        aviso: 'La tabla completa se muestra al usuario. Si un programa se imparte en varios espacios, su matrícula es la suma de todos.' };
    },
    tabla_espacios({ columnas, grupo, porcentaje, incluir_dependencias = false, titulo = '' }) {
      // columnas: [{nombre, partes:[{tabla, columnas, bloque?}]}]; porcentaje: {parte: índice, total: índice} (opcional)
      const nn = Buscador.norm, cols = Array.isArray(columnas) ? columnas.slice(0, 5) : [];
      if (!cols.length) throw new E('Indica «columnas»: [{nombre, partes:[{tabla, columnas}]}].');
      const L = cols.map((c, i) => ladoEspacios(c.partes, `columnas[${i}]`));
      const claves = []; L.forEach(m => m.forEach((v, k) => { if (!claves.includes(k)) claves.push(k); }));
      const g = grupo ? nn(grupo) : null, filas = [];
      const sid = (ids, nom) => { ids.forEach(asegurarCelda); return ids.length === 1 ? ids[0] : H.calcular_serie({ operacion: 'suma', ids, nombre: nom }).id; };
      claves.forEach(k => {
        const info = L.map(m => m.get(k)).find(Boolean);
        if (g && !info.grupo.includes(g) && !nn(info.nombre).includes(g)) return;
        if (!g && !incluir_dependencias && /^dependencia/.test(info.grupo)) return;
        filas.push({ nombre: info.nombre, ids: L.map((m, i) => { const x = m.get(k); return x ? sid(x.ids, `${info.nombre}: ${cols[i].nombre}`) : null; }) });
      });
      if (filas.length < 2) throw new E('No encontré suficientes espacios con esos filtros.');
      const enc = ['Espacio académico', ...cols.map(c => String(c.nombre || 'Valor'))];
      const totales = cols.map((c, i) => { const ids = filas.map(f => f.ids[i]).filter(Boolean); return ids.length > 1 ? H.calcular_serie({ operacion: 'suma', ids, nombre: `Suma de la tabla: ${c.nombre}` }).id : null; });
      if (porcentaje && Number.isInteger(porcentaje.parte) && Number.isInteger(porcentaje.total)) {
        const pa = porcentaje.parte, pt = porcentaje.total; enc.push(`% ${cols[pa].nombre} / ${cols[pt].nombre}`);
        filas.forEach(f => { const a = f.ids[pa], b = f.ids[pt]; let id = null;
          if (a && b && SER[b] && Object.values(SER[b]).some(v => v)) { try { id = H.calcular_serie({ operacion: 'proporcion', id: a, id2: b, nombre: `${f.nombre}: %` }).id; } catch (e) { id = null; } }
          f.ids.push(id); });
        totales.push(totales[pa] && totales[pt] ? H.calcular_serie({ operacion: 'proporcion', id: totales[pa], id2: totales[pt], nombre: 'Suma de la tabla: %' }).id : null);
      }
      const ult = id => { if (!id || !SER[id]) return null; const ks = Object.keys(SER[id]); return r(SER[id][ks[ks.length - 1]]); };
      const fuentes = [...new Set(cols.flatMap(c => (Array.isArray(c.partes) ? c.partes : [c.partes]).map(p => String(p.tabla).toUpperCase())))];
      const tabla = { titulo: String(titulo || '').slice(0, 120) || `${cols.map(c => c.nombre).join(' y ')} por espacio académico`, encabezados: enc, filas, totales,
        fuente: `Fuente: Agenda Estadística 2025, tablas ${fuentes.join(', ')}.` };
      return { descripcion: `Armó una tabla con ${filas.length} espacios y ${enc.length - 1} columnas (tablas ${fuentes.join(', ')})`, tabla,
        totales: Object.fromEntries(enc.slice(1).map((h, i) => [h, ult(totales[i])])),
        primeras_filas: filas.slice(0, 8).map(f => [f.nombre, ...f.ids.map(ult)]),
        series: [...filas.flatMap(f => f.ids), ...totales].filter(Boolean).map(id => ({ id })),
        aviso: 'La tabla completa se muestra al usuario debajo de tu respuesta; no la copies, comenta lo principal.' };
    },
    cruzar_espacios({ numerador, denominador, operacion = 'proporcion', grupo, orden, n = 15, incluir_institutos = false }) {
      // cada lado: [{tabla, columnas:[...], bloque?}] — se suman las columnas y tablas de ese lado en cada espacio
      const nn = Buscador.norm;
      const op = sinAcentos(operacion).startsWith('raz') ? 'razon' : 'proporcion';
      const N = ladoEspacios(numerador, 'numerador'), D = ladoEspacios(denominador, 'denominador');
      const g = grupo ? nn(grupo) : null, filas = [], sinDen = [];
      for (const [k, a] of N) {
        const b = D.get(k); if (!b) continue;
        if (g && !a.grupo.includes(g) && !nn(b.nombre).includes(g)) continue;
        if (!g && !incluir_institutos && /^instituto/.test(a.grupo)) continue;
        if (/^dependencia/.test(a.grupo)) continue;
        if (!b.v) { if (a.v) sinDen.push(b.nombre); continue; }
        const lid = ids => { ids.forEach(asegurarCelda); return ids.length === 1 ? ids[0] : H.calcular_serie({ operacion: 'suma', ids, nombre: `${b.nombre}: suma` }).id; };
        const idn = lid(a.ids), idd = lid(b.ids);
        const res = H.calcular_serie({ operacion: op, id: idn, id2: idd, nombre: `${b.nombre}: ${op === 'razon' ? 'razón' : '%'}` });
        const ks = Object.keys(res.valores); filas.push({ id: res.id, espacio: b.nombre, numerador: r(a.v), denominador: r(b.v), valor: res.valores[ks[ks.length - 1]] });
      }
      if (filas.length < 2) throw new E('No encontré suficientes espacios con dato en las dos tablas. Revisa tablas, columnas o grupo.');
      const desc = orden ? !sinAcentos(orden).startsWith('men') : op === 'proporcion';
      filas.sort((x, y) => desc ? y.valor - x.valor : x.valor - y.valor);
      const top = filas.slice(0, Math.max(2, Math.min(30, Math.trunc(n) || 15)));
      return { descripcion: `Cruzó ${filas.length} espacios: ${op === 'razon' ? 'numerador ÷ denominador' : 'numerador ÷ denominador × 100'}`, operacion: op,
        espacios_calculados: filas.length, resultado: top, ultimos: filas.slice(-5).reverse(), sin_denominador: sinDen.slice(0, 10),
        series: top.map(x => ({ id: x.id })), aviso: 'Los valores ya están calculados; grafica con los id S… de «resultado».' };
    },
    calcular_serie({ operacion = '', id, id2, ids, nombre: nom = '' }) {
      let op = sinAcentos(operacion);
      op = { division: 'razon', dividir: 'razon', cociente: 'razon', entre: 'razon', porcentaje: 'proporcion', resta: 'diferencia', variacion: 'variacion_anual', crecimiento_anual: 'variacion_anual' }[op] || op;
      if (!OPS_SERIE.includes(op)) throw new E(`Operación desconocida «${operacion}». Usa una de: ${OPS_SERIE.join(', ')}.`);
      let ent;
      if (op === 'suma') { ent = (Array.isArray(ids) ? ids : [id, id2].filter(Boolean)).map(vid); if (ent.length < 2) throw new E('Para sumar indica al menos dos ids en «ids».'); }
      else if (op === 'variacion_anual') ent = [vid(id)];
      else { if (!id || !id2) throw new E('Indica «id» (numerador o primer término) e «id2» (denominador o segundo término).'); ent = [vid(id), vid(id2)]; }
      const vals = {};
      if (op === 'variacion_anual') {
        anios(ent[0]).forEach(a => { const v0 = SER[ent[0]][a - 1], v1 = SER[ent[0]][a]; if (v0 != null && v1 != null && v0 !== 0) vals[a] = r((v1 - v0) / v0 * 100, 4); });
      } else {
        let comunes = null;
        ent.forEach(i => { const s = new Set(anios(i)); comunes = comunes ? [...comunes].filter(x => s.has(x)) : [...s]; });
        comunes.sort((a, b) => a - b).forEach(a => {
          const v = ent.map(i => SER[i][a]);
          if (op === 'suma') vals[a] = r(v.reduce((s, x) => s + x, 0), 4);
          else if (op === 'diferencia') vals[a] = r(v[0] - v[1], 4);
          else if (v[1] !== 0) vals[a] = r(v[0] / v[1] * (op === 'proporcion' ? 100 : 1), 4);
        });
      }
      const as = Object.keys(vals).map(Number);
      if (!as.length) throw new E('Esos indicadores no tienen años en común para calcular la serie.');
      const simb = { razon: '÷', proporcion: '÷', diferencia: '−', suma: '+' }[op];
      const formula = op === 'variacion_anual' ? `variación anual de ${nombre(ent[0])}` : ent.map(nombre).join(` ${simb} `) + (op === 'proporcion' ? ' × 100' : '');
      let nm = String(nom || '').trim().slice(0, 100) || (op === 'variacion_anual' ? `Variación anual de ${nombre(ent[0])}` : ent.map(i => nombre(i).split(' › ').pop()).join(` ${simb} `));
      if ((op === 'proporcion' || op === 'variacion_anual') && !nm.includes('%')) nm += ' (%)';
      const nid = 'S' + (++nSeries);
      SER[nid] = vals;
      byId[nid] = { id: nid, ruta: nm, concepto: nm, eje: 'Serie calculada', archivo: 'calc', fila_excel: '', derivada: { op, ids: ent, formula } };
      return { id: nid, descripcion: `Creó la serie ${nid}: ${nm} = ${formula} (${as.length} años, ${as[0]}–${as[as.length - 1]})`,
        indicador: nm, formula, unidad: unid(nid), valores: Object.fromEntries(as.map(a => [a, r(vals[a])])) };
    },
    graficar({ tipo = 'linea', ids, desde, hasta, anio, titulo = '' }) {
      let tp = sinAcentos(tipo);
      tp = { lineas: 'linea', barra: 'barras', columnas: 'barras', comparacion: 'comparar_anio', comparar: 'comparar_anio', barras_horizontales: 'comparar_anio', cambio: 'cambio_anios', cambio_anual: 'cambio_anios', diferencia: 'cambio_anios' }[tp] || tp;
      if (!TIPOS.includes(tp)) throw new E(`Tipo de gráfica desconocido «${tipo}». Usa: ${TIPOS.join(', ')}.`);
      const l = [...new Set(lista(ids).map(vid))];
      const max = tp === 'comparar_anio' ? 30 : tp === 'cambio_anios' ? 80 : tp === 'barras' ? 2 : 4;
      if (!l.length) throw new E('Indica al menos un id en «ids».');
      if (l.length > max) throw new E(`La gráfica «${tp}» admite máximo ${max} indicadores; haz otra gráfica para los demás.`);
      if (tp === 'comparar_anio' && l.length < 2) throw new E('Para comparar en un año indica al menos 2 indicadores.');
      const us = [...new Set(l.map(unid))];
      if (us.length > 1) throw new E(`Esos indicadores tienen unidades distintas (${us.map(u => u || 'cantidad').join(', ')}). Haz una gráfica para cada unidad.`);
      titulo = String(titulo || '').trim().slice(0, 120);
      if (tp === 'cambio_anios') {  // cada indicador con su valor en dos años y la diferencia
        const comunes = Object.keys(SER[l[0]]).map(Number).filter(a => l.every(i => SER[i][a] != null)).sort((x, y) => x - y);
        let h = van(hasta) || comunes[comunes.length - 1], d = van(desde) || Math.max(...comunes.filter(a => a < h));
        if (!d || !h || d === h || !isFinite(d)) throw new E('Para el cambio indica dos años distintos con datos («desde» y «hasta»).');
        if (d > h) [d, h] = [h, d];
        const faltan = l.filter(i => SER[i][d] == null || SER[i][h] == null).map(nombre);
        if (faltan.length) throw new E(`Sin dato en ${d} o ${h} para: ${faltan.slice(0, 10).join('; ')}. Quita esos indicadores.`);
        const orden = [...l].sort((x, y) => (SER[y][h] - SER[y][d]) - (SER[x][h] - SER[x][d]));
        return { descripcion: `Preparó gráfica del cambio ${d}–${h} de ${l.length} indicadores (del que más subió al que más bajó)`,
          grafica: { tipo: tp, ids: orden, desde: d, hasta: h, titulo: titulo || `Cambio ${d}–${h}` },
          valores_graficados: Object.fromEntries(orden.map(i => [nombre(i), { desde: r(SER[i][d]), hasta: r(SER[i][h]), cambio: r(SER[i][h] - SER[i][d]) }])), unidad: us[0],
          aviso: 'Usa estos valores de «cambio» tal cual: positivo es aumento y negativo es disminución.' };
      }
      if (tp === 'comparar_anio') {
        const a = van(anio) || comun(l);
        const faltan = l.filter(i => SER[i][a] == null).map(nombre);
        if (faltan.length) throw new E(`Sin dato en ${a} para: ${faltan.join('; ')}. Elige otro año o quita esos indicadores.`);
        return { descripcion: `Preparó gráfica de barras comparando ${l.length} indicadores en ${a}`,
          grafica: { tipo: tp, ids: l, anio: a, titulo: titulo || `Comparación ${a}` },
          valores_graficados: Object.fromEntries(l.map(i => [nombre(i), r(SER[i][a])])), unidad: us[0] };
      }
      let d = van(desde, AMIN), h = van(hasta, AMAX); if (d > h) [d, h] = [h, d];
      const resumen = l.map(i => {
        const t = tramo(i, d, h), ks = Object.keys(t).map(Number), k1 = ks[0], k2 = ks[ks.length - 1];
        const km = ks.reduce((m, k) => t[k] > t[m] ? k : m, k1);
        return { indicador: nombre(i), primer_anio: k1, valor_inicial: r(t[k1]), ultimo_anio: k2, valor_final: r(t[k2]), maximo: r(t[km]), anio_maximo: km };
      });
      return { descripcion: `Preparó gráfica de ${tp === 'linea' ? 'líneas' : 'barras'} de ${l.length} indicador${l.length > 1 ? 'es' : ''}, ${d}–${h}`,
        grafica: { tipo: tp, ids: l, desde: d, hasta: h, titulo: titulo || (l.length === 1 ? nombre(l[0]) : `Evolución ${d}–${h}`) }, resumen, unidad: us[0] };
    },
  };

  function ejecutar(nombreH, args) {
    const fn = H[nombreH];
    if (!fn) return { error: `La herramienta «${nombreH}» no existe.` };
    try { return fn(args && typeof args === 'object' ? args : {}); }
    catch (e) { if (e instanceof E) return { error: e.message }; return { error: 'No se pudo completar: ' + e.message }; }
  }
  const idsEn = a => [a?.id, a?.id2, ...lista(a?.ids)].map(x => String(x ?? '')).filter(x => SER[x]);
  return { ejecutar, idsEn, nombre, OPS, TIPOS, OPS_SERIE, evaluar };
})();

/* Verificación: cada número que escribe Claude debe salir de los datos o de una herramienta */
const NUMRE = /(?<![\w.,])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)/g;
const numerosTxt = t => [...String(t).matchAll(NUMRE)].map(m => [m[1], parseFloat(m[1].replace(/,/g, ''))]);
function numerosEn(o) {
  if (typeof o === 'number') return [o];
  if (typeof o === 'string') return numerosTxt(o).map(x => x[1]);
  if (Array.isArray(o)) return o.flatMap(numerosEn);
  if (o && typeof o === 'object') return Object.values(o).flatMap(numerosEn);
  return [];
}
function sinVerificar(texto, ids, pregunta, extra) {
  const base = [...extra];
  ids.forEach(id => {
    const vs = Object.values(SER[id] || {});
    base.push(...vs);
    vs.forEach(a => vs.forEach(b => { if (a !== b) { base.push(Math.abs(a - b)); if (a) base.push(Math.abs((b - a) / a * 100)); } }));
  });
  const enPregunta = new Set(numerosTxt(pregunta).map(x => x[1]));
  const cerca = (x, a) => Math.abs(x - a) <= Math.max(0.051, Math.abs(a) * 0.0005) || (Number.isInteger(x) && Math.abs(x - a) < 0.5 + 1e-9);
  const malos = [];
  numerosTxt(texto).forEach(([crudo, x]) => {
    if (enPregunta.has(x) || (Number.isInteger(x) && (x <= 31 || (x >= 1990 && x <= 2100)))) return;
    if (!base.some(a => [1, 1000, 1e6].some(f => cerca(x * f, a)))) malos.push(crudo);
  });
  return [...new Set(malos)];
}

const INSTRUCCIONES = `Eres el asistente estadístico de la Universidad Autónoma del Estado de México (UAEMEX). Respondes con las series históricas 2004-2025 de la Agenda Estadística 2025 usando las herramientas de esta página.

Cómo trabajar:
1. Toda cifra que menciones debe venir de una herramienta (obtener_valores, calcular o graficar). No uses cifras de memoria.
2. Para cualquier operación (diferencias, porcentajes, sumas, promedios, crecimiento, proporciones, alumnos por profesor) usa calcular. No hagas cuentas por tu cuenta.
3. En calcular y graficar, refiérete a los indicadores por su id; la herramienta toma los valores exactos.
4. Si los indicadores sugeridos no sirven, usa buscar_indicadores. Si de plano no existe el dato, dilo y menciona el más parecido. Las series no tienen datos por facultad ni por programa: para eso usa las tablas anuales (regla 10).
5. Los indicadores del eje "Sistema incorporado" son de escuelas particulares incorporadas; úsalos solo si preguntan por ellas.
6. Si la pregunta pide una gráfica, comparar indicadores o ver una evolución, usa graficar (máximo 4 gráficas). La gráfica se dibuja sola con los datos reales; tú eliges indicadores, años y tipo, y la comentas con las cifras de su "resumen" o "valores_graficados". Si piden gráficas "por separado", haz una gráfica para cada serie.
7. Para analizar o graficar un resultado calculado año por año (por ejemplo alumnos por PTC, el porcentaje que representa una parte, una suma de niveles o la variación anual), usa primero calcular_serie: crea una serie nueva con id S1, S2… que puedes usar en graficar y en calcular.
8. Cuando haya varios indicadores posibles para un concepto (por ejemplo, el total de PTC registrados en la SEP y el personal académico de tiempo completo), elige el más adecuado y di en la respuesta cuál usaste.
9. Si una herramienta devuelve "error", corrige la llamada o explica que no hay dato.
10. Además de las series hay tablas anuales con detalle de 2018 a 2025 (por omisión usa el año más reciente; si piden otro año o comparar años, consulta con anio o usa calcular con la operación cambio sobre la celda, p. ej. A26.f3.c0 desde 2018 hasta 2025; algunas tablas solo existen en un año y algunos renglones cambian de nombre, como los programas que antes de 2025 se separaban por modalidad «(mixta)»). Personal (P01–P18): personal académico y administrativo por espacio universitario, categoría y sexo; PROED; concursos; juicios de promoción; capacitación; carrera administrativa; personal de escuelas incorporadas. Docencia (A01–A69): planes y programas educativos, acreditaciones y posgrados (listas de texto); matrícula por nivel, sistema, municipio, espacio y programa; ingreso; egreso; titulación; eficiencia terminal; reprobación; abandono; transición y promoción; alumnado con discapacidad o hablante de lenguas indígenas; estudios avanzados; escuelas incorporadas; tutoría; orientación; acervo, recursos electrónicos e infraestructura. Ciencia (C01–C27): PTC registrados en la SEP, con perfil Prodep e investigadores por espacio y grado; miembros del SNII por espacio y nivel (bloques PTC y no PTC); licencias y apoyos académicos; cuerpos académicos y LGAC (listas de texto); proyectos de investigación por espacio, área, fuente de financiamiento y tipo; recursos asignados; productos académicos; revistas y publicaciones de divulgación (listas); Octubre mes de la ciencia; redes de colaboración (lista); becas Verano Delfín; becarios extranjeros (lista); patentes en trámite y diplomados superiores. Extensión (E01–E61): alumnado becado y becas por nivel, espacio, programa, tipo y fuente de financiamiento (montos en miles de pesos); seguro estudiantil y afiliación a servicios de salud; consultorios y atenciones médicas y psicológicas; servicio social y prácticas profesionales por programa; servicios comunitarios y brigadas (lista); CELe y CILC (lenguas); educación continua (lista); convenios por sector, tipo y servicio; emprendimiento; seguimiento de egresados (ocupación, empleo afín, desocupación); Clínica Multidisciplinaria de Salud; deporte y cultura física. Varias tablas de Extensión vienen por nivel educativo (Bachillerato › Plantel…, Estudios profesionales › Facultad…). Difusión (D01–D18): identidad y cultura; talleres culturales por espacio; eventos artísticos y culturales; Casa de las Diligencias; patrimonio e innovación cultural; exposiciones (lista); conferencias; talleres de ciencia y cultura; CeAC; elenco artístico; función y producción editorial; publicaciones (lista); revistas publicadas; presentaciones y producciones teatrales; visitas guiadas por espacio. Gestión (G01–G45): certificación ISO; manuales; finanzas (origen y aplicación de recursos, recursos etiquetados, adquisiciones en miles de pesos); bienes inventariados e inmuebles; obra universitaria; servicios de mantenimiento y servicios generales por tipo y por espacio; salas de lactancia; Potrobús; computadoras por espacio y en red; sistemas y sitios web; comunidades virtuales; videoconferencias; internet inalámbrico; planeación y evaluación; fomento ambiental y residuos peligrosos; protección universitaria; Consejo Universitario; legislación y convenios; igualdad de género (jornadas y participantes); transparencia; comunicación universitaria y redes sociales. Internacionalización (I01–I09): movilidad del alumnado UAEMEX y externo por país, institución y espacio; movilidad del personal; convenios internacionales vigentes. Cobertura (M01): población, matrícula estatal y nacional, matrícula UAEMEX y porcentajes de cobertura y participación por nivel. Presencia (R01–R10): espacios por municipio, institutos y centros de investigación, espacios culturales, CELe, CILC, incubadoras, unidades de emprendimiento, centros deportivos, librerías y DES (listas con domicilio y año de creación). Fichas por espacio: un resumen de cada espacio (año de fundación, alumnado por programa, tutoría, investigación, movilidad, becas, servicio social, personal e infraestructura): O01–O22 organismos académicos (facultades y escuela), U01–U12 centros universitarios, V01–V07 unidades académicas profesionales, N01–N08 institutos y centros de investigación, B01–B11 planteles de la Escuela Preparatoria; úsalas para «ficha», «resumen» o «año de fundación» de un espacio; para el cambio entre años en cada espacio usa cambio_espacios (una sola llamada, nunca dos gráficas separadas por año ni restas a mano); para un dato de todas las fichas (p. ej. el año de fundación de cada espacio o el espacio más antiguo) usa dato_fichas, nunca consultes las fichas una por una; para comparar espacios usa las tablas por sección. Las tablas de estudios profesionales y avanzados traen el detalle por programa educativo (por ejemplo «Facultad › Ingeniería › Licenciatura en Ingeniería Civil»). Para datos por facultad, plantel, centro universitario, UAP, instituto o dependencia, por categoría o por sexo, usa buscar_tablas y luego consultar_tabla (con «grupo», por ejemplo «Facultad», para traer solo sus espacios). Cada celda tiene un id (por ejemplo P02.f23.c3) que puedes usar en calcular, calcular_serie y graficar; para comparar espacios en una gráfica usa graficar con tipo comparar_anio (hasta 30 barras). Las celdas vacías de la tabla original se leen como 0. No sumes columnas de promedios. La «matrícula total» de la UAEMEX es la del sistema dependiente (serie «Matrícula» y sus niveles; 100,491 en 2025). El sistema incorporado (escuelas incorporadas, tabla A12 columnas «Incorporado») se reporta siempre por separado: nunca lo sumes al dependiente ni uses la columna «Total» de A12 como matrícula total. Cita la tabla usada (por ejemplo «tabla P02, Personal académico y administrativo 2025»). «PTC» y «profesor/a de tiempo completo» (o «personal académico de tiempo completo») son lo mismo. Por omisión los PTC de cada espacio salen de P03 sumando «Profesoras / es › Tiempo completo › Hombres» y «› Mujeres» (en total son 1,572 en 2025); C01 son solo los PTC registrados en la SEP, C02 los de perfil Prodep y C04 los del SNII: úsalas solo si la pregunta menciona SEP, Prodep, SNII o grado académico.
11. Para «¿qué programa (o carrera, licenciatura) tiene más o menos…?» usa ordenar_filas, que revisa todas las filas. Si la pregunta dice «por espacio académico», «por sede», «por facultad» o «en cada…», responde con cada programa contado en su sede (sumar_sedes=false) y nombra la sede. Si no lo dice, responde con el programa sumado en todas sus sedes (sumar_sedes=true) e indica en cuántas sedes se imparte, y menciona también cuál es el mayor en una sola sede. Nunca sumes columnas de promedios o índices entre sedes. «Mejor» depende del indicador: en eficiencia terminal o titulación es el valor más alto; en reprobación o abandono, el más bajo (usa orden «menor»). En eficiencia terminal usa por omisión la de cohorte, que es la más comparable, y explica que la global puede pasar de 100%. Escribe porcentajes con máximo 2 decimales. Grafica con los ids que devuelve.
12. Para relaciones entre personal y alumnos por espacio (por ejemplo alumnos por PTC): los PTC de cada espacio están en P03 como «Profesoras / es › Tiempo completo › Hombres» y «› Mujeres» (súmalos con calcular_serie); la matrícula del espacio es la suma de A26 (licenciatura), A40 (posgrado por espacio) y A15 (bachillerato) que le correspondan. Usa cruzar_espacios (operacion razon) y di que una cifra menor de alumnos por profesor es una mejor relación. Para proporciones entre dos grupos de personal (por ejemplo, % de PTC que están en el SNII, con perfil Prodep o con doctorado) usa cruzar_espacios con operacion proporcion: más alto es mejor. Nunca calcules razones o porcentajes a mano. Si una pregunta necesita datos de dos tablas cuyos nombres no coinciden exactamente (por ejemplo, la matrícula de los programas del SNP: lista A08 y matrícula A39), crúzalas con la herramienta que corresponda en lugar de decir que no se puede. Para «¿dónde se imparte / en cuántos espacios se ofrece el programa X?» usa donde_se_imparte (busca el programa en la matrícula por espacio, aunque el nombre esté escrito distinto). Si piden una tabla, lista o cuadro por espacio, usa tabla_espacios (se muestra completa al usuario; en tu texto comenta solo lo principal y recuerda que PTC son profesoras y profesores de tiempo completo). No incluyas institutos de investigación salvo que los pidan.

Respuesta final: en español, de 2 a 5 frases, sin listas, títulos ni negritas. Escribe las cifras en formato mexicano (100,491 y 2.6%) con su unidad, tal como salieron de las herramientas, y menciona brevemente cómo se calculó cuando hiciste una operación.`;

let sample = null, dl = null;
const MENSAJES_IA = {
  not_granted: 'No se dio permiso para usar Claude en esta página. El buscador y el explorador siguen funcionando.',
  sampling_disabled: 'Claude no está disponible para tu cuenta. El buscador y el explorador siguen funcionando.',
  tools_unavailable: 'Esta versión de la app de Claude no permite que la IA use las herramientas. Actualiza la app o usa claude.ai en el navegador.',
  rate_limited: 'Alcanzaste el límite de uso de tu cuenta de Claude por ahora. Intenta más tarde.',
  session_expired: 'Tu sesión de Claude expiró. Vuelve a iniciar sesión.',
  refused: 'Claude no pudo responder esa pregunta. Intenta formularla de otra forma.',
  empty_completion: 'Claude no devolvió texto. Intenta con una pregunta más concreta.',
  prompt_too_large: 'La consulta resultó demasiado grande. Pide menos años o menos indicadores a la vez.',
};

async function preguntarIA(b) {
  if (!sample) return;
  if (iaCtl) iaCtl.abort();
  const ctl = iaCtl = new AbortController();
  const candidatos = buscador.buscar(b.t, 10).resultados.map(r => r.id);
  const pasos = [], graficas = [], idsUsados = [], numsHerr = [], tablasIA = [];
  const espera = p('Claude está trabajando… Suele tardar de 20 a 90 segundos; mientras tanto ya ves el dato del buscador.', 'estado');
  espera.id = 'ia-espera';
  const det = document.createElement('button'); det.type = 'button'; det.className = 'btn-mini'; det.textContent = 'Detener'; det.style.marginLeft = '10px';
  det.onclick = () => ctl.abort(); espera.append(det);
  $('respuesta').prepend(espera);
  const avance = t => { const e = document.getElementById('ia-espera'); if (e && e.firstChild) e.firstChild.textContent = t; };

  const herramienta = (name, description, inputSchema) => ({
    name, description, inputSchema,
    execute(input) {
      if (name === 'graficar' && graficas.length >= 4) return { error: 'Ya hay 4 gráficas en esta respuesta; no se pueden agregar más.' };
      const res = Calc.ejecutar(name, input);
      Calc.idsEn(input).forEach(i => { if (!idsUsados.includes(i)) idsUsados.push(i); });
      (res.series || []).forEach(s => { if (!idsUsados.includes(s.id)) idsUsados.push(s.id); });
      if (res.grafica) graficas.push(res.grafica);
      if (res.tabla && tablasIA.length < 2) tablasIA.push(res.tabla);
      numsHerr.push(...numerosEn(res));
      pasos.push({ descripcion: res.descripcion || res.error, error: !!res.error });
      avance(`Claude está trabajando… ${res.descripcion || 'revisando'}`);
      return res;
    },
  });
  const tools = [
    herramienta('buscar_indicadores', 'Busca indicadores del catálogo por palabras clave y devuelve hasta 15 con su id. Úsala si los indicadores sugeridos no sirven.',
      { type: 'object', properties: { texto: { type: 'string', description: "Palabras clave, p. ej. 'egreso doctorado'" } }, required: ['texto'] }),
    herramienta('obtener_valores', 'Devuelve los valores por año de uno o varios indicadores (máximo 8).',
      { type: 'object', properties: { ids: { type: 'array', items: { type: 'string' } }, desde: { type: 'integer' }, hasta: { type: 'integer' } }, required: ['ids'] }),
    herramienta('calcular', 'Cálculos exactos con los datos (también con series S… creadas con calcular_serie). Operaciones: valor (id, anio); cambio (id, desde, hasta: diferencia y % de cambio); crecimiento_anual_promedio (id, desde, hasta: tasa compuesta); promedio, maximo, minimo (id, desde, hasta); suma (ids, anio); proporcion (id = parte, id2 = total, anio); razon (id, id2, anio: p. ej. alumnos por profesor); diferencia (id, id2, anio); expresion (aritmética con números). Sin anio usa el más reciente disponible.',
      { type: 'object', properties: { operacion: { type: 'string', enum: Calc.OPS }, id: { type: 'string' }, id2: { type: 'string' }, ids: { type: 'array', items: { type: 'string' } }, anio: { type: 'integer' }, desde: { type: 'integer' }, hasta: { type: 'integer' }, expresion: { type: 'string' } }, required: ['operacion'] }),
    herramienta('buscar_tablas', 'Busca tablas anuales (detalle por espacio universitario, programa, categoría o sexo) por palabras clave. Devuelve hasta 5 tablas con su id (P01…P18, A01…A69), tipo (numérica o lista de texto), años, grupos de filas, columnas y filas que coinciden.',
      { type: 'object', properties: { texto: { type: 'string', description: "Palabras clave, p. ej. 'personal académico facultad' o 'PROED'" } }, required: ['texto'] }),
    herramienta('consultar_tabla', 'Devuelve celdas de una tabla anual con su id, fila, columna y valor (máximo 240 celdas); en una lista de texto devuelve sus renglones (filtra con «filas»). Filtra con grupo (devuelve los espacios dentro de un grupo, p. ej. «Facultad», «Centro universitario UAEM», «Plantel»), filas (texto que deben contener) y columnas (texto que deben contener, p. ej. «Tiempo completo › Total»).',
      { type: 'object', properties: { tabla: { type: 'string', description: 'Id de la tabla, p. ej. P02' }, grupo: { type: 'string' }, filas: { type: 'array', items: { type: 'string' } }, columnas: { type: 'array', items: { type: 'string' } }, anio: { type: 'integer' } }, required: ['tabla'] }),
    herramienta('ordenar_filas', 'Ordena TODAS las filas de una tabla anual (sin tope de 150) por una columna y devuelve las primeras n con su id. nivel «programa» (por omisión) ordena programas educativos; nivel «espacio» ordena facultades, planteles, centros, etc. Con sumar_sedes=true suma el mismo programa en todas las sedes donde se imparte (crea series S… que se pueden graficar). Filtra con grupo (p. ej. «Facultad» o «Ingeniería»). Úsala para «¿qué programa/facultad tiene más o menos…?».',
      { type: 'object', properties: { tabla: { type: 'string' }, columna: { type: 'string', description: 'Texto de la columna; por omisión «Total»' }, nivel: { type: 'string', enum: ['programa', 'espacio'] }, grupo: { type: 'string' }, sumar_sedes: { type: 'boolean' }, orden: { type: 'string', enum: ['mayor', 'menor'] }, n: { type: 'integer' }, anio: { type: 'integer' } }, required: ['tabla'] }),
    herramienta('cambio_espacios', 'Cambio de un indicador entre dos años EN CADA espacio académico, con gráfica de cambio (los dos años y la diferencia, del que más subió al que más bajó) y tabla completa. partes: [{tabla, columnas, bloque?}] que se suman (matrícula = A26 «Total» + A40 «Total» + A15 «Total»; PTC = P03 «Profesoras / es › Tiempo completo › Hombres» + «› Mujeres»; personal académico = P03 «Total»). Úsala para «cómo cambió X de 2024 a 2025 por espacio / en cada facultad».',
      { type: 'object', properties: { partes: { type: 'array', items: { type: 'object' } }, desde: { type: 'integer' }, hasta: { type: 'integer' }, grupo: { type: 'string', description: 'p. ej. «Facultad» para solo facultades' }, titulo: { type: 'string' } }, required: ['partes'] }),
    herramienta('dato_fichas', 'Reúne un mismo dato de TODAS las fichas por espacio (O facultades y escuela, U centros universitarios, V UAP, N institutos y centros, B planteles), p. ej. «Año de fundación», y muestra la tabla al usuario ordenada. Úsala para «año de fundación de cada espacio», «¿cuál es la facultad más antigua?» o cualquier dato que solo esté en las fichas.',
      { type: 'object', properties: { concepto: { type: 'string', description: 'p. ej. «Año de fundación»' }, tipo: { type: 'string', description: 'Opcional: facultad, plantel, centro universitario, unidad académica, instituto' } }, required: ['concepto'] }),
    herramienta('donde_se_imparte', 'Busca un programa educativo por su nombre (aunque esté escrito distinto: «Licenciatura de/en…», con modalidad, etc.) en la matrícula por espacio y programa (A26 licenciatura, A39 posgrado) y muestra en cuántos y cuáles espacios se ofrece, con su matrícula. Úsala para «¿dónde se imparte…?», «¿en cuántos espacios se ofrece…?».',
      { type: 'object', properties: { programa: { type: 'string', description: 'Nombre o parte del nombre, p. ej. «Derecho» o «Ingeniería en Computación»' }, nivel: { type: 'string', enum: ['licenciatura', 'especialidad', 'maestria', 'doctorado'] }, grupo: { type: 'string', description: 'p. ej. «Facultad» para contar solo facultades' } }, required: ['programa'] }),
    herramienta('matricula_programas_lista', 'Cruza una lista de programas (por omisión A08, programas en el Sistema Nacional de Posgrados) con la matrícula por programa (por omisión A39), emparejando por nombre y nivel aunque los nombres no coincidan exactamente; suma los espacios donde se imparte cada programa y muestra la tabla al usuario. Úsala para «¿cuántos alumnos tiene cada programa del SNP?» y, con por_espacio, para «programas del SNP por espacio académico».',
      { type: 'object', properties: { lista: { type: 'string' }, tabla: { type: 'string' }, por_espacio: { type: 'boolean', description: 'true: un renglón por espacio y programa (para «por espacio académico» o «dónde se imparte»)' }, espacio: { type: 'string', description: 'Filtra un espacio, p. ej. «Química»' } } }),
    herramienta('tabla_espacios', 'Muestra al usuario una TABLA con una columna por indicador en cada espacio académico (p. ej. PTC y PTC en el SNII). columnas: [{nombre, partes:[{tabla, columnas, bloque?}]}] (las partes se suman; PTC = P03 «Profesoras / es › Tiempo completo › Hombres» + «› Mujeres»; SNII de PTC = C04 «Total»; matrícula = A26 + A40 + A15 «Total»). porcentaje opcional {parte, total} (índices de columnas) agrega la columna de %. Úsala cuando pidan una tabla, lista o cuadro por espacio.',
      { type: 'object', properties: { columnas: { type: 'array', items: { type: 'object' } }, grupo: { type: 'string' }, porcentaje: { type: 'object' }, incluir_dependencias: { type: 'boolean' }, titulo: { type: 'string' } }, required: ['columnas'] }),
    herramienta('cruzar_espacios', 'Cruza dos indicadores de tablas anuales en CADA espacio académico y calcula proporcion (numerador ÷ denominador × 100) o razon (numerador ÷ denominador). Cada lado es una lista de {tabla, columnas, bloque?}: las columnas y tablas de un lado se suman (p. ej. PTC = P03 «Profesoras / es › Tiempo completo › Hombres» + «› Mujeres»; matrícula = A26 + A40 + A15 «Total»; SNII de PTC = C04 «Total» (su primer bloque es el de PTC)). Devuelve los espacios ordenados con ids S… para graficar. Úsala para «mejor relación entre X y Y por espacio»; nunca calcules esas razones a mano.',
      { type: 'object', properties: { numerador: { type: 'array', items: { type: 'object' } }, denominador: { type: 'array', items: { type: 'object' } }, operacion: { type: 'string', enum: ['proporcion', 'razon'] }, grupo: { type: 'string' }, orden: { type: 'string', enum: ['mayor', 'menor'] }, n: { type: 'integer' }, incluir_institutos: { type: 'boolean' } }, required: ['numerador', 'denominador'] }),
    herramienta('calcular_serie', 'Crea una serie nueva calculada año por año a partir de indicadores (o de otras series S…). Operaciones: razon (id ÷ id2, p. ej. alumnos por PTC); proporcion (id ÷ id2 × 100, en %); diferencia (id − id2); suma (ids); variacion_anual (% de cambio de id respecto al año anterior). Devuelve el id de la serie (S1, S2…) y sus valores; úsalo en graficar o calcular.',
      { type: 'object', properties: { operacion: { type: 'string', enum: Calc.OPS_SERIE }, id: { type: 'string' }, id2: { type: 'string' }, ids: { type: 'array', items: { type: 'string' } }, nombre: { type: 'string', description: 'Nombre corto en español, p. ej. «Alumnos de bachillerato por PTC»' } }, required: ['operacion'] }),
    herramienta('graficar', 'Muestra al usuario una gráfica dibujada con los datos reales. Tipos: linea (evolución de 1 a 4 indicadores con la misma unidad); barras (evolución en columnas, 1 o 2 indicadores); comparar_anio (barras que comparan de 2 a 30 indicadores o celdas de tabla en un año); cambio_anios (de 2 a 80 indicadores o celdas, cada uno con su valor en dos años —desde, hasta— y la diferencia, ordenados del que más subió al que más bajó; úsala para «cómo cambió X de 2024 a 2025 por espacio»). Devuelve un resumen con las cifras clave.',
      { type: 'object', properties: { tipo: { type: 'string', enum: Calc.TIPOS }, ids: { type: 'array', items: { type: 'string' } }, desde: { type: 'integer' }, hasta: { type: 'integer' }, anio: { type: 'integer' }, titulo: { type: 'string' } }, required: ['tipo', 'ids'] }),
  ];
  const pista = b.q.unico ? `\nLa pregunta menciona el año ${b.q.unico}.` : b.q.desde ? `\nLa pregunta se refiere al periodo ${b.q.desde}-${b.q.hasta}.` : '';
  const prompt = `${INSTRUCCIONES}\n\nPregunta: ${b.t}${pista}\n\nIndicadores sugeridos (id: indicador):\n` +
    candidatos.map(i => `- ${i}: ${Calc.nombre(i)} (${byId[i].eje})`).join('\n');
  const t0 = performance.now();
  try {
    const res = await sample(prompt, { tools, signal: ctl.signal });
    if (ctl !== iaCtl) return;
    const texto = String(res.text || '').replace(/\*\*/g, '').trim();
    const conDatos = idsUsados.filter(i => SER[i]);
    mostrarRespuestaIA(b, {
      respuesta: texto, graficas, pasos, tablas: tablasIA,
      id: graficas.length ? graficas[0].ids[0] : (conDatos[0] || candidatos[0]),
      sin_verificar: sinVerificar(texto, (conDatos.length ? conDatos : candidatos.slice(0, 3)).slice(0, 8), b.t, numsHerr),
      etiqueta: `Respuesta de Claude · ${Math.round((performance.now() - t0) / 1000)} s${res.truncated ? ' · respuesta cortada' : ''}`,
    });
  } catch (e) {
    if (ctl !== iaCtl) return;
    if (e && e.code === 'cancelled') { $('respuesta').prepend(p('Consulta a Claude detenida.', 'estado')); return; }
    $('respuesta').prepend(p(MENSAJES_IA[e && e.code] || 'Hubo un problema al consultar a Claude. Intenta de nuevo.', 'aviso err'));
    if (e && ['not_granted', 'sampling_disabled', 'tools_unavailable', 'not_declared', 'capability_disabled', 'capability_removed'].includes(e.code)) desactivarIA(MENSAJES_IA[e.code] || '');
  } finally { const w = document.getElementById('ia-espera'); if (w) w.remove(); }
}

function mostrarRespuestaIA(b, j) {
  if (j.graficas.length || (j.tablas && j.tablas.length)) { quitarGraficasIA(); $('respuesta').innerHTML = ''; $('alternativas').hidden = true; }
  else if (j.id && byId[j.id] && SER[j.id]) responder(j.id, b.q);
  const blq = document.createElement('div'); blq.className = 'ia-resp';
  blq.append(p(j.etiqueta, 'estado'));
  j.respuesta.split(/\n+/).filter(s => s.trim()).forEach(s => blq.append(p(s)));
  if (j.sin_verificar.length)
    blq.append(p(`Revisa estas cifras: Claude las mencionó pero no coinciden con los datos ni con los cálculos: ${j.sin_verificar.join(', ')}. Confía en la gráfica y la tabla.`, 'aviso err'));
  if (j.pasos.length) {
    const det = document.createElement('details'); det.className = 'pasos';
    const sum = document.createElement('summary'); sum.textContent = `Ver cómo obtuvo la respuesta (${j.pasos.length} paso${j.pasos.length > 1 ? 's' : ''})`; det.append(sum);
    const ol = document.createElement('ol');
    j.pasos.forEach(s => { const li = document.createElement('li'); li.textContent = s.descripcion; if (s.error) li.className = 'paso-error'; ol.append(li); });
    det.append(ol); blq.append(det);
  }
  $('respuesta').prepend(blq);
  if (j.graficas.length || (j.tablas && j.tablas.length)) {
    $('panel-res').hidden = true;
    let ref = $('respuesta');
    (j.tablas || []).forEach(t => { const pn = panelTablaIA(t); ref.after(pn); ref = pn; });
    j.graficas.forEach(g => { const pn = panelIA(g); ref.after(pn); ref = pn; pn._render(); });
  }
}

function desactivarIA(msg) {
  iaLista = false; $('ia-activa').checked = false; $('ia-activa').disabled = true;
  if (msg) $('ia-modelo').textContent = msg;
}

document.body.classList.add('sin-descargas');
(async () => {
  const c = window.claude;
  if (!c || typeof c.use !== 'function') return;
  c.use('downloads').then(d => { dl = d; if (d) document.body.classList.remove('sin-descargas'); }).catch(() => {});
  try { sample = await c.use('sample'); } catch (_) { sample = null; }
  if (!sample) return;
  let lim = null; try { lim = await sample.limits(); } catch (_) {}
  $('ia-box').hidden = false;
  if (lim && !lim.tools) { desactivarIA(MENSAJES_IA.tools_unavailable); return; }
  iaLista = true;
  $('ia-modelo').textContent = 'Usa tu propia cuenta de Claude; la primera vez te pedirá permiso.';
})();
