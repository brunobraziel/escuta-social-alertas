# Integração GitHub

`workflows/monitorar.yml` é o único workflow ativo. Ele agenda o catálogo completo uma vez por hora e permite seleção manual de modo e alerta. Consulte o README em `workflows/` para os parâmetros e etapas.

Novos alertas são registrados em `alertas.json`, sem novos YAMLs. Veja o [tutorial de criação](../docs/README.md).

O alerta `gtrends_em_alta_brasil` usa a variável secreta `BQ_SERVICE_ACCOUNT_JSON` com credencial de serviço somente leitura para o BigQuery. Consulte [a documentação do alerta](../tendencias_bq/README.md).
