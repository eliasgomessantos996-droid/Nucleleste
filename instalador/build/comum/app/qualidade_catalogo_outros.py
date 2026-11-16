"""Modelos prontos (continuação de `qualidade_catalogo.py`): planos 5W2H, matriz de risco, SWOT, organogramas, registros de ocorrência,
critérios de avaliação de fornecedores e perguntas da pesquisa de satisfação, todos para um centro de medicina nuclear.

Mesmo aviso do catálogo principal: são pontos de partida. Ajuste responsáveis, prazos e valores e valide com o responsável técnico e o
supervisor de proteção radiológica antes de apresentar a um órgão."""
from __future__ import annotations

# ------------------------------------------------------------------ planos de ação 5W2H
# (o quê, por quê, onde, quem, como, prazo em dias)
PLANOS = {
    'radioprotecao_anual': {
        'titulo': 'Programa anual de proteção radiológica', 'area': 'Radioproteção',
        'descricao': 'Rotina anual do plano de proteção radiológica: monitoração, calibrações, treinamentos e relatórios.',
        'acoes': [
            ('Calibrar e aferir monitores de radiação e calibrador de dose nos prazos', 'Garantir medidas confiáveis', 'Laboratório de radiofármacos', 'Supervisor de proteção radiológica', 'Cronograma anual com certificados arquivados.', 60),
            ('Levantamento radiométrico das áreas (taxas de exposição) e comparação com os limites do plano', 'Verificar a blindagem e a classificação das áreas', 'Setor de medicina nuclear', 'Supervisor de proteção radiológica', 'Mapa de pontos de medida, registro e relatório.', 90),
            ('Troca e análise mensal dos dosímetros individuais', 'Acompanhar as doses ocupacionais', 'Setor de medicina nuclear', 'Supervisor de proteção radiológica', 'Controle de entrega e devolução e análise das leituras.', 30),
            ('Treinamento anual de radioproteção e emergências para toda a equipe', 'Manter a competência', 'Setor de medicina nuclear', 'Supervisor de proteção radiológica', 'Lista de presença, conteúdo e avaliação.', 120),
            ('Simulado de derramamento e de situação de emergência', 'Testar a resposta', 'Setor de medicina nuclear', 'Qualidade', 'Cenário, tempo de resposta e lições aprendidas.', 150),
            ('Revisar o plano de proteção radiológica e o plano de gerência de rejeitos', 'Manter atualizados e aprovados', 'Direção', 'Responsável técnico', 'Revisão anual com registro de mudanças e aprovação.', 180),
            ('Relatório anual de atividades e conferência da documentação exigida pela CNEN', 'Cumprir a regulamentação', 'Administração', 'Responsável técnico', 'Checklist da documentação e protocolo de envio.', 180)]},
    'cq_equipamentos': {
        'titulo': 'Controle de qualidade e manutenção de equipamentos', 'area': 'Equipamentos',
        'descricao': 'Calendário de testes de constância, controle de qualidade e manutenção da gama-câmara, SPECT, curiômetro e demais equipamentos.',
        'acoes': [
            ('Teste de constância diário do calibrador de dose', 'Confiabilidade da atividade administrada', 'Laboratório de radiofármacos', 'Supervisor de proteção radiológica', 'Fonte de referência e planilha com limites.', 1),
            ('Controle de qualidade diário/semanal da gama-câmara (uniformidade, pico de energia, fundo)', 'Qualidade da imagem', 'Sala de imagem', 'Tecnólogo', 'Planilha de testes com critérios de aceitação.', 7),
            ('Testes periódicos do SPECT (centro de rotação, resolução, sensibilidade)', 'Qualidade tomográfica', 'Sala de imagem', 'Físico médico', 'Calendário do fabricante e das normas.', 90),
            ('Manutenção preventiva programada de todos os equipamentos', 'Evitar paradas', 'Sala de imagem', 'Responsável técnico', 'Contrato com visitas e registro das ordens de serviço.', 90),
            ('Controle de qualidade do monitor de contaminação e dos monitores de área', 'Segurança da equipe', 'Laboratório', 'Supervisor de proteção radiológica', 'Teste com fonte e certificado de calibração.', 30),
            ('Conferência mensal das planilhas de controle de qualidade pela direção técnica', 'Acompanhar o cumprimento', 'Qualidade', 'Responsável técnico', 'Assinar as planilhas e abrir ação para desvios.', 30)]},
    'ona_preparacao': {
        'titulo': 'Preparação para a acreditação ONA', 'area': 'Acreditação',
        'descricao': 'Passos para organizar a documentação, os indicadores e as evidências exigidas na avaliação.',
        'acoes': [
            ('Mapear e desenhar os processos principais com fluxogramas aprovados', 'Padronizar a rotina', 'Qualidade', 'Qualidade', 'Usar a aba Fluxogramas com os modelos prontos e aprovar a versão.', 45),
            ('Elaborar e aprovar os protocolos (POPs) dos processos críticos', 'Registrar a forma correta de fazer', 'Qualidade', 'Responsável técnico', 'Usar a aba Protocolos e coletar assinaturas.', 60),
            ('Definir indicadores, metas e responsáveis de cada setor', 'Gerir por resultados', 'Qualidade', 'Gerência', 'Aba Indicadores com metas aprovadas.', 30),
            ('Implantar o gerenciamento de riscos e a notificação de eventos', 'Segurança do paciente', 'Qualidade', 'Qualidade', 'Matriz de risco e aba Ocorrências.', 60),
            ('Avaliar e qualificar os fornecedores críticos', 'Atender a requisitos de compras', 'Compras', 'Compras', 'Avaliação de fornecedores com critérios definidos.', 60),
            ('Programa de treinamento com avaliação de eficácia', 'Competência da equipe', 'Todos os setores', 'Gerência', 'Matriz de treinamentos e registros.', 90),
            ('Auditoria interna com plano de ação das não conformidades', 'Verificar a prontidão', 'Todos os setores', 'Qualidade', 'Checklist e relatório de auditoria.', 120)]},
    'seguranca_paciente': {
        'titulo': 'Metas de segurança do paciente', 'area': 'Segurança do paciente',
        'descricao': 'Ações para identificação do paciente, comunicação, medicação/radiofármaco seguro, prevenção de quedas e de infecção.',
        'acoes': [
            ('Identificar o paciente por nome completo e data de nascimento em todas as etapas', 'Evitar troca de pacientes', 'Todos os setores', 'Qualidade', 'Checklist e orientação na recepção, sala de dose e imagem.', 15),
            ('Dupla checagem de radiofármaco, atividade e paciente antes da administração', 'Administração segura', 'Sala de dose', 'Supervisor de proteção radiológica', 'Registro com duas assinaturas.', 15),
            ('Triagem de gravidez e amamentação registrada antes da dose', 'Proteger paciente e feto', 'Recepção e sala de dose', 'Responsável técnico', 'Campo obrigatório na ficha.', 15),
            ('Prevenir quedas (maca, escada, pacientes sedados ou idosos)', 'Evitar eventos adversos', 'Sala de imagem', 'Enfermagem', 'Orientação, apoio e sinalização.', 30),
            ('Higiene das mãos e limpeza de superfícies e equipamentos', 'Prevenir infecção', 'Todos os setores', 'Enfermagem', 'POP, insumos disponíveis e observação periódica.', 30),
            ('Comunicação efetiva na passagem de plantão e nos resultados críticos', 'Evitar falhas de informação', 'Todos os setores', 'Gerência', 'Formulário de passagem e fluxo de comunicação ao médico.', 30)]},
    'licencas_documentos': {
        'titulo': 'Licenças, alvarás e vencimentos', 'area': 'Regulatório',
        'descricao': 'Controle dos documentos legais do serviço e dos vencimentos (autorização da CNEN, licença sanitária, certificados).',
        'acoes': [
            ('Levantar todas as licenças e autorizações com data de validade', 'Não deixar vencer', 'Administração', 'Responsável técnico', 'Planilha de controle e aviso 90 dias antes.', 15),
            ('Renovar a autorização de operação da CNEN e a licença sanitária nos prazos', 'Manter o funcionamento legal', 'Administração', 'Responsável técnico', 'Protocolar com antecedência e arquivar o comprovante.', 90),
            ('Manter atualizados os registros profissionais (CRM, CRF, CNEN) da equipe', 'Regularidade profissional', 'Administração', 'Gerência', 'Cópias digitalizadas e validade.', 30),
            ('Arquivar os certificados de calibração e de manutenção dos equipamentos', 'Evidências para fiscalização', 'Administração', 'Qualidade', 'Pasta digital por equipamento.', 30)]},
    'treinamento_anual': {
        'titulo': 'Plano anual de treinamento', 'area': 'Pessoas',
        'descricao': 'Matriz de treinamentos obrigatórios e de reciclagem da equipe do centro de medicina nuclear.',
        'acoes': [
            ('Integração de novos colaboradores (rotinas, segurança, LGPD)', 'Padronizar a entrada', 'Recursos humanos', 'Gerência', 'Roteiro de integração com registro.', 15),
            ('Radioproteção básica e emergências (anual para toda a equipe)', 'Segurança radiológica', 'Setor de medicina nuclear', 'Supervisor de proteção radiológica', 'Aula, prova e lista de presença.', 90),
            ('Suporte básico de vida e atendimento de intercorrências', 'Segurança do paciente', 'Setor de medicina nuclear', 'Enfermagem', 'Treino prático com simulado.', 120),
            ('Biossegurança, higienização e gerenciamento de resíduos', 'Prevenir infecção e descarte inadequado', 'Todos os setores', 'Qualidade', 'Treinamento e checklist.', 120),
            ('Atendimento ao paciente e comunicação (recepção e técnicos)', 'Melhorar a experiência', 'Recepção', 'Gerência', 'Oficina com casos reais.', 150),
            ('Avaliar a eficácia dos treinamentos (prova ou observação)', 'Confirmar o aprendizado', 'Todos os setores', 'Qualidade', 'Formulário de eficácia.', 180)]},
    'lgpd_seguranca_info': {
        'titulo': 'Proteção de dados e segurança da informação', 'area': 'Informação',
        'descricao': 'Ações de LGPD e de segurança dos dados dos pacientes, imagens e laudos.',
        'acoes': [
            ('Definir quem acessa o quê no sistema (perfis e módulos) e revisar periodicamente', 'Menor privilégio', 'TI / Gerência', 'Gerência', 'Revisão trimestral dos acessos.', 30),
            ('Backup diário com cópia externa e teste de restauração', 'Não perder dados', 'TI', 'Responsável de TI', 'Aba de Backup e teste trimestral.', 30),
            ('Termo de confidencialidade para a equipe e prestadores', 'Sigilo profissional', 'Recursos humanos', 'Gerência', 'Assinatura e arquivo.', 30),
            ('Política de retenção e descarte de documentos e imagens', 'Cumprir prazos legais', 'Administração', 'Responsável técnico', 'Tabela de temporalidade.', 60)]},
}

