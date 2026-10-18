# Alerta BQ: assuntos em alta por estado

ID `gtrends_em_alta_brasil`; módulo `tendencias_bq.em_alta_brasil`; tabela `comite-tecnologia.analise_redes.gtrends_em_alta_brasil`.

O alerta roda a cada hora pelo workflow genérico e consulta a ingestão mais recente com `hora_ingestao` dentro da última hora. A consulta valida que os registros compartilham um único `ingestao_id`; uma ingestão ambígua causa falha em vez de combinar lotes. Se ainda não houver ingestão na última hora, não envia mensagem.

Os resultados são agrupados por UF. A mensagem exibe até quatro assuntos por estado, ordenados por `aumento` decrescente e depois `volume` decrescente, com rótulo, volume, aumento e indicadores `ativa`/`candidato` quando verdadeiros. As UFs são distribuídas em duas seções do embed do Discord para respeitar o limite de tamanho. O alerta não transforma o volume em contagem de pessoas nem em intenção de voto.

O alerta está temporariamente em paralelo com `tendencias_por_estado`, para permitir validar os dados e a apresentação. Envia no máximo um alerta por `hora_ingestao` confirmada; um lote novo gera outro alerta mesmo quando o texto é igual ao lote anterior. Após a validação, o fluxo antigo pode ser removido.

## Credenciais e execução

No GitHub, configure o repository secret `BQ_SERVICE_ACCOUNT_JSON` com o JSON da conta de serviço. Ela precisa de permissão para criar jobs de consulta no projeto `comite-tecnologia` e ler a tabela no dataset `analise_redes` (por exemplo, BigQuery Job User no projeto e BigQuery Data Viewer no dataset). O segredo só é passado ao processo do alerta; não é escrito no repositório nem no estado.

Localmente, use Application Default Credentials, por exemplo `GOOGLE_APPLICATION_CREDENTIALS` apontando para uma credencial local. O alerta não imprime credenciais.

```sh
python -m tendencias_bq.em_alta_brasil --dry-run
python main.py --alert gtrends_em_alta_brasil --mode dry-run
python main.py --alert gtrends_em_alta_brasil --mode test
```

`dry-run` consulta o BigQuery, imprime JSON e não envia nem altera estado. `test` envia uma mensagem marcada como teste e não registra a entrega de produção. No modo normal, o alerta salva o hash do conteúdo somente após confirmação do Discord e não repete conteúdo idêntico.

## Desenvolvimento

`bigquery.py` mantém o acesso em leitura e permite somente o ID de tabela previsto. Os testes usam mocks, sem chamadas ao BigQuery ou ao Discord.
