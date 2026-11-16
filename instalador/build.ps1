# Gera instalador\saida\Setup-Nucleleste-<versão>.exe (Windows 10/11, 32 e 64 bits).
# Requisitos na máquina de build: Python 3 com pip, Inno Setup 6 e internet (só para baixar o Python embutido e as dependências).
#   powershell -ExecutionPolicy Bypass -File instalador\build.ps1
param(
    [string]$PythonVersao = "3.14.4",     # versão do Python embutido (precisa existir em python.org/ftp/python)
    [string]$Iscc = ""
)
$ErrorActionPreference = "Stop"
$aqui = $PSScriptRoot
$raiz = Split-Path $aqui -Parent
$cache = Join-Path $aqui "cache"
$build = Join-Path $aqui "build"
$versao = (Get-Content (Join-Path $raiz "VERSION") -Raw).Trim()
$pyMenor = ($PythonVersao -split '\.')[0..1] -join '.'           # 3.14
$pyTag = ($PythonVersao -split '\.')[0..1] -join ''               # 314

if (-not $Iscc) {
    foreach ($c in @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe")) {
        if (Test-Path $c) { $Iscc = $c; break }
    }
}
if (-not $Iscc) { throw "Inno Setup 6 não encontrado. Instale com: winget install JRSoftware.InnoSetup" }
$python = (Get-Command python -ErrorAction Stop).Source
Write-Host "Versão $versao | Python embutido $PythonVersao | Inno: $Iscc"

if (Test-Path $build) { Remove-Item $build -Recurse -Force }
New-Item -ItemType Directory -Force $cache, $build | Out-Null

# --- ícone e imagens (Pillow só é necessário aqui)
if (-not (Test-Path (Join-Path $raiz "nucleleste.ico"))) { & $python (Join-Path $aqui "gerar_icone.py") }
# imagens animadas do instalador (átomo e NucleAI)
& $python (Join-Path $aqui "gerar_visual.py")
if ($LASTEXITCODE -ne 0) { throw "gerar_visual.py falhou (precisa do Pillow: pip install pillow)" }

# --- Python embutido + dependências, uma cópia por arquitetura
$arqs = @(
    @{ nome = "x64"; zip = "amd64"; plataforma = "win_amd64" },
    @{ nome = "x86"; zip = "win32"; plataforma = "win32" }
)
foreach ($a in $arqs) {
    $arquivo = "python-$PythonVersao-embed-$($a.zip).zip"
    $zip = Join-Path $cache $arquivo
    if (-not (Test-Path $zip)) {
        Write-Host "Baixando $arquivo ..."
        Invoke-WebRequest "https://www.python.org/ftp/python/$PythonVersao/$arquivo" -OutFile $zip -UseBasicParsing
    }
    $dest = Join-Path $build "py-$($a.nome)"
    Expand-Archive $zip $dest -Force
    # a cópia de pythonw.exe vira "Nucleleste.exe": o Gerenciador de Tarefas e o firewall mostram o nome do programa
    Copy-Item (Join-Path $dest "pythonw.exe") (Join-Path $dest "Nucleleste.exe")
    # caminhos de importação: stdlib zipada, pasta do Python, pacotes instalados e a raiz do programa (..)
    $pth = Join-Path $dest "python$pyTag._pth"
    Set-Content $pth -Encoding ASCII -Value @("python$pyTag.zip", ".", "Lib\site-packages", "..", "import site")
    $site = Join-Path $dest "Lib\site-packages"
    New-Item -ItemType Directory -Force $site | Out-Null
    & $python -m pip install --disable-pip-version-check -q --target $site --platform $a.plataforma --python-version $pyMenor `
        --implementation cp --only-binary=:all: -r (Join-Path $raiz "requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "pip falhou para $($a.nome)" }
    if ($a.nome -eq "x64") {
        # robô da Medcloud (só 64 bits; usa o Chrome/Edge do computador, então não há navegador para embutir)
        & $python -m pip install --disable-pip-version-check -q --target $site --platform $a.plataforma --python-version $pyMenor `
            --implementation cp --only-binary=:all: -r (Join-Path $raiz "requirements-medcloud.txt")
        if ($LASTEXITCODE -ne 0) { throw "pip falhou para o playwright ($($a.nome))" }
    }
    Remove-Item (Join-Path $site "bin") -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem $dest -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
    Write-Host ("  {0}: {1:N1} MB" -f $a.nome, ((Get-ChildItem $dest -Recurse -File | Measure-Object Length -Sum).Sum / 1MB))
}

# --- arquivos comuns (código do sistema)
$comum = Join-Path $build "comum"
New-Item -ItemType Directory -Force $comum | Out-Null
Copy-Item (Join-Path $raiz "app") (Join-Path $comum "app") -Recurse
Get-ChildItem (Join-Path $comum "app") -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
foreach ($f in "tray.pyw", "nucleleste.ico", "VERSION", "LEIA-ME.md") { Copy-Item (Join-Path $raiz $f) $comum }
$fer = Join-Path $comum "ferramentas"
New-Item -ItemType Directory -Force $fer | Out-Null
foreach ($f in "exportar_mdb.ps1", "importar_dados.py") { Copy-Item (Join-Path $raiz "ferramentas\$f") $fer }
foreach ($f in "Migrar dados do sistema antigo.cmd", "Importar planilha de exames.cmd", "Importar dados do Banco de Horas antigo.cmd") { Copy-Item (Join-Path $aqui $f) $comum }
foreach ($f in "instalar_servico.ps1", "remover_servico.ps1") { Copy-Item (Join-Path $aqui $f) $comum }

# --- compila o instalador
& $Iscc "/DVersao=$versao" "/DRaiz=$raiz" (Join-Path $aqui "nucleleste.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup falhou" }
$saida = Join-Path $aqui "saida\Setup-Nucleleste-$versao.exe"
Write-Host ("`nPronto: {0} ({1:N1} MB)" -f $saida, ((Get-Item $saida).Length / 1MB))
