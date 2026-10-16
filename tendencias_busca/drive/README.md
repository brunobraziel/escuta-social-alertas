# Termos do documento de Escuta Social

`termos.py` valida e lê uma lista revisada por `ESCUTA_SOCIAL_TERMS_JSON`. Não lê o documento via rede: o acesso de um conector externo não é herdado pelo GitHub Actions.

A lista privada não foi exportada ao GitHub. Isso depende de autorização explícita do responsável. Não grave o conteúdo do documento neste repositório público. O formato, as limitações da versão revisada e os passos pendentes estão no [README do escopo](../README.md).

O executor chama `load_terms()` em cada execução. Se o ambiente estiver sem a lista, falha sem enviar. Não existe uma lista padrão embutida nem substituição silenciosa por termos de exemplo.
