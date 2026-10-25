# Política nas buscas — RSS Google Trends

Alerta `politica_google_trends_rss`, integrado ao catálogo e workflow compartilhados. Consulta o RSS público Brasil a cada execução do catálogo (cron horário07 e após ETL); não usa SerpAPI, BigQuery ou IA. A pausa das coletas SerpAPI permanece independente.

Publica até dez grupos políticos disponíveis, sem completar com assuntos inventados. Filtra títulos e contexto das manchetes, excluindo loterias mesmo quando a notícia menciona eleição. Janela máxima48h; descarta datas futuras além de10min. O recorte automático não garante cobertura completa de política.

Agrupamento conservador: mesmas palavras significativas normalizadas, ignorando ordem, acentos e conectivos. Não agrupa apenas por pessoa ou manchete e não faz agrupamento semântico amplo. Todos os termos selecionados e suas estimativas aparecem explicitamente, com paginação sem corte. Ranking pela maior estimativa individual do grupo (sem somas), desempate por recência e título. Não representa assuntos mais falados em redes nem opinião pública.

Compara a observação atual com a coleta anterior válida de até48h, armazenada no namespace `politica_rss_v1` do estado compartilhado. Setas mostram posição, não variação de volume; apresenta faixa anterior por termo idêntico. Não inventa percentuais nem queda quando termo sai do RSS. Primeira coleta informa ausência de base. Ranking/estimativas inalterados não geram mensagem, mas atualizam a observação. Confirma páginas individualmente para retomar envio parcial sem repetir páginas confirmadas. Uma falha após envio antes da persistência ainda pode repetir mensagem.

`--dry-run` só mostra dados; `--test` envia teste identificado sem mudar estado; modo normal é live. Nenhum modo chama SerpAPI. Falha da fonte é erro, RSS válido sem elegíveis não envia. Discord confirmado é espelhado pelo bridge WhatsApp existente; recibos de transporte devem ser validados separadamente. Segredos e credenciais não são armazenados no estado.
