@echo off
cd /d "%~dp0"
rem Para usar otro modelo, quita "rem" de la siguiente linea y cambia el nombre:
rem set MODELO=qwen2.5:14b
rem Para permitir otras computadoras de la red, quita "rem" de esta linea:
rem set HOST=0.0.0.0
rem Modo de trabajo: guiado (recomendado, por omision), herramientas o simple:
rem set MODO=guiado
python servidor.py
if errorlevel 9009 py servidor.py
pause
