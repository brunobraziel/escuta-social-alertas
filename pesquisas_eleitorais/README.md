# Pesquisas eleitorais

Alerta do catálogo: `pesquisa_presidente`. O `main.py` importa `pesquisas_eleitorais.run` e chama `run(argv)`.

## Arquivos e chamadas

- `run.py`: consulta RSS de G1 e CNN dos últimos sete dias; escolhe a notícia elegível de publicação mais recente e envia um alerta.
- `parser.py`: identifica notícias de intenção de voto, valida a tabela e monta a mensagem. Não usa aprovação, rejeição ou percentuais de recortes.
- `{site}/presidente.py`: configuração de feed e hosts para cada portal. O executor importa esses módulos; não são scripts independentes.

```sh
python main.py --alert pesquisa_presidente --mode dry-run
python main.py --alert pesquisa_presidente --mode test
```

Também é possível executar o escopo diretamente com `python -m pesquisas_eleitorais.run --dry-run`.

## Escopo e limites

Presidente, Brasil, segundo turno, votos totais. Exige tabela explícita com candidatos/partidos, brancos/nulos, indecisos e soma próxima de 100%; instituto, período de coleta, amostra, margem de erro, confiança e registro BR informado pela matéria. O formato inicial suportado é a tabela textual do G1; resumos da CNN podem não trazer dados suficientes e são ignorados.

Os nomes aparecem em ordem alfabética. Não há previsão, comparação ou interpretação de vantagem. A notícia mais recente encontrada não é necessariamente a última pesquisa nacional nem a de coleta mais recente. Republicações e a janela dos feeds limitam a cobertura. O registro é transcrito da notícia, sem verificação automática no PesqEle: https://www.tse.jus.br/eleicoes/pesquisas-eleitorais .

O teste envia uma pesquisa real com `[TESTE]` e não grava deduplicação; falha se não encontrar dados suficientes. Em produção, o identificador combina registro, cargo, abrangência, turno e base de votos, evitando repetir a mesma pesquisa em URLs diferentes.
