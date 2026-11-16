# O negócio e o produto

Síntese de **o que a empresa faz e como o sistema a apoia**, construída a partir do código, dos textos de ajuda escritos pela própria clínica (`ajuda_conteudo_*.py`), dos modelos de documentos (`blindagem_docs.py`, fichas) e do histórico de versões (`novidades.py`). Marcação: **[FATO]** lido no código · **[CONTEXTO]** conhecimento geral do setor, não verificável no código · **[?]** intenção desconhecida.

## 1. O que a empresa faz
- **Centro de Medicina Nuclear do Leste Mineiro (Nucleleste), em Governador Valadares (MG)** [FATO: `LEIA-ME`, `config.clinica_cidade`, feriados locais em `prazo_laudo.py`].
- É uma clínica de **diagnóstico por imagem em medicina nuclear**. O paciente recebe um **radiofármaco** (substância com um isótopo radioativo, como o tecnécio-99m) e imagens são adquiridas por equipamento próprio; um médico nuclear emite o **laudo** [CONTEXTO; confirmado pelos campos `radio`, `eluicao`, `farmaco`, `lote`, `atividade prescrita/administrada`, `hora da injeção` em exames realizados].
- Exames cadastrados por padrão [FATO: `db.EXAMES_PADRAO`, tela de exames]: **MIBI** (miocárdio, com variações Estresse, Repouso e Protocolo), **ÓSSEA**, **RENAL / DMSA / DTPA**, **PULMONAR**, **LINFONODO (sentinela)**, **SPECT cerebral**, **TGI (tireoide)**, **PARATGI (paratireoide)**, **GÁLIO**. Há também fichas de "**Plano terapêutico MDN**" (cisternocintilografia, dacriocintilografia, esvaziamento gástrico, glândulas salivares, gálio, MIBG, refluxo gastroesofágico, samário), baseadas no POP MDN 24 [FATO: `fichas_plano.py`].
- **Doses de iodo, gálio e PCI** são agendadas à parte, com **preparo** (dieta e suspensão de medicação, orientação de 15 ou 30 dias para o iodo) [FATO: `views_medicamentos.py`].
- O gerador de **Mo-99/Tc-99m** é a fonte do tecnécio; suas **blindagens** são controladas (validade, devolução ao fornecedor) [FATO: `blindagens.py`].

## 2. Quem usa o sistema
- Uso interno, por login e senha, **em um PC servidor e navegadores nos demais PCs** da clínica [FATO: `servidor.py`, `tray.pyw`].
- Papéis observados nos textos e permissões [FATO: `ajuda_conteudo_c.py`, `modulos.py`]: **recepção** (atendimento, agenda, caixa), **técnico** (exames realizados, laudos, blindagens), **financeiro** (contas, faturamento, caixa diário), **gerência** (permissões, caixa, backups, prazos, qualidade), **administração** (tudo), **departamento pessoal / banco de horas**, **estagiário** (lança fichas; só consulta a agenda) e **funcionário** (vê só o próprio banco de horas).
- Pacientes interagem só pela **pesquisa de satisfação** (QR Code, rede interna) [FATO].
- Origem: o sistema **substituiu uma planilha** ("VERSÃO 2.1 RECEPÇÃO") e um banco Access (`BD.mdb`), cujas tabelas eram LOGIN, CADCLIENTE, CADCONVENIO, CADMEDICO, LANCAMENTO, PROTOCOLOGUIAS, CAIXA, MEDICAMENTOS e CONTASAPAGAR [FATO: `ferramentas/importar_dados.py`].

## 3. A jornada de um exame (do contato à cobrança)
1. **Agendamento** (Agenda): horários por exame e por dia; reserva de vagas para um convênio; lista de espera; MIBI com Estresse/Repouso/Protocolo. A agenda não depende do cadastro de clientes [FATO: `agenda.py`].
2. **Confirmação e faltas**: texto de WhatsApp pronto (lembrete, falta, reagendamento); faltas podem ser **resgatadas** (reagendadas) e o resgate é creditado ao usuário [FATO].
3. **Chegada (recepção)**: cadastra o cliente (nome, CPF, nascimento e sexo obrigatórios), **lança o atendimento** com exame, convênio, médico solicitante, medicamentos em uso e **questionário da ficha PNT** (SIM/NÃO) [FATO: `views_atendimentos.py`, `fichas.py`].
4. **Fichas impressas** por exame (ficha geral, PNT, termo, orientações, SAE, escore NEWS, etiqueta) com a **previsão de entrega do laudo** [FATO].
5. **Cobrança no balcão ou por guia**: convênios marcados "vai para o caixa" (ex.: Particular, SMS, Mais Med) geram lançamento no **caixa**; os demais geram **guia** no protocolo [FATO: `convenios.gera_caixa`].
6. **Realização do exame** (Exames realizados): o técnico registra rádio/fármaco, lote, atividades e horas; o exame entra no **Mapa de laudos** em "Processando imagem" [FATO].
7. **Laudo**: Processando imagem → Laudando → Liberado → Entregue; ao liberar, todos recebem aviso; o laudo em Word pode ser aberto pelo nome do paciente numa pasta de rede [FATO: `laudos.py`, `laudos_word.py`].
8. **Faturamento**: notas por convênio/particular, tributos, recebimento, glosa e prazo médio [FATO].

