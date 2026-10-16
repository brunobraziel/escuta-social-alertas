# Termos do documento de Escuta Social

`termos.py` valida e lê uma lista revisada por `ESCUTA_SOCIAL_TERMS_JSON`. Não lê o documento via rede: o acesso de um conector externo não é herdado pelo GitHub Actions.

A lista revisada de 20 termos e nove clusters da guia Google Trends, item 3, grupos 1–3 foi armazenada, com autorização explícita do responsável, na variável do repositório `ESCUTA_SOCIAL_TERMS_JSON` (Settings → Secrets and variables → Actions → Variables). O valor pode ser consultado e editado nessa tela. O workflow usa `vars.ESCUTA_SOCIAL_TERMS_JSON` e a recebe pelo ambiente; ela não está em arquivos versionados. Não grave o conteúdo do documento neste repositório público. O formato, as limitações da versão revisada e os passos pendentes estão no [README do escopo](../README.md).

O executor chama `load_terms()` em cada execução. Se o ambiente estiver sem a lista, falha sem enviar. Não existe uma lista padrão embutida nem substituição silenciosa por termos de exemplo.