# ------------------------------------------------------------------ matriz de risco
# (título, processo, causa, consequência, probabilidade 1-5, impacto 1-5, resposta, ação, prazo em dias)
RISCOS = {
    'radioprotecao': {
        'titulo': 'Radioproteção', 'descricao': 'Exposição ocupacional, contaminação, rejeitos e acesso às áreas controladas.',
        'itens': [
            ('Exposição ocupacional acima do limite de dose', 'Manipulação e administração', 'Falta de uso de blindagem, tempo excessivo ou dosímetro fora de uso', 'Dose acima do limite e afastamento do trabalhador', 2, 5, 'Mitigar', 'Blindagens, rodízio de tarefas e análise mensal dos dosímetros.', 30),
            ('Contaminação de superfícies e pessoas', 'Manipulação e administração', 'Derramamento, gotejamento ou falha na técnica', 'Propagação do material radioativo e exposição não prevista', 3, 4, 'Mitigar', 'Kit de derramamento, treinamento e monitoração rotineira.', 30),
            ('Rejeito radioativo descartado fora do plano', 'Gerência de rejeitos', 'Segregação inadequada ou falta de medição de liberação', 'Infração, dano ambiental e risco à população', 2, 5, 'Mitigar', 'Checklist de rejeitos e conferência pelo supervisor.', 30),
            ('Perda ou furto de fonte ou material radioativo', 'Recebimento e armazenamento', 'Armazenamento sem controle de acesso e inventário', 'Evento de segurança física e comunicação obrigatória à CNEN', 1, 5, 'Mitigar', 'Cofre/armário blindado, inventário e controle de chave.', 30),
            ('Acesso de pessoas não autorizadas a áreas controladas', 'Circulação de pacientes e visitantes', 'Sinalização insuficiente e acompanhantes sem orientação', 'Exposição desnecessária de terceiros', 3, 3, 'Mitigar', 'Sinalização, portas com aviso e orientação na recepção.', 15),
            ('Paciente injetado liberado sem orientação de radioproteção', 'Alta do paciente', 'Pressa ou falta de roteiro padronizado', 'Exposição de familiares e do público', 3, 3, 'Mitigar', 'Roteiro de orientação entregue por escrito.', 15)]},
    'seguranca_paciente': {
        'titulo': 'Segurança do paciente', 'descricao': 'Identificação, administração, intercorrências e comunicação.',
        'itens': [
            ('Administração do radiofármaco ao paciente errado', 'Administração', 'Falha de identificação ou homônimos', 'Exposição indevida e exame trocado', 2, 5, 'Mitigar', 'Dois identificadores e checagem dupla na sala de dose.', 15),
            ('Atividade administrada fora da prescrição', 'Administração', 'Erro de medição, de decaimento ou de prescrição', 'Imagem inadequada ou exposição maior', 3, 4, 'Mitigar', 'Dupla checagem e teste de constância do curiômetro.', 15),
            ('Administração a paciente grávida sem triagem', 'Triagem', 'Pergunta não feita ou não registrada', 'Exposição do feto', 2, 5, 'Mitigar', 'Campo obrigatório na ficha e cartaz de aviso.', 10),
            ('Extravasamento do radiofármaco', 'Administração', 'Acesso venoso inadequado ou técnica inadequada', 'Dose no tecido e exame prejudicado', 3, 3, 'Mitigar', 'Teste do acesso com soro e registro dos casos.', 15),
            ('Reação adversa ou intercorrência clínica', 'Atendimento', 'Reação alérgica, mal-estar ou descompensação', 'Dano ao paciente se o atendimento demorar', 2, 5, 'Mitigar', 'Carrinho de emergência conferido e equipe treinada.', 30),
            ('Queda do paciente', 'Sala de imagem', 'Maca alta, paciente idoso ou sedado, piso molhado', 'Trauma e evento adverso', 2, 4, 'Mitigar', 'Apoio na maca e orientação, piso seco.', 15),
            ('Laudo liberado com erro de lateralidade ou paciente', 'Laudo', 'Revisão ausente ou dados trocados', 'Conduta clínica errada', 2, 5, 'Mitigar', 'Revisão e conferência de dados antes da liberação.', 15)]},
    'radiofarmacos_equipamentos': {
        'titulo': 'Radiofármacos e equipamentos', 'descricao': 'Fornecimento, qualidade do radiofármaco e disponibilidade dos equipamentos.',
        'itens': [
            ('Falha na entrega do radiofármaco ou do gerador', 'Compras', 'Dependência de um único fornecedor ou atraso logístico', 'Cancelamento de exames e perda de receita', 3, 4, 'Mitigar', 'Segundo fornecedor qualificado e calendário de entregas.', 45),
            ('Eluato do gerador fora da especificação', 'Preparo', 'Gerador no fim da vida ou controle de qualidade não feito', 'Imagem inadequada', 2, 4, 'Mitigar', 'Checklist de eluição e CQ do eluato.', 15),
            ('Parada da gama-câmara', 'Imagem', 'Manutenção insuficiente ou falha do detector', 'Suspensão do atendimento', 3, 4, 'Mitigar', 'Contrato de manutenção e peças críticas.', 45),
            ('Calibrador de dose sem calibração em dia', 'Laboratório', 'Calendário sem responsável', 'Atividades administradas incertas', 2, 5, 'Mitigar', 'Calendário com alerta e responsável.', 30),
            ('Falta de energia ou queda do sistema', 'Todos os setores', 'Rede elétrica instável', 'Parada de atendimento e risco aos equipamentos', 3, 3, 'Mitigar', 'Nobreak, estabilizador e plano de contingência.', 45),
            ('Falha de refrigeração ou de armazenamento de kits', 'Laboratório', 'Equipamento sem monitoramento', 'Perda de insumos', 2, 3, 'Mitigar', 'Monitoramento diário de temperatura e alarme.', 30)]},
    'administrativo_financeiro': {
        'titulo': 'Administrativo, financeiro e informação', 'descricao': 'Convênios, dados dos pacientes e continuidade do negócio.',
        'itens': [
            ('Glosa elevada por falhas de guia ou autorização', 'Faturamento', 'Conferência insuficiente antes do envio', 'Perda de receita', 4, 3, 'Mitigar', 'Checklist por convênio e análise mensal das glosas.', 30),
            ('Vazamento ou perda de dados de pacientes', 'Informação', 'Acesso sem controle ou ausência de backup', 'Infração à LGPD e perda de histórico', 2, 5, 'Mitigar', 'Perfis de acesso, backup com cópia externa e termo de sigilo.', 30),
            ('Vencimento de licença ou autorização', 'Regulatório', 'Falta de controle de validade', 'Interdição do serviço', 2, 5, 'Mitigar', 'Planilha de vencimentos e alerta de 90 dias.', 15),
            ('Falta de pacientes por faltas e cancelamentos', 'Agenda', 'Confirmação insuficiente', 'Ociosidade e perda de radiofármaco', 4, 3, 'Mitigar', 'Confirmação 48 h e lista de espera.', 15),
            ('Dependência de uma pessoa-chave', 'Gestão', 'Conhecimento concentrado', 'Interrupção na ausência', 3, 3, 'Mitigar', 'Substitutos treinados e procedimentos escritos.', 60),
            ('Atraso no pagamento a fornecedores críticos', 'Financeiro', 'Fluxo de caixa sem acompanhamento', 'Suspensão de fornecimento', 2, 4, 'Mitigar', 'Calendário de pagamentos e reserva.', 30)]},
}

