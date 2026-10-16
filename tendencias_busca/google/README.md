# Google Trends

`coleta.py` implementa `trending(uf)`, `compare_all(terms, states)` e validação/calibração regional. É importado pelo executor do escopo; não tem execução independente.

RSS estadual: `https://trends.google.com/trending/rss?geo=BR-UF`. O campo link do canal precisa confirmar a UF; um feed nacional não é aceito como estadual. São consideradas entradas publicadas nas últimas 24 horas. A ordem é a do feed.

Explore: `/trends/api/explore` e `/trends/api/widgetdata/comparedgeo`, endpoints públicos não oficiais. Sem confirmação de dados reais, o alerta permanece inativo. Falhas e HTTP 429 interrompem a coleta, sem contornar restrições. O token retornado pelo widget não é credencial persistente nem deve ser registrado nos logs.

Veja os limites, a comparação de lotes e os comandos no [README do escopo](../README.md). A fonte oficial anunciada ainda depende de aprovação para acesso antecipado.
