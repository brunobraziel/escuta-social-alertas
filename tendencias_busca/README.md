# Tendências de busca por estado

ID: `tendencias_por_estado`. Executor: `tendencias_busca.run`, com o mesmo contrato `run(argv=None)` dos demais alertas. **Ativo no catálogo**: a chave `SERPAPI_API_KEY` foi cadastrada e o diagnóstico SerpApi foi concluído com sucesso em 16/10/2026. O endpoint direto do Google retornou HTTP 429 e não é usado como fallback.

## O que o post deve mostrar

Uma única mensagem do Discord, com duas seções (dois embeds no mesmo POST), cobrindo os 26 estados e o Distrito Federal:

1. **Assuntos em alta:** até dois destaques da lista pública de tendências por UF nas últimas 24 horas. Preserva a ordem do RSS; não representa o ranking absoluto de todas as buscas.
2. **Escuta Social:** consulta todos os termos revisados do documento, mesmo fora das tendências, e mostra até dois destaques de maior interesse relativo por UF. Não filtra somente termos que aparecem no RSS.

Se houver estado sem dados suficientes para comparar todos os termos, isso é informado em vez de inventar uma ordem. Se a comparação falhar inteiramente (429, CAPTCHA/formato inesperado etc.), não é enviado resumo parcial apresentado como completo. Ausência de interesse mensurável não significa ausência de buscas. Os dados não medem apoio, opinião pública, intenção de voto ou volume absoluto.

## Arquivos e chamadas

```text
main.py → alertas.json → tendencias_busca.run.run(argv)
                           → drive/termos.py: lista privada revisada
                           → google/coleta.py: RSS + Explore regional
                           → resumo.py: duas seções e fingerprint
                           → core.alerta.send_discord: um POST/tópico
```

- `run.py`: valida configuração, consulta comparações, reúne feeds e envia somente quando o conteúdo exibido muda.
- `estados.py`: códigos e nomes das 27 UFs.
- `drive/termos.py`: lê `ESCUTA_SOCIAL_TERMS_JSON`; não acessa o Drive automaticamente e não contém nomes privados no código.
- `google/coleta.py`: RSS, referência comum e validação dos lotes; contém também o coletor direto legado, que retornou 429.
- `google/serpapi.py`: coletor de comparação usado pelo executor e pelo diagnóstico; no máximo dois lotes/consultas por coleta.
- `janela.py`: impede qualquer coleta ou diagnóstico a partir de 25/10/2026 00h00 em Fortaleza.
- `resumo.py`: mantém separadas as duas medidas, limita o tamanho da mensagem e calcula novidade sem timestamps ou variações pequenas de pontuação.

## Lista de termos e privacidade

A lista revisada com nove termos foi configurada, com autorização do responsável, no repository secret `ESCUTA_SOCIAL_TERMS_JSON`. Ela não está em arquivos versionados. Não grave os dados no código ou logs; o workflow público recebe a lista pelo ambiente.

A implementação espera este formato em `ESCUTA_SOCIAL_TERMS_JSON` (exemplo fictício):

```json
{
  "source_url": "https://docs.google.com/document/d/ID_DO_DOCUMENTO/edit",
  "source_modified": "2026-10-16T00:00:00Z",
  "terms": ["Tema A", "Tema B"]
}
```

O snapshot autorizado está armazenado como repository secret; o workflow já passa o secret ao executor. A lista deve ser revisada novamente quando o documento mudar. O post informa a versão usada. O acesso ao Drive por um conector externo **não concede acesso ao GitHub Actions**; sincronização automática do documento exigiria uma integração autenticada adicional, ainda não implementada.

## Comparabilidade

A referência comum é escolhida entre os cinco termos do primeiro lote, priorizando presença mensurável nas UFs e mediana do índice. A seleção não usa consulta extra. Os valores de cada termo são divididos pelo valor dessa referência na mesma UF e depois reescalados em relação ao maior entre os monitorados naquela UF. Isso evita concatenar índices normalizados independentes sem referência. O método produz uma aproximação sensível à amostragem/arredondamento; não é uma contagem de pessoas ou buscas.

Se faltarem termos ou a referência não puder ser medida, a UF fica como `dados insuficientes`. Valores zero são tratados como abaixo da resolução, não ausência de buscas. Os destaques só são exibidos quando o segundo colocado supera o limite conservador de incerteza dos termos arredondados a zero em todos os lotes. Todos os termos são consultados. As comparações usam a mesma janela de 24 horas, tipo de pesquisa e abrangência Brasil. O corpo mostra apenas os destaques; os demais termos foram consultados, não omitidos da coleta. Os números do índice não são exibidos no post.

## SerpApi: conta e limites

