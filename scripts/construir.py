"""Builds claude_page/consulta-universidatos.html (Claude version) and the index.html files of static_site/ and local_server/ from web/ and data/."""
import re
from pathlib import Path
B = str(Path(__file__).resolve().parent.parent) + '/'
t = open(B + 'web/plantilla_publica.html', encoding='utf-8').read()
headc = open(B + 'web/_head.css.html', encoding='utf-8').read()
busc = open(B + 'web/buscador.js', encoding='utf-8').read()
data = open(B + 'data/series_uaemex.json', encoding='utf-8').read().replace('</', '<\\/')
tablas = open(B + 'data/tablas_uaemex.json', encoding='utf-8').read().replace('</', '<\\/')
# las tablas van comprimidas (gzip + base64) para que la página pese poco y quepa en el límite de tamaño; fflate (MIT) las descomprime
import gzip, base64
ff = open(B + 'web/vendor/fflate-0.8.2.umd.js', encoding='utf-8').read()
gz = base64.b64encode(gzip.compress(open(B + 'data/tablas_uaemex.json', 'rb').read(), 9)).decode()
def comprimir(html):
    viejo_t = '<script id="tablas" type="application/json">__TABLAS__</script>'
    assert html.count(viejo_t) == 1
    html = html.replace(viejo_t, '<script>/* fflate 0.8.2 · MIT License · (c) 2023 Arjun Barrett */\n' + ff + '</script>\n<script id="tablas" type="text/plain">' + gz + '</script>')
    viejo_p = "const TAB = JSON.parse(document.getElementById('tablas').textContent);"
    assert html.count(viejo_p) == 1
    return html.replace(viejo_p, "const TAB = (()=>{ const b=atob(document.getElementById('tablas').textContent.trim()), u=new Uint8Array(b.length); for(let i=0;i<b.length;i++) u[i]=b.charCodeAt(i); return JSON.parse(new TextDecoder().decode(fflate.gunzipSync(u))); })();")
# index.html para GitHub Pages y Ollama
head = headc.replace('<style>\n/* Layout', '<style>\n[hidden]{display:none!important}\nhtml,body{margin:0}\nimg{max-width:100%}\n/* Layout', 1)
idx = comprimir(t.replace('__HEAD__', head)).replace('__BUSCADOR__', busc).replace('__DATA__', data)
for f in ['static_site/index.html', 'local_server/index.html']:
    open(B + f, 'w', encoding='utf-8').write(idx)
# versión Claude
js = open(B + 'web/ia_claude.js', encoding='utf-8').read()
head = headc.replace('<style>\n/* Layout', '<style>\n[hidden]{display:none!important}\nimg{max-width:100%}\n/* Layout', 1)
head = head.replace('.panel-ia + .panel-ia{margin-top:0}', '.panel-ia + .panel-ia{margin-top:0}\n.sin-descargas .acciones{display:none}')
body = t[t.index('<body>') + 6:t.index('</body>')]
ini, fin = body.index('async function preguntarIA(b){'), body.index('/* ---------- Explorador ---------- */')
body = body[:ini] + js + '\n\n' + body[fin:]
viejo = re.search(r"function descargar\(nombre,blob\)\{.*?\}\n", body).group(0)
body = body.replace(viejo, """async function descargar(nombre,blob){
  if(!dl) return;
  try{ await dl.save({filename:nombre,data:blob}); }
  catch(e){ if(e&&e.code!=='declined'){ const n=p('No se pudo guardar el archivo'+(e&&e.code==='rate_limited'?': espera un momento e intenta de nuevo.':'.'),'aviso err'); $('respuesta').prepend(n); setTimeout(()=>n.remove(),6000); } }
}
""")
for a, b in [(' Redactar la respuesta con IA local</label>', ' Responder también con Claude</label>'),
             ('Escribe lo que buscas con palabras sencillas, por ejemplo «matrícula licenciatura 2020» o «PTC en el SNII desde 2015». Verás la cifra, su evolución y el archivo de origen.',
              'Escribe lo que buscas, por ejemplo «matrícula licenciatura 2020», o pide un cálculo o una gráfica: «crecimiento anual de la matrícula desde 2015», «grafica la matrícula por nivel». El buscador responde al instante y Claude redacta, calcula y grafica con los datos oficiales.')]:
    assert body.count(a) == 1, a
    body = body.replace(a, b)
pag = '<title>Consulta Universidatos UAEMEX</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n' + head + body
pag = comprimir(pag).replace('__BUSCADOR__', busc).replace('__DATA__', data)
assert 'api/estado' not in pag
open(B + 'claude_page/consulta-universidatos.html', 'w', encoding='utf-8').write(pag)
print('construido', len(pag))
