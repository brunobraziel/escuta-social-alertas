# Como criar um alerta

Este tutorial usa **calendário de pagamentos do Bolsa Família** como exemplo. Ele não está instalado nem ativo no catálogo: os trechos abaixo servem para criar um alerta novo. Execute os comandos a partir da raiz do repositório.

## 1. Defina o comportamento

Antes do código, escolha o tema, fontes, gatilho, janela de publicação, limite de mensagens e o que identifica uma ocorrência única. Neste exemplo: G1 RSS, últimas 48 horas, até três notícias por execução, tema Bolsa Família + termos de calendário/pagamento/NIS, deduplicação por alerta e URL.

O alerta avisa que saiu uma notícia relacionada ao tema. Não confirma sozinho que o calendário mudou. RSS não garante cobertura completa. Novas fontes precisam de endpoint válido, hosts permitidos e avaliação das condições de acesso.

## 2. Crie a estrutura

```text
servicos/
├── __init__.py
├── README.md
├── bolsa_familia.py                 Executor deste alerta
└── g1/
    ├── __init__.py
    ├── README.md
    └── calendario_pagamentos.py     Fonte e filtro deste site/tema
```

```sh
mkdir -p servicos/g1
touch servicos/__init__.py servicos/g1/__init__.py
```

Se a pasta de escopo já existe, acrescente um módulo específico sem substituir seu executor atual. Não copie outro escopo inteiro com filtros e listas de sites que não serão usados.

## 3. Configure fonte e filtro

Conteúdo de `servicos/g1/calendario_pagamentos.py`:

```python
from core.alerta import normalize
from core.fontes import G1_FEED as FEED_URL, G1_HOSTS as ALLOWED_HOSTS


def matches(title, description):
    text = normalize(title + " " + description)
    return "bolsa familia" in text and any(
        term in text for term in ("calendario", "pagamento", "nis")
    )
```

O predicado recebe título e descrição e retorna um booleano. Este filtro simples é um ponto inicial: refine correspondências por palavras e contexto se houver ruído. As configurações dos primeiros alertas expõem apenas feed/hosts; novos alertas podem manter o filtro no arquivo do site como neste exemplo.

## 4. Implemente o executor

Conteúdo de `servicos/bolsa_familia.py`:

```python
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from core.alerta import fetch_feed, identifier, send_discord
from servicos.g1.calendario_pagamentos import (
    FEED_URL, ALLOWED_HOSTS, matches,
)

ALERT_ID = "bolsa_familia_calendario"


def run(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", default="state.json")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args(argv)

    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not args.dry_run and not webhook:
        parser.error("Configure DISCORD_WEBHOOK_URL ou use --dry-run")

    if args.test:
        articles = [{
            "title": "Exemplo fictício: calendário do Bolsa Família",
            "description": "Teste de integração; não é uma notícia real.",
            "url": "https://g1.globo.com/",
            "published": datetime.now(timezone.utc).isoformat(),
        }]
    else:
        articles = fetch_feed(
            FEED_URL, ALLOWED_HOSTS, hours=48, predicate=matches,
        )

    state_path = Path(args.state)
    state = (
        json.loads(state_path.read_text())
        if state_path.exists() else {"sent": []}
    )
    delivered = 0
    for article in articles:
        key = identifier(ALERT_ID + ":" + article["url"])
        if not args.test and key in state["sent"]:
            continue
        alert = {
            **article,
            "alert_title": "Bolsa Família — calendário e pagamentos",
            "footer": "Notícia temática; consulte a fonte para orientações.",
        }
        if args.dry_run:
            print(json.dumps(alert, ensure_ascii=False))
        else:
            send_discord(webhook, alert, "G1", test=args.test)
            if not args.test:
                state["sent"].append(key)
                temporary = state_path.with_suffix(".tmp")
                temporary.write_text(json.dumps(state))
                temporary.replace(state_path)
        delivered += 1
        if delivered >= 3:
            break


if __name__ == "__main__":
    run()
```

O runner genérico importa esse módulo e chama `run(argv)`; não chama um arquivo diretamente pelo caminho. Importar o módulo não deve coletar dados nem enviar mensagens.

O runner converte `--mode dry-run` em `--dry-run`, `--mode test` em `--test` e `--mode live` em ausência dessas flags. Sempre passa `--state CAMINHO`. Por isso, o executor precisa aceitar esses argumentos mesmo se executado diretamente.

