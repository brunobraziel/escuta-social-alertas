# Poder360 / PoderData

`presidente.py` configura a editoria pública para descoberta em `web.discover`, chamada por `pesquisas_eleitorais.run`. Não é um executor separado. Até seis matérias por consulta, com publicação nos últimos sete dias. O HTML complementa os dados que o RSS da editoria não fornece. Sem contorno de bloqueios.

Resultados são validados pelo parser compartilhado. Se não for possível validar percentuais, uma notícia com registro BR e escopo presidencial de segundo turno pode gerar aviso com link, sem números. Consulte o [README do escopo](../README.md).
