"""Modelos prontos de fluxograma (ponto de partida para desenhar os processos da clínica) e a biblioteca de causas e ações
que o robô do PDCA usa para montar os planos."""
from __future__ import annotations

# ------------------------------------------------------------------ fluxogramas
# cada etapa: (id, forma, texto, coluna, linha, raia). Posições em grade; o editor guarda em pixels.
_MODELOS = {
    'agendamento': ('Agendamento de exame', [('Recepção', '#e3f2fd'), ('Paciente', '#fff8e1'), ('Convênio', '#f3e5f5')], [
        ('n1', 'inicio', 'Paciente pede o exame', 0, 0, 'r1'),
        ('n2', 'processo', 'Conferir pedido médico e dados', 1, 0, 'r0'),
        ('n3', 'decisao', 'Precisa de autorização?', 2, 0, 'r0'),
        ('n4', 'processo', 'Solicitar autorização', 2, 1, 'r2'),
        ('n5', 'decisao', 'Autorizado?', 3, 1, 'r2'),
        ('n6', 'processo', 'Marcar horário na agenda', 3, 0, 'r0'),
        ('n7', 'documento', 'Orientações de preparo', 4, 0, 'r0'),
        ('n8', 'fim', 'Exame agendado', 5, 0, 'r1'),
        ('n9', 'fim', 'Informar paciente e médico', 4, 1, 'r1')],
        [('n1', 'n2', ''), ('n2', 'n3', ''), ('n3', 'n4', 'Sim'), ('n3', 'n6', 'Não'), ('n4', 'n5', ''), ('n5', 'n6', 'Sim'),
         ('n5', 'n9', 'Não'), ('n6', 'n7', ''), ('n7', 'n8', '')]),
    'atendimento': ('Atendimento no dia do exame', [('Recepção', '#e3f2fd'), ('Enfermagem / técnico', '#e8f5e9'), ('Médico', '#fce4ec')], [
        ('n1', 'inicio', 'Chegada do paciente', 0, 0, 'r0'),
        ('n2', 'processo', 'Identificar (nome e nascimento)', 1, 0, 'r0'),
        ('n3', 'documento', 'Ficha e questionário', 2, 0, 'r0'),
        ('n4', 'decisao', 'Preparo correto?', 3, 1, 'r1'),
        ('n5', 'processo', 'Administrar radiofármaco', 4, 1, 'r1'),
        ('n6', 'processo', 'Registrar atividade e lote', 5, 1, 'r1'),
        ('n7', 'processo', 'Aquisição das imagens', 6, 1, 'r1'),
        ('n8', 'processo', 'Remarcar e orientar', 4, 0, 'r0'),
        ('n9', 'fim', 'Exame enviado para laudo', 7, 2, 'r2')],
        [('n1', 'n2', ''), ('n2', 'n3', ''), ('n3', 'n4', ''), ('n4', 'n5', 'Sim'), ('n4', 'n8', 'Não'), ('n5', 'n6', ''),
         ('n6', 'n7', ''), ('n7', 'n9', '')]),
    'laudo': ('Laudo e entrega', [('Técnico', '#e8f5e9'), ('Médico', '#fce4ec'), ('Recepção', '#e3f2fd')], [
        ('n1', 'inicio', 'Imagens prontas', 0, 0, 'r0'),
        ('n2', 'processo', 'Processar imagens', 1, 0, 'r0'),
        ('n3', 'processo', 'Laudar', 2, 1, 'r1'),
        ('n4', 'decisao', 'Revisão ok?', 3, 1, 'r1'),
        ('n5', 'processo', 'Liberar laudo', 4, 1, 'r1'),
        ('n6', 'processo', 'Avisar e entregar', 5, 2, 'r2'),
        ('n7', 'fim', 'Laudo entregue', 6, 2, 'r2')],
        [('n1', 'n2', ''), ('n2', 'n3', ''), ('n3', 'n4', ''), ('n4', 'n5', 'Sim'), ('n4', 'n3', 'Não'), ('n5', 'n6', ''), ('n6', 'n7', '')]),
    'compras': ('Compras e recebimento', [('Solicitante', '#fff8e1'), ('Compras', '#e3f2fd'), ('Almoxarifado', '#e8f5e9')], [
        ('n1', 'inicio', 'Necessidade de material', 0, 0, 'r0'),
        ('n2', 'processo', 'Cotar com fornecedores qualificados', 1, 1, 'r1'),
        ('n3', 'decisao', 'Fornecedor aprovado na avaliação?', 2, 1, 'r1'),
        ('n4', 'processo', 'Emitir pedido', 3, 1, 'r1'),
        ('n5', 'processo', 'Receber e conferir', 4, 2, 'r2'),
        ('n6', 'decisao', 'Conforme?', 5, 2, 'r2'),
        ('n7', 'fim', 'Estocar e registrar', 6, 2, 'r2'),
        ('n8', 'processo', 'Registrar não conformidade e devolver', 6, 1, 'r1')],
        [('n1', 'n2', ''), ('n2', 'n3', ''), ('n3', 'n4', 'Sim'), ('n3', 'n2', 'Não'), ('n4', 'n5', ''), ('n5', 'n6', ''),
         ('n6', 'n7', 'Sim'), ('n6', 'n8', 'Não')]),
}

