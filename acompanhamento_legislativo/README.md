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