## 4. Dinheiro
Receita vem de **convênios** (faturamento, com valor por exame e convênio) e do **particular** (caixa do balcão em dinheiro ou PIX com nota fiscal). Despesas por **contas a pagar** com fornecedores e parcelamento. O **caixa diário** reproduz o controle da empresa em quatro contas (Banco do Brasil, Unicred, Caixa Econômica, dinheiro). O **repasse médico** é calculado a partir de quem "veio" na agenda × valor do convênio × percentual [FATO]. Os quatro controles não se integram automaticamente (pendência 22).

## 5. Conformidade e qualidade
- **ONA (acreditação)**: relatório de indicadores e módulo de Qualidade completo (indicadores com metas, robô do PDCA, Ishikawa, 5 Porquês, GUT, 5W2H, riscos, SWOT, fluxogramas, organograma, ocorrências, satisfação e avaliação de fornecedores) [FATO].
- **Radioproteção e transporte (CNEN)**: devolução das **blindagens de gerador de tecnécio** ao fornecedor segue documentos preenchidos pelo sistema: declaração para transporte, declaração do expedidor (formulário em modelo CNEN, material radioativo classe 7, ONU 2910, "volume exceptivo"), etiquetas e planilha. Destinatário e transportador estão **fixos no código** [FATO: `blindagem_docs.py`]. O código não contém dosimetria, controle de rejeitos nem registros de radioproteção além disso (pendência 38).
- **Vencimentos**: documentos de fiscalização (licenças, alvarás) têm avisos em 60, 30, 15, 7, 1 e 0 dias [FATO: `avisos.py`].
- **Segurança dos dados**: auditoria de tudo (quem fez o quê), "desfazer", backup em zip com restauração protegida por código, senha com *hash*, CSRF [FATO].
- **Pessoal**: banco de horas a partir do relógio de ponto, escala, documentos do DP e área do funcionário [FATO].

## 6. Glossário
| Termo | Significado no sistema |
|---|---|
| Atendimento | Registro da recepção; gera guia ou caixa e imprime fichas |
| Exame realizado | Registro técnico (radiofármaco, lote, atividades); alimenta o Mapa de laudos |
| Guia | Protocolo de convênio, gerado automaticamente por atendimento |
| Caixa / Movimento de caixa | Recebimento do balcão por usuário e por dia |
| Blindagem | Gerador de tecnécio com validade, devolvido ao fornecedor |
| PNT | Ficha com questionário por exame (MIBI, óssea, renal, pulmonar, SPECT, TGI, paratireoide, linfonodo) |
| SAE | Ficha geral de enfermagem, impressa em todos os exames [HIPÓTESE: sigla] |
| NEWS | Escore clínico impresso com o MIBI e o pulmonar [HIPÓTESE: sigla] |
| MDN | Plano terapêutico (POP MDN 24) [?] |
| UNACON | Convênio/serviço oncológico para o qual se reservam horários; hoje a reserva vale para qualquer convênio [?] |
| Resgate | Falta reagendada ou desistência tratada, creditada a quem fez |
| Mapa de laudos | Quadro com situação de cada laudo |
| Número I | Identificador do funcionário no relógio de ponto |
| Glosa | Diferença entre o líquido faturado e o recebido do convênio |
| ONA | Organização Nacional de Acreditação |
| CNEN | Comissão Nacional de Energia Nuclear |
| 3F, DEG, RAD | Códigos em nomes de arquivos de laudos em Word [?] |

## 7. História do produto (versões em `novidades.py`)
- **1.4.4 (16/10/2026)**: fornecedores e compra parcelada; imprimir a agenda do dia; movimento de caixa com exclusão pela gerência.
- **1.4.5**: restauração de backup pelo sistema; menu recolhido.
- **1.4.6**: reserva de horários, desfazer na agenda, favoritos, formatação da agenda, excluir agenda só pela gerência.
- **1.4.7**: anexos em banco próprio (`anexos.db`); backup em zip; fichas "Plano terapêutico MDN"; abrir laudo em Word; barra lateral nova; acesso automático ao Banco de Horas; perfis Usuário/Administrador e Estagiário; tema e brilho; datas editáveis de parcelas.
- **1.4.8**: logo e átomo animados no login.
- **1.4.9 (17/10/2026)**: Caixa diário da empresa; ordem dos exames na agenda; cor do calendário.
- **1.5.0 (18/10/2026, em desenvolvimento)**: imagens no chat (24 h), Qualidade completa e robô do PDCA, NucleAI com 37 comandos, desfazer geral, prazo de laudo configurável, mapa de laudos por usuário, retificação, pesquisa de satisfação por QR Code, valores por exame em todos os convênios, e teste de sobrecarga (milhões de registros).
- O banco real tem **centenas de milhares a milhões** de linhas de histórico importadas do sistema antigo (os comentários de desempenho citam testes com 3,6 milhões de atendimentos) [FATO: `views_dashboard.py`; o volume real da clínica não foi medido].

## 8. O que o sistema não faz (não encontrado no código)
Envio automático de WhatsApp ou e-mail; integração com equipamentos de imagem, PACS ou sistema de laudos; faturamento eletrônico (TISS) ou NF-e; controle de estoque de radiofármacos; dosimetria de pessoal; backup agendado automático; login por provedor externo (adiado, depende de HTTPS).
