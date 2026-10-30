#!/bin/bash
# Arranque para Mac y Linux. En Mac se puede abrir con doble clic.
cd "$(dirname "$0")"

# Modelo de Ollama (descárgalo antes con: ollama pull qwen2.5:14b)
export MODELO=qwen2.5:14b

# Para permitir otras computadoras de la red, quita el # de la siguiente línea:
# export HOST=0.0.0.0

# Modo de trabajo: guiado (recomendado), herramientas o simple
export MODO=guiado

python3 servidor.py