# ------------------------------------------------------------------ SWOT
SWOT = {
    'servico': {
        'titulo': 'Análise SWOT do centro de medicina nuclear', 'descricao': 'Visão geral do serviço: pontos fortes e fracos internos e oportunidades e ameaças do ambiente.',
        'itens': {
            'F': [('Equipe técnica especializada e com formação em medicina nuclear', 5), ('Sistema próprio integrado de recepção, agenda, laudos e financeiro', 4),
                  ('Controle de radioproteção e de rejeitos estabelecido', 4), ('Parcerias com convênios e médicos solicitantes', 3)],
            'FR': [('Dependência de poucos fornecedores de radiofármacos e geradores', 4), ('Processos ainda pouco padronizados por escrito (POPs)', 4),
                   ('Agenda com muitas faltas e cancelamentos', 3), ('Equipamentos que exigem manutenção especializada e peças importadas', 3)],
            'O': [('Aumento da demanda por diagnóstico e estadiamento oncológico e cardiológico', 5), ('Acreditação ONA como diferencial competitivo', 4),
                  ('Novos radiofármacos e protocolos (PSMA, DOTATATO, etc.)', 4), ('Parcerias com hospitais e clínicas da região', 3)],
            'A': [('Oscilações no fornecimento nacional de radionuclídeos', 5), ('Glosas e atrasos de pagamento dos convênios', 4),
                  ('Mudanças regulatórias da CNEN e da ANVISA', 3), ('Concorrência de serviços com tecnologia mais nova (PET/CT)', 4)]}},
    'radioprotecao': {
        'titulo': 'SWOT da radioproteção e conformidade', 'descricao': 'Análise focada no cumprimento da regulamentação e na segurança radiológica.',
        'itens': {
            'F': [('Supervisor de proteção radiológica designado e atuante', 5), ('Dosimetria individual contratada e em dia', 4), ('Áreas controladas sinalizadas', 3)],
            'FR': [('Treinamentos de emergência sem simulados regulares', 4), ('Registros em papel dispersos', 3), ('Acompanhantes sem orientação padronizada', 3)],
            'O': [('Digitalizar os registros de radioproteção e rejeitos', 4), ('Auditorias internas periódicas para antecipar a fiscalização', 4), ('Consultoria externa de física médica', 3)],
            'A': [('Fiscalização com exigência de documentação completa', 4), ('Rotatividade de profissionais treinados', 3), ('Incidente de contaminação ou perda de fonte', 5)]}},
    'expansao': {
        'titulo': 'SWOT para novo equipamento ou novo exame', 'descricao': 'Para decidir sobre a compra de um equipamento ou a oferta de um novo procedimento.',
        'itens': {
            'F': [('Espaço físico e blindagem adequados ou adaptáveis', 4), ('Equipe com capacidade de absorver o novo exame', 3), ('Base de pacientes e médicos solicitantes', 4)],
            'FR': [('Investimento e capital de giro limitados', 5), ('Necessidade de treinamento específico', 3), ('Mais carga sobre a agenda e o laudo', 3)],
            'O': [('Demanda reprimida na região pelo exame', 5), ('Tabela dos convênios favorável ao procedimento', 4), ('Parcerias com serviços de referência', 3)],
            'A': [('Concorrentes que já oferecem o exame', 4), ('Falta de cobertura por parte dos convênios', 4), ('Atrasos na entrega do equipamento e no licenciamento', 3)]}},
}

