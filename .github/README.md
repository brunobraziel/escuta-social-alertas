# Integração GitHub

`workflows/monitorar.yml` é o único workflow ativo. Ele agenda o catálogo completo a cada 30 minutos e permite seleção manual de modo e alerta. Consulte o README em `workflows/` para os parâmetros e etapas.

Novos alertas são registrados em `alertas.json`, sem novos YAMLs. Veja o [tutorial de criação](../docs/README.md).
