@echo off
chcp 65001 > nul
title Gerador de Etiquetas ZPL

echo.
echo  ================================================
echo   Gerador de Etiquetas ZPL ^-^> PDF
echo  ================================================
echo.
echo  Iniciando servidor... Aguarde.
echo.

cd /d "%~dp0"

start "" http://localhost:5000

python app.py

pause
