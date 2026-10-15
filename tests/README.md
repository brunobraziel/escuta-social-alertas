# Testes

Execute da raiz: `python -m unittest discover -s tests -v`.

- `test_alerta.py`: filtro legislativo, feed/datas/hosts, deduplicação, falha de entrega e webhooks em canais de texto/fórum.
- `test_pesquisas.py`: extração da tabela, exclusão de rejeição/aprovação, dados incompletos e separação das bases de votos.
- `test_runner.py`: continuidade após falha de um alerta, catálogo e proteção contra testes em massa.

Usam fixtures e mocks, sem chamadas à rede ou envio real. A coleta real é validada separadamente com `python main.py --mode dry-run`.
