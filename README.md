# Escuta Social Alertas

Scripts Python para coletar notícias via RSS e BigQuery e enviar alertas ao Discord. Python 3.12, com `google-cloud-bigquery` para o alerta BQ. Um workflow executa os alertas ativos do catálogo uma vez por hora.

## Organização

```text
.github/workflows/monitorar.yml     Agendamento e execução genérica
alertas.json                       Catálogo de alertas ativos
main.py                            Entrada única / seleção de alerta e modo
acompanhamento_legislativo/run.py   Execução do alerta escala_6x1
acompanhamento_legislativo/{site}/  Configuração de cada fonte do escopo
pesquisas_eleitorais/run.py         Execução do alerta pesquisa_presidente
pesquisas_eleitorais/parser.py      Extração e validação das pesquisas
pesquisas_eleitorais/{site}/        Configuração de cada fonte do escopo
core/                              RSS, fontes e envio compartilhados
tendencias_busca/                   Resumo estadual em duas seções (SerpApi)
tendencias_bq/                      Alertas diários com dados do BigQuery
tests/                             Testes sem rede e sem mensagens reais
```

Cada pasta possui README com responsabilidades e comandos. Os arquivos `__init__.py` apenas identificam pacotes Python; não executam coleta.

## Executar localmente

Execute todos os comandos a partir da raiz do repositório:

```sh
python main.py --list
python main.py --mode dry-run
python main.py --alert escala_6x1 --mode dry-run
python main.py --alert pesquisa_presidente --mode dry-run
python -m tendencias_bq.monitoramento_temas --dry-run  # consulta BigQuery
python -m unittest discover -s tests -v
```

| Modo | Efeito |
| --- | --- |
| `dry-run` (padrão local) | Consulta fontes e imprime resultados; não envia nem modifica estado |
| `live` | Envia novidades ao Discord e registra entregas confirmadas |
| `test` | Envia mensagem identificada como teste, sem modificar estado; exige um único alerta |

Para `live` e `test`, forneça `DISCORD_WEBHOOK_URL` no ambiente. Nunca coloque seu valor no código, nos comandos versionados ou nos logs.

```sh
python main.py --alert escala_6x1 --mode test
python main.py --alert pesquisa_presidente --mode test
python main.py --mode live
```

O teste legislativo usa exemplo fictício; o teste de pesquisa busca uma notícia real elegível e falha se não houver nenhuma. Ausência de notícias na execução normal é válida. Falha em um alerta não impede os seguintes, mas deixa a execução geral com erro.

## GitHub Actions

Existe somente um workflow: **Executar alertas**. Roda no minuto 7 de cada hora, selecionando os alertas ativos em `alertas.json` conforme a agenda individual. A frequência fica apenas em `.github/workflows/monitorar.yml`, no campo `schedule.cron`. Para mudar para 15 minutos, por exemplo, use `7,22,37,52 * * * *`.

1. Cadastre um **Repository secret** `DISCORD_WEBHOOK_URL` em Settings → Secrets and variables → Actions.
2. Cadastre `BQ_SERVICE_ACCOUNT_JSON` como repository secret, contendo a credencial JSON de uma conta de serviço com acesso de leitura ao dataset `analise_redes` e permissão para executar jobs BigQuery.
3. Abra Actions → Executar alertas → Run workflow.
4. Escolha `mode` e informe `alert`: `all`, `escala_6x1`, `pesquisa_presidente`, `gtrends_monitoramento_temas` ou `tendencias_por_estado`.
5. Para `test`, informe um ID específico; `all` é recusado para evitar mensagens de teste em massa.

Sem `DISCORD_WEBHOOK_URL`, agendamentos e execuções `live` passam a simulação com aviso. O alerta BQ também requer `BQ_SERVICE_ACCOUNT_JSON`; sem ele, esse alerta registra falha e os outros continuam. O envio cria um tópico por alerta em canais de fórum; em canais de texto, envia diretamente. Parâmetros de tópico existentes na URL são preservados.

A execução é sequencial e mantém o estado compartilhado na branch `alert-state`. A migração preserva os hashes já existentes; não apague essa branch. Entregas confirmadas são salvas mesmo se outro alerta falhar. O token precisa de `contents: write` para atualizar a branch. Não existe garantia de entrega exatamente uma vez: falhas entre envio e gravação podem causar repetição.

Os agendamentos do GitHub podem atrasar e ser desativados após 60 dias sem atividade em repositórios públicos. Os logs são públicos e podem conter metadados públicos das matérias; não adicione documentos internos ou credenciais.

## Fluxo de trigger do job e das notificações