# ------------------------------------------------------------------ organogramas
# (id, cargo, setor, id do superior ou None, cor)
ORGANOGRAMAS = {
    'basico': {
        'titulo': 'Centro de medicina nuclear de pequeno porte', 'descricao': 'Direção, responsável técnico, supervisor de proteção radiológica e as equipes assistencial e administrativa.',
        'nos': [(1, 'Direção / Sócios', 'Direção', None, '#255f39'),
                (2, 'Responsável técnico (médico nuclear)', 'Direção técnica', 1, '#1565c0'),
                (3, 'Supervisor de proteção radiológica', 'Radioproteção', 1, '#c62828'),
                (4, 'Gerência administrativa', 'Administração', 1, '#6a1b9a'),
                (5, 'Médicos nucleares', 'Corpo clínico', 2, '#1565c0'),
                (6, 'Coordenação técnica / tecnólogos', 'Imagem', 2, '#2e7d32'),
                (7, 'Enfermagem e técnicos', 'Assistência', 2, '#2e7d32'),
                (8, 'Físico médico (consultoria)', 'Radioproteção', 3, '#c62828'),
                (9, 'Recepção e agendamento', 'Recepção', 4, '#6a1b9a'),
                (10, 'Faturamento e financeiro', 'Faturamento', 4, '#6a1b9a'),
                (11, 'Qualidade', 'Qualidade', 4, '#ef6c00'),
                (12, 'Apoio (limpeza e manutenção)', 'Apoio', 4, '#757575')]},
    'completo': {
        'titulo': 'Serviço com terapia e comissão de qualidade', 'descricao': 'Estrutura com terapia (iodo-131 e outros), comissões e áreas de apoio.',
        'nos': [(1, 'Diretoria', 'Direção', None, '#255f39'),
                (2, 'Direção técnica / Responsável técnico', 'Direção técnica', 1, '#1565c0'),
                (3, 'Direção administrativa', 'Administração', 1, '#6a1b9a'),
                (4, 'Comissão de qualidade e segurança do paciente', 'Qualidade', 1, '#ef6c00'),
                (5, 'Supervisor de proteção radiológica (SPR)', 'Radioproteção', 2, '#c62828'),
                (6, 'Medicina nuclear diagnóstica', 'Diagnóstico', 2, '#1565c0'),
                (7, 'Terapia com radionuclídeos', 'Terapia', 2, '#1565c0'),
                (8, 'Radiofarmácia / laboratório', 'Radiofarmácia', 2, '#2e7d32'),
                (9, 'Físico médico', 'Radioproteção', 5, '#c62828'),
                (10, 'Gerência de rejeitos', 'Radioproteção', 5, '#c62828'),
                (11, 'Imagem (gama-câmara/SPECT)', 'Imagem', 6, '#2e7d32'),
                (12, 'Laudos', 'Corpo clínico', 6, '#1565c0'),
                (13, 'Enfermagem', 'Assistência', 7, '#2e7d32'),
                (14, 'Recepção e agenda', 'Recepção', 3, '#6a1b9a'),
                (15, 'Faturamento e convênios', 'Faturamento', 3, '#6a1b9a'),
                (16, 'Financeiro e compras', 'Financeiro', 3, '#6a1b9a'),
                (17, 'TI e sistema', 'TI', 3, '#757575'),
                (18, 'Recursos humanos', 'RH', 3, '#757575')]},
    'radioprotecao': {
        'titulo': 'Organização da proteção radiológica', 'descricao': 'Quem responde por quê na radioproteção do serviço (titular, supervisor, físico, trabalhadores).',
        'nos': [(1, 'Titular da autorização (CNEN)', 'Direção', None, '#255f39'),
                (2, 'Supervisor de proteção radiológica', 'Radioproteção', 1, '#c62828'),
                (3, 'Responsável técnico', 'Direção técnica', 1, '#1565c0'),
                (4, 'Físico médico / especialista em dosimetria', 'Radioproteção', 2, '#c62828'),
                (5, 'Trabalhadores ocupacionalmente expostos', 'Setor de medicina nuclear', 2, '#2e7d32'),
                (6, 'Gerência de rejeitos', 'Radioproteção', 2, '#c62828'),
                (7, 'Comissão de emergência', 'Radioproteção', 1, '#ef6c00')]},
}