# ---- fluxogramas da rotina de um centro de medicina nuclear (ajuste só os nomes dos cargos e as regras do seu serviço)
_MODELOS.update({
    'recebimento_radiofarmaco': ('Recebimento de radiofármaco e gerador', [('Fornecedor / transporte', '#fff8e1'), ('Recebimento', '#e3f2fd'), ('Radioproteção', '#fde7e9')], [
        ('n1', 'inicio', 'Volume radioativo chega', 0, 0, 'r0'),
        ('n2', 'processo', 'Conferir embalagem, rótulo e nota', 1, 0, 'r1'),
        ('n3', 'processo', 'Medir a taxa de exposição na superfície', 2, 0, 'r2'),
        ('n4', 'decisao', 'Conforme?', 3, 0, 'r2'),
        ('n5', 'processo', 'Registrar no inventário e armazenar blindado', 4, 0, 'r2'),
        ('n6', 'documento', 'Registro de recebimento', 5, 0, 'r2'),
        ('n7', 'processo', 'Registrar não conformidade e acionar o fornecedor', 4, 0, 'r1'),
        ('n8', 'fim', 'Material liberado para uso', 6, 0, 'r2')],
        [('n1', 'n2', ''), ('n2', 'n3', ''), ('n3', 'n4', ''), ('n4', 'n5', 'Sim'), ('n4', 'n7', 'Não'), ('n5', 'n6', ''), ('n6', 'n8', '')]),
    'preparo_radiofarmaco': ('Preparo e controle de qualidade do radiofármaco', [('Laboratório', '#e8f5e9'), ('Radioproteção', '#fde7e9'), ('Médico nuclear', '#fce4ec')], [
        ('n1', 'inicio', 'Prescrição do exame', 0, 0, 'r2'),
        ('n2', 'processo', 'Eluir o gerador / reconstituir o kit', 1, 0, 'r0'),
        ('n3', 'processo', 'Controle de qualidade (rendimento, pureza, pH)', 2, 0, 'r0'),
        ('n4', 'decisao', 'Dentro da especificação?', 3, 0, 'r0'),
        ('n5', 'processo', 'Fracionar e medir a atividade no calibrador', 4, 0, 'r0'),
        ('n6', 'processo', 'Rotular (paciente, atividade, hora)', 5, 0, 'r0'),
        ('n7', 'processo', 'Descartar e registrar a não conformidade', 4, 0, 'r1'),
        ('n8', 'fim', 'Dose pronta para o paciente', 6, 0, 'r0')],
        [('n1', 'n2', ''), ('n2', 'n3', ''), ('n3', 'n4', ''), ('n4', 'n5', 'Sim'), ('n4', 'n7', 'Não'), ('n5', 'n6', ''), ('n6', 'n8', '')]),
    'administracao_dose': ('Administração do radiofármaco', [('Sala de dose / enfermagem', '#e8f5e9'), ('Paciente', '#fff8e1'), ('Médico nuclear', '#fce4ec')], [
        ('n1', 'inicio', 'Paciente chega à sala de dose', 0, 0, 'r1'),
        ('n2', 'processo', 'Identificar (nome completo e nascimento)', 1, 0, 'r0'),
        ('n3', 'decisao', 'Gestante ou lactante?', 2, 0, 'r0'),
        ('n4', 'processo', 'Avaliar a conduta com o médico nuclear', 3, 0, 'r2'),
        ('n5', 'processo', 'Dupla checagem: atividade, radiofármaco e paciente', 3, 0, 'r0'),
        ('n6', 'processo', 'Testar o acesso venoso com soro', 4, 0, 'r0'),
        ('n7', 'processo', 'Administrar a dose', 5, 0, 'r0'),
        ('n8', 'documento', 'Registrar atividade, hora, lote e responsável', 6, 0, 'r0'),
        ('n9', 'processo', 'Orientar hidratação, espera e radioproteção', 7, 0, 'r0'),
        ('n10', 'fim', 'Paciente aguarda a captação', 8, 0, 'r1')],
        [('n1', 'n2', ''), ('n2', 'n3', ''), ('n3', 'n4', 'Sim'), ('n3', 'n5', 'Não'), ('n4', 'n5', ''), ('n5', 'n6', ''), ('n6', 'n7', ''),
         ('n7', 'n8', ''), ('n8', 'n9', ''), ('n9', 'n10', '')]),
    'aquisicao_imagem': ('Aquisição das imagens', [('Tecnólogo', '#e8f5e9'), ('Médico nuclear', '#fce4ec'), ('Paciente', '#fff8e1')], [
        ('n1', 'inicio', 'Paciente aguarda a captação', 0, 0, 'r2'),
        ('n2', 'processo', 'Esvaziar a bexiga e retirar objetos metálicos', 1, 0, 'r2'),
        ('n3', 'processo', 'Posicionar e iniciar o protocolo', 2, 0, 'r0'),
        ('n4', 'processo', 'Adquirir as imagens', 3, 0, 'r0'),
        ('n5', 'decisao', 'Imagem adequada?', 4, 0, 'r0'),
        ('n6', 'processo', 'Repetir ou complementar com o médico', 4, 0, 'r1'),
        ('n7', 'processo', 'Processar as imagens', 5, 0, 'r0'),
        ('n8', 'fim', 'Enviar para o laudo', 6, 0, 'r0')],
        [('n1', 'n2', ''), ('n2', 'n3', ''), ('n3', 'n4', ''), ('n4', 'n5', ''), ('n5', 'n7', 'Sim'), ('n5', 'n6', 'Não'), ('n6', 'n4', ''), ('n7', 'n8', '')]),
    'derramamento': ('Derramamento de material radioativo', [('Quem presencia', '#fff8e1'), ('Supervisor de proteção radiológica', '#fde7e9'), ('Equipe de resposta', '#e8f5e9')], [
        ('n1', 'inicio', 'Derramamento ocorre', 0, 0, 'r0'),
        ('n2', 'processo', 'Avisar a equipe e isolar a área', 1, 0, 'r0'),
        ('n3', 'processo', 'Proteger-se: luvas, avental e sobrecalçado', 2, 0, 'r2'),
        ('n4', 'processo', 'Conter com material absorvente', 3, 0, 'r2'),
        ('n5', 'processo', 'Acionar o supervisor de proteção radiológica', 3, 0, 'r1'),
        ('n6', 'processo', 'Descontaminar de fora para dentro', 4, 0, 'r2'),
        ('n7', 'processo', 'Monitorar pessoas e superfície', 5, 0, 'r1'),
        ('n8', 'decisao', 'Abaixo do limite de liberação?', 6, 0, 'r1'),
        ('n9', 'processo', 'Repetir a descontaminação', 6, 0, 'r2'),
        ('n10', 'documento', 'Registrar a ocorrência e os rejeitos', 7, 0, 'r1'),
        ('n11', 'fim', 'Área liberada', 8, 0, 'r1')],
        [('n1', 'n2', ''), ('n2', 'n3', ''), ('n3', 'n4', ''), ('n2', 'n5', ''), ('n4', 'n6', ''), ('n6', 'n7', ''), ('n7', 'n8', ''), ('n8', 'n10', 'Sim'),
         ('n8', 'n9', 'Não'), ('n9', 'n7', ''), ('n10', 'n11', '')]),
    'rejeitos': ('Gerência de rejeitos radioativos', [('Geração', '#fff8e1'), ('Radioproteção', '#fde7e9'), ('Descarte', '#e8f5e9')], [
        ('n1', 'inicio', 'Rejeito gerado (seringas, frascos, materiais)', 0, 0, 'r0'),
        ('n2', 'processo', 'Segregar por radionuclídeo e meia-vida', 1, 0, 'r0'),
        ('n3', 'processo', 'Identificar (data, atividade, radionuclídeo)', 2, 0, 'r0'),
        ('n4', 'processo', 'Armazenar para decaimento em área blindada', 3, 0, 'r1'),
        ('n5', 'processo', 'Medir a taxa de exposição', 4, 0, 'r1'),
        ('n6', 'decisao', 'Abaixo do limite de liberação?', 5, 0, 'r1'),
        ('n7', 'processo', 'Manter em decaimento e reavaliar', 5, 0, 'r2'),
        ('n8', 'documento', 'Registrar a liberação', 6, 0, 'r1'),
        ('n9', 'fim', 'Descartar como resíduo comum ou infectante', 7, 0, 'r2')],
        [('n1', 'n2', ''), ('n2', 'n3', ''), ('n3', 'n4', ''), ('n4', 'n5', ''), ('n5', 'n6', ''), ('n6', 'n8', 'Sim'), ('n6', 'n7', 'Não'), ('n7', 'n5', ''), ('n8', 'n9', '')]),
    'intercorrencia': ('Reação adversa ou intercorrência com o paciente', [('Equipe presente', '#e8f5e9'), ('Médico', '#fce4ec'), ('Qualidade', '#fff3e0')], [
        ('n1', 'inicio', 'Paciente apresenta reação ou mal-estar', 0, 0, 'r0'),
        ('n2', 'processo', 'Interromper a administração e chamar ajuda', 1, 0, 'r0'),
        ('n3', 'processo', 'Avaliar sinais vitais e iniciar o suporte', 2, 0, 'r0'),
        ('n4', 'processo', 'Acionar o médico responsável', 2, 0, 'r1'),
        ('n5', 'decisao', 'Precisa de remoção?', 3, 0, 'r1'),
        ('n6', 'processo', 'Encaminhar ao serviço de emergência', 4, 0, 'r1'),
        ('n7', 'processo', 'Observar até a estabilidade', 4, 0, 'r0'),
        ('n8', 'documento', 'Registrar o evento e notificar', 5, 0, 'r2'),
        ('n9', 'processo', 'Analisar a causa (Ishikawa e 5 porquês)', 6, 0, 'r2'),
        ('n10', 'fim', 'Plano de ação e acompanhamento', 7, 0, 'r2')],
        [('n1', 'n2', ''), ('n2', 'n3', ''), ('n2', 'n4', ''), ('n4', 'n5', ''), ('n5', 'n6', 'Sim'), ('n5', 'n7', 'Não'), ('n6', 'n8', ''), ('n7', 'n8', ''),
         ('n8', 'n9', ''), ('n9', 'n10', '')]),
    'faturamento_convenio': ('Faturamento de convênio e cobrança', [('Recepção', '#e3f2fd'), ('Faturamento', '#f3e5f5'), ('Convênio', '#fff8e1')], [
        ('n1', 'inicio', 'Atendimento realizado com guia', 0, 0, 'r0'),
        ('n2', 'processo', 'Conferir guia, autorização e assinatura', 1, 0, 'r0'),
        ('n3', 'processo', 'Lançar o atendimento', 2, 0, 'r1'),
        ('n4', 'decisao', 'Documentação completa?', 3, 0, 'r1'),
        ('n5', 'processo', 'Corrigir as pendências', 3, 0, 'r0'),
        ('n6', 'processo', 'Gerar a fatura e o protocolo', 4, 0, 'r1'),
        ('n7', 'processo', 'Enviar ao convênio', 5, 0, 'r2'),
        ('n8', 'processo', 'Emitir a nota fiscal', 5, 0, 'r1'),
        ('n9', 'decisao', 'Pagamento integral?', 6, 0, 'r2'),
        ('n10', 'processo', 'Analisar a glosa e recorrer', 7, 0, 'r1'),
        ('n11', 'fim', 'Recebimento conciliado', 8, 0, 'r2')],
        [('n1', 'n2', ''), ('n2', 'n3', ''), ('n3', 'n4', ''), ('n4', 'n6', 'Sim'), ('n4', 'n5', 'Não'), ('n5', 'n3', ''), ('n6', 'n8', ''), ('n8', 'n7', ''),
         ('n7', 'n9', ''), ('n9', 'n11', 'Sim'), ('n9', 'n10', 'Não'), ('n10', 'n11', '')]),
    'controle_equipamentos': ('Controle de qualidade e manutenção de equipamentos', [('Operador / tecnólogo', '#e8f5e9'), ('Físico médico / supervisor', '#fde7e9'), ('Assistência técnica', '#fff8e1')], [
        ('n1', 'inicio', 'Dia de funcionamento / calendário do teste', 0, 0, 'r0'),
        ('n2', 'processo', 'Realizar o teste de constância ou controle de qualidade', 1, 0, 'r0'),
        ('n3', 'documento', 'Registrar o resultado na planilha', 2, 0, 'r0'),
        ('n4', 'decisao', 'Dentro do limite?', 3, 0, 'r1'),
        ('n5', 'processo', 'Liberar o equipamento para uso', 4, 0, 'r1'),
        ('n6', 'processo', 'Bloquear o uso e sinalizar', 4, 0, 'r0'),
        ('n7', 'processo', 'Abrir o chamado de manutenção', 5, 0, 'r2'),
        ('n8', 'processo', 'Reparar e recalibrar', 6, 0, 'r2'),
        ('n9', 'processo', 'Repetir os testes', 7, 0, 'r1'),
        ('n10', 'fim', 'Equipamento liberado e registro arquivado', 8, 0, 'r1')],
        [('n1', 'n2', ''), ('n2', 'n3', ''), ('n3', 'n4', ''), ('n4', 'n5', 'Sim'), ('n4', 'n6', 'Não'), ('n6', 'n7', ''), ('n7', 'n8', ''), ('n8', 'n9', ''),
         ('n9', 'n5', ''), ('n5', 'n10', '')]),
    'treinamento': ('Treinamento e competência da equipe', [('Gestor', '#e3f2fd'), ('Qualidade', '#fff3e0'), ('Colaborador', '#e8f5e9')], [
        ('n1', 'inicio', 'Admissão ou necessidade de treinamento', 0, 0, 'r0'),
        ('n2', 'processo', 'Definir competências e conteúdos', 1, 0, 'r0'),
        ('n3', 'processo', 'Planejar o treinamento e a data', 2, 0, 'r1'),
        ('n4', 'processo', 'Realizar o treinamento', 3, 0, 'r2'),
        ('n5', 'documento', 'Lista de presença e material', 4, 0, 'r1'),
        ('n6', 'processo', 'Avaliar a eficácia (prova ou observação)', 5, 0, 'r1'),
        ('n7', 'decisao', 'Competente?', 6, 0, 'r1'),
        ('n8', 'processo', 'Reforçar o treinamento', 6, 0, 'r2'),
        ('n9', 'fim', 'Registro na matriz de treinamentos', 7, 0, 'r1')],
        [('n1', 'n2', ''), ('n2', 'n3', ''), ('n3', 'n4', ''), ('n4', 'n5', ''), ('n5', 'n6', ''), ('n6', 'n7', ''), ('n7', 'n9', 'Sim'), ('n7', 'n8', 'Não'), ('n8', 'n6', '')]),
    'reclamacao': ('Tratamento de reclamações e não conformidades', [('Cliente', '#fff8e1'), ('Quem recebe', '#e3f2fd'), ('Gerência / qualidade', '#fff3e0')], [
        ('n1', 'inicio', 'Reclamação ou ocorrência', 0, 0, 'r0'),
        ('n2', 'processo', 'Acolher e registrar em Ocorrências', 1, 0, 'r1'),
        ('n3', 'processo', 'Ação imediata para resolver', 2, 0, 'r1'),
        ('n4', 'decisao', 'Grave ou recorrente?', 3, 0, 'r2'),
        ('n5', 'processo', 'Abrir problema no PDCA (Ishikawa e 5 porquês)', 4, 0, 'r2'),
        ('n6', 'processo', 'Executar o plano de ação', 5, 0, 'r2'),
        ('n7', 'processo', 'Responder ao cliente', 4, 0, 'r1'),
        ('n8', 'processo', 'Verificar a eficácia', 6, 0, 'r2'),
        ('n9', 'fim', 'Encerrar a ocorrência', 7, 0, 'r2')],
        [('n1', 'n2', ''), ('n2', 'n3', ''), ('n3', 'n4', ''), ('n4', 'n5', 'Sim'), ('n4', 'n7', 'Não'), ('n5', 'n6', ''), ('n6', 'n8', ''), ('n8', 'n9', ''), ('n7', 'n9', '')]),
    'terapia_iodo': ('Terapia com radionuclídeo (ex.: iodo-131)', [('Médico nuclear', '#fce4ec'), ('Supervisor de proteção radiológica', '#fde7e9'), ('Enfermagem', '#e8f5e9'), ('Paciente', '#fff8e1')], [
        ('n1', 'inicio', 'Indicação de terapia', 0, 0, 'r0'),
        ('n2', 'processo', 'Consulta e orientação sobre a terapia', 1, 0, 'r0'),
        ('n3', 'documento', 'Termo de consentimento assinado', 2, 0, 'r3'),
        ('n4', 'decisao', 'Gravidez excluída e condições adequadas?', 3, 0, 'r0'),
        ('n5', 'processo', 'Adiar e reorientar', 4, 0, 'r0'),
        ('n6', 'processo', 'Planejar isolamento e orientações de radioproteção', 4, 0, 'r1'),
        ('n7', 'processo', 'Preparar e medir a atividade', 5, 0, 'r1'),
        ('n8', 'processo', 'Administrar a dose', 6, 0, 'r2'),
        ('n9', 'processo', 'Monitorar a taxa de exposição e liberar', 7, 0, 'r1'),
        ('n10', 'documento', 'Alta com instruções escritas', 8, 0, 'r1'),
        ('n11', 'fim', 'Acompanhamento clínico', 9, 0, 'r0')],
        [('n1', 'n2', ''), ('n2', 'n3', ''), ('n3', 'n4', ''), ('n4', 'n6', 'Sim'), ('n4', 'n5', 'Não'), ('n5', 'n2', ''), ('n6', 'n7', ''), ('n7', 'n8', ''),
         ('n8', 'n9', ''), ('n9', 'n10', ''), ('n10', 'n11', '')]),
    'controle_documentos': ('Controle de documentos e protocolos (POPs)', [('Autor', '#e3f2fd'), ('Qualidade', '#fff3e0'), ('Direção', '#e8f5e9')], [
        ('n1', 'inicio', 'Necessidade de criar ou revisar um documento', 0, 0, 'r0'),
        ('n2', 'processo', 'Elaborar o documento', 1, 0, 'r0'),
        ('n3', 'processo', 'Revisar conteúdo e formato', 2, 0, 'r1'),
        ('n4', 'decisao', 'Conforme?', 3, 0, 'r1'),
        ('n5', 'processo', 'Ajustar o documento', 3, 0, 'r0'),
        ('n6', 'processo', 'Aprovar e assinar', 4, 0, 'r2'),
        ('n7', 'processo', 'Distribuir e treinar a equipe', 5, 0, 'r1'),
        ('n8', 'fim', 'Publicar a versão vigente e arquivar a anterior', 6, 0, 'r1')],
        [('n1', 'n2', ''), ('n2', 'n3', ''), ('n3', 'n4', ''), ('n4', 'n6', 'Sim'), ('n4', 'n5', 'Não'), ('n5', 'n3', ''), ('n6', 'n7', ''), ('n7', 'n8', '')]),
})
MODELOS = [(k, v[0]) for k, v in _MODELOS.items()]