```text
schedule (uma vez por hora) ou Run workflow (manual)
  → job monitorar: checkout + Python + testes
  → restaura histórico da branch alert-state
  → main.py seleciona os alertas ativos e aplica agenda quando --scheduled
  → cada executor consulta os feeds e filtra conteúdo elegível
  → compara a ocorrência com o histórico
      → sem novidades: termina sem chamar o Discord
      → novidade: envia mensagem e registra entrega confirmada
  → persiste o estado compartilhado, somente com mudanças
```

O gatilho automático é `schedule`, com cron `7 * * * *`: executa no minuto **07 de toda hora** (por exemplo, 10h07, 11h07 e 12h07 em Fortaleza). GitHub pode atrasar o início. O gatilho manual é `workflow_dispatch`, pelo botão Run workflow. Push/commit não disparam este workflow; publicar código ou alterar a branch de estado não envia mensagens por si só. O agendamento lê a versão da branch padrão.

O job precisa consultar os feeds para descobrir se há novidades. **Executar a consulta não significa notificar**: o Discord só é chamado em `live` quando há conteúdo elegível ainda não entregue. Sem correspondências, pesquisa com dados insuficientes ou ocorrência já enviada, o canal fica em silêncio. Nenhuma mensagem de “sem notícias”, resumo vazio ou confirmação periódica é enviada.

| Alerta | O que conta como novidade |
| --- | --- |
| `escala_6x1` | URL elegível ainda não enviada |
| `pesquisa_presidente` | Pesquisa elegível selecionada cujo registro/cargo/abrangência/turno/base de votos ainda não foi enviado |

Uma nova URL sobre a mesma pesquisa não gera outro alerta de pesquisa. Alterar o texto de uma notícia mantendo a mesma URL não gera novo alerta legislativo. Na primeira execução sem histórico, conteúdos elegíveis dentro da janela de busca podem ser enviados mesmo tendo sido publicados antes da ativação.

A regra de silêncio vale para a operação normal. `test` é uma solicitação manual de mensagem de teste, identificada como `[TESTE]`, e ignora deduplicação; `dry-run` nunca envia. Erros ficam nos logs/status do GitHub Actions e não geram mensagens no Discord por este código. Preferências pessoais de e-mail do GitHub são independentes do alerta do canal.

O estado só recebe uma ocorrência depois da confirmação do Discord. Preservar `alert-state` evita reenvios. Se um executor falhar, os demais continuam; o workflow termina com erro e salva as entregas já confirmadas, desde que a restauração do estado tenha funcionado.

## Criar novos alertas

Siga o [tutorial completo, com exemplo de Bolsa Família](docs/README.md) ou o [plano/checklist para novos alertas](docs/PLANO_NOVO_ALERTA.md). Eles mostram como estruturar o executor, registrá-lo no catálogo, testar e ativar no GitHub.

O fluxo de chamada é:

```text
monitorar.yml → main.py → alertas.json → módulo.run(argv)
                                      → configuração por site
                                      → core.alerta → Discord
```

1. Crie um executor importável, por exemplo `servicos/bolsa_familia.py`, e configurações como `servicos/g1/calendario_pagamentos.py`.
2. No executor, implemente `run(argv=None)` com `--state`, `--dry-run` e `--test`.
3. Registre um ID único e o caminho do módulo em `alertas.json`, preservando os alertas existentes.
4. Adicione testes, execute em `dry-run` e documente filtros, fontes, limites e deduplicação.
5. Publique na branch padrão. O agendamento único passa a executar o novo alerta se `ativo` for `true`.

Um arquivo `.py` novo, sozinho, **não é descoberto automaticamente**. O `main.py` só executa módulos registrados no catálogo. Também não importa automaticamente todos os sites de uma pasta: o executor de cada alerta escolhe suas configurações de fonte.

Um escopo pode ter vários alertas. Nesse caso, use módulos diferentes, como `servicos.bolsa_familia` e `servicos.tarifa_zero`, cada um com seu próprio ID. O nome `run.py` é uma convenção dos primeiros exemplos, não uma exigência do runner; a função `run(argv=None)` é o contrato.

Para desativar, altere `ativo` para `false`. Alertas desativados também não podem ser selecionados manualmente pelo runner. Para voltar a executar, reative no catálogo. Não apague os identificadores do estado.

Não crie um YAML por alerta. O workflow base é compartilhado; campos opcionais `agenda.intervalo_horas` e `agenda.fim_exclusivo` permitem limitar um alerta nas execuções agendadas. O intervalo deve dividir 24 (1, 2, 3, 4, 6, 8, 12 ou 24 horas), alinhado ao horário de Fortaleza. Chamadas manuais não aplicam o intervalo, mas o executor de tendências também impõe seu encerramento.

## Cobertura

Fontes de notícias: G1 e CNN via RSS. RSS tem janela limitada e não garante cobertura integral. Reavalie as condições de uso de cada fonte antes de ampliar a coleta; esta implementação não pressupõe licença irrestrita de reprodução.

