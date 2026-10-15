# Componentes compartilhados

- `fontes.py`: endpoints RSS e hosts permitidos de G1 e CNN. Importado pelas configurações dos sites; não depende de um escopo específico.
- `alerta.py`: coleta e valida RSS, normaliza textos, fornece o filtro legislativo atual, calcula hashes e envia mensagens ao Discord. `fetch_feed` aceita um filtro e limite de descrição personalizados; pesquisas fornecem seu próprio filtro.

Estes arquivos são bibliotecas: não devem ser chamados como executores. Use `python main.py --alert ID --mode dry-run` na raiz. `send_discord` exige confirmação de mensagem, trata HTTP 429 e cria tópico quando o Discord informa que o destino é fórum. Não registre o valor do webhook.

O estado contém apenas `{"sent": ["hash", ...]}`. Cada executor preserva entradas existentes e grava atomicamente depois do envio confirmado. O runner genérico executa os escopos em sequência.
