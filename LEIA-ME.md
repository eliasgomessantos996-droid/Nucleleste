# Sistema de Recepção — Nucleleste

Sistema web que substitui a planilha **VERSÃO 2.1 RECEPÇÃO1.xlsm** + banco **BD.mdb**.
Roda em um computador da clínica e é acessado pelo navegador (Chrome/Edge) em todos os computadores da rede.

## Instalação (recomendado): Setup-Nucleleste-X.Y.Z.exe

Um único instalador para **Windows 10 e 11, 32 ou 64 bits** (`instalador\saida\Setup-Nucleleste-1.3.0.exe`). Não precisa instalar Python nem manter janela preta aberta.

1. Execute o Setup como administrador e siga o assistente (pasta dos dados, banco existente opcional, porta, senha do ADMIN).
2. **O sistema liga junto com o computador**, mesmo antes de alguém entrar no Windows, e volta sozinho se cair ou se o PC reiniciar (tarefa do Windows "Sistema Nucleleste (servidor)": inicia no boot, reinicia a cada falha e confere a cada 5 minutos). Quando um usuário entra, aparece o ícone do átomo na **bandeja** (perto do relógio) como painel de controle; fechá-lo não derruba o sistema. Se o instalador não for executado como administrador, o sistema funciona só enquanto o ícone da bandeja estiver aberto.
3. **Clique duplo** no ícone abre o sistema no navegador. **Botão direito** mostra: endereço neste computador, endereços na rede (clique para copiar), ver o local do programa, a pasta dos dados e dos backups, o log, fazer backup agora, sobre e sair.
4. Nos outros computadores da rede, use o endereço "Na rede" mostrado no menu (ex.: `http://192.168.0.10:8080`).

O banco de dados fica em `C:\ProgramData\Nucleleste` (separado do programa; atualizações nunca o apagam). Para atualizar, rode o novo Setup por cima: ele fecha o sistema, guarda um backup do banco, troca o programa e reinicia. Desinstalar mantém os dados (pergunta se quer apagá-los).

Para trazer os dados do Access: atalho **Nucleleste - Migrar dados do sistema antigo** no menu Iniciar. Para a planilha de exames: **Nucleleste - Importar planilha de exames** (ou escolha o arquivo durante a instalação). Para o programa Banco de Horas antigo: **Nucleleste - Importar dados do Banco de Horas antigo**.

Instalação automatizada: `Setup-Nucleleste-1.3.0.exe /VERYSILENT /DADOS="D:\Nucleleste" /PORTA=8080 /SENHA=SuaSenha`.

Para gerar um novo instalador (após mudar o código): `powershell -ExecutionPolicy Bypass -File instalador\build.ps1` (precisa de Inno Setup 6 e internet na primeira vez).

## Como usar (modo simples, com Python, sem instalador)

