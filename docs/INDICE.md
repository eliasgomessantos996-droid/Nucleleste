# Documentação técnica do Sistema Nucleleste (engenharia reversa)

Esta documentação foi reconstruída a partir do código, sem acesso ao histórico da conversa que originou o sistema.
Cada afirmação deve apontar para um arquivo/símbolo. O que não tem evidência fica em [PENDENCIAS_E_DUVIDAS.md](PENDENCIAS_E_DUVIDAS.md).

Convenção de confiança: **[FATO]** lido no código · **[HIPÓTESE]** inferido · **[?]** intenção desconhecida · **[CONTEXTO]** conhecimento geral do setor, não verificável no código.

## Visão do sistema [FATO]
Sistema web de recepção e gestão do Centro de Medicina Nuclear do Leste Mineiro, em Governador Valadares (MG) (versão em `VERSION`: 1.5.0).
Flask + Waitress + SQLite, um servidor em um PC da clínica; os demais PCs usam o navegador (porta 8080 por padrão).
Origem declarada: substitui a planilha `VERSÃO 2.1 RECEPÇÃO1.xlsm` e o banco `BD.mdb` (`LEIA-ME.md`; importadores em `ferramentas/` e `app/cli.py`).
Para entender **o que a empresa faz**, comece por [NEGOCIO_E_PRODUTO.md](NEGOCIO_E_PRODUTO.md).

## Documentos
| Documento | Conteúdo | Estado |
|---|---|---|
| [NEGOCIO_E_PRODUTO.md](NEGOCIO_E_PRODUTO.md) | o que a clínica faz, quem usa, jornada do exame, conformidade, glossário, história das versões | concluído |
| [ARQUITETURA.md](ARQUITETURA.md) | tecnologias, estrutura, pontos de entrada, ciclo da requisição, mapa de módulos e plano | Fase 1 concluída |
| [MODULOS.md](MODULOS.md) | detalhe por módulo (blocos 1 a 9 e front-end) | blocos 1 a 9 lidos (ressalvas abaixo) |
| [FLUXOS.md](FLUXOS.md) | fluxos de ponta a ponta (12) | concluído |
| [REGRAS_DE_NEGOCIO.md](REGRAS_DE_NEGOCIO.md) | regras, cálculos, permissões (§1–§15) | concluído para os módulos lidos |
| [DADOS_E_INTEGRACOES.md](DADOS_E_INTEGRACOES.md) | tabelas, persistência, integrações | bloco 1 em detalhe; demais por inventário |
| [INTERFACE.md](INTERFACE.md) | telas observadas em execução local com banco falso e fluxos testados | parcial (9 telas, 3 fluxos) |
| [TESTES_E_COMPORTAMENTOS.md](TESTES_E_COMPORTAMENTOS.md) | suíte (448 testes na época da documentação; 518 depois das alterações, 0 falhas) e o que ela comprova | concluído |
| [PENDENCIAS_E_DUVIDAS.md](PENDENCIAS_E_DUVIDAS.md) | lacunas e inconsistências (41 itens; 4 já resolvidos) | aberto |
| [ALTERACOES.md](ALTERACOES.md) | mudanças feitas no código depois da documentação (19 a 20/10/2026) | concluído; as demais páginas descrevem o sistema **antes** delas |

## Registro de progresso
| Fase | Estado | Observação |
|---|---|---|
| 1 Inventário | **concluída** | ver ARQUITETURA.md |
| 2 Módulos | **concluída com ressalvas** | blocos 1 a 9 lidos; bloco 10 (testes) mapeado por nome e executado |
| 3 Fluxos | **concluída** | 12 fluxos em FLUXOS.md |
| 4 Regras | **concluída** para os módulos lidos | REGRAS_DE_NEGOCIO.md §1–§15 |
| 5 Verificação | **concluída** | suíte completa em cópia isolada; telas e fluxos conferidos em execução local |

## O que foi lido e o que não foi (ressalvas)
- **Lidos por inteiro:** os módulos Python de `app/` dos blocos 1 a 9 (banco, autenticação, permissões, auditoria, cadastros, atendimentos, fichas, medicamentos, exames realizados, laudos, blindagens e seus documentos, agenda, movimento, caixa diário, financeiro, faturamento, fornecedores, Banco de Horas completo, chat, avisos, anexos, documentos, atualização, NucleAI e ajuda, qualidade e robô, pesquisa, ONA, dashboard, saúde, backup, CLI), mais `servidor.py`, `tray.pyw`, `INICIAR.bat`, `ferramentas/importar_dados.py`, os textos de ajuda, o histórico de versões e os scripts `app.js`, `sessao.js`, `chat.js`, `agenda.js`, `bh.js`, `atualizacao.js`, `aguarde.js`, `faturamento.js` e o formulário de atendimento.
- **Lidos só em parte:** `views_qualidade.py` (330 das 664 linhas; o resto foi mapeado por rotas).
- **Não lidos linha a linha (só mapeados por busca ou assinatura):** os geradores secundários de PDF/Excel (`agenda_docs`, `agenda_rel_docs`, `agenda_fin_docs`, `ajuda_docs`, `ona_docs`, `pesquisa_docs`, `movimento_docs`, `fornecedores_docs`, `qualidade_docs`), `ajuda_alias.py`, `ajuda_frases.py`, `ajuda_base.py`; 153 templates HTML (7,6 mil linhas, exceto o de atendimento); 10 scripts de `static/js` (`dashboard.js`, `fluxograma.js`, `qualidade.js`, `tutorial.js`, `favoritos.js`, `menu.js`, `agenda_faltas.js`, `boasvindas.js`, `saude.js`, `tema.js`); 2,3 mil linhas de CSS; os 42 arquivos de teste (só os nomes dos testes); `ferramentas/` exceto `importar_dados.py`; `instalador/`.
- **Executado:** a suíte de testes (cópia isolada) e o sistema local com banco falso (9 telas, cadastro, atendimento, fichas). **Não** foi aberto o banco real nem a instalação em `C:\ProgramData\Nucleleste`.

Nada foi alterado no código, nos dados reais ou na instalação. Tudo o que foi criado fora de `docs/` está na pasta temporária da sessão (cópia do código, ambiente virtual e logs), que pode ser apagada.
