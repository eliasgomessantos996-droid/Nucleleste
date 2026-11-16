# Exporta todas as tabelas do banco Access (BD.mdb) para arquivos JSON.
# Precisa rodar no PowerShell 32 bits (o driver Jet/ACE instalado é 32 bits):
#   C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe -ExecutionPolicy Bypass -File exportar_mdb.ps1 -Banco ..\BD.mdb -Senha XXXX -Saida ..\dados\exportacao_mdb
param(
    [Parameter(Mandatory = $true)][string]$Banco,
    [string]$Senha = "",
    [Parameter(Mandatory = $true)][string]$Saida
)
$ErrorActionPreference = "Stop"
$Banco = (Resolve-Path $Banco).Path
New-Item -ItemType Directory -Force $Saida | Out-Null
$Saida = (Resolve-Path $Saida).Path

$provedores = @("Microsoft.Jet.OLEDB.4.0", "Microsoft.ACE.OLEDB.12.0")
$cn = $null
foreach ($p in $provedores) {
    try {
        $cs = "Provider=$p;Data Source=$Banco;Mode=Read;Jet OLEDB:Database Password=$Senha"
        $cn = New-Object System.Data.OleDb.OleDbConnection($cs)
        $cn.Open()
        break
    } catch {
        $cn = $null
        $ultimoErro = $_.Exception.Message
    }
}
if (-not $cn) { Write-Error "Não foi possível abrir o banco: $ultimoErro"; exit 1 }

$utf8 = New-Object System.Text.UTF8Encoding($false)
$tabelas = $cn.GetSchema("Tables") | Where-Object { $_.TABLE_TYPE -eq "TABLE" }
foreach ($t in $tabelas) {
    $nome = $t.TABLE_NAME
    $cmd = $cn.CreateCommand()
    $cmd.CommandText = "SELECT * FROM [$nome]"
    $rd = $cmd.ExecuteReader()
    $cols = @()
    for ($i = 0; $i -lt $rd.FieldCount; $i++) { $cols += $rd.GetName($i) }
    $linhas = New-Object System.Collections.ArrayList
    while ($rd.Read()) {
        $o = [ordered]@{}
        for ($i = 0; $i -lt $rd.FieldCount; $i++) {
            $v = $rd.GetValue($i)
            if ($v -is [System.DBNull]) { $v = $null }
            elseif ($v -is [datetime]) { $v = $v.ToString("yyyy-MM-ddTHH:mm:ss") }
            elseif ($v -is [decimal]) { $v = [double]$v }
            elseif ($v -is [byte[]]) { $v = $null }
            $o[$cols[$i]] = $v
        }
        [void]$linhas.Add($o)
    }
    $rd.Close()
    $json = ConvertTo-Json -InputObject @($linhas) -Depth 3
    [System.IO.File]::WriteAllText((Join-Path $Saida "$nome.json"), $json, $utf8)
    Write-Host ("  {0,-22} {1,6} registros" -f $nome, $linhas.Count)
}
$cn.Close()
Write-Host "Exportação concluída em $Saida"
