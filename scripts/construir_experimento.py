"""Arma pagina/experimento-claude.html: la página de consulta con Claude + el modo experimento (corre preguntas.json)."""
import json
from pathlib import Path
B = str(Path(__file__).resolve().parent.parent) + '/'
pag = open(B + 'claude_page/consulta-universidatos.html', encoding='utf-8').read()
exp = open(B + 'web/experimento_claude.js', encoding='utf-8').read()
preg = json.load(open(B + 'local_server/preguntas.json', encoding='utf-8'))
preg = [{'id': q['id'], 'pregunta': q['pregunta']} for q in preg]  # sin las respuestas correctas
estilo = """<style>
.panel-exp{max-width:1100px;margin:16px auto;padding:16px;border:2px solid var(--acento,#2563eb);border-radius:10px;background:var(--fondo-panel,#fff)}
.panel-exp h2{margin:0 0 8px;font-size:1.2rem}
.panel-exp .xpc-botones{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.xpc-tabla-caja{max-height:420px;overflow:auto;margin-top:8px}
#xpc-tabla{border-collapse:collapse;width:100%;font-size:.88rem}
#xpc-tabla th,#xpc-tabla td{border-bottom:1px solid #ddd;padding:4px 6px;text-align:left;vertical-align:top}
#xpc-tabla{table-layout:fixed}
#xpc-tabla td,#xpc-tabla th{white-space:normal!important;font-family:var(--f-body,inherit)!important;overflow-wrap:anywhere}
#xpc-tabla th:nth-child(1){width:48px}#xpc-tabla th:nth-child(2){width:38%}#xpc-tabla th:nth-child(4){width:44px}
</style>
"""
pag = pag.replace('<title>Consulta Universidatos UAEMEX</title>', '<title>Experimento Universidatos</title>', 1)
i = pag.index('<script>\n(function(){\nconst D = JSON.parse(')
pag = pag[:i] + estilo + '<script id="preguntas-exp" type="application/json">' + json.dumps(preg, ensure_ascii=False).replace('</', '<\\/') + '</script>\n' + pag[i:]
fin = '})();\n</script>'
assert pag.count(fin) == 1
pag = pag.replace(fin, exp + '\n' + fin)
open(B + 'claude_page/experimento-claude.html', 'w', encoding='utf-8').write(pag)
print('experimento', len(pag))
