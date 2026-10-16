# Acompanhamento legislativo

Alerta do catálogo: `escala_6x1`. Chamado pelo orquestrador `main.py`, que importa `acompanhamento_legislativo.run` e chama `run(argv)`.

## Arquivos e chamadas

- `run.py`: percorre G1 e CNN, coleta matérias das últimas 48 horas, evita URLs já enviadas e entrega no máximo três novidades por execução. Usa `core.alerta` para coleta, filtro temático e Discord.
- `g1/escala_6x1.py` e `cnn/escala_6x1.py`: fornecem `FEED_URL` e `ALLOWED_HOSTS` para o executor.
- `uol/escala_6x1.py`: configuração reservada, fora da lista de fontes ativas.

```sh
python main.py --alert escala_6x1 --mode dry-run
python main.py --alert escala_6x1 --mode test
```

Para diagnosticar uma fonte isolada, a interface específica também funciona:

```sh
python -m acompanhamento_legislativo.run --site g1 --dry-run
```

Filtro: exige variante de escala 6x1 no título e termos de promulgação, vigência, transição ou publicação no título/descrição. Uma correspondência é uma notícia temática, não confirmação de mudança legal. Termos genéricos podem causar ruído; RSS pode deixar notícias de fora.

Teste: mensagem fictícia marcada como `[TESTE]`, sem mexer no histórico. Execução normal: hashes das URLs no estado compartilhado, gravados após confirmação do Discord.

## Estender este escopo

Para outro tema legislativo, crie um executor separado (por exemplo, `acompanhamento_legislativo/nova_proposta.py`) com `run(argv=None)` e registre `acompanhamento_legislativo.nova_proposta` sob um novo ID em `alertas.json`. Passe um filtro próprio ao coletor: o filtro padrão é específico da escala 6x1. Não substitua `run.py` para adicionar uma proposta independente.

Para adicionar somente um portal à escala 6x1, crie sua configuração e inclua o site na lista `SITES` do executor existente. Não há descoberta automática de subpastas. Documente e teste o conector antes de ativar. Veja o [tutorial completo](../docs/README.md). Nenhum workflow adicional é necessário.

## Agendamento e novidades

O workflow único consulta este alerta uma vez por hora, no minuto 07. Sem notícia elegível nova, o executor não chama o Discord. Consultas vazias e ocorrências já enviadas ficam apenas nos logs; o modo manual `test` é a exceção solicitada para validar mensagens. Veja o [fluxo do job](../README.md#fluxo-de-trigger-do-job-e-das-notificações).
