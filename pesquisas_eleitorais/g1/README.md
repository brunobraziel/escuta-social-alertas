# G1 — pesquisas_eleitorais

`presidente.py` define `FEED_URL` e `ALLOWED_HOSTS`, importados de `core/fontes.py`. O `run.py` do escopo importa a configuração e chama o coletor RSS compartilhado. Não há execução ao importar este arquivo.

Execute da raiz: `python main.py --alert pesquisa_presidente --mode dry-run`. Veja `../README.md` para os critérios e limites do alerta. O portal só gera mensagem quando há conteúdo suficiente para o filtro/parser do escopo.
