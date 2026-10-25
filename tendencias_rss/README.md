# Top10 de Política — Google Trends Em alta

O alerta `politica_google_trends_rss` mantém o ID por compatibilidade, mas a fonte de produção é agora a página pública Google Trends Em alta, Brasil, categoria Política14, últimas24h. O RSS geral tem somente dez entradas e não fornece cobertura suficiente de política nem os detalhamentos dos grupos; não é fallback.

Usa dados públicos renderizados na página (`AF_initDataCallback`, ds:0), sem autenticação, SerpAPI ou BigQuery para a coleta. A estrutura é validada: mudança de formato, falha HTTP ou ausência de tópicos políticos gera erro explícito, nunca resumo substituído pelo RSS reduzido. Endpoint público não documentado como API estável; precisa monitoramento de compatibilidade.

Seleciona os dez grupos políticos com maior estimativa, desempate por início mais recente e título. Inclui tendências ativas e encerradas na janela24h, como a página. Categoria e todos os termos de cada grupo são fornecidos pelo próprio Google: não cria agrupamentos por mera semelhança de palavras. Publica uma única imagem com dez cartões, cada um com até cinco termos de exemplo distintos após normalização, preservando a escrita da fonte. Indica a quantidade de outras variantes, sem listá-las no grupo. A versão em texto é o mesmo resumo conciso da imagem. A estimativa é do grupo; não se atribui o volume do grupo a cada variante e não se somam valores. Consultas podem conter alegações; não são afirmações do alerta nem comprovam veracidade, apoio ou voto.

Comparação entre coletas de até48h no namespace `politica_trending_v3`: mostra mudança de posição e faixa estimada anterior do mesmo tópico. Reutiliza a observação da fonte completa v2 como base inicial quando disponível, sem comparar com o RSS reduzido. Não inventa percentuais próprios nem confunde queda de posição com queda de buscas. Grupos ausentes não são interpretados como queda. Novo termo agrupado muda o conteúdo e pode gerar mensagem.

Agenda compartilhada do catálogo: cron horário07 e apósETL. Sem workflow adicional. Estado compartilhado preservado, deduplicação por ranking/estimativas/termos. Registra páginas confirmadas para retomar envio parcial. Discord confirmado espelha no bridge WhatsApp existente; confirmação de entrega é recibo separado no SQLite. Falha entre confirmação e persistência ainda pode duplicar. `--dry-run` não envia nem muda estado; `--test` identifica teste e não muda estado. Credenciais WhatsApp separadas de BigQuery. Coletas SerpAPI seguem pausadas.

Imagem usa `presentation=politics` no worker existente. Reação♿ na imagem solicita o snapshot conciso no privado do próprio participante, com a mesma autenticação e deduplicação por relatório/pessoa dos resumos estaduais. Não altera regras de origem/destino nem permite destinatário privado no Pub/Sub.

## Resumo e interpretação pelo Vertex AI

No modo live, depois da deduplicação, chama `tendencias_bq.analise_ia.analyze(kind="politica")`. Reutiliza a integração Vertex AI REST do projetoGCP configurado no módulo compartilhado, modelo Gemini3.1Flash-Lite, WIF/credencial `WHATSAPP_GOOGLE_APPLICATION_CREDENTIALS` separada do BigQuery e habilitação `TRENDS_AI_ENABLED=true` já passada pelo workflow. Não adiciona novas chaves nem secrets.

Envia somente Top10, até5exemplos por grupo, faixa estimada e posição/faixa anterior do mesmo título. Prompt específico distingue estimativa do grupo e mudança de posição, não infere opinião/voto nem confirma alegações, e proíbe reagrupar. Resposta JSON precisa de evidências válidas, dois textos até450caracteres e clusters vazio. Observado e Interpretação entram na legenda e no mesmo texto canônico arquivado para resposta privada.

Cache por fingerprint atual/anterior, tipo e modelo; reserva anterior à chamada usa o MESMO orçamento globalestimadoUS$3, teto/input/output e encerramento já definidos na integração existente. Falha/timeout também fica em cache sem retry; alerta mantém os dados e imagem sem síntese. Ranking inalterado é suprimido antes da chamada. Dry-run/test não chamam Vertex nem gastam cota. Testes usam mocks; nenhuma geração real ou produção foi acionada nesta implementação.
