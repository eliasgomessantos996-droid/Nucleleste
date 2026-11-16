@echo off
setlocal
title Importar planilha de exames (EXAMES.xlsx)
cd /d "%~dp0"

set /p DADOS=<"%~dp0local_dados.txt"
echo ==============================================================
echo  Importa a planilha EXAMES.xlsx (controle de realizacao de exames)
echo  para o modulo "Exames realizados".
echo  Os lancamentos que vieram de uma importacao anterior sao
echo  substituidos; os lancados a mao no sistema sao mantidos.
echo  Uma copia do banco atual e guardada na pasta de backups.
echo  Pasta dos dados: %DADOS%
echo ==============================================================
echo.
set "XLSX="
set /p "XLSX=Caminho da planilha EXAMES.xlsx: "
if not defined XLSX ( echo Cancelado. & pause & exit /b 0 )
set "XLSX=%XLSX:"=%"
if not exist "%XLSX%" ( echo Arquivo nao encontrado: %XLSX% & pause & exit /b 1 )
echo.
echo Importando (leva cerca de 1 minuto)...
"%~dp0py\python.exe" -m app.cli --dados "%DADOS%" importar-exames "%XLSX%"
if errorlevel 1 ( echo A importacao falhou. ) else ( echo. & echo Concluido. Abra o sistema em "Exames realizados". )
pause
