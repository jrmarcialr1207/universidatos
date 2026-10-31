# Resultados del experimento

## Resumen por condición

| Modelo | Condición | Respuestas | Exactitud (con dato) | Cifra incorrecta | Se abstuvo | Abstención correcta (sin dato) | Errores | Segundos (mediana) |
|---|---|---|---|---|---|---|---|---|
| claude (default) | claude | 52 | 100.0 % | 0.0 % | 0.0 % | 0.0 % | 0 | 2.8 |
| llama3.1:8b | sin_herramientas | 52 | 0.0 % | 8.7 % | 91.3 % | 100.0 % | 0 | 2.0 |
| llama3.1:8b | rag | 52 | 43.5 % | 39.1 % | 17.4 % | 50.0 % | 0 | 7.9 |
| llama3.1:8b | herramientas | 52 | 8.7 % | 34.8 % | 56.5 % | 33.3 % | 0 | 16.1 |
| llama3.1:8b | guiado | 52 | 63.0 % | 19.6 % | 17.4 % | 66.7 % | 0 | 3.2 |
| qwen2.5:7b | sin_herramientas | 52 | 0.0 % | 10.9 % | 89.1 % | 100.0 % | 0 | 1.5 |
| qwen2.5:7b | rag | 52 | 50.0 % | 39.1 % | 10.9 % | 66.7 % | 0 | 10.2 |
| qwen2.5:7b | herramientas | 52 | 34.8 % | 45.7 % | 19.6 % | 16.7 % | 0 | 8.4 |
| qwen2.5:7b | guiado | 52 | 60.9 % | 30.4 % | 8.7 % | 50.0 % | 0 | 3.7 |

## Exactitud por categoría (% de respuestas correctas)

| Modelo | Condición | serie | cambio | tabla | orden | razon | cambio_espacio | ficha | sin_respuesta |
|---|---|---|---|---|---|---|---|---|---|
| claude (default) | claude | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 0.0 |
| llama3.1:8b | sin_herramientas | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |
| llama3.1:8b | rag | 100.0 | 71.4 | 0.0 | 0.0 | 20.0 | 0.0 | 0.0 | 50.0 |
| llama3.1:8b | herramientas | 0.0 | 42.9 | 0.0 | 0.0 | 20.0 | 0.0 | 0.0 | 33.3 |
| llama3.1:8b | guiado | 78.6 | 57.1 | 50.0 | 75.0 | 20.0 | 50.0 | 100.0 | 66.7 |
| qwen2.5:7b | sin_herramientas | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |
| qwen2.5:7b | rag | 100.0 | 100.0 | 0.0 | 0.0 | 40.0 | 0.0 | 0.0 | 66.7 |
| qwen2.5:7b | herramientas | 71.4 | 57.1 | 0.0 | 0.0 | 40.0 | 0.0 | 0.0 | 16.7 |
| qwen2.5:7b | guiado | 78.6 | 57.1 | 50.0 | 50.0 | 20.0 | 50.0 | 100.0 | 50.0 |

Exactitud (con dato): preguntas cuya respuesta está en los datos. Abstención correcta (sin dato): preguntas fuera de los datos en las que el sistema dijo que no tenía la información en lugar de dar una cifra.
Revisa a mano en calificacion.csv las respuestas marcadas como incorrectas: la calificación automática busca la cifra exacta y puede no reconocer formas como «cerca de 100 mil».
