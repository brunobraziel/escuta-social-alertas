# Mensagem original de 16/10/2026

- `2026-10-16_mensagem_original.json`: snapshot fiel do post do Discord, com os dois embeds originais e metadados de origem.
- `2026-10-16_mensagem_original.md`: versão legível do mesmo conteúdo para revisar o layout.

Esse teste antigo tinha **dois destaques por UF e nenhum índice numérico exibido**. Não há como recuperar os demais termos ou valores a partir desse texto; `general` e `monitored` são `null` para não inventar dados. O formato novo das próximas coletas terá quatro destaques mensuráveis e índices relativos 0–100.

Preview local, sem rede, API, credenciais ou envio:

```sh
python -m tendencias_busca.run --cached --dry-run --cache-file dados/exemplos/2026-10-16_mensagem_original.json
```

Para experimentar apresentações, trabalhe sobre esse JSON/Markdown. Não use `test`, `probe` ou `dry-run` sem `--cached`: eles podem consultar fontes. O índice de Trends não é número absoluto de buscas.