**SerpApi (`serpapi.com`) e SearchApi (`searchapi.io`) são empresas diferentes.** O plano usado nesta implementação é o Free da [SerpApi](https://serpapi.com/pricing), que na consulta de 16/10/2026 anuncia **250 buscas por mês**. A [SearchApi](https://www.searchapi.io/) anuncia **100 requisições de teste**; sua chave não funciona neste conector. Confirme o saldo no painel da conta antes de ativar.

Cadastre a chave da SerpApi como **Repository secret `SERPAPI_API_KEY`**, sem colocá-la no chat ou em arquivos. As consultas enviam os termos pesquisados ao provedor; a resposta bruta, chave e termos não são registrados pelo diagnóstico. A SerpApi é independente do Google. Referência: https://serpapi.com/google-trends-api .

A lista atual de nove termos exige dois lotes, com um termo comum. Cada lote retorna recortes estaduais do Brasil; não se faz uma consulta paga por estado. O código bloqueia listas que exijam mais de dois lotes, evitando ampliar consumo sem rever a cota. Não há retentativas automáticas. O consumo real deve ser confirmado no painel: consultas com erro/cache podem ter tratamento próprio do provedor.

## Agenda diária e encerramento

O workflow único continua de hora em hora. Em execuções `schedule`, chama `main.py --scheduled`, que aplica `agenda` do catálogo. Para este alerta:

```json
{
  "intervalo_horas": 24,
  "fim_exclusivo": "2026-10-25T00:00:00-03:00"
}
```

Horários previstos em Fortaleza: **00h07, uma vez por dia**. Até **24/10/2026 às 23h59**; a última execução prevista é 24/10 às 00h07. Não há promessa de envio às 23h59: esse é o encerramento. O Google Trends pode retornar dados insuficientes; o GitHub pode atrasar ou perder uma execução.

Conta conservadora para nove dias completos de 16 a 24/10: 9 coletas × 2 consultas = **18 consultas**, deixando 232 de uma cota intacta de 250 para diagnóstico e testes. Começar depois reduz as execuções restantes. Chamadas manuais consomem cota adicional e não seguem a restrição de horário diário; até simulações usam a API. Não use a chave em outros projetos sem recalcular o saldo.

O encerramento também é aplicado dentro do executor e do diagnóstico: depois dele não há consultas, mesmo em chamadas manuais. Os outros alertas continuam de hora em hora, sem data final nesta configuração.

## Validação e operação

1. Lista revisada do Drive: já configurada como secret autorizado.
2. `SERPAPI_API_KEY` foi cadastrada pelo responsável e validada.
3. Rode o diagnóstico `probe` pelo workflow: só mostra contagens/códigos de erro, sem termos ou resultados individuais. Cada diagnóstico pode consumir até duas consultas.
4. O alerta foi ativado após diagnóstico válido. Para suspender, altere `ativo` para `false`, preservando histórico.

Para validação local, com os secrets no ambiente:

```sh
python -m tendencias_busca.diagnostico
python -m tendencias_busca.run --dry-run --states MG,SP
```

O `dry-run` imprime o resumo: não rode com a lista privada em logs públicos sem autorização para divulgar os resultados. `--test` envia um resumo real identificado como teste, não um exemplo fictício; pode ser solicitado manualmente após configuração da chave. A alternativa oficial do Google continua em acesso antecipado: https://developers.google.com/search/apis/trends .

## Silêncio e estado

O estado compartilhado preserva `sent` e armazena o hash `latest_trends` e a data `trends_attempt_date`, sem resultados privados. Não grava consultas, nomes, índices ou o documento privado na branch de estado. A cada execução, compara com o último resumo entregue; se a lista/ordem dos destaques não mudou, fica em silêncio. Mudança apenas de horário, pontuação ou versão do documento sem mudança na lista não gera notificação.

`dry-run` imprime o conteúdo que seria enviado e não modifica o estado. **Não rode o dry-run com a lista privada em logs públicos sem autorização para divulgar os resultados.** O modo test ignora a deduplicação e não modifica o histórico. Erros ficam no status/log do job, sem mensagem ao Discord.

## Tentativa isolada sem expor resultados

Actions → Executar alertas → Run workflow: `mode: probe`, `alert: tendencias_por_estado`. Esse modo chama `diagnostico.py` mesmo com o alerta inativo, apenas para verificar a fonte. Não ativa o catálogo, não envia ao Discord, não grava estado e não imprime termos ou resultados individuais. Em 429, encerra sem retentar. A comparação exige no máximo dois lotes para a lista atual; para na primeira falha. Só após comparação válida confere RSS de MG, SP e CE.

Localmente, com o secret no ambiente: `python -m tendencias_busca.diagnostico`. Não substitua por `--dry-run` em logs públicos, pois esse último imprime o resumo.

## Limite adicional para preservar a cota

O executor em `live` registra `trends_attempt_date` antes de consultar a SerpApi. Se já houve tentativa naquele dia de Fortaleza, termina sem novas consultas, mesmo após falha. Isso evita consumo duplicado por reexecução do workflow. A tentativa é salva pelo workflow mesmo se a API falhar. Os identificadores de entregas continuam preservados; falha não marca resumo como enviado.

`probe`, `test` e `dry-run` são ações manuais que podem consumir até duas consultas extras cada; não executá-las repetidamente. O diagnóstico e o teste de ativação já foram solicitados e não fazem parte das 18 consultas estimadas de nove dias completos. O consumo efetivo deve ser acompanhado no painel do provedor.
