@echo off
setlocal
title Migrar dados do sistema antigo (BD.mdb)
cd /d "%~dp0"

set /p DADOS=<"%~dp0local_dados.txt"
echo ==============================================================
echo  Importa os dados do sistema antigo (BD.mdb + planilha .xlsm)
echo  ATENCAO: os dados atuais do sistema serao SUBSTITUIDOS.
echo  Uma copia do banco atual e guardada na pasta de backups.
echo  Pasta dos dados: %DADOS%
echo ==============================================================
echo.
set "MDB="
set /p "MDB=Caminho do BD.mdb: "
set "XLSM="
set /p "XLSM=Caminho da planilha .xlsm (opcional, para o historico de logins): "
set "SENHA="
set /p "SENHA=Senha do banco Access (a mesma usada na planilha): "
echo.
set /p "OK=Digite SIM para substituir os dados do sistema: "
if /I not "%OK%"=="SIM" ( echo Cancelado. & pause & exit /b 0 )

echo Fechando o sistema...
taskkill /F /IM Nucleleste.exe >nul 2>nul
timeout /t 2 /nobreak >nul

set "PS=%SystemRoot%\SysWOW64\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PS%" set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
set "EXPORT=%TEMP%\nucleleste_exportacao"
echo.
echo 1/2 Exportando o BD.mdb...
"%PS%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0ferramentas\exportar_mdb.ps1" -Banco "%MDB%" -Senha "%SENHA%" -Saida "%EXPORT%"
if errorlevel 1 ( echo Falha ao exportar o banco Access. Verifique o caminho e a senha. & pause & exit /b 1 )

echo.
echo 2/2 Importando...
set "NUCLELESTE_DADOS=%DADOS%"
if defined XLSM (
    "%~dp0py\python.exe" "%~dp0ferramentas\importar_dados.py" --dump "%EXPORT%" --banco "%DADOS%\sistema.db" --planilha "%XLSM%" --substituir
) else (
    "%~dp0py\python.exe" "%~dp0ferramentas\importar_dados.py" --dump "%EXPORT%" --banco "%DADOS%\sistema.db" --substituir
)
set "RES=%ERRORLEVEL%"

rem a exportacao contem as senhas antigas em texto puro: apagar sempre
rmdir /s /q "%EXPORT%" 2>nul

echo Reiniciando o sistema...
start "" "%~dp0py\Nucleleste.exe" "%~dp0tray.pyw"
if not "%RES%"=="0" ( echo A importacao falhou. O banco anterior continua em %DADOS%\backups. ) else ( echo. & echo Migracao concluida. Os usuarios entram com as mesmas senhas do sistema antigo. )
pause
