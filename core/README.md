# Componentes compartilhados

- `fontes.py`: endpoints RSS e hosts permitidos de G1 e CNN. Importado pelas configurações dos sites; não depende de um escopo específico.
- `alerta.py`: coleta e valida RSS, normaliza textos, fornece o filtro legislativo atual, calcula hashes e envia mensagens ao Discord. `fetch_feed` aceita um filtro e limite de descrição personalizados; pesquisas fornecem seu próprio filtro.

Estes arquivos são bibliotecas: não devem ser chamados como executores. Use `python main.py --alert ID --mode dry-run` na raiz. `send_discord` exige confirmação de mensagem, trata HTTP 429 e cria tópico quando o Discord informa que o destino é fórum. Não registre o valor do webhook.

O estado contém `{"sent": ["hash", ...]}` e pode conter hashes adicionais de outros escopos, como `latest_trends`; preserve campos desconhecidos. Cada executor preserva entradas existentes e grava atomicamente depois do envio confirmado. O runner genérico executa os escopos em sequência.

## Reutilizar em novos alertas

O [tutorial de criação](../docs/README.md) contém um executor completo. Passe seu próprio `predicate` ao `fetch_feed`: se omitir, ele usa o filtro legislativo existente.

`fetch_feed(url, allowed_hosts, hours=48, predicate=matches, description_limit=450)` retorna matérias com `title`, `description`, `url` e `published`, ordenadas por publicação decrescente. A validação de hosts se aplica às URLs de matérias retornadas; não representa licença de acesso ao feed. Datas inválidas ou fora da janela são ignoradas; falhas de rede/XML geram exceção.

`send_discord(webhook, article, site, test=False)` exige esses quatro campos e aceita `alert_title`, `message` e `footer` personalizados. Novos temas devem definir título e rodapé próprios para não herdar o texto legislativo padrão. `message` substitui o corpo padrão. `test=True` identifica a mensagem e o tópico; o executor continua responsável por não gravar o estado.

`identifier(text)` calcula SHA-256. Para novos alertas, prefira `identifier(ALERT_ID + ":" + occurrence_key)`. O segredo vem do ambiente; a função de envio não lê o catálogo ou o estado.

Resumos com duas seções podem passar `details_message` junto de `message`: são dois embeds dentro de uma única mensagem/postagem do Discord. Ambos precisam ter no máximo 2.800 caracteres; o envio recusa mensagens maiores em vez de cortar a segunda seção silenciosamente.
