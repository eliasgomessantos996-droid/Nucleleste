# Para e remove a tarefa do servidor do Sistema Nucleleste (usado na atualização, na desinstalação e nos testes).
param(
    [string]$Nome = "Sistema Nucleleste (servidor)",
    [switch]$SoParar    # só interrompe (para trocar arquivos); não apaga a tarefa
)
$ErrorActionPreference = "SilentlyContinue"
if (Get-ScheduledTask -TaskName $Nome) {
    Stop-ScheduledTask -TaskName $Nome
    if (-not $SoParar) { Unregister-ScheduledTask -TaskName $Nome -Confirm:$false }
}
exit 0
