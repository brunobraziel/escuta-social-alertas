# Alertas do Trends Monitor

O alerta ativo `gtrends_monitoramento_temas` usa `tendencias_bq.monitoramento_temas` e lê `comite-tecnologia.analise_redes.gtrends_monitoramento_temas`. O leitor seleciona o último lote nas últimas 24 horas pelo `ingestao_id` e recupera todas as linhas, mesmo com timestamps individuais. A deduplicação impede repetir o lote já enviado.

A mensagem do WhatsApp agrupa consultas por macrotema, busca-base e área geográfica; mostra até quatro consultas distintas e prioriza a lista em alta pela posição. A coleta atual de consultas relacionadas é nacional (BR), portanto não são atribuídos estados. O Discord apresenta a primeira consulta de cada grupo; o WhatsApp mantém até quatro. Não se tratam índices relativos da lista top como volume absoluto nem como crescimento.

Mantém o secret `BQ_SERVICE_ACCOUNT_JSON`, envio espelhado para WhatsApp após confirmação do Discord, execução manual e execução após ETL. Não usa buscas SerpAPI adicionais. O módulo legado por estado continua disponível no código, mas não integra o catálogo ativo.

## Visão por estado, a cada hora

O alerta `monitoramento_estados_horario` usa `gtrends_monitoramento_cidades`, somente `job=estados` e `resolucao=REGION`. Seleciona o lote estadual completo mais recente nas últimas 24 horas, exclui a referência e índices nulos/zero, elimina termos repetidos por UF e mostra até cinco termos por interesse relativo à mesma referência. Não mistura linhas CITY nem o lote nacional de consultas relacionadas. Os 27 estados são mostrados; ausência de índice válido é informada. O ranking é restrito aos termos monitorados, não uma lista geral de tendências espontâneas.

O envio ocorre uma única vez por lote REGION, com o horário da coleta explícito. Cron, execuções manuais e gatilhos ETL não reenviam o mesmo lote, nem em horas diferentes. Um lote novo pode ser enviado na mesma hora do anterior. O workflow existente no minuto 07 executa o alerta, sujeito aos atrasos do GitHub Actions. Encerra os envios agendados ao fim de 24/10 em Fortaleza. Não altera a frequência da coleta nem consome novas buscas SerpAPI.

### Variação por tópico

Cada tópico do resumo estadual mostra ↑ (+x,x%), ↓ (-x,x%) ou → (0,0%) comparando o índice relativo à referência com o lote estadual anterior (até 48 horas). O cálculo é `(índice atual / índice anterior - 1) × 100`, por UF, termo normalizado, grupo e período da busca. As duas horas de coleta aparecem na mensagem. Valores são arredondados a uma casa decimal.

Sem linha anterior comparável, mostra “sem base”; com índice anterior zero, não calcula porcentagem. Não compara com municípios, grupos diferentes ou janelas de busca diferentes. A lista continua sendo os cinco termos com maior índice atual, não os que mais cresceram. Como a referência também pode variar, a porcentagem não mede crescimento da quantidade absoluta de buscas. O mesmo lote não é reenviado na hora seguinte.