# ------------------------------------------------------------------ registros de ocorrência (preenchem o formulário)
# (nome do modelo, tipo, gravidade, setor, descrição, ação imediata)
OCORRENCIAS = (
    ('Derramamento de material radioativo', 'Evento adverso', 'Moderada', 'Radiofarmácia / sala de dose',
     'Derramamento de radiofármaco em bancada/piso (informar radionuclídeo, atividade estimada, local e pessoas envolvidas).',
     'Área isolada e sinalizada, equipe avisada, descontaminação com kit, monitoração de pessoas e superfície, registro e comunicação ao supervisor de proteção radiológica.'),
    ('Extravasamento de radiofármaco', 'Evento adverso', 'Leve', 'Sala de dose',
     'Extravasamento durante a injeção (informar local, volume estimado e paciente).',
     'Interrompida a injeção, membro elevado, orientada a lavagem local, médico nuclear comunicado e registro da imagem/dose no local.'),
    ('Atividade fora da faixa de tolerância', 'Não conformidade', 'Moderada', 'Sala de manipulação',
     'Atividade medida diferente da prescrita além da tolerância do protocolo (informar atividade prescrita, medida e horário).',
     'Dose não administrada ou ajustada com decisão do médico nuclear; verificação do calibrador de dose; registro.'),
    ('Paciente identificado incorretamente (quase falha)', 'Quase falha', 'Moderada', 'Recepção / sala de dose',
     'Erro de identificação percebido antes da administração ou do exame (informar o ponto em que foi detectado).',
     'Processo interrompido, paciente reidentificado com dois identificadores e etapa refeita.'),
    ('Reação adversa ao radiofármaco', 'Evento adverso', 'Grave', 'Sala de dose',
     'Reação alérgica ou mal-estar após a administração (informar sintomas, horário e conduta).',
     'Atendimento imediato conforme protocolo de emergência, médico acionado, paciente monitorado e notificação à vigilância quando aplicável.'),
    ('Repetição de imagem', 'Retrabalho / repetição de exame', 'Leve', 'Sala de imagem',
     'Imagem repetida (movimento, artefato, posicionamento ou falha de aquisição).',
     'Paciente reposicionado e imagem repetida; motivo registrado.'),
    ('Laudo retificado', 'Laudo retificado', 'Moderada', 'Laudo',
     'Laudo retificado após a liberação (informar motivo: dado do paciente, lateralidade, texto).',
     'Laudo corrigido e reenviado; paciente e médico solicitante informados.'),
    ('Equipamento parado', 'Equipamento parado', 'Moderada', 'Sala de imagem',
     'Parada de equipamento (informar equipamento, horário e sintoma).',
     'Pacientes reagendados, assistência técnica acionada e pacientes informados.'),
    ('Reclamação do paciente', 'Reclamação', 'Leve', 'Recepção',
     'Reclamação registrada pelo paciente (informar tema: espera, atendimento, preparo, resultado).',
     'Paciente ouvido e atendido pela gerência; resposta registrada.'),
    ('Autorização do convênio negada', 'Não conformidade', 'Leve', 'Faturamento',
     'Exame sem autorização válida do convênio no dia do atendimento.',
     'Paciente informado; contato com o convênio; exame remarcado ou liberado conforme decisão da gerência.'),
    ('Elogio', 'Elogio', 'Leve', 'Recepção', 'Elogio recebido de paciente ou acompanhante (informar a quem se dirige).', 'Elogio repassado à equipe.'),
    ('Dosímetro perdido ou esquecido', 'Não conformidade', 'Leve', 'Radioproteção',
     'Dosímetro individual extraviado, danificado ou esquecido fora do local.', 'Supervisor de proteção radiológica avisado; dose estimada e dosímetro substituído.'),
)

