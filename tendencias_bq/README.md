# Alertas do Trends Monitor

O alerta ativo `gtrends_monitoramento_temas` usa `tendencias_bq.monitoramento_temas` e lê `comite-tecnologia.analise_redes.gtrends_monitoramento_temas`. O leitor seleciona o último lote nas últimas 24 horas pelo `ingestao_id` e recupera todas as linhas, mesmo com timestamps individuais. A deduplicação impede repetir o lote já enviado.

A mensagem do WhatsApp agrupa consultas por macrotema, busca-base e área geográfica; mostra até quatro consultas distintas e prioriza a lista em alta pela posição. A coleta atual de consultas relacionadas é nacional (BR), portanto não são atribuídos estados. O Discord apresenta a primeira consulta de cada grupo; o WhatsApp mantém até quatro. Não se tratam índices relativos da lista top como volume absoluto nem como crescimento.

Mantém o secret `BQ_SERVICE_ACCOUNT_JSON`, envio espelhado para WhatsApp após confirmação do Discord, execução manual e execução após ETL. Não usa buscas SerpAPI adicionais. O módulo legado por estado continua disponível no código, mas não integra o catálogo ativo.
