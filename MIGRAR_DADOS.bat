@echo off
setlocal
title Migrar dados do sistema antigo (BD.mdb)
cd /d "%~dp0"

echo ==============================================================
echo  Importa os dados do sistema antigo (BD.mdb + planilha .xlsm)
echo  ATENCAO: os dados do sistema NOVO serao SUBSTITUIDOS.
echo  (uma copia do banco atual e guardada em dados\backups)
echo  Feche o sistema novo (janela do INICIAR) antes de continuar.
echo ==============================================================
echo.

set "MDB=%~dp0..\BD.mdb"
set /p "MDB=Caminho do BD.mdb [%MDB%]: "
set "XLSM="
for %%F in ("%~dp0..\*.xlsm") do set "XLSM=%%~fF"
set /p "XLSM=Caminho da planilha .xlsm (para o historico de logins) [%XLSM%]: "
set "SENHA="
set /p "SENHA=Senha do banco Access (a mesma usada na planilha): "
echo.
set /p "OK=Digite SIM para substituir os dados do sistema novo: "
if /I not "%OK%"=="SIM" (
    echo Cancelado.
    pause
    exit /b 0
)

set "VENV=%LOCALAPPDATA%\SistemaNucleleste\venv"
if not exist "%VENV%\Scripts\python.exe" (
    echo Rode o INICIAR.bat uma vez antes da migracao.
    pause
    exit /b 1
)

set "EXPORT=%~dp0dados\exportacao_mdb"
echo.
echo 1/2 Exportando o BD.mdb...
C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0ferramentas\exportar_mdb.ps1" -Banco "%MDB%" -Senha "%SENHA%" -Saida "%EXPORT%"
if errorlevel 1 (
    echo Falha ao exportar o banco Access. Verifique o caminho e a senha.
    pause
    exit /b 1
)

echo.
echo 2/2 Importando para o sistema novo...
if defined XLSM (
    "%VENV%\Scripts\python.exe" ferramentas\importar_dados.py --dump "%EXPORT%" --planilha "%XLSM%" --substituir
) else (
    "%VENV%\Scripts\python.exe" ferramentas\importar_dados.py --dump "%EXPORT%" --substituir
)
set "RES=%ERRORLEVEL%"

rem A exportacao contem senhas em texto puro do sistema antigo: apagar.
rmdir /s /q "%EXPORT%" 2>nul

if not "%RES%"=="0" (
    echo A importacao falhou. O banco anterior continua em dados\backups.
) else (
    echo.
    echo Migracao concluida. Os usuarios entram com as mesmas senhas do sistema antigo.
)
pause
