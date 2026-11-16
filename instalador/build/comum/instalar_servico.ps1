# Cria (ou recria) a tarefa do Windows que mantém o servidor do Sistema Nucleleste sempre no ar:
#   - inicia no boot do computador, antes de qualquer usuário entrar (conta SYSTEM);
#   - se o processo cair, o Windows o reinicia (a cada 1 minuto, até 999 vezes);
#   - a cada 5 minutos tenta iniciar de novo (não faz nada se já estiver rodando) como segunda proteção;
#   - sem limite de tempo de execução e permitido em notebook na bateria.
# Precisa de administrador (a menos que se use -ContaAtual, para testes: inicia no logon do usuário atual).
param(
    [Parameter(Mandatory = $true)][string]$Exe,       # ...\py\Nucleleste.exe
    [Parameter(Mandatory = $true)][string]$Script,    # ...\tray.pyw
    [string]$Dados = "",                              # pasta dos dados (opcional; o programa também lê local_dados.txt)
    [string]$Nome = "Sistema Nucleleste (servidor)",
    [int]$ReinicioMinutos = 1,
    [int]$ReforcoMinutos = 5,
    [switch]$ContaAtual,
    [switch]$NaoIniciar
)
$ErrorActionPreference = "Stop"
try {
    $dir = Split-Path $Script -Parent
    $acao = New-ScheduledTaskAction -Execute $Exe -Argument ('"{0}" --servidor' -f $Script) -WorkingDirectory $dir

    if ($ContaAtual) {
        $gatilho1 = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
        $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
    } else {
        $gatilho1 = New-ScheduledTaskTrigger -AtStartup
        $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
    }
    # reforço periódico (não duplica: MultipleInstances = IgnoreNew)
    $gatilho2 = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $ReforcoMinutos)

    $config = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
        -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes $ReinicioMinutos) `
        -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -Hidden

    Register-ScheduledTask -TaskName $Nome -Action $acao -Trigger @($gatilho1, $gatilho2) -Principal $principal -Settings $config `
        -Description "Mantém o Sistema de Recepção Nucleleste no ar (inicia com o Windows e reinicia se cair)." -Force | Out-Null
    if (-not $NaoIniciar) { Start-ScheduledTask -TaskName $Nome }
    Write-Host "Tarefa '$Nome' criada."
    exit 0
} catch {
    Write-Host "ERRO ao criar a tarefa: $($_.Exception.Message)"
    exit 1
}
