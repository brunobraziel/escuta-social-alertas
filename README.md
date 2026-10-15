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

## Adicionar ou desativar alertas

1. Crie uma pasta de escopo com `run.py`, README e subpastas por site. Reutilize `core/`.
2. Exponha `run(argv=None)`, aceitando `--state`, `--dry-run` e `--test`. Não execute ações ao importar o módulo.
3. Em `live`, leia o estado existente e acrescente apenas identificadores de entregas confirmadas; preserve as entradas dos outros alertas. Em `test` e `dry-run`, não altere o estado.
4. Registre em `alertas.json`: `id` único, `modulo` importável, `ativo` booleano e `descricao`.
5. Inclua testes e valide com `python main.py --alert seu_id --mode dry-run`.

Não é preciso criar ou editar workflows para adicionar um alerta. Para desativar um alerta, altere `ativo` para `false`; isso preserva o histórico.

## Cobertura

Fontes ativas: G1 e CNN via RSS; sem coleta adicional do HTML das matérias. RSS tem janela limitada e não garante cobertura integral. UOL permanece reservado e desativado porque o endpoint consultado não forneceu XML válido. BBC, Metrópoles e Brasil Paralelo não estão implementados. Reavalie as condições de uso de cada fonte antes de ampliar a coleta; esta implementação não pressupõe licença irrestrita de reprodução.

Detalhes dos filtros e limitações: [legislativo](acompanhamento_legislativo/README.md) e [pesquisas](pesquisas_eleitorais/README.md).