# grupo de cada modelo na galeria e uma frase de apresentação
INFO = {
    'agendamento': ('Atendimento', 'Do pedido do paciente à marcação, com autorização do convênio.'),
    'atendimento': ('Atendimento', 'Chegada, identificação, preparo, dose e imagens no dia do exame.'),
    'laudo': ('Atendimento', 'Do processamento à entrega do laudo ao paciente.'),
    'compras': ('Apoio', 'Cotação, fornecedor qualificado, pedido e conferência no recebimento.'),
    'recebimento_radiofarmaco': ('Radiofarmácia e radioproteção', 'Conferência e registro de volumes radioativos recebidos.'),
    'preparo_radiofarmaco': ('Radiofarmácia e radioproteção', 'Eluição, controle de qualidade, fracionamento e rotulagem.'),
    'administracao_dose': ('Radiofarmácia e radioproteção', 'Identificação, triagem, dupla checagem e registro da dose.'),
    'aquisicao_imagem': ('Atendimento', 'Posicionamento, aquisição, repetição e envio ao laudo.'),
    'derramamento': ('Radiofarmácia e radioproteção', 'Resposta a derramamento: conter, descontaminar, monitorar e registrar.'),
    'rejeitos': ('Radiofarmácia e radioproteção', 'Segregação, decaimento, medição e liberação de rejeitos.'),
    'intercorrencia': ('Segurança do paciente', 'Conduta diante de reação adversa, com registro e análise.'),
    'terapia_iodo': ('Radiofarmácia e radioproteção', 'Fluxo simplificado da terapia com radionuclídeo.'),
    'controle_equipamentos': ('Apoio', 'Teste de constância, bloqueio, manutenção e liberação do equipamento.'),
    'faturamento_convenio': ('Apoio', 'Conferência, fatura, nota fiscal, glosa e recebimento.'),
    'treinamento': ('Apoio', 'Planejamento, execução e eficácia dos treinamentos.'),
    'reclamacao': ('Segurança do paciente', 'Registro, resposta e tratamento da causa.'),
    'controle_documentos': ('Apoio', 'Elaboração, revisão, aprovação e distribuição dos POPs.'),
}


