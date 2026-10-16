# Escuta Social Alertas

Scripts Python para coletar notícias via RSS e enviar alertas ao Discord. Python 3.12, somente biblioteca padrão. Um workflow executa os alertas ativos do catálogo a cada 30 minutos.

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

Existe somente um workflow: **Executar alertas**. Roda nos minutos 7 e 37 de cada hora, executando todos os alertas ativos em `alertas.json`. A frequência fica apenas em `.github/workflows/monitorar.yml`, no campo `schedule.cron`. Para mudar para 15 minutos, por exemplo, use `7,22,37,52 * * * *`.

1. Cadastre um **Repository secret** `DISCORD_WEBHOOK_URL` em Settings → Secrets and variables → Actions.
2. Abra Actions → Executar alertas → Run workflow.
3. Escolha `mode` e informe `alert`: `all`, `escala_6x1` ou `pesquisa_presidente`.
4. Para `test`, informe um ID específico; `all` é recusado para evitar mensagens de teste em massa.

Sem o secret, agendamentos e execuções `live` passam a simulação com aviso. O envio cria um tópico por alerta em canais de fórum; em canais de texto, envia diretamente. Parâmetros de tópico existentes na URL são preservados.

A execução é sequencial e mantém o estado compartilhado na branch `alert-state`. A migração preserva os hashes já existentes; não apague essa branch. Entregas confirmadas são salvas mesmo se outro alerta falhar. O token precisa de `contents: write` para atualizar a branch. Não existe garantia de entrega exatamente uma vez: falhas entre envio e gravação podem causar repetição.

Os agendamentos do GitHub podem atrasar e ser desativados após 60 dias sem atividade em repositórios públicos. Os logs são públicos e podem conter metadados públicos das matérias; não adicione documentos internos ou credenciais.

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

Não crie um YAML por alerta. Frequência, ambiente e secret são compartilhados pelo workflow único.

## Cobertura

Fontes ativas: G1 e CNN via RSS; sem coleta adicional do HTML das matérias. RSS tem janela limitada e não garante cobertura integral. UOL permanece reservado e desativado porque o endpoint consultado não forneceu XML válido. BBC, Metrópoles e Brasil Paralelo não estão implementados. Reavalie as condições de uso de cada fonte antes de ampliar a coleta; esta implementação não pressupõe licença irrestrita de reprodução.

Detalhes dos filtros e limitações: [legislativo](acompanhamento_legislativo/README.md) e [pesquisas](pesquisas_eleitorais/README.md).
