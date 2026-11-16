@echo off
setlocal
title Importar dados do programa Banco de Horas antigo
cd /d "%~dp0"

set /p DADOS=<"%~dp0local_dados.txt"
echo ==============================================================
echo  Traz para o modulo "Banco de Horas" do Nucleleste os dados do
echo  programa antigo (arquivo banco.sqlite3): funcionarios, ponto,
echo  jornadas, documentos, mensagens e usuarios.
echo  So funciona se o Banco de Horas do Nucleleste ainda estiver vazio.
echo  Uma copia do banco atual e guardada na pasta de backups.
echo  Pasta dos dados: %DADOS%
echo ==============================================================
echo.
set "ARQ=C:\ProgramData\BancoDeHoras\dados\banco.sqlite3"
set /p "ARQ=Caminho do banco.sqlite3 [Enter = %ARQ%]: "
set "ARQ=%ARQ:"=%"
if not exist "%ARQ%" ( echo Arquivo nao encontrado: %ARQ% & pause & exit /b 1 )
"%~dp0py\python.exe" -m app.cli --dados "%DADOS%" importar-bh "%ARQ%"
pause