def galeria():
    """Modelos de fluxograma agrupados para a galeria: [(grupo, [{chave, nome, frase, etapas, raias}])]."""
    grupos = {}
    for chave, v in _MODELOS.items():
        grupo, frase = INFO.get(chave, ('Outros', ''))
        grupos.setdefault(grupo, []).append({'chave': chave, 'nome': v[0], 'frase': frase, 'etapas': len(v[2]), 'raias': len(v[1])})
    ordem = ['Atendimento', 'Radiofarmácia e radioproteção', 'Segurança do paciente', 'Apoio', 'Outros']
    return [(g, grupos[g]) for g in ordem if g in grupos]
LARGURA, ALTURA, PASSO_X, RAIA_Y = 170, 64, 220, 150


def fluxo(chave):
    """Desenho do modelo no formato do editor (nós, ligações e raias)."""
    if chave not in _MODELOS:
        return {'nos': [], 'ligacoes': [], 'raias': [], 'modo_cor': 'tipo'}
    _nome, raias, nos, ligs = _MODELOS[chave]
    saida_nos = []
    for nid, forma, texto, col, lin, raia in nos:
        forma = 'inicio' if forma == 'fim' else forma
        saida_nos.append({'id': nid, 'forma': forma, 'texto': texto, 'x': 40 + col * PASSO_X, 'y': int(raia[1:]) * RAIA_Y + (RAIA_Y - ALTURA) // 2,
                          'l': LARGURA, 'a': ALTURA, 'cor': '', 'raia': raia, 'responsavel': '', 'status': 'a_implantar', 'obs': ''})
    return {'nos': saida_nos, 'ligacoes': [{'de': a, 'para': b, 'rotulo': r, 'cor': ''} for a, b, r in ligs],
            'raias': [{'id': 'r%d' % i, 'nome': n, 'cor': c} for i, (n, c) in enumerate(raias)], 'modo_cor': 'tipo'}