# ------------------------------------------------------------------ critérios de avaliação de fornecedores
# (nome, descrição, peso 1-5)
CRITERIOS = {
    'radiofarmacos': {
        'titulo': 'Fornecedor de radiofármacos e geradores', 'descricao': 'Para quem fornece radionuclídeos, kits frios e geradores.',
        'criterios': [
            ('Pontualidade e regularidade da entrega', 'Entregas no horário, sem falta; cumprimento do cronograma de produção.', 5),
            ('Qualidade e certificado do produto', 'Certificado de análise, atividade e pureza conforme especificação.', 5),
            ('Licenciamento e documentação (CNEN/ANVISA)', 'Autorizações, registro do produto e transporte regularizados.', 5),
            ('Embalagem e transporte do material radioativo', 'Integridade, rotulagem e taxa de exposição conforme a norma.', 4),
            ('Suporte técnico e atendimento de urgência', 'Responde rápido, reposição em falha e orientação técnica.', 3),
            ('Preço e condições comerciais', 'Preço compatível e prazo de pagamento.', 2)]},
    'equipamentos': {
        'titulo': 'Manutenção e assistência técnica de equipamentos', 'descricao': 'Para assistência técnica, calibração e manutenção de gama-câmara, curiômetro e monitores.',
        'criterios': [
            ('Tempo de atendimento ao chamado', 'Resposta e visita dentro do prazo do contrato.', 5),
            ('Qualidade do serviço e resolução do problema', 'Resolve na primeira visita, sem reincidência.', 5),
            ('Certificados de calibração e relatórios', 'Certificados rastreáveis e relatório de serviço legível.', 4),
            ('Competência técnica e treinamento', 'Técnicos treinados pelo fabricante.', 4),
            ('Disponibilidade de peças', 'Reposição de peças no prazo.', 3),
            ('Preço e condições comerciais', 'Preço e custo-benefício do contrato.', 2)]},
    'materiais': {
        'titulo': 'Materiais, medicamentos e descartáveis', 'descricao': 'Para insumos, medicamentos, seringas, EPI e material de escritório.',
        'criterios': [
            ('Qualidade e conformidade do produto', 'Registro, validade adequada e sem defeitos.', 5),
            ('Prazo de entrega', 'Entregas no prazo; atrasos reduzem a nota.', 4),
            ('Documentação fiscal e sanitária', 'Notas, lotes, registro ANVISA e laudos.', 4),
            ('Atendimento e troca de produtos', 'Resolve devoluções e erros com agilidade.', 3),
            ('Preço e condições comerciais', 'Preço de mercado e condições de pagamento.', 3)]},
    'servicos': {
        'titulo': 'Serviços terceirizados (limpeza, resíduos, dosimetria, transporte)', 'descricao': 'Para serviços de apoio ligados à biossegurança e à radioproteção.',
        'criterios': [
            ('Cumprimento do escopo e da periodicidade', 'Serviço executado no prazo e conforme o contrato.', 5),
            ('Regularidade legal e licenças', 'Alvarás, licenças ambientais, licença sanitária e, quando for o caso, CNEN.', 5),
            ('Treinamento e conduta dos profissionais', 'Equipe orientada sobre áreas controladas e biossegurança.', 4),
            ('Relatórios e rastreabilidade', 'Comprovantes de coleta, laudos de dosimetria e manifestos.', 4),
            ('Atendimento e comunicação', 'Responde às solicitações e informa mudanças.', 3),
            ('Preço e condições comerciais', 'Preço compatível e prazo de pagamento.', 2)]},
}

