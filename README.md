# Escuta Social Alertas

Scripts Python para coletar notícias via RSS e enviar alertas ao Discord. Python 3.12, somente biblioteca padrão. Um workflow executa os alertas ativos do catálogo uma vez por hora.

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
2. Abra Actions → Executar alertas → Run workflow.
3. Escolha `mode` e informe `alert`: `all`, `escala_6x1` ou `pesquisa_presidente`.
4. Para `test`, informe um ID específico; `all` é recusado para evitar mensagens de teste em massa.

Sem o secret, agendamentos e execuções `live` passam a simulação com aviso. O envio cria um tópico por alerta em canais de fórum; em canais de texto, envia diretamente. Parâmetros de tópico existentes na URL são preservados.

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

Siga o [tutorial completo, com exemplo de Bolsa Família](docs/README.md). Ele mostra quais arquivos criar, como escrever o executor, registrar o catálogo e validar no GitHub.

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

Fontes de notícias: G1 e CNN via RSS. O escopo de pesquisas também lê HTML público de matérias candidatas e descobre notícias na editoria PoderData do Poder360. RSS tem janela limitada e não garante cobertura integral. UOL permanece reservado e desativado porque o endpoint consultado não forneceu XML válido. BBC, Metrópoles e Brasil Paralelo não estão implementados. Reavalie as condições de uso de cada fonte antes de ampliar a coleta; esta implementação não pressupõe licença irrestrita de reprodução.

Detalhes dos filtros e limitações: [legislativo](acompanhamento_legislativo/README.md) e [pesquisas](pesquisas_eleitorais/README.md).

## Resumo estadual de buscas

O alerta `tendencias_por_estado` envia duas mensagens: assuntos em alta por UF e interesse regional de **todos os 20 termos**, em nove clusters independentes da guia Google Trends do Drive. Os termos e clusters ficam na variável editável `ESCUTA_SOCIAL_TERMS_JSON`, com `mode: clusters_daily`. Veja [configuração e métricas](tendencias_busca/README.md).

A agenda é **uma vez por dia, às 00h07 de Fortaleza**, até 24/10/2026. Os alertas de pesquisas eleitorais e escala 6x1 continuam **de hora em hora**, com envio só quando houver novidade elegível. O workflow genérico continua único e horário.

Tendências consome até **9 consultas SerpApi por dia**: 72 consultas de 17 a 24/10, além das já usadas e dos testes. O job não usa IA nem tokens de IA. Cache e trava por cluster evitam repetir chamadas pagas no mesmo dia após falhas ou reexecuções. A mensagem normal não é repetida no mesmo dia e não é enviada se seu conteúdo não mudou.

## Testar a apresentação sem novas consultas

A branch `alert-state` guarda `dados/tendencias/ultima_coleta.json` e `dados/tendencias/ultima_mensagem.md`. Use `replay` para ler os dados sem rede, ou `replay-test` para reenviar as mensagens salvas como teste. `test` pode fazer até nove consultas na primeira coleta do dia; testes posteriores reutilizam os resultados preservados.

Os valores são relativos ao termo/cluster e não representam contagem absoluta de buscas. Não há ranking único dos 20 termos. A [amostra original](dados/exemplos/README.md) permanece como registro histórico.