# ------------------------------------------------------------------ biblioteca do robô do PDCA
# Para cada tipo de problema: causas prováveis por categoria do Ishikawa (6M), a cadeia de 5 Porquês sugerida e as ações (5W2H).
BIBLIOTECA = {
    'faltas': {
        'causas': {'Método': ['Confirmação do agendamento não é feita ou é feita tarde', 'Orientação de preparo pouco clara'],
                   'Mão de obra': ['Equipe sem roteiro de confirmação por telefone/WhatsApp'],
                   'Meio ambiente': ['Dificuldade de transporte do paciente', 'Horários pouco convenientes'],
                   'Medição': ['Motivo da falta não é registrado']},
        'porques': ['Pacientes faltam ao exame marcado.', 'Não foram lembrados ou não entenderam o preparo.',
                    'A confirmação não é feita de forma sistemática.', 'Não existe rotina com responsável e prazo para confirmar.',
                    'O processo de agendamento não prevê a etapa de confirmação.'],
        'acoes': [('Confirmar todos os agendamentos 48 h antes', 'Reduzir faltas', 'Recepção', 'Recepção',
                   'Ligação ou mensagem com o preparo e pedido de confirmação; registrar no sistema.'),
                  ('Registrar o motivo de cada falta', 'Conhecer a causa', 'Qualidade', 'Recepção',
                   'Classificar as faltas no Pareto (motivo) toda semana.'),
                  ('Manter lista de espera ativa para encaixe', 'Aproveitar vagas', 'Agenda', 'Recepção',
                   'Usar a lista de espera da agenda para ocupar horários de quem desmarcar.')],
    },
    'laudo': {
        'causas': {'Método': ['Fila de laudos sem priorização por data'], 'Mão de obra': ['Escala de laudistas insuficiente'],
                   'Máquina': ['Lentidão ou parada da estação de processamento'], 'Medição': ['Prazo não é acompanhado diariamente']},
        'porques': ['Laudos saem depois de 24 h.', 'Exames ficam parados na etapa de laudo.', 'Não há acompanhamento diário da fila.',
                    'Não existe responsável por cobrar o prazo.', 'O processo de laudo não tem indicador de prazo acompanhado.'],
        'acoes': [('Revisar a fila no Mapa de laudos duas vezes ao dia', 'Cumprir 24 h', 'Mapa de laudos', 'Coordenação técnica',
                   'Priorizar os mais antigos e sinalizar atrasos.'),
                  ('Ajustar a escala de laudo nos dias de maior volume', 'Equilibrar demanda', 'Médicos', 'Direção técnica',
                   'Comparar volume por dia com a disponibilidade de laudistas.')],
    },
    'cadastro': {
        'causas': {'Método': ['Campos obrigatórios não conferidos no atendimento'], 'Mão de obra': ['Treinamento da recepção desatualizado'],
                   'Medição': ['Completude do cadastro não é acompanhada']},
        'porques': ['Exames com cadastro incompleto.', 'Campos ficam em branco no atendimento.', 'A conferência não é feita.',
                    'Não há checklist de identificação.', 'O protocolo de identificação não está padronizado.'],
        'acoes': [('Checklist de identificação (nome completo e data de nascimento)', 'Segurança do paciente', 'Recepção', 'Recepção',
                   'Conferir os dois identificadores antes de cada etapa.'),
                  ('Treinar a equipe no protocolo de identificação', 'Padronizar', 'Recepção', 'Qualidade', 'Treinamento curto com registro de presença.')],
    },
    'atividade': {
        'causas': {'Material': ['Atividade do radiofármaco diferente da esperada no fracionamento'], 'Medição': ['Curiômetro sem verificação diária'],
                   'Método': ['Registro da atividade feito depois, de memória']},
        'porques': ['Atividade administrada difere da prescrita.', 'A dose medida não confere com a prescrição.',
                    'A medição não é verificada antes da administração.', 'Falta conferência dupla.', 'O procedimento não exige dupla checagem.'],
        'acoes': [('Dupla checagem da atividade antes de administrar', 'Segurança e radioproteção', 'Sala de manipulação', 'Supervisor de radioproteção',
                   'Conferir prescrição x medição e registrar na hora.'),
                  ('Verificação diária do curiômetro', 'Confiabilidade da medida', 'Laboratório', 'Supervisor de radioproteção',
                   'Teste de constância diário com registro.')],
    },
    'glosa': {
        'causas': {'Método': ['Guias e autorizações incompletas no faturamento'], 'Medição': ['Glosas não são analisadas por motivo'],
                   'Mão de obra': ['Conferência das guias concentrada em uma pessoa']},
        'porques': ['O convênio paga menos que o faturado.', 'Itens são glosados.', 'As guias saem com pendências.',
                    'Não há conferência antes do envio.', 'O processo de faturamento não tem checklist por convênio.'],
        'acoes': [('Checklist de conferência das guias por convênio', 'Reduzir glosa', 'Faturamento', 'Faturamento',
                   'Conferir autorização, assinaturas e códigos antes de enviar.'),
                  ('Recorrer das glosas indevidas e registrar o motivo', 'Recuperar receita', 'Faturamento', 'Faturamento',
                   'Planilha de recursos com prazo e resultado.')],
    },
    'financeiro': {
        'causas': {'Método': ['Contas sem conferência semanal de vencimento'], 'Medição': ['Fluxo de caixa sem acompanhamento']},
        'porques': ['Contas vencem sem pagamento.', 'O vencimento não foi visto a tempo.', 'Não há rotina semanal de conferência.',
                    'Não há responsável definido.', 'O processo de contas a pagar não tem calendário.'],
        'acoes': [('Conferência semanal das contas a vencer', 'Evitar juros', 'Financeiro', 'Financeiro', 'Revisar Contas a pagar toda segunda-feira.')],
    },
    'vencimentos': {
        'causas': {'Método': ['Vencimentos não acompanhados com antecedência'], 'Material': ['Blindagens paradas sem destino']},
        'porques': ['Itens vencidos sem providência.', 'O vencimento não gerou ação.', 'Os avisos não foram tratados.',
                    'Não há responsável pelos vencimentos.', 'Não existe rotina mensal de conferência.'],
        'acoes': [('Rotina mensal de vencimentos (documentos, licenças e blindagens)', 'Manter conformidade', 'Administração', 'Gerência',
                   'Conferir o que vence em 60 dias e abrir as providências.')],
    },
    'chamados': {
        'causas': {'Mão de obra': ['Gerência sem disponibilidade para responder'], 'Método': ['Pedidos de ajuda sem prazo de resposta']},
        'porques': ['Pedidos de ajuda demoram para ser atendidos.', 'Ninguém vê o pedido a tempo.', 'Não há responsável por turno.',
                    'O atendimento depende de uma pessoa.', 'Não foi definido um prazo de resposta.'],
        'acoes': [('Definir responsável por turno para os pedidos de ajuda', 'Responder rápido', 'Gerência', 'Gerência',
                   'Escala simples com substituto.')],
    },
    'ocorrencias': {
        'causas': {'Método': ['Procedimento não seguido ou desatualizado'], 'Mão de obra': ['Falta de treinamento'],
                   'Máquina': ['Falha de equipamento']},
        'porques': ['Ocorrências graves registradas.', 'Uma etapa do processo falhou.', 'A barreira de segurança não funcionou.',
                    'A barreira não estava definida ou não foi seguida.', 'O processo não tem análise de risco atualizada.'],
        'acoes': [('Analisar cada ocorrência grave em até 72 h', 'Evitar repetição', 'Qualidade', 'Qualidade',
                   'Ishikawa e 5 Porquês com a equipe envolvida.'),
                  ('Atualizar a matriz de risco do processo', 'Prevenir', 'Qualidade', 'Qualidade', 'Revisar probabilidade e impacto.')],
    },
    'satisfacao': {
        'causas': {'Método': ['Tempo de espera longo', 'Comunicação falha sobre preparo e resultado'], 'Meio ambiente': ['Conforto da sala de espera']},
        'porques': ['Satisfação abaixo da meta.', 'Pacientes reclamam da experiência.', 'Expectativas não são alinhadas.',
                    'Não há rotina de comunicação.', 'O processo de atendimento não mede a experiência.'],
        'acoes': [('Informar o tempo estimado de espera na chegada', 'Melhorar a experiência', 'Recepção', 'Recepção', 'Aviso verbal e cartaz.'),
                  ('Ler os comentários da pesquisa toda semana', 'Agir rápido', 'Qualidade', 'Qualidade', 'Tratar cada reclamação como ocorrência.')],
    },
    'fornecedores': {
        'causas': {'Método': ['Avaliação de fornecedores sem calendário'], 'Material': ['Fornecedor com entregas não conformes']},
        'porques': ['Fornecedores sem avaliação em dia.', 'As reavaliações não foram feitas.', 'Não há calendário de avaliação.',
                    'Não há responsável.', 'O processo de compras não exige fornecedor qualificado.'],
        'acoes': [('Avaliar todos os fornecedores ativos e definir a reavaliação', 'Atender a ONA', 'Qualidade', 'Compras',
                   'Usar a Avaliação de fornecedores com os critérios definidos.')],
    },
    'retrabalho': {
        'causas': {'Método': ['Protocolo de aquisição não padronizado'], 'Máquina': ['Movimento ou falha na aquisição'],
                   'Mão de obra': ['Orientação ao paciente insuficiente']},
        'porques': ['Exames repetidos ou laudos retificados.', 'A primeira aquisição ou laudo não ficou adequado.',
                    'Uma etapa não foi conferida.', 'Não há checklist da etapa.', 'O processo não tem ponto de controle.'],
        'acoes': [('Checklist de qualidade da imagem antes de liberar o paciente', 'Evitar repetição', 'Sala de exame', 'Técnico',
                   'Conferir posicionamento e contagem.')],
    },
}
