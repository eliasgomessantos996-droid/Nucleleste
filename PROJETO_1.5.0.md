# Projeto 1.5.0

Estado: **em desenvolvimento** (`VERSION` 1.5.0). Plano aprovado: chat com imagens, Qualidade completa, robô do PDCA e teste de sobrecarga.
Base: 1.4.9 (instalador `instalador/saida/Setup-Nucleleste-1.4.9.exe` gerado; instalação real ainda não atualizada).

## Itens da 1.5.0
| # | Item | Área / módulo | Status |
|---|------|---------------|--------|
| 1 | Imagens no chat, apagadas em 24 h (conteúdo no anexos.db, rota protegida, limpeza no laço de avisos) | `chat.py`, `views_chat.py`, `chat.js` | Feito e testado |
| 2 | Central da qualidade e indicadores (KPI) com metas e série mensal | `qualidade_dados.py`, `views_qualidade.py` | Feito e testado |
| 3 | Ciclo PDCA, Pareto, Ishikawa, 5 Porquês, GUT, matriz de risco, 5W2H, SWOT (com PDF/Excel/impressão) | `qualidade.py`, `qualidade_docs.py`, `templates/qualidade/` | Feito e testado |
| 4 | Fluxograma de processos (editor SVG) e organograma | `fluxograma.js`, `qualidade.js` | Feito e testado |
| 5 | Ocorrências, pesquisa de satisfação, motivo das faltas | `qualidade.py` | Feito e testado |
| 6 | Avaliação de fornecedores (ONA) com critérios, relatório e PDF por avaliação | `qualidade.py`, `qualidade_docs.py` | Feito e testado |
| 7 | Robô do PDCA (motor de regras) com rotina diária e aviso à gerência | `qualidade_robo.py`, `qualidade_modelos.py` | Feito e testado |
| 8 | Teste de sobrecarga (gerador de dados, carga HTTP, teste de queda) e otimizações | `ferramentas/`, dashboard, registros, atendimentos, KPI, ONA | Feito e testado |
| 9 | Login OAuth | — | Fora desta versão (depende de domínio com HTTPS) |

Status possíveis: A fazer · Em andamento · Feito e testado · Fora desta versão.

## Como cada item será feito
1. Ler o módulo e o teste dele antes de editar.
2. Alterar só o que o item pede, sem mexer no comportamento do resto.
3. Escrever ou ajustar testes e ver rodar.
4. Conferir na tela quando o item for visual.
5. Registrar o item no log de atualizações (`app/novidades.py`) na entrada da 1.5.0.

## Fechamento da versão
- Subir o `VERSION` para 1.5.0 (só quando o trabalho começar).
- Rodar a suíte completa (4 grupos em paralelo) e mostrar o resultado.
- Gerar o instalador (`instalador/build.ps1`) e instalar na instalação real, somente com a aprovação do usuário (a instalação em uso exige a permissão do Windows).

## Regras fixas do projeto
- Não mexer na instalação real (`C:\ProgramData\Nucleleste`) nem rodar instalador sem aprovação.
- Não fazer commit nem push sem pedido.
- Mostrar o resultado dos testes sem afirmar o que não foi verificado.
- Se algo imprevisto for tocado, parar e perguntar.

## Pendências herdadas da 1.4.9
- Instalar a 1.4.9 na instalação real (aguarda aprovação).
- Caixa diário da empresa: regras de conta por despesa e taxa de PIX ainda precisam de confirmação; histórico de agosto e setembro não foi importado.
- Ordem das agendas e cor do calendário foram testadas no código, não na tela instalada.

## Resultado do teste de sobrecarga (ambiente isolado, dados sintéticos, máquina de 4 núcleos e 16 GB)
Ferramentas: `ferramentas/gerar_carga.py` (dados), `ferramentas/servidor_carga.py` (servidor de teste), `ferramentas/carga_http.py`
(usuários simultâneos), `ferramentas/teste_queda.py` (queda no meio das gravações). Nenhuma toca a instalação real nem a porta 8080.

| Cenário | Antes das otimizações | Depois |
|---|---|---|
| Escala M (2 milhões de linhas), 50 usuários | 4 req/s · p50 3,2 s · 44 erros (tempo esgotado) | 24,5 req/s · p50 0,33 s · 0 erros |
| Escala M, 20 usuários | — | 17 req/s · p50 0,11 s · p95 0,86 s · 0 erros |
| Escala M, 200 usuários (estresse) | — | 23 req/s (saturado) · p50 5,2 s · 0 erros · memória estável (~710 MB) |
| Dashboard "tudo", escala M, uma pessoa | 205 s | 5 a 7 s (depois 0,1 s pelo cache) |
| Dashboard "tudo", escala L (20 milhões) | 128 s (já com a 1ª rodada) | 45 s na primeira abertura, 1,5 s depois |
| Queda do servidor no meio de ~340 gravações | — | banco íntegro, todas as gravações confirmadas salvas |

Escala XL (50 milhões) não foi gerada: precisaria de ~11 GB e deixaria o disco abaixo da folga de 8 GB.
Limite encontrado: um único processo Python satura perto de 25 req/s nesta máquina; para mais de ~50 usuários ativos ao mesmo
tempo seria preciso outro modelo de servidor. Na escala L ainda ficam lentos (primeira abertura): dashboard de período longo e
o painel de indicadores (~17 s). Ideia futura: índice de busca por trecho de nome (FTS5) no cadastro de clientes.
