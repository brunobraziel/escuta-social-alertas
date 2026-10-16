# CNN — pesquisas_eleitorais

`presidente.py` define `FEED_URL` e `ALLOWED_HOSTS`, importados de `core/fontes.py`. O `run.py` do escopo importa a configuração e chama o coletor RSS compartilhado. Não há execução ao importar este arquivo.

Execute da raiz: `python main.py --alert pesquisa_presidente --mode dry-run`. Veja `../README.md` para os critérios e limites do alerta. O portal só gera mensagem quando há conteúdo suficiente para o filtro/parser do escopo.

## Criar ou habilitar uma fonte

Veja o [tutorial](../../docs/README.md). Acrescentar um arquivo nesta pasta não o executa: o executor do escopo precisa importá-lo e incluí-lo entre as fontes. Para uma regra independente, crie um executor próprio no escopo e registre outro ID no catálogo; não registre este arquivo de configuração como executor.
