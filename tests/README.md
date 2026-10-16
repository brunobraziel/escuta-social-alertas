# Testes

Execute da raiz: `python -m unittest discover -s tests -v`.

- `test_alerta.py`: filtro legislativo, feed/datas/hosts, deduplicação, falha de entrega e webhooks em canais de texto/fórum.
- `test_pesquisas.py`: extração da tabela, exclusão de rejeição/aprovação, dados incompletos e separação das bases de votos.
- `test_runner.py`: continuidade após falha de um alerta, catálogo e proteção contra testes em massa.

Usam fixtures e mocks, sem chamadas à rede ou envio real. A coleta real é validada separadamente com `python main.py --mode dry-run`.

## Testar um alerta novo

Crie `test_{tema}.py` com testes do filtro/parser e do comportamento de entrega/estado. Importe o executor do escopo e forneça argumentos com `run(["--dry-run", "--state", caminho])`, usando um diretório temporário e mocks de rede/Discord. Confirme que falhas não registram entrega e que simulação/teste não modificam o histórico dos outros alertas. O [tutorial](../docs/README.md) mostra a interface esperada e a validação manual pelo workflow.

A suíte também verifica que feeds vazios não chamam o Discord e não alteram o estado, além de impedir novo envio da mesma pesquisa mesmo com outra URL. O teste legislativo de deduplicação confirma que rodar novamente com a mesma notícia não gera segunda mensagem.