O estado é compartilhado: leia o arquivo existente, preserve entradas dos outros alertas e acrescente somente entregas confirmadas. Prefixe novas chaves com o ID do alerta para que dois temas possam avisar sobre a mesma URL. As chaves antigas dos alertas existentes devem permanecer intactas.

Não capture falhas de coleta como lista vazia: zero correspondências é normal; falha de acesso ou envio precisa resultar em exceção ou saída diferente de zero. O runner registra qual alerta falhou e continua com os seguintes.

## 5. Registre no catálogo

Acrescente este objeto à lista `alertas` de `alertas.json`, sem remover os existentes:

```json
{
  "id": "bolsa_familia_calendario",
  "modulo": "servicos.bolsa_familia",
  "ativo": true,
  "descricao": "Notícias sobre calendário e pagamentos do Bolsa Família"
}
```

| Campo | Uso |
| --- | --- |
| `id` | Nome único usado em `--alert`; não pode ser `all` |
| `modulo` | Caminho Python importável, com pontos, sem `.py` ou barras |
| `ativo` | Booleano JSON `true`/`false`; somente ativos podem ser executados |
| `descricao` | Explicação mostrada por `python main.py --list` |

Para validar antes de entrar no agendamento, mantenha as alterações locais até terminar o `dry-run`. Ao publicar um registro com `ativo: true` na branch padrão, ele entra automaticamente na próxima execução agendada. `ativo: false` também bloqueia execução manual pelo runner; para validar assim, use a interface direta do módulo.

## 6. Documente e teste

Em `servicos/README.md`, descreva o ID, executor, comandos, gatilho, janela, limites, teste e deduplicação. Em `servicos/g1/README.md`, explique o arquivo de fonte/filtro e como o executor o importa.

Adicione `tests/test_servicos.py` para conferir pelo menos:

- notícia relevante aceita e notícia de outro tema rejeitada;
- envio confirmado não repetido na próxima execução;
- erro de envio sem registrar a notícia como entregue;
- `dry-run` e `test` preservando o estado existente;
- nenhum envio quando a coleta retorna vazia ou todas as ocorrências já estão no histórico.

Use mocks/fixtures nos testes; não use o Discord real na suíte.

```sh
python -m unittest discover -s tests -v
python main.py --list
python main.py --alert bolsa_familia_calendario --mode dry-run
```

O `dry-run` consulta a fonte real, mas não envia nem grava estado. O exemplo de teste do tutorial usa mensagem fictícia; alertas que usam dados reais no teste precisam documentar esse comportamento e o que acontece quando não encontram notícia.

## 7. Publique e valide no GitHub

Faça commit e push dos arquivos Python, READMEs, testes e `alertas.json`. Não inclua `state.json`, `.env` ou credenciais.

Em Actions → **Executar alertas** → Run workflow:

1. Use `mode: dry-run`, `alert: bolsa_familia_calendario` para validar coleta.
2. Use `mode: test`, com o mesmo ID, para enviar um exemplo identificado ao canal.
3. Use `mode: live`, com o mesmo ID, para enviar novidades reais.

O repository secret `DISCORD_WEBHOOK_URL` existente é reutilizado. O teste ignora deduplicação e não marca a ocorrência como entregue; portanto, repeti-lo envia outra mensagem de teste.

Nenhum YAML novo é necessário. O workflow único chama todos os alertas ativos uma vez por hora. Não há frequência individual por alerta nesta versão: mudar `schedule.cron` altera a frequência de todos. Não rode uma cópia antiga de workflow para o mesmo alerta.

## Adicionar somente um site a um alerta existente

Isso não exige um novo registro no catálogo. Crie a configuração em `{escopo}/{site}/`, documente-a, inclua-a na seleção de fontes do executor e valide suas correspondências. Criar a pasta não a habilita automaticamente. Não registre cada arquivo de configuração como um alerta: o catálogo aponta para executores com `run(argv=None)`.

Para uma regra independente, com seu próprio teste e deduplicação, crie outro executor e outro ID. Ambos podem compartilhar a mesma pasta de escopo e os componentes de `core/`.

## Gatilho e silêncio na operação normal

O [README principal](../README.md#fluxo-de-trigger-do-job-e-das-notificações) descreve o fluxo completo. O workflow consulta fontes uma vez por hora; cada executor só chama o Discord depois de encontrar uma ocorrência elegível e inédita. Não envie mensagens de “sem resultados” ou “execução concluída” ao canal. Registre essas informações apenas nos logs. O exemplo deste tutorial segue essa regra.
