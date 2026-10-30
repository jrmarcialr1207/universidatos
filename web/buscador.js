/* Buscador por reglas para las series de la Agenda Estadística UAEMEX.
   Funciona en el navegador (window.Buscador) y en Node (module.exports). */
(function (raiz) {
  const norm = s => String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
    .replace(/[^a-z0-9%ñ\s]/g, ' ').replace(/\s+/g, ' ').trim();

  const VACIAS = new Set(('de la el en los las del y o a al un una unos unas cuantos cuantas cuanto cuanta cual cuales ' +
    'como ha han hay que por para con se su sus es son fue fueron era total numero cantidad dato datos ' +
    'universidad uaemex uaem tiene tenia tuvo hubo me dime muestra mostrar ver quiero saber sobre ' +
    'desde hasta entre ano anos año años ultimos ultimo periodo durante cada evolucion crecimiento crecido ' +
    'cambio cambiado comportamiento tendencia historico historia actual hoy ahora este esta escuela escuelas institucion instituciones general').split(' '));

  // Cada clave del usuario se traduce a uno o varios términos que aparecen en las rutas.
  const SINONIMOS = {
    licenciatura: ['estudios profesionales', 'licenciatura'], licenciaturas: ['estudios profesionales', 'licenciatura'],
    carrera: ['estudios profesionales'], carreras: ['estudios profesionales'], superior: ['estudios profesionales'],
    profesional: ['estudios profesionales'], profesionales: ['estudios profesionales'],
    posgrado: ['estudios avanzados'], posgrados: ['estudios avanzados'], avanzados: ['estudios avanzados'],
    prepa: ['bachillerato'], preparatoria: ['bachillerato'], preparatorias: ['bachillerato'], bachilleratos: ['bachillerato'],
    alumnos: ['matricula', 'alumnado'], alumnas: ['matricula', 'alumnado'], estudiantes: ['matricula', 'alumnado'], inscritos: ['matricula'],
    alumnado: ['matricula', 'alumnado'], matriculados: ['matricula'],
    profesores: ['personal academico', 'ptc'], profesoras: ['personal academico', 'ptc'], docentes: ['personal academico', 'ptc'],
    maestros: ['personal academico', 'ptc'], academicos: ['personal academico'],
    ptc: ['ptc'], 'tiempo completo': ['tiempo completo', 'ptc'],
    sni: ['snii'], snii: ['snii'], sistema: ['snii'],
    investigadores: ['investigadoras', 'snii'], investigadoras: ['investigadoras'], investigacion: ['proyectos de investigacion'],
    proyectos: ['proyectos'], doctores: ['doctorado'], doctorados: ['doctorado'], maestrias: ['maestria'], especialidades: ['especialidad'],
    titulados: ['titulacion', 'tituladas'], titulacion: ['titulacion', 'tituladas'], tituladas: ['tituladas'],
    egresados: ['egreso', 'egresadas'], egresadas: ['egreso', 'egresadas'], egreso: ['egreso'],
    graduados: ['graduadas', 'graduacion'],
    eficiencia: ['eficiencia terminal'], terminal: ['eficiencia terminal'],
    abandono: ['abandono'], desercion: ['abandono'], reprobacion: ['reprobacion'], reprobados: ['reprobacion'],
    ingreso: ['ingreso'], aspirantes: ['solicitudes de ingreso'], solicitudes: ['solicitudes de ingreso'],
    aceptacion: ['aceptacion'], aceptados: ['inscrito a 1er', 'aceptacion'], nuevo: ['inscrito a 1er'], primer: ['inscrito a 1er'],
    becas: ['becado', 'becas'], becados: ['becado'], becarios: ['becado'],
    movilidad: ['nacional', 'internacional'], intercambio: ['internacional'], extranjero: ['internacional'], internacional: ['internacional'],
    presupuesto: ['recursos'], dinero: ['recursos'], recursos: ['recursos'], subsidio: ['subsidio'], ingresos: ['ingresos propios', 'ingresos'],
    gasto: ['aplicacion de los recursos'], computadoras: ['computadoras'], equipos: ['computadoras'],
    personal: ['personal'], trabajadores: ['personal'], administrativos: ['personal administrativo'],
    convenios: ['convenios'], cultura: ['presentaciones artisticas', 'cultural'], libros: ['libros', 'volumenes'],
    biblioteca: ['acervo bibliografico', 'bibliotecas'], bibliotecas: ['bibliotecas'], acervo: ['acervo'],
    programas: ['programas educativos', 'planes de estudio'], planes: ['planes de estudio'],
    calidad: ['calidad', 'excelencia'], acreditados: ['acreditad'], excelencia: ['excelencia'],
    tutoria: ['tutoria'], tutores: ['tutoras'], deporte: ['deportivas'], deportes: ['deportivas'],
    incorporadas: ['incorporad'], incorporados: ['incorporad'], particulares: ['incorporad'],
    cuerpos: ['cuerpos academicos'], patentes: ['patentes'], revistas: ['revistas'],
  };

  // Términos que, si el usuario no los menciona, deben restar puntos (evita que gane un desglose raro).
  const ESPECIFICOS = ['incorporad', 'porcentaje', '%', 'indice', 'cohorte', 'ciees', 'copaes', 'fomix', 'pifop', 'cifrhs', 'pnpc', 'sitaa', 'tutoria', 'excelencia', 'calidad', 'acreditad', 'capacitad', 'evaluables'];

  function analizar(texto, anioMin = 2004, anioMax = 2025) {
    const n = norm(texto);
    const anios = (n.match(/\b(19|20)\d{2}\b/g) || []).map(Number).filter(a => a >= 1990 && a <= 2100);
    let desde = null, hasta = null, unico = null;
    const ult = n.match(/ultimos? (\d{1,2}) anos?/);
    if (ult) { hasta = anioMax; desde = Math.max(anioMin, anioMax - Number(ult[1]) + 1); }
    else if (anios.length >= 2) { desde = Math.min(...anios); hasta = Math.max(...anios); }
    else if (anios.length === 1) {
      if (/\bdesde\b|\ba partir\b/.test(n)) { desde = anios[0]; hasta = anioMax; }
      else if (/\bhasta\b/.test(n)) { desde = anioMin; hasta = anios[0]; }
      else unico = anios[0];
    }
    const pideTasa = /porcentaje|%|indice|tasa|proporcion/.test(n);
    // frases de dos palabras primero
    let resto = ' ' + n.replace(/\b(19|20)\d{2}\b/g, ' ').replace(/ultimos? \d{1,2} anos?/, ' ') + ' ';
    const grupos = [];
    for (const k of Object.keys(SINONIMOS)) if (k.includes(' ') && resto.includes(' ' + k + ' ')) {
      grupos.push(SINONIMOS[k]); resto = resto.replace(' ' + k + ' ', ' ');
    }
    for (const w of resto.split(' ')) {
      if (!w || VACIAS.has(w) || /^\d+$/.test(w)) continue;
      if (SINONIMOS[w]) grupos.push(SINONIMOS[w]);
      else if (w.length >= 3) grupos.push([raizPalabra(w)]);
    }
    return { grupos, desde, hasta, unico, pideTasa, menciona: n };
  }
  function raizPalabra(w) { return w.length > 5 ? w.replace(/(es|s)$/, '') : w; }

  function crear(indicadores, series) {
    const lista = indicadores.filter(i => series[i.id] && Object.keys(series[i.id]).length).map(i => {
      const partes = i.ruta.split(' > ');
      return { ...i, _hoja: ' ' + norm(partes[partes.length - 1]) + ' ', _padres: ' ' + norm(partes.slice(0, -1).join(' ')) + ' ', _eje: ' ' + norm(i.eje) + ' ', _n: partes.length };
    });
    const contiene = (campo, t) => campo.includes(' ' + t) ;

    function buscar(texto, max = 8) {
      const q = analizar(texto);
      if (!q.grupos.length) return { q, resultados: [] };
      const res = [];
      for (const i of lista) {
        let pts = 0, cubiertos = 0; const faltan = [];
        for (const g of q.grupos) {
          let mejor = 0;
          for (const t of g) {
            if (contiene(i._hoja, t)) mejor = Math.max(mejor, 3);
            else if (contiene(i._padres, t)) mejor = Math.max(mejor, 2);
            else if (contiene(i._eje, t)) mejor = Math.max(mejor, 1.5);
          }
          if (mejor >= 1.5) cubiertos++; else faltan.push(g);
          pts += mejor;
        }
        if (pts < 2) continue;
        if (cubiertos === q.grupos.length) pts += 3;
        const texto_i = i._hoja + i._padres;
        for (const e of ESPECIFICOS) if (texto_i.includes(e) && !q.menciona.includes(e === '%' ? 'porcentaje' : e)) pts -= (e === '%' || e === 'porcentaje' || e === 'indice') && q.pideTasa ? 0 : 1.5;
        if (q.pideTasa && /%|porcentaje|indice/.test(texto_i)) pts += 1.5;
        if (i.archivo === 'His08' && !q.menciona.includes('incorporad') && !q.menciona.includes('particular')) pts -= 3;
        pts -= (i._n - 1) * 0.25;           // prefiere totales sobre desgloses profundos
        if (i._padres.trim() === '') pts += 0.5;
        res.push({ id: i.id, pts, faltan });
      }
      res.sort((a, b) => b.pts - a.pts);
      return { q, resultados: res.slice(0, max) };
    }
    return { buscar, analizar };
  }

  const api = { crear, analizar, norm };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else raiz.Buscador = api;
})(typeof window !== 'undefined' ? window : globalThis);