# ------------------------------------------------------------------ pesquisa de satisfação
PERGUNTAS = {
    'padrao': {
        'titulo': 'Pesquisa completa do paciente', 'descricao': 'Recepção, espera, equipe, orientação, limpeza, conforto, segurança e nota geral.',
        'perguntas': ['Como você avalia o atendimento da recepção?', 'Como você avalia o tempo de espera até ser atendido?',
                      'Como você avalia a cordialidade e o respeito da equipe técnica?',
                      'Como você avalia as explicações recebidas sobre o preparo e a realização do exame?',
                      'Como você avalia a limpeza e a organização da clínica?', 'Como você avalia o conforto das instalações (salas e sala de espera)?',
                      'Como você avalia a segurança e o cuidado durante o exame?', 'Como você avalia a facilidade para agendar o exame?',
                      'De modo geral, como você avalia a clínica?']},
    'medicina_nuclear': {
        'titulo': 'Foco em medicina nuclear (orientação e segurança)', 'descricao': 'Preparo, explicação sobre radiação, cuidado na injeção e orientações após o exame.',
        'perguntas': ['Como você avalia a orientação recebida antes do exame (jejum, medicamentos, horário)?',
                      'Como você avalia as explicações sobre o procedimento e a radiação antes da injeção?',
                      'Como você avalia o cuidado e a delicadeza da equipe na aplicação da injeção?',
                      'Como você avalia o tempo de espera entre a injeção e o início das imagens?',
                      'Como você avalia o conforto durante a realização das imagens?',
                      'Como você avalia as orientações dadas depois do exame (cuidados e contato com outras pessoas)?',
                      'Como você avalia o prazo e a clareza da entrega do resultado?',
                      'De modo geral, como você avalia o serviço de medicina nuclear?']},
    'rapida': {
        'titulo': 'Pesquisa rápida (cinco perguntas)', 'descricao': 'Para uso no dia a dia, com poucas perguntas.',
        'perguntas': ['Como você avalia o atendimento da recepção?', 'Como você avalia o tempo de espera?', 'Como você avalia a equipe técnica?',
                      'Como você avalia as informações recebidas sobre o exame?', 'De modo geral, como você avalia a clínica?']},
    'acolhimento': {
        'titulo': 'Acolhimento e experiência', 'descricao': 'Dá ênfase ao acolhimento, à privacidade e à comunicação.',
        'perguntas': ['Como você avalia o acolhimento ao chegar à clínica?', 'Como você avalia o respeito à sua privacidade?',
                      'Como você avalia a clareza das informações dadas pela equipe?', 'Como você avalia o tempo de espera?',
                      'Como você avalia a limpeza dos ambientes?', 'Como você avalia o conforto da sala de espera?',
                      'Você recomendaria a clínica para um familiar ou amigo?']},
}