1. Instale o **Python 3** (https://www.python.org/downloads/) marcando **“Add python.exe to PATH”**.
2. Dê dois cliques em **`INICIAR.bat`**. Na primeira vez ele instala os componentes (precisa de internet).
3. O navegador abre em `http://localhost:8080`. Nos outros computadores, use `http://NOME-DO-PC:8080`
   (o nome aparece na janela preta). Libere a porta 8080 no Firewall do Windows se pedir.
4. Entre com o mesmo usuário e senha da planilha. **Troque as senhas** em *Configuração → Alterar senha*.

A janela preta precisa ficar aberta enquanto o sistema estiver em uso.

## Onde estão os dados

- `dados/sistema.db` — banco de dados principal (SQLite): cadastros, atendimentos, financeiro, agenda, usuários, banco de horas.
- `dados/anexos.db` — banco dos **anexos** (PDF, Word, Excel e imagens dos módulos Documentos e Departamento Pessoal). O `sistema.db` guarda só a
  referência (`anexo_id`) e os dados do arquivo; o conteúdo fica aqui, para o banco principal e os backups não crescerem com os PDFs. Na primeira
  inicialização da versão 1.4.7 os anexos antigos são levados para o `anexos.db` automaticamente (com cópia de segurança, conferência do SHA-256 e VACUUM).
- **Faça backups** (menu *Backup*); eles ficam em `dados/backups`. Cada backup é um `.zip` com `sistema.db`, `anexos.db` e um `LEIA-ME.txt` com o passo
  a passo. **Os dois bancos devem sempre ser restaurados juntos.**
- **Restaurar** (só administração e gerência): *Backup → Restaurar o último backup* ou *Restaurar* na linha do arquivo; *Buscar em outra pasta* lista os
  backups válidos de um pendrive, disco ou pasta de rede. Toda restauração pede um código de verificação digitado (6 números, 5 minutos, uso único) e
  antes guarda o estado atual em `ANTES-DE-RESTAURAR_*.zip`. Backups antigos (`.db`) continuam aceitos (restauram só o `sistema.db`).
- **Laudos em Word:** em *Configuração → Dados da clínica* a gestão informa a pasta dos laudos; em *Lançar atendimento*, cada exame anterior tem o botão
  *Abrir laudo (Word)*, que procura o arquivo pelo nome do paciente.
- Para mudar a porta ou a pasta do banco, edite `config.json`.
- Evite deixar o banco em pasta sincronizada pelo OneDrive enquanto o sistema está aberto
  (a sincronização pode gerar conflitos). O ideal é rodar no servidor/PC fixo da recepção, em pasta local.

## Migração dos dados antigos

Os dados do `BD.mdb` e o histórico de logins da planilha **já foram importados**.
Se a recepção continuar usando a planilha até a troca definitiva, rode **`MIGRAR_DADOS.bat`** no dia
da virada para reimportar tudo (substitui os dados do sistema novo; o banco anterior vai para `dados/backups`).
A senha pedida é a do banco Access (a mesma que está no código da planilha).

Correções feitas na importação: datas convertidas para formato padrão, convênios repetidos/sujos
(ex.: código "18" repetido várias vezes) ligados ao cadastro pelo nome, senhas guardadas com criptografia (hash).
Dez datas de nascimento digitadas erradas no sistema antigo (ex.: `81/11/1970`) foram mantidas como texto e
aparecem em vermelho no cadastro do cliente para correção.

## O que cada tela faz (equivalência com a planilha)

| Planilha (formulário/aba) | Sistema novo |
|---|---|
| LOGIN / MENU | Tela de login e menu lateral |
| CADCLIENTE, PESQUISARCLIENTE | Cadastros → Clientes (CPF validado, CEP automático, idade calculada, histórico) |
| CADCONVENIO | Cadastros → Convênios (inclui valores e se vai para o caixa) |
| CADMEDICO, PESQUISARMEDICOS | Cadastros → Médicos (médico novo digitado no atendimento entra sozinho) |
| LANCAMENTO2 (Lançar atendimento), FICHAGERAL (Lançar outros), FICHALINFONODO | Lançamentos → Lançar atendimento (um só formulário: exame da lista ou digitado; questionário do linfonodo aparece sozinho) |
| Fichas FICHA GERAL, FICHA MIBI, PNTs, SAE, TERMO/DR. HAROLDO, ESCORE NEWS, FICHACLIENTE | Impressas automaticamente após o lançamento, com o mesmo layout; podem ser reimpressas a qualquer momento pelo histórico |
| PROTOCOLOGUIA | Lançamentos → Protocolo de guias (filtro por período/convênio, impressão) |
| CAIXA / CAIXADIARIO | Lançamentos → Caixa (valor, forma de pagamento, nota fiscal, status) |
| MEDICAMENTOS, LISTAMEDICAMENTOS, FICHAAGENDAMENTO, IODOHIPER, IODOPOSCIR | Agendar medicamento / Agenda de medicamentos |
| CONTASAPAGAR, CADCONTAS, aba CONTAS A PAGAR | Financeiro → Contas a pagar (quitar com banco, imprimir relação) |
| (novo, 1.4.4) | **Fornecedores** (Contas a pagar → Fornecedores): cadastro manual ou pelo CNPJ (consulta na internet, BrasilAPI/ReceitaWS), vínculo com a conta e relatório **Contas por fornecedor** (PDF e Excel). **Compra parcelada**: ao lançar a conta, marque "Compra parcelada" e cada vencimento vira uma conta identificada como 1/3, 2/3, 3/3 |
| (novo, 1.4.4) | **Agenda do dia**: "Imprimir o dia" pergunta se é para imprimir todos os exames ou só um; o relatório sai sempre em **uma página**, só com horário, paciente e convênio. **Movimento de caixa**: a gerência exclui lançamentos (a exclusão fica na auditoria); na 1.4.4 o movimento de caixa antigo foi zerado uma única vez (com cópia do banco antes) |
| RELATORIO* | Financeiro → Relatórios |
| (novo) | **Dashboard**: indicadores, gráficos animados, alertas de contas/doses/caixa e filtro de período |
| ATESTADO, DECLARAÇÕES, RECIBO | Outros → Atestados e declarações |
| Pastas (laudos, fotos, PDF) | Outros → Pastas |
| Backup, Novo usuário, Alterar senha, aba log | Configuração |

**PDF das fichas:** em vez de salvar PDFs numa pasta, o sistema guarda o atendimento e permite reimprimir
as fichas quando quiser. Para gerar PDF, clique em *Imprimir* e escolha **“Salvar como PDF”**.

**Regras mantidas da planilha:** convênios PARTICULAR, SMS e MAIS MED vão para o caixa; os demais geram
protocolo de guia (configurável em Convênios). MIBI exige “medicamentos em uso”. Se o cliente já tem exames,
é obrigatório indicar o último exame. A Escore NEWS sai em 2 vias. Preparo de 15 dias imprime a orientação
IODOHIPER; 30 dias, IODOPOSCIR.

**Fichas por exame:** em *Cadastros → Exames e fichas* (administrador) dá para escolher quais fichas cada
exame imprime e quantas cópias. Na tela de impressão também é possível marcar/desmarcar fichas na hora.

## Faturamento

Módulo **Financeiro → Faturamento**: cadastre a fatura (convênio ou PARTICULAR, data de referência, nota fiscal, valor bruto, tributos em valor único; o líquido é calculado) e use **Receber** para registrar a quitação (data, valor, banco/conta; diferenças viram glosa). **Faturamento: relatórios** é o dashboard financeiro: bruto, tributos, líquido, recebido x a receber por convênio, evolução mensal, envelhecimento, prazo médio de recebimento e glosas.

## Usuários e permissões

O administrador cria usuários em **Configuração → Usuários e perfis** e marca, com caixas de seleção, quais módulos cada um vê (há atalhos de perfil: Recepção, Financeiro, Todos). Módulos desmarcados somem do menu e ficam bloqueados mesmo digitando o endereço. Cada usuário troca a própria senha em **Alterar senha**. Quem já existia antes mantém o acesso que tinha, sem os módulos novos.

Todo lançamento guarda o usuário que o fez, e o módulo **Registros de atividades** (também selecionável por perfil) lista quem fez o quê e quando, com filtros por usuário, módulo, período e texto. Senhas nunca são gravadas.

## Banco de Horas

Módulo **Banco de Horas** (menu lateral): o programa autônomo "Banco de Horas" agora vive dentro do Nucleleste e usa o mesmo banco de dados, os mesmos usuários e os mesmos backups.

- **Painel de saldos**: saldo anterior, movimento e saldo acumulado de cada funcionário no mês, com as pendências de conferência.
- **Funcionários do ponto**: cadastro pelo *Número I* do relógio de ponto, jornadas por vigência (44 h, 20 h ou personalizada), saldo inicial e estagiários (só escala).
- **Importar ponto**: planilha `.xls` do relógio (a original fica guardada; arquivo repetido é reconhecido; dias divergentes preservam o original). Dias sem batidas viram folga.
- **Extrato** do funcionário com **correção de dia** (batidas, falta, abono, folga, feriado) e **ajustes de saldo**, tudo com justificativa e histórico.
- **Relatório mensal**: prévia e **PDF para assinatura** (versionado; com marca d'água RASCUNHO enquanto houver pendências).
- **Escala mensal** (inclui estagiários) com PDF, **Departamento Pessoal** (documentos e folhas de ponto assinadas, arquivar com justificativa), **Mensagens** com os funcionários (ao vivo) e **Minha área** (o funcionário vê só o próprio saldo e a situação dos documentos).
- Permissões (em *Usuários e perfis*): **Banco de Horas: consulta**, **gestão**, **Departamento Pessoal**, **Mensagens** e **Minha área (funcionário)**. O acesso do funcionário é criado na ficha dele (com senha provisória que ele troca no primeiro login).
- As regras de cálculo são as do programa original (mesmos testes automatizados).

## Exames realizados (planilha EXAMES.xlsx)

Módulo **Lançamentos → Exames realizados / Lançar exame realizado**: o controle de realização (rádio, eluição, fármaco, lote, atividade prescrita/administrada, horários, responsável) como na planilha, com um cadastro por exame.

- O paciente é escolhido entre os **clientes cadastrados** (preenche nome, nascimento e convênio) e o médico entre os **médicos cadastrados**; o resto é digitado. Rádio, fármaco, lote, eluição, atividade e responsável são sugeridos a partir do último exame do mesmo tipo.
- **Cores como na planilha**: cada tipo de exame tem a sua cor na lista, na impressão e na exportação (óssea = ciano, MIBI = vermelho, DTPA = verde, DMSA = azul, tireoide = rosa, linfonodo = cinza, pulmonar = marrom, iodo/PCI = amarelo, paratireoide = laranja, gálio = magenta, SPECT = roxo...). As cores e as palavras que identificam cada tipo se editam em **Cores dos exames**. Filtro por tipo clicando na etiqueta colorida.
- **Trazer atendimentos do dia** cria as linhas a partir dos atendimentos lançados na recepção.
- Os lançamentos da planilha (≈36 mil, de 2018 a 2026) são carregados pela importação (instalador, atalho do menu Iniciar ou *Cores dos exames → Importar planilha*). Datas digitadas com ano errado são corrigidas na importação e marcadas na observação.

## Fichas personalizadas

Em **Exames e fichas → Fichas personalizadas** a clínica cria documentos próprios (termos, orientações) com campos como `{nome}`, `{cpf}`, `{exame}`, `{medico}`, `{data}`. Eles aparecem na lista "Fichas a imprimir" de qualquer atendimento e podem ser marcados em cada exame para sair sempre juntos.

## Segurança da sessão

O login não expira por inatividade: quem deixa o sistema aberto continua conectado e **online**. Fechar o navegador (ou escolher **Sair (logoff)**) encerra o acesso, e abrir de novo pede o login outra vez.

## Mensagens (chat)

Todos os usuários conversam entre si em **Mensagens**. As mensagens chegam na hora (conexão em tempo real) e ficam gravadas até serem lidas. Recursos da conversa:

- **Pesquisar na conversa** (lupa no alto, ou Ctrl+F): acha mensagens sem diferenciar acentos nem maiúsculas e leva até elas.
- **Responder a uma mensagem**: o botão ↩ da mensagem cita o texto original, e tocar na citação leva até ele.
- **Digitando…**: aparece quando a outra pessoa está escrevendo.
- Dois tracinhos ao lado da hora mostram que a mensagem foi lida.
- Contatos do sistema (só leitura): **AVISOS DO SISTEMA** (avisos de atualização; a gerência recebe também vencimentos de documentos e de caixa), **LAUDOS DO SISTEMA** (laudo liberado, com o botão "Marcar como entregue e ver no mapa"; a mensagem some em 3 dias) e a **NucleAI**.

## NucleAI (assistente de ajuda)

O botão redondo no canto inferior direito de qualquer tela abre uma conversa com a **NucleAI**, que mostra o passo a passo do sistema. O usuário pode responder com o **número** das listas (tema, módulo e área) ou **escrever a dúvida com as próprias palavras**: a NucleAI entende, mesmo com erros de digitação, e responde direto, mostra algumas possibilidades para escolher ou, se não entender, pede para reformular ou seguir a lista. Cada pessoa só vê os temas e módulos que o seu perfil acessa.

Depois da instrução, a NucleAI pergunta se ajudou (sim; sim, mas quero perguntar de novo; não) e pede uma nota de 1 a 5. Se não ajudou, oferece outra área, outro módulo, outro tema, **chamar a gerência** ou encerrar. A conversa é temporária e é apagada ao encerrar; o resumo (quem perguntou, assunto, dúvida, resultado e nota) fica para os relatórios.

**Chamar a gerência**: as pessoas escolhidas em *NucleAI → Configurações* (ou toda a gerência) recebem uma mensagem da NucleAI com o botão **Falar com o usuário**. Ele abre a conversa com uma pergunta pronta ("sua dúvida é sobre isso mesmo?") e botões Sim/Não. Quando a pessoa confirma, a NucleAI envia à gerência um resumo detalhado da área, com o passo a passo, o que o módulo faz, quem acessa, as outras áreas do módulo, uma lista de verificação e a citação deste LEIA-ME. Se ninguém da lista estiver online, a NucleAI avisa o usuário que a gerência responderá assim que possível.

**Módulo NucleAI (só administração, logo abaixo de Início)**: *Painel* (consultas, taxa de resolução, notas, chamados, temas e áreas mais consultados, áreas com mais "não ajudou", dúvidas escritas que não foram entendidas, por dia, por usuário; PDF e Excel), *Chamados* (andamento de cada pedido à gerência), *Conteúdo* (corrigir os textos da ajuda e criar áreas, módulos e temas novos, com permissão por módulo; vale na hora) e *Configurações* (ligar ou desligar, quem recebe os chamados, tempo para apagar conversas abandonadas e da despedida).

## Atualizações do sistema

Ao abrir o instalador de uma atualização no computador onde estão os dados, todos os usuários recebem, pelo AVISOS DO SISTEMA, a mensagem de que o sistema será atualizado em **3 minutos** (uma faixa com a contagem aparece na tela) e o instalador espera esse prazo antes de encerrar o programa. Depois da atualização, quem acessar vê por cerca de 1 minuto uma tela de espera animada e, ao voltar, uma mensagem de boas-vindas à nova versão. A gerência também pode avisar os usuários antes, em *Backup → Avisar usuários*.

## Pastas

O botão **Abrir** abre a pasta no Explorador de Arquivos do computador de quem clicou. Em cada computador, uma única vez: clique em **Configurar este computador** (arquivo `.reg` de uso pessoal que só permite abrir pastas), abra-o e, ao clicar em Abrir, marque "Sempre permitir".

### Perfis antigos

- **Administrador** (o usuário SISTEMA, e quem ele promover): usuários, backup, log de acessos,
  exames/fichas, exclusão de atendimentos, dados da clínica.
- **Recepção**: todo o restante.

## Alterar o layout de uma ficha

As fichas foram geradas a partir da própria planilha. Para mudar uma ficha: edite a aba no Excel, salve e rode
(com Python e `openpyxl` instalados):

```
python ferramentas\converter_fichas.py "..\VERSÃO 2.1 RECEPÇÃO1.xlsm"
```

O mapeamento das células que recebem dados do paciente fica no início de `ferramentas/converter_fichas.py`.

## Estrutura

```
INICIAR.bat              inicia o sistema
MIGRAR_DADOS.bat         reimporta os dados do BD.mdb
servidor.py              servidor (Waitress)
config.json              porta e pasta dos dados
app/                     código (Flask) e telas
app/templates/fichas/    fichas geradas da planilha
ferramentas/             conversor de fichas, exportação do Access e importação
dados/                   bancos (sistema.db e anexos.db), chave da sessão e backups (.zip)
```
