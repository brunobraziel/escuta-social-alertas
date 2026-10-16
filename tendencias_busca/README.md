# Tendências por estado e Escuta Social

ID `tendencias_por_estado`; módulo `tendencias_busca.run`. Configuração atual: `mode: filter_trending`, em `ESCUTA_SOCIAL_TERMS_JSON`.

## Duas mensagens no Discord

1. **Assuntos em alta — geral:** até quatro assuntos recentes por UF, preservando a ordem do RSS público do Google Trends.
2. **Escuta Social — assuntos em alta filtrados:** até quatro assuntos por UF que contenham termos do item 3 da guia Google Trends do documento, grupos 1, 2 e 3. O filtro examina todos os assuntos coletados, antes do corte de quatro. Informa `nenhuma correspondência` quando há feed, mas nenhum assunto corresponde ao dicionário.

São dois envios separados. Cada mensagem tem seu próprio controle de novidade: se o conteúdo visível continuar igual, não é reenviada. Falha no segundo envio preserva a confirmação do primeiro. O modo `test` força ambos com identificação de teste, salva o cache e não marca entrega de produção.

O filtro ignora maiúsculas e acentos e exige limites de palavra: `SUS` corresponde a `quem criou o sus`, mas não a `Jesus`. Não usa sinônimos nem infere temas pelo sentido. Um assunto pode corresponder a vários termos e clusters. Os títulos completos e todas as correspondências ficam no JSON; o Discord abrevia títulos para caber nas 27 UFs. O feed público tem cobertura limitada e não é o ranking absoluto de todas as buscas. Ausência no feed não significa ausência de buscas.

## Configuração editável

**Settings → Secrets and variables → Actions → Variables → ESCUTA_SOCIAL_TERMS_JSON**.

O workflow passa `${{ vars.ESCUTA_SOCIAL_TERMS_JSON }}` como variável de ambiente. Credenciais do Discord e da SerpApi continuam em secrets; a chave SerpApi não é usada no modo atual. A lista foi revisada em 16/10/2026, na guia Google Trends, item 3. Não há sincronização automática com o Drive.

Formato ilustrativo, sem termos reais embutidos no código:

```json
{
  "mode": "filter_trending",
  "source_url": "https://docs.google.com/document/d/ID/edit",
  "source_tab": "ID_DA_GUIA",
  "source_modified": "2026-10-16",
  "terms": ["Tema A", "Tema B"],
  "clusters": [
    {"id": "1A", "name": "Grupo A", "terms": ["Tema A"]},
    {"id": "1B", "name": "Grupo B", "terms": ["Tema B"]}
  ]
}
```

`terms` deve ser a concatenação dos termos de `clusters`, na mesma ordem e sem duplicatas. Cada cluster aceita de um a cinco termos. A configuração atual contém **20 termos em 9 clusters**: 1A, 1B, 2A, 2B, 2C, 3A, 3B, 3C e 3D. Para mudar termos, edite a variável, preserve os clusters e atualize a versão; não precisa alterar o código. `source_modified` identifica a data da versão revisada; `source_revision` pode registrar a revisão exata lida no Drive.

## Fluxo e consumo

```text
workflow único → main.py --scheduled → alertas.json
  → tendencias_busca.run → load_terms
  → filtrado.execute → RSS de 27 UFs → filtro.filter_topics
  → filtro.reports → dois envios com deduplicação independente
  → state.json → branch alert-state + JSON/Markdown exportados
```

- `run.py`: argumentos, encerramento, seleção do modo e reprodução do cache.
- `filtrado.py`: coleta RSS, deduplicação por mensagem e persistência das confirmações.
- `filtro.py`: correspondência dos assuntos aos clusters e formatação.
- `drive/termos.py`: validação da variável, sem acesso automático ao Drive.
- `google/coleta.py`: feeds por UF; também contém comparação direta legada.
- `google/serpapi.py` e `resumo.py`: comparação regional antiga; não são chamados no modo `filter_trending`.
- `cache.py`: grava dados, textos e exporta arquivos reutilizáveis.

A agenda permanece a cada **3 horas**, até 24/10/2026 às 23h59 de Fortaleza: 00h07, 03h07, 06h07, 09h07, 12h07, 15h07, 18h07 e 21h07. O GitHub pode atrasar ou perder execuções. Após o encerramento, o executor e o diagnóstico não consultam fontes; reprodução do cache continua disponível. O workflow base segue de hora em hora para os outros alertas.

Cada coleta atual faz **27 leituras RSS e zero consultas SerpApi**, tanto em `live` quanto em `test` e `dry-run`. Não há consultas individuais por termo nem retentativa automática de coleta em caso de bloqueio. O diagnóstico `probe` lê somente MG, SP e CE. Ele não envia mensagens.

## Relação com a documentação do Drive

O documento descreve uma arquitetura mais ampla, com DataForSEO/Google Ads, volumes históricos municipais, fallback cidade→UF, aceleração em relação a 30 dias, comparação com Brasil e Rising Queries. Essas etapas **não estão implementadas** neste alerta. O escopo atual usa somente o dicionário dos grupos 1–3 para filtrar assuntos em alta por UF; não estima números de buscas, aceleração, apoio político ou intenção de voto.

Uma futura comparação de todos os termos precisaria respeitar os nove clusters independentes, inclusive os três termos isolados. Seriam nove consultas por coleta regional. Em nove dias completos, seriam 648 consultas a cada 3h ou 486 a cada 4h, acima da cota de 250 informada para esta conta. Por orientação do responsável, foi escolhido o filtro RSS. A comparação legada de nove termos em dois lotes não representa o novo dicionário.

## Testes e dados persistidos

Actions → Executar alertas → `alert: tendencias_por_estado`:

- `test`: coleta real RSS e envia as duas mensagens de teste; zero SerpApi.
- `dry-run`: coleta RSS e imprime o resultado, sem envio ou mudança de estado.
- `probe`: diagnóstico reduzido sem envio.
- `replay`: lê o cache, sem rede ou envio.
- `replay-test`: reenvia as mensagens salvas com `[TESTE] [CACHE]`, sem consultar fontes, preservando as datas originais.

A branch `alert-state` mantém `state.json`, `dados/tendencias/ultima_coleta.json` e `dados/tendencias/ultima_mensagem.md`. O JSON contém os assuntos completos, termos/IDs dos clusters correspondentes, os dois textos e confirmações. A configuração original do documento e credenciais não são incluídas. Resultados e arquivos são públicos, conforme autorizado.

`trends_rss_latest_general` e `trends_rss_latest_filtered` são os hashes dos conteúdos confirmados. Os demais campos do estado são preservados. Os snapshots antigos de comparação continuam legíveis; `recover` e `recover-discord` são ferramentas legadas de recuperação, não o fluxo atual de coleta. A [amostra original](../dados/exemplos/README.md) permanece como registro histórico, sem alteração retroativa.
