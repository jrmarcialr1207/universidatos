# Experimento: ¿qué tan bien responde Universidatos?

Compara cuatro formas de responder las mismas 52 preguntas, cuyas respuestas correctas se tomaron directamente de las tablas y series (archivo `preguntas.json`):

| Condición | Qué hace el modelo |
|---|---|
| `sin_herramientas` | Responde de memoria, sin datos (línea base) |
| `rag` | Recibe las series más parecidas a la pregunta y redacta |
| `herramientas` | Elige y usa las 14 herramientas del sistema |
| `guiado` | El planificador calcula los hechos y el modelo solo los redacta |

Las preguntas son de 8 tipos: dato de una serie, cambio entre años, dato de una tabla por espacio, ordenamiento, razones y porcentajes, cambio en un espacio, fichas, y 6 preguntas **sin respuesta en los datos** (por ejemplo, la matrícula de 2030), donde lo correcto es decir que no se tiene el dato.

## Cómo correrlo

1. Copia estos archivos a la carpeta del servidor local (la que tiene `servidor.py`): `experimento.py`, `evaluar.py`, `preguntas.json`.
2. Abre Ollama y verifica que tienes el modelo: `ollama pull qwen2.5:7b`
3. En una terminal, dentro de esa carpeta:

```
python experimento.py
```

Tarda aproximadamente 1 a 2 horas con qwen2.5:7b (208 respuestas; el modo con herramientas es el más lento). Puedes dejarlo corriendo: si se interrumpe, al volver a ejecutarlo continúa donde se quedó.

4. Al terminar:

```
python evaluar.py
```

Genera `resumen.md` (tablas de resultados) y `calificacion.csv` (cada respuesta con su calificación). Envíame esos dos archivos y el `resultados_qwen2.5_7b.jsonl`.

## Opcional (fortalece el artículo)

- **Otro modelo local**, para mostrar que el resultado no depende de Qwen: `ollama pull llama3.1:8b` y luego `python experimento.py --modelo llama3.1:8b`
- **Variación entre corridas**: `python experimento.py --repeticiones 3`

## Notas

- No cierres la computadora ni la dejes suspender mientras corre.
- `generar_preguntas.py` vuelve a crear `preguntas.json` a partir de los datos (no necesitas correrlo).
