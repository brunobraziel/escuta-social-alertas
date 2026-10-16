# Tendências e Escuta Social diária

ID `tendencias_por_estado`; módulo `tendencias_busca.run`; modo atual `clusters_daily` na variável do repositório `ESCUTA_SOCIAL_TERMS_JSON`.

## Agenda e consumo

O workflow genérico continua **de hora em hora**, minuto 07. Pesquisas de intenção de voto e escala 6x1 participam de todas essas execuções. Tendências tem `agenda.intervalo_horas: 24`: execução prevista **uma vez por dia, às 00h07 de Fortaleza**, até 24/10/2026, com encerramento exclusivo em 25/10 às 00h00. O GitHub pode atrasar ou perder execuções. Horário é previsão, não garantia de entrega.

São **até nove consultas SerpApi por dia**, uma por cluster, cada qual retorna recortes de todos os estados do Brasil. Os três termos isolados continuam separados; os demais respeitam os agrupamentos do documento. Não há chamada paga por UF. Cada coleta também lê 27 feeds públicos RSS para a seção geral.

De 17 a 24/10 são oito dias: **72 consultas** em uma execução diária; três execuções diárias dariam **216**, mas essa frequência não está ativada. Nove dias completos de 16 a 24/10 dariam 81 e 243, respectivamente. Consultas anteriores e testes devem ser somados ao consumo. O job não usa modelo de IA e não consome tokens de IA.

A implementação atual mantém **uma coleta paga por dia**, independentemente de alterar só a agenda do catálogo. Para aumentar frequência é necessário revisar também o cache/limite diário de `clusters.py` e o orçamento.

## Duas mensagens no Discord

1. **Assuntos em alta — geral:** até quatro assuntos por UF, na ordem do RSS público, nas últimas 24h. Não é ranking absoluto de todas as buscas.
2. **Escuta Social diária:** consulta **todos os 20 termos**, mesmo fora das tendências, em **nove clusters independentes**. Mostra a tabela por UF, com os números na ordem dos termos de cada cluster indicada na legenda. As duas seções/embeds dessa tabela pertencem à mesma segunda mensagem.

Para os clusters de termo único 1A, 2A e 2B, o número é índice geográfico de interesse relativo de 0–100 para aquele termo. Para os clusters com vários termos, é a participação relativa de cada termo entre os termos daquele cluster na UF (%). Não compare números entre clusters nem os interprete como quantidades de buscas, percentual da população, apoio ou intenção de voto. A escala não é unificada entre os clusters. A distribuição relativa é sujeita a amostragem e arredondamento.

`n/d` indica ausência de dados para a UF naquele cluster. Zero pode representar interesse abaixo da resolução e não prova ausência de buscas. Não há ranking global dos 20 termos. Os nomes completos e todos os valores ficam no JSON salvo; a mensagem usa códigos dos clusters e legenda para caber nas 27 UFs. O modo anterior `filter_trending` permanece no código como alternativa, mas não é o modo configurado.

## Configuração editável

**Settings → Secrets and variables → Actions → Variables → ESCUTA_SOCIAL_TERMS_JSON**. O workflow usa `${{ vars.ESCUTA_SOCIAL_TERMS_JSON }}` como variável de ambiente. `SERPAPI_API_KEY` e `DISCORD_WEBHOOK_URL` permanecem como repository secrets.

A variável contém `mode: clusters_daily`, `source_url`, `source_tab`, `source_modified`, `source_revision`, `terms` e `clusters`. A lista foi revisada em 16/10/2026 a partir da guia Google Trends, item 3, grupos 1–3. `terms` deve ser a concatenação dos termos dos clusters na mesma ordem, sem duplicatas. Cada cluster aceita de um a cinco termos, no máximo nove clusters por dia. Não existe sincronização automática com o Drive.

Formato ilustrativo:

