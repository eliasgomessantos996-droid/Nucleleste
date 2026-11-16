; Instalador do Sistema de Recepção Nucleleste — Windows 10/11, 32 e 64 bits (um único Setup).
; Compilar com instalador\build.ps1 (monta a pasta build\ e chama o ISCC).
#ifndef Versao
  #define Versao "1.0.0"
#endif
#ifndef Raiz
  #define Raiz ".."
#endif
#define AppNome "Sistema de Recepção Nucleleste"

[Setup]
AppId={{B6F3C3D2-7A41-4E0B-9C2E-5D7A1F0A9E11}
AppName={#AppNome}
AppVersion={#Versao}
AppVerName={#AppNome} {#Versao}
AppPublisher=Nucleleste - Centro de Medicina Nuclear
DefaultDirName={autopf}\Nucleleste
UsePreviousAppDir=yes
DisableProgramGroupPage=yes
DisableDirPage=auto
UsedUserAreasWarning=no
; 64 bits instala em Program Files; 32 bits em Program Files (x86). O mesmo Setup serve para os dois.
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=commandline
OutputDir=saida
OutputBaseFilename=Setup-Nucleleste-{#Versao}
SetupIconFile={#Raiz}\nucleleste.ico
UninstallDisplayIcon={app}\nucleleste.ico
UninstallDisplayName={#AppNome}
WizardStyle=modern
DisableWelcomePage=no
; imagens geradas por gerar_visual.py (átomo e NucleAI); a lateral gira sozinha nas páginas de abertura e de conclusão
WizardImageFile=visual\lateral.bmp
WizardSmallImageFile=visual\pequena.bmp
Compression=lzma2/max
SolidCompression=yes
CloseApplications=no
ShowLanguageDialog=no
VersionInfoVersion={#Versao}
VersionInfoCompany=Nucleleste
VersionInfoDescription=Instalador do {#AppNome}

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Messages]
WelcomeLabel1=Bem-vindo ao Nucleleste
WelcomeLabel2=Este assistente instala o [name/ver] no seu computador, com a NucleAI, a assistente que ensina o passo a passo de cada tela.%n%nFeche os outros programas antes de continuar. Se for uma atualização, os seus dados são mantidos.
FinishedHeadingLabel=Tudo pronto!
FinishedLabel=O [name] foi instalado.%n%nEm qualquer tela do sistema, o botão redondo da NucleAI, no canto inferior direito, mostra o passo a passo do que você precisar.

[Tasks]
Name: "desktopicon"; Description: "Criar um atalho na Área de Trabalho"; GroupDescription: "Atalhos:"
Name: "servico"; Description: "Ligar o sistema junto com o computador, mesmo antes de alguém entrar no Windows, e reiniciá-lo sozinho se cair (recomendado)"; GroupDescription: "Funcionamento:"; Check: IsAdmin
Name: "iniciar"; Description: "Mostrar o ícone da bandeja quando um usuário entrar no Windows"; GroupDescription: "Funcionamento:"
Name: "firewall"; Description: "Liberar o acesso dos outros computadores da rede (Firewall do Windows)"; GroupDescription: "Funcionamento:"; Check: IsAdmin

[Dirs]
; pasta dos dados: gravável por todos os usuários do PC (o banco e os backups ficam aqui, fora de Program Files)
Name: "{code:DadosDir}"; Permissions: users-modify
Name: "{code:DadosDir}\backups"; Permissions: users-modify
Name: "{code:DadosDir}\logs"; Permissions: users-modify

[InstallDelete]
; limpeza total do programa antes de copiar a nova versão (os dados ficam em outra pasta e não são tocados)
Type: filesandordirs; Name: "{app}\py"
Type: filesandordirs; Name: "{app}\app"

[Files]
Source: "build\comum\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "build\py-x64\*"; DestDir: "{app}\py"; Flags: recursesubdirs createallsubdirs ignoreversion; Check: Is64BitInstallMode
Source: "build\py-x86\*"; DestDir: "{app}\py"; Flags: recursesubdirs createallsubdirs ignoreversion; Check: not Is64BitInstallMode
; quadros das animações do instalador (usados só durante a instalação, não vão para o computador)
Source: "visual\anim\*.bmp"; Flags: dontcopy

[Icons]
Name: "{autoprograms}\Sistema Nucleleste"; Filename: "{app}\py\Nucleleste.exe"; Parameters: """{app}\tray.pyw"""; WorkingDir: "{app}"; IconFilename: "{app}\nucleleste.ico"; Comment: "Inicia o sistema (ícone na bandeja)"
Name: "{autodesktop}\Sistema Nucleleste"; Filename: "{app}\py\Nucleleste.exe"; Parameters: """{app}\tray.pyw"""; WorkingDir: "{app}"; IconFilename: "{app}\nucleleste.ico"; Tasks: desktopicon
Name: "{autoprograms}\Nucleleste - Pasta dos dados"; Filename: "{code:DadosDir}"
Name: "{autoprograms}\Nucleleste - Migrar dados do sistema antigo"; Filename: "{app}\Migrar dados do sistema antigo.cmd"; WorkingDir: "{app}"; IconFilename: "{app}\nucleleste.ico"
Name: "{autoprograms}\Nucleleste - Importar planilha de exames"; Filename: "{app}\Importar planilha de exames.cmd"; WorkingDir: "{app}"; IconFilename: "{app}\nucleleste.ico"
Name: "{autoprograms}\Nucleleste - Importar dados do Banco de Horas antigo"; Filename: "{app}\Importar dados do Banco de Horas antigo.cmd"; WorkingDir: "{app}"; IconFilename: "{app}\nucleleste.ico"
Name: "{autoprograms}\Nucleleste - Leia-me"; Filename: "{app}\LEIA-ME.md"

[Registry]
; início automático junto com o Windows (todos os usuários quando instalado como administrador)
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "SistemaNucleleste"; ValueData: """{app}\py\Nucleleste.exe"" ""{app}\tray.pyw"""; Flags: uninsdeletevalue; Tasks: iniciar; Check: IsAdminInstallMode
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "SistemaNucleleste"; ValueData: """{app}\py\Nucleleste.exe"" ""{app}\tray.pyw"""; Flags: uninsdeletevalue; Tasks: iniciar; Check: not IsAdminInstallMode

[Run]
; inicia a bandeja como o usuário que abriu o instalador (não como administrador elevado)
Filename: "{app}\py\Nucleleste.exe"; Parameters: """{app}\tray.pyw"""; WorkingDir: "{app}"; Description: "Iniciar o sistema agora (ícone na bandeja)"; Flags: nowait postinstall runasoriginaluser
Filename: "{cmd}"; Parameters: "/C timeout /T 5 /NOBREAK >nul & start """" ""http://localhost:{code:Porta}"""; Description: "Abrir o sistema no navegador"; Flags: runhidden nowait postinstall skipifsilent runasoriginaluser

[UninstallRun]
Filename: "{sys}\schtasks.exe"; Parameters: "/End /TN ""Sistema Nucleleste (servidor)"""; Flags: runhidden; RunOnceId: "ParaTarefa"
Filename: "{sys}\schtasks.exe"; Parameters: "/Delete /TN ""Sistema Nucleleste (servidor)"" /F"; Flags: runhidden; RunOnceId: "RemoveTarefa"
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM Nucleleste.exe"; Flags: runhidden; RunOnceId: "MataBandeja"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Sistema Nucleleste"""; Flags: runhidden; RunOnceId: "RemoveFirewall"

[Code]
var
  PgDados: TInputDirWizardPage;
  PgBanco: TInputFileWizardPage;
  PgExames: TInputFileWizardPage;
  PgPorta: TInputQueryWizardPage;
  PgAdmin: TInputQueryWizardPage;

// valor de /NOME=valor na linha de comando (instalação silenciosa); senão, o padrão
function ParamOu(Nome, Padrao: String): String;
var
  I: Integer;
  P, Pref: String;
begin
  Result := Padrao;
  Pref := '/' + Nome + '=';
  for I := 1 to ParamCount do
  begin
    P := ParamStr(I);
    if CompareText(Copy(P, 1, Length(Pref)), Pref) = 0 then
    begin
      Result := Copy(P, Length(Pref) + 1, MaxInt);
      Break;
    end;
  end;
end;

function DadosDir(Param: String): String;
begin
  Result := RemoveBackslash(PgDados.Values[0]);
end;

function Porta(Param: String): String;
begin
  Result := Trim(PgPorta.Values[0]);
end;

function BancoExistente: Boolean;
begin
  Result := FileExists(DadosDir('') + '\sistema.db');
end;

function UsandoBancoFornecido: Boolean;
begin
  Result := Trim(PgBanco.Values[0]) <> '';
end;

procedure RegisterPreviousData(PreviousDataKey: Integer);
begin
  SetPreviousData(PreviousDataKey, 'Dados', DadosDir(''));
  SetPreviousData(PreviousDataKey, 'Porta', Porta(''));
end;

// ---------------------------------------------------------------- visual animado
// O Inno Setup não tem animação própria: um temporizador do Windows (SetTimer) troca os quadros a cada 90 ms.
type
  TProcTemporizador = procedure(Janela: LongWord; Mensagem: LongWord; IdEvento: LongWord; Tempo: LongWord);

function SetTimer(hWnd: LongWord; nIDEvent, uElapse: LongWord; lpTimerFunc: LongWord): LongWord; external 'SetTimer@user32.dll stdcall';
function KillTimer(hWnd: LongWord; nIDEvent: LongWord): Boolean; external 'KillTimer@user32.dll stdcall';

const
  QUADROS_LAT = 16;
  QUADROS_PEQ = 12;
  COR_VERDE = $395F25;       // RGB 37,95,57 (a cor do sistema)

var
  IdRelogio: LongWord;
  QuadroLat, QuadroPeq, Passo, FraseIdx: Integer;
  ImgInstala, ImgAviso: TBitmapImage;
  LblFrase, LblAviso: TNewStaticText;
  Frases: array of String;
  AvisoAtivo: Boolean;

procedure CarregaQuadro(Img: TBitmapImage; Prefixo: String; N: Integer);
begin
  try
    Img.Bitmap.LoadFromFile(ExpandConstant('{tmp}\') + Prefixo + Format('%.2d', [N]) + '.bmp');
  except
    // se um quadro faltar, a animação só pula esse passo
  end;
end;

procedure TrocaFrase;
begin
  FraseIdx := (FraseIdx + 1) mod GetArrayLength(Frases);
  if LblFrase <> nil then LblFrase.Caption := Frases[FraseIdx];
  if LblAviso <> nil then LblAviso.Caption := Frases[FraseIdx];
end;

procedure AoTic(Janela: LongWord; Mensagem: LongWord; IdEvento: LongWord; Tempo: LongWord);
begin
  try
    Passo := Passo + 1;
    QuadroLat := (QuadroLat + 1) mod QUADROS_LAT;
    QuadroPeq := (QuadroPeq + 1) mod QUADROS_PEQ;
    if WizardForm.CurPageID = wpWelcome then
      CarregaQuadro(WizardForm.WizardBitmapImage, 'lat', QuadroLat)
    else if WizardForm.CurPageID = wpFinished then
      CarregaQuadro(WizardForm.WizardBitmapImage2, 'lat', QuadroLat)
    else if (WizardForm.CurPageID = wpInstalling) and (ImgInstala <> nil) then
      CarregaQuadro(ImgInstala, 'peq', QuadroPeq);
    if AvisoAtivo and (ImgAviso <> nil) then
      CarregaQuadro(ImgAviso, 'peq', QuadroPeq);
    if (Passo mod 30) = 0 then TrocaFrase;
  except
    // a animação nunca pode atrapalhar a instalação
  end;
end;

procedure DeinitializeSetup;
begin
  if IdRelogio <> 0 then KillTimer(0, IdRelogio);
end;

procedure CriaAnimacaoEm(Pai: TWinControl; Topo, Largura: Integer; var Img: TBitmapImage; var Rotulo: TNewStaticText);
begin
  Img := TBitmapImage.Create(WizardForm);
  Img.Parent := Pai;
  Img.Left := 0;
  Img.Top := Topo;
  Img.Width := ScaleX(64);
  Img.Height := ScaleY(64);
  Img.Stretch := True;
  Rotulo := TNewStaticText.Create(WizardForm);
  Rotulo.Parent := Pai;
  Rotulo.Left := Img.Left + Img.Width + ScaleX(14);
  Rotulo.Top := Topo + ScaleY(14);
  Rotulo.Width := Largura - Rotulo.Left;
  Rotulo.AutoSize := False;
  Rotulo.WordWrap := True;
  Rotulo.Height := ScaleY(40);
  Rotulo.Font.Size := 11;
  Rotulo.Font.Style := [fsBold];
  Rotulo.Font.Color := COR_VERDE;
  Rotulo.Caption := Frases[0];
end;

procedure PersonalizarVisual;
begin
  // cabeçalho e títulos nas cores do sistema
  WizardForm.MainPanel.Color := COR_VERDE;
  WizardForm.PageNameLabel.Font.Color := clWhite;
  WizardForm.PageDescriptionLabel.Font.Color := $ECF2E8;
  WizardForm.WelcomeLabel1.Font.Color := COR_VERDE;
  WizardForm.FinishedHeadingLabel.Font.Color := COR_VERDE;

  SetArrayLength(Frases, 8);
  Frases[0] := 'Aplicando a dose do gerador...';
  Frases[1] := 'Calibrando a gama câmara...';
  Frases[2] := 'Organizando a agenda de exames...';
  Frases[3] := 'Contando o troco do caixa...';
  Frases[4] := 'Ensinando a NucleAI a ajudar você...';
  Frases[5] := 'Liberando laudos (a tinta está secando)...';
  Frases[6] := 'Conferindo a meia-vida do tecnécio...';
  Frases[7] := 'Preparando o botão redondo da NucleAI...';

  // animação na página de instalação: átomo girando e frases divertidas
  CriaAnimacaoEm(WizardForm.InstallingPage, WizardForm.ProgressGauge.Top + WizardForm.ProgressGauge.Height + ScaleY(24),
    WizardForm.ProgressGauge.Width, ImgInstala, LblFrase);

  ExtractTemporaryFiles('*.bmp');
  IdRelogio := SetTimer(0, 0, 90, CreateCallback(@AoTic));
end;

procedure InitializeWizard;
begin
  PgDados :=CreateInputDirPage(wpSelectDir, 'Pasta dos dados',
    'Onde ficarão o banco de dados e os backups?',
    'O banco de dados (clientes, atendimentos, financeiro) fica separado do programa, para que as atualizações nunca o apaguem.' + #13#10 +
    'Recomendado: manter a pasta sugerida. Clique em Avançar para continuar.', False, '');
  PgDados.Add('');
  // prioridade: parâmetro /DADOS= (instalação automatizada) > pasta da instalação anterior > padrão
  PgDados.Values[0] := ParamOu('DADOS', GetPreviousData('Dados', ExpandConstant('{commonappdata}\Nucleleste')));

  PgBanco := CreateInputFilePage(PgDados.ID, 'Banco de dados existente (opcional)',
    'Você já tem um banco de dados do sistema (arquivo sistema.db)?',
    'Se estiver trocando de computador, escolha aqui o arquivo sistema.db (ou um backup .db) para continuar com os mesmos dados.' + #13#10 +
    'Se for uma instalação nova, deixe em branco. Para trazer dados do sistema antigo (BD.mdb), use depois o atalho "Migrar dados do sistema antigo".');
  PgBanco.Add('Arquivo do banco de dados:', 'Banco de dados (*.db)|*.db|Todos os arquivos (*.*)|*.*', '.db');
  PgBanco.Values[0] := ParamOu('BANCO', '');

  PgExames := CreateInputFilePage(PgBanco.ID, 'Planilha de exames (opcional)',
    'Quer trazer a planilha EXAMES.xlsx para o módulo "Exames realizados"?',
    'Escolha o arquivo EXAMES.xlsx (controle de realização de exames, uma aba por mês) para carregar todos os lançamentos dele, ' +
    'com as cores de cada tipo de exame. A importação leva cerca de 1 minuto.' + #13#10 +
    'Pode deixar em branco e importar depois pelo atalho "Importar planilha de exames" ou em Cores dos exames, dentro do sistema.');
  PgExames.Add('Planilha de exames:', 'Planilha do Excel (*.xlsx;*.xlsm)|*.xlsx;*.xlsm|Todos os arquivos (*.*)|*.*', '.xlsx');
  PgExames.Values[0] := ParamOu('EXAMES', '');

  PgPorta := CreateInputQueryPage(PgExames.ID, 'Porta de acesso',
    'Em qual porta o sistema vai responder?',
    'Os computadores da rede acessam por http://NOME-DO-PC:PORTA. A porta 8080 serve na maioria dos casos.');
  PgPorta.Add('Porta (1024 a 65535):', False);
  PgPorta.Values[0] := ParamOu('PORTA', GetPreviousData('Porta', '8080'));

  PgAdmin := CreateInputQueryPage(PgPorta.ID, 'Administrador do sistema',
    'Defina a senha do usuário ADMIN',
    'O usuário ADMIN acessa todos os módulos e cria os outros usuários. Anote a senha em local seguro.');
  PgAdmin.Add('Senha do ADMIN:', True);
  PgAdmin.Add('Repita a senha:', True);
  PgAdmin.Values[0] := ParamOu('SENHA', '');
  PgAdmin.Values[1] := ParamOu('SENHA', '');

  PersonalizarVisual;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if PageID = PgBanco.ID then
    Result := BancoExistente   // atualização: já há dados, não pergunta
  else if PageID = PgAdmin.ID then
    Result := BancoExistente or UsandoBancoFornecido;  // senha só para instalação nova
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  N: Integer;
begin
  Result := True;
  if CurPageID = PgDados.ID then
  begin
    if Trim(PgDados.Values[0]) = '' then
    begin
      MsgBox('Informe a pasta dos dados.', mbError, MB_OK);
      Result := False;
    end;
  end
  else if CurPageID = PgBanco.ID then
  begin
    if UsandoBancoFornecido and not FileExists(PgBanco.Values[0]) then
    begin
      MsgBox('O arquivo informado não foi encontrado.', mbError, MB_OK);
      Result := False;
    end;
  end
  else if CurPageID = PgExames.ID then
  begin
    if (Trim(PgExames.Values[0]) <> '') and not FileExists(PgExames.Values[0]) then
    begin
      MsgBox('A planilha informada não foi encontrada.', mbError, MB_OK);
      Result := False;
    end;
  end
  else if CurPageID = PgPorta.ID then
  begin
    N := StrToIntDef(Trim(PgPorta.Values[0]), 0);
    if (N < 1024) or (N > 65535) then
    begin
      MsgBox('Informe um número de porta entre 1024 e 65535.', mbError, MB_OK);
      Result := False;
    end;
  end
  else if CurPageID = PgAdmin.ID then
  begin
    if Length(PgAdmin.Values[0]) < 3 then
    begin
      MsgBox('A senha deve ter pelo menos 3 caracteres.', mbError, MB_OK);
      Result := False;
    end
    else if PgAdmin.Values[0] <> PgAdmin.Values[1] then
    begin
      MsgBox('As duas senhas não conferem.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure Executa(Exe, Params: String);
var
  Codigo: Integer;
begin
  Exec(Exe, Params, ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, Codigo);
end;

// chave do servidor (guardada junto dos dados): prova ao sistema que o pedido vem do instalador neste computador
function LerChave: String;
var
  Linhas: TArrayOfString;
begin
  Result := '';
  if LoadStringsFromFile(DadosDir('') + '\chave_secreta.txt', Linhas) and (GetArrayLength(Linhas) > 0) then
    Result := Trim(Linhas[0]);
end;

// pede ao sistema em funcionamento o aviso de 3 minutos; devolve os segundos a esperar (-1 = o sistema não respondeu)
function PedirAviso: Integer;
var
  Http: Variant;
  Resposta: String;
begin
  Result := -1;
  try
    Http := CreateOleObject('WinHttp.WinHttpRequest.5.1');
    Http.SetTimeouts(2000, 2000, 5000, 15000);
    Http.Open('POST', 'http://127.0.0.1:' + Porta('') + '/atualizacao/iniciar', False);
    Http.SetRequestHeader('X-Chave', LerChave);
    Http.Send('');
    if Http.Status = 200 then
    begin
      Resposta := Http.ResponseText;
      Result := StrToIntDef(Trim(Resposta), -1);
    end;
  except
    Result := -1;
  end;
end;

// computador-base (onde estão os dados): todos os funcionários recebem a mensagem do sistema e o instalador espera
// o prazo antes de encerrar o programa. /AVISO=0 pula a espera (uso técnico).
procedure AvisarEEsperar;
var
  Total, Falta: Integer;
  Pg: TOutputProgressWizardPage;
begin
  if ParamOu('AVISO', '') = '0' then Exit;
  if not BancoExistente then Exit;
  Total := PedirAviso;
  if Total <= 0 then Exit;
  if Total > 3600 then Total := 3600;
  Pg := CreateOutputProgressPage('Avisando os usuários',
    'Todos os funcionários receberam a mensagem de que o sistema será atualizado.');
  CriaAnimacaoEm(Pg.Surface, Pg.ProgressBar.Top + Pg.ProgressBar.Height + ScaleY(24), Pg.SurfaceWidth, ImgAviso, LblAviso);
  AvisoAtivo := True;
  Pg.Show;
  try
    Falta := Total;
    while Falta > 0 do
    begin
      Pg.SetText('Aguardando o prazo para ninguém perder dados que ainda não foram salvos.',
        'Tempo restante: ' + IntToStr(Falta div 60) + ':' + Format('%.2d', [Falta mod 60]));
      Pg.SetProgress(Total - Falta, Total);
      Sleep(1000);  // o Sleep do Inno mantém a janela respondendo
      Falta := Falta - 1;
    end;
  finally
    AvisoAtivo := False;
    Pg.Hide;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Codigo: Integer;
  Marca: TArrayOfString;
begin
  AvisarEEsperar;
  if BancoExistente then
  begin
    // o sistema novo, ao iniciar, mostra a tela de espera por cerca de 1 minuto para quem acessar o link
    SetArrayLength(Marca, 1);
    Marca[0] := GetDateTimeString('yyyy-mm-dd hh:nn:ss', '-', ':');
    SaveStringsToFile(DadosDir('') + '\atualizando.txt', Marca, False);
  end;
  // fecha a bandeja/servidor da versão anterior para poder trocar os arquivos
  // (primeiro para a tarefa, senão o Windows reiniciaria o servidor no meio da atualização)
  Exec(ExpandConstant('{sys}\schtasks.exe'), '/End /TN "Sistema Nucleleste (servidor)"', '', SW_HIDE, ewWaitUntilTerminated, Codigo);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM Nucleleste.exe', '', SW_HIDE, ewWaitUntilTerminated, Codigo);
  Sleep(1200);
  Result := '';
end;

// Google Chrome ou Microsoft Edge no computador (o robô da Medcloud usa um deles; nenhum navegador vai dentro do Setup)
function ChromeInstalado: Boolean;
begin
  Result := FileExists(ExpandConstant('{commonpf}\Google\Chrome\Application\chrome.exe'))
         or FileExists(ExpandConstant('{commonpf32}\Google\Chrome\Application\chrome.exe'))
         or FileExists(ExpandConstant('{localappdata}\Google\Chrome\Application\chrome.exe'));
end;

function EdgeInstalado: Boolean;
begin
  Result := FileExists(ExpandConstant('{commonpf}\Microsoft\Edge\Application\msedge.exe'))
         or FileExists(ExpandConstant('{commonpf32}\Microsoft\Edge\Application\msedge.exe'));
end;

// Sem Chrome nem Edge o sistema funciona normal; só a integração com a Medcloud fica sem navegador. Oferece abrir a página de download.
procedure ConferirNavegadorDoRobo;
var
  Codigo: Integer;
begin
  if not Is64BitInstallMode then Exit;   // o robô da Medcloud só vai na versão de 64 bits
  if ChromeInstalado or EdgeInstalado then Exit;
  if WizardSilent then Exit;
  if MsgBox('Para criar o acesso do paciente na Medcloud, o sistema usa o Google Chrome (ou o Microsoft Edge), e nenhum dos dois foi encontrado neste computador.' + #13#10 + #13#10 +
            'O resto do sistema funciona normalmente. Deseja abrir agora a página de download do Google Chrome?',
            mbConfirmation, MB_YESNO) = IDYES then
    ShellExec('open', 'https://www.google.com/chrome/', '', '', SW_SHOWNORMAL, ewNoWait, Codigo);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Py, Dados, Pw, Carimbo: String;
  Cab: TArrayOfString;
begin
  if CurStep = ssInstall then
  begin
    // atualização: guarda uma cópia do banco antes de trocar o programa
    if BancoExistente then
    begin
      ForceDirectories(DadosDir('') + '\backups');
      Carimbo := GetDateTimeString('yyyy-mm-dd_hh-nn-ss', '-', '-');
      CopyFile(DadosDir('') + '\sistema.db', DadosDir('') + '\backups\ANTES_ATUALIZACAO_' + Carimbo + '.db', False);
      // os anexos (PDF, Word...) ficam em outro banco: a cópia leva os dois, com o mesmo carimbo
      if FileExists(DadosDir('') + '\anexos.db') then
        CopyFile(DadosDir('') + '\anexos.db', DadosDir('') + '\backups\ANTES_ATUALIZACAO_' + Carimbo + '_anexos.db', False);
    end;
  end;

  if CurStep = ssPostInstall then
  begin
    Py := ExpandConstant('{app}\py\python.exe');
    Dados := DadosDir('');
    // onde estão os dados (a bandeja lê este arquivo)
    SetArrayLength(Cab, 1);
    Cab[0] := Dados;
    SaveStringsToUTF8File(ExpandConstant('{app}\local_dados.txt'), Cab, False);

    Executa(Py, '-m app.cli --dados "' + Dados + '" config ' + Porta(''));
    if UsandoBancoFornecido then
      Executa(Py, '-m app.cli --dados "' + Dados + '" importar-db "' + PgBanco.Values[0] + '"')
    else if not BancoExistente then
    begin
      // instalação nova: grava a senha do ADMIN em arquivo temporário que o próprio comando apaga
      Pw := ParamOu('SENHA', PgAdmin.Values[0]);
      if Pw = '' then Pw := 'admin';
      SetArrayLength(Cab, 1);
      Cab[0] := Pw;
      SaveStringsToUTF8File(ExpandConstant('{tmp}\nucl_pw.txt'), Cab, False);
      Executa(Py, '-m app.cli --dados "' + Dados + '" admin-senha "' + ExpandConstant('{tmp}\nucl_pw.txt') + '"');
      DeleteFile(ExpandConstant('{tmp}\nucl_pw.txt'));
    end;

    // planilha de exames (opcional): carrega os lançamentos no módulo "Exames realizados"
    if (Trim(PgExames.Values[0]) <> '') and FileExists(PgExames.Values[0]) then
    begin
      WizardForm.StatusLabel.Caption := 'Importando a planilha de exames (cerca de 1 minuto)...';
      Executa(Py, '-m app.cli --dados "' + Dados + '" importar-exames "' + PgExames.Values[0] + '"');
    end;

    // servidor como tarefa do Windows: liga no boot (conta SYSTEM) e reinicia se cair
    if WizardIsTaskSelected('servico') then
      Executa(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
        '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\instalar_servico.ps1') + '" -Exe "' +
        ExpandConstant('{app}\py\Nucleleste.exe') + '" -Script "' + ExpandConstant('{app}\tray.pyw') + '"')
    else
      // sem a opção marcada, garante que não sobre uma tarefa de versão anterior
      Executa(ExpandConstant('{sys}\schtasks.exe'), '/Delete /TN "Sistema Nucleleste (servidor)" /F');

    // regra do Firewall restrita a este programa e a esta porta
    if WizardIsTaskSelected('firewall') then
    begin
      Executa(ExpandConstant('{sys}\netsh.exe'), 'advfirewall firewall delete rule name="Sistema Nucleleste"');
      Executa(ExpandConstant('{sys}\netsh.exe'),
        'advfirewall firewall add rule name="Sistema Nucleleste" dir=in action=allow protocol=TCP localport=' + Porta('') +
        ' program="' + ExpandConstant('{app}\py\Nucleleste.exe') + '" profile=any enable=yes');
    end;

    ConferirNavegadorDoRobo;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Linhas: TArrayOfString;
  Dados: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    // só pergunta no desinstalador interativo; em modo silencioso os dados são mantidos
    if (not UninstallSilent) and LoadStringsFromFile(ExpandConstant('{app}\local_dados.txt'), Linhas) and (GetArrayLength(Linhas) > 0) then
    begin
      Dados := Trim(Linhas[0]);
      if (Dados <> '') and DirExists(Dados) then
        if MsgBox('Deseja apagar TAMBÉM os dados (banco de dados, backups e logs)?' + #13#10 + #13#10 + Dados + #13#10 + #13#10 +
                  'Escolha "Não" para manter os dados (recomendado).', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
          DelTree(Dados, True, True, True);
    end;
  end;
end;