Detalhes dos filtros e limitações: [legislativo](acompanhamento_legislativo/README.md), [pesquisas](pesquisas_eleitorais/README.md) e [alertas BQ](tendencias_bq/README.md).

## Resumo de consultas relacionadas

O alerta ativo `gtrends_monitoramento_temas` consulta o lote mais recente do Trends Monitor no BigQuery e resume as consultas por tema, busca-base e área. A coleta atual é nacional. Lê o lote inteiro pelo identificador, mesmo com horários individuais por linha, e não repete um lote já enviado. Veja [configuração](tendencias_bq/README.md).

O alerta antigo que consultava SerpAPI diretamente permanece desativado. Os alertas ativos são verificados de hora em hora e após ingestões concluídas; isso não garante mensagem quando não houver novidade elegível.

## Testar a apresentação sem novas consultas

A branch `alert-state` guarda `dados/tendencias/ultima_coleta.json` e `dados/tendencias/ultima_mensagem.md`. Use `replay` para ler os dados sem rede, ou `replay-test` para reenviar as mensagens salvas como teste. `test` pode fazer até nove consultas na primeira coleta do dia; testes posteriores reutilizam os resultados preservados.

Os valores são relativos ao termo/cluster e não representam contagem absoluta de buscas. Não há ranking único dos 20 termos. A [amostra original](dados/exemplos/README.md) permanece como registro histórico.

## Alertas após conclusão do ETL

Os workflows ativos Boralula e Trends Monitor de escuta-social-etl solicitam
`workflow_dispatch` de `monitorar.yml` em `main`, com `mode=live` e `alert=all`,
somente após sucesso da ingestão. O campo opcional `etl_run_url` identifica a
execução de origem no título e nos logs. A execução usa o mesmo histórico
`alert-state` e a mesma fila das verificações horárias, preservando a deduplicação.
Não cria mensagens de status de ETL no WhatsApp.

No repositório ETL, `ALERTAS_DISPATCH_TOKEN` deve conter um fine-grained PAT
com acesso apenas a este repositório e permissão `Actions: write`. Não usar
a credencial local do GitHub CLI nem um token com acesso a todos os repositórios.

### Síntese de IA e consultas agrupadas

Os dois alertas de BigQuery podem usar Gemini 3.1 Flash-Lite via Vertex AI no projeto
`escuta-whatsapp-261018`, endpoint global. `TRENDS_AI_ENABLED=true` habilita a camada;
a credencial é a WIF de WhatsApp/IA, separada do BigQuery. A IA não consulta SerpAPI,
nem busca notícias. O ranking estadual mostra até cinco termos válidos por UF,
ordenados pelo índice relativo; a IA não altera os índices, percentuais ou ranking.

Cada mensagem acrescenta uma observação e uma interpretação de até 450 caracteres
cada, com 2 a 3 frases: movimentos do índice estadual e leitura dos padrões de busca.
O tom textual só é descrito quando explícito nas palavras; não representa sentimento
da população, apoio ou intenção de voto. Sem evidência, o tom é indeterminado.
Consultas nacionais recebem a lista e os valores da fonte; sem lote anterior, a IA
não afirma quedas ou evolução entre coletas. Consultas similares podem ser agrupadas somente dentro da mesma
busca-base, macrotema e geografia, com intenção e similaridade compatíveis. Os
termos originais continuam visíveis na linha `Agrupadas:`. Não se somam índices ou
posições; perguntas sobre criação, aumento, consulta e cadastro permanecem distintas.
O WhatsApp mantém as variantes completas dos quatro grupos selecionados por base;
o Discord usa uma versão compacta. Nenhuma tabela ou linha do BigQuery é modificada.

O cache persistido em `alert-state/state.json` identifica lote atual, lote anterior,
tipo de alerta e versão do analisador; reenvios horários reutilizam a mesma análise.
A aplicação reserva US$0,02 ANTES de cada chamada (incluindo timeouts/falhas) e bloqueia
novas chamadas ao chegar a US$3. Limites: 40.000 bytes por requisição, 4.096 tokens de
saída, sem ferramentas, sem grounding e sem retries de geração. São limites conservadores
pelas tarifas globais padrão de US$0,25/M entrada e US$1,50/M saída, verificadas em
21/10/2026: https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing
Esse teto da aplicação não substitui o faturamento ou orçamento global do projeto.
As chamadas encerram em 25/10/2026 às 00h de Fortaleza. Falha, resposta inválida ou
limite atingido preservam o alerta com dados originais e agrupamento básico de grafia.
`dry-run` não chama IA nem envia mensagens.

O alerta `escala_6x1` é enviado somente ao Discord, inclusive no modo de teste;
os demais alertas mantêm seu encaminhamento ao WhatsApp.