```json
{
  "mode": "clusters_daily",
  "source_url": "https://docs.google.com/document/d/ID/edit",
  "source_modified": "2026-10-16",
  "terms": ["Tema A", "Tema B"],
  "clusters": [{"id": "1A", "terms": ["Tema A"]}, {"id": "1B", "terms": ["Tema B"]}]
}
```

A legenda das métricas em `clusters.py` corresponde aos IDs reais do documento; preserve esses IDs e os agrupamentos se editar a lista.

## Fluxo e segurança da cota

```text
workflow por hora → main.py --scheduled → catálogo com intervalo 24h
 → run.py → load_terms → clusters.execute
 → collect: cache diário por cluster → SerpApi → RSS
 → duas mensagens com controle de entrega independente
 → state.json e arquivos exportados na branch alert-state
```

Cada tentativa é persistida **antes** da chamada paga, e o resultado é salvo após cada retorno. Um cluster já concluído hoje é reutilizado; um cluster que falhou não é consultado novamente no mesmo dia. Se o job for reexecutado, não há repetição desses pedidos, inclusive em `test`. Após uma interrupção, clusters ainda não tentados podem ser consultados. Alterar a configuração após iniciar a coleta do dia bloqueia uma nova coleta naquele dia. Não há retentativa automática da API.

Cada mensagem normal é enviada no máximo uma vez por dia e apenas se seu conteúdo mudou. Falha na segunda não perde a confirmação da primeira; nova execução pode reenviar só a pendente, sem recolher a comparação. Testes forçam envio e não marcam a entrega de produção. `dry-run` não salva tentativas/resultados e pode consumir nove consultas extras: prefira `replay` para apresentação. Não repita testes com outro arquivo de estado, pois isso elimina o histórico que protege a cota.

O encerramento em 25/10 é aplicado antes de qualquer coleta, inclusive manual. Outros alertas continuam sem essa data final.

## Operação e arquivos

Actions → Executar alertas → `alert: tendencias_por_estado`:

- `test`: coleta ou reutiliza os nove clusters do dia e envia as duas mensagens de teste.
- `live`: usa a trava diária e o controle de novidade/entrega.
- `probe`: neste modo, informa como testar; **não faz chamadas pagas** nem envia.
- `dry-run`: consulta/reutiliza dados e imprime o resultado, sem persistir ou enviar; pode consumir cota.
- `replay`: lê o snapshot sem rede ou envio.
- `replay-test`: reenvia as duas mensagens do cache com `[TESTE] [CACHE]`, sem consultar fontes.

`clusters.py` coordena a coleta, a tabela e os envios. `google/serpapi.py` usa `GEO_MAP_0` para termo único e `GEO_MAP` para comparação de vários termos. `drive/termos.py` valida a configuração. `cache.py` exporta dados e textos. `filtrado.py`/`filtro.py` são a alternativa de filtro RSS; `resumo.py` contém o formato legado de comparação em lotes.

A branch `alert-state` mantém `state.json`, `dados/tendencias/ultima_coleta.json` e `dados/tendencias/ultima_mensagem.md`. Os resultados contêm todos os termos/valores por UF e cluster, os textos e confirmações; são públicos, conforme autorizado. Credenciais e o texto integral do documento não são gravados. O estado preserva campos desconhecidos dos outros alertas. `trends_clusters_day` guarda tentativas/resultados diários; `trends_daily_*` controla entregas. O cache permite ajustar apresentação sem repetir consultas pagas.

## Limites do escopo

A documentação do Drive também propõe DataForSEO/Google Ads, volumes municipais históricos, fallback cidade→UF, aceleração relativa a 30 dias e Brasil, e Rising Queries. Essas análises não estão implementadas. Este alerta entrega interesse regional dos clusters nas últimas 24h e assuntos em alta por UF. Não fornece contagens absolutas ou comparação com baseline histórico.

[Documentação do provedor: interesse regional de termo único](https://serpapi.com/google-trends-interest-by-region). A [amostra original](../dados/exemplos/README.md) e os modos legados de recuperação continuam preservados como histórico, sem alteração retroativa.
