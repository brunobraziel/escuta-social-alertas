# Plano e conhecimento: criar um novo alerta

Este documento é um roteiro para planejar, implementar, testar e ativar um alerta neste repositório. O tutorial com exemplo de código está em [`README.md`](README.md); consulte também o [README principal](../README.md) e o contrato dos componentes em [`core/README.md`](../core/README.md).

## 1. Entenda o modelo

O alerta é um módulo Python importável que expõe `run(argv=None)`. O runner em `main.py` lê `alertas.json`, importa o módulo registrado e passa os argumentos de execução. As fontes não são descobertas automaticamente: o próprio executor decide quais configurações de sites chamar.

```text
.github/workflows/monitorar.yml
  → main.py
    → alertas.json (ID ativo e caminho do módulo)
      → módulo.run(argv)
        → fontes / filtros / parser
        → estado compartilhado
        → core.alerta.send_discord(...)
```

Um arquivo novo, uma pasta de site ou um README, por si só, não ativa nada. Para entrar no agendamento, o alerta precisa estar registrado com `"ativo": true` em `alertas.json` na branch padrão.

## 2. Planejamento — responder antes de codificar

Registre estas decisões no README do escopo:

- **Objetivo:** que fato ou mudança o alerta deve comunicar?
- **Elegibilidade:** quais condições tornam um item notificável? Quais itens parecidos devem ser rejeitados?
- **Fontes:** quais RSS, páginas ou APIs serão consultados? São públicas e acessíveis sem contornar bloqueios?
- **Janela:** quão recente precisa ser a publicação? A fonte cobre essa janela de forma confiável?
- **Ocorrência única:** por URL, ID da fonte, registro de pesquisa, combinação de campos ou outra chave estável?
- **Frequência e limite:** quantas vezes consultar e quantas mensagens enviar por execução?
- **Mensagem:** qual título, resumo, link, fonte, data e ressalva são necessários para interpretar o alerta?
- **Limitações:** o que a coleta não cobre e o que uma correspondência não comprova?
- **Credenciais e custo:** usa segredo, API paga, cota, cache ou proteção contra repetição de consultas?

Se o novo comportamento for apenas adicionar um portal a um alerta existente, avalie ampliar a lista de fontes daquele executor. Crie outro ID quando houver regra, estado, finalidade ou ciclo de vida independentes.

## 3. Estrutura recomendada

Use o escopo temático existente quando fizer sentido. Para um escopo novo, um formato possível é:

```text
servicos/
├── __init__.py
├── README.md
├── bolsa_familia.py             # executor: run(argv=None)
└── g1/
    ├── __init__.py
    ├── README.md
    └── calendario_pagamentos.py  # configuração/filtro da fonte
tests/
└── test_servicos.py
```

Escolha nomes que descrevam o tema e mantenha cada executor independente. Não sobrescreva o executor de um alerta existente para acrescentar um tema distinto. `__init__.py` identifica pacotes; não deve iniciar coletas.

## 4. Implementação: contrato e regras de estado

O executor deve:

1. Definir `run(argv=None)` e aceitar `--state`, `--dry-run` e `--test`.
2. Interpretar a ausência de `--dry-run` e `--test` como execução normal (`live`), porque é assim que o runner invoca o módulo.
3. Ler `DISCORD_WEBHOOK_URL` do ambiente para enviar. Nunca gravar o valor em código, logs, documentação ou estado.
4. Coletar e validar conteúdo, deixando erros de fonte distinguíveis de uma coleta válida sem resultados.
5. Ler e preservar o estado compartilhado, inclusive campos desconhecidos de outros alertas.
6. Criar uma chave de deduplicação estável e com namespace próprio, por exemplo `identifier("meu_alerta:" + occurrence_key)`.
7. Chamar `send_discord` somente para conteúdo elegível e ainda não entregue. Personalizar `alert_title`, `message` ou `footer` para não herdar texto de outro tema.
8. Marcar como entregue apenas depois da confirmação do Discord e persistir imediatamente. Uma falha de envio não pode consumir a ocorrência.
9. Não alterar o estado em `dry-run` nem em `test`. O teste deve ser claramente marcado; prefira uma mensagem fictícia se isso validar a integração necessária.
10. Retornar normalmente se não houver novidades; levantar erro ou terminar com código diferente de zero se coleta/envio falhar.

Para feeds RSS compatíveis, `core.alerta.fetch_feed(url, allowed_hosts, hours=..., predicate=...)` valida HTTPS/host, datas e janela, e retorna itens ordenados. Ele pode lançar exceções para falhas de rede ou XML; não converta essas falhas em lista vazia. `identifier` e `send_discord` também estão em `core.alerta`. Para HTML, APIs ou formatos especiais, implemente validação e limites adequados ao caso.

O estado é compartilhado entre todos os alertas. Não substitua o arquivo inteiro por um estado local novo, não remova hashes existentes e não use apenas a URL como chave quando duas regras diferentes puderem alertar sobre o mesmo conteúdo.

## 5. Catálogo e agenda

Adicione uma entrada única a `alertas.json`:

```json
{
  "id": "meu_alerta",
  "modulo": "servicos.meu_alerta",
  "ativo": false,
  "descricao": "O que este alerta monitora"
}
```

O `id` deve ser único e não pode ser `all`; `modulo` é um caminho Python importável sem `.py`. Comece com `ativo: false` enquanto valida, se não quiser que ele participe dos próximos agendamentos. Alertas inativos também não são executáveis por `main.py`; para teste isolado, invoque o módulo diretamente.

Sem `agenda`, o alerta participa de cada execução agendada do workflow (atualmente de hora em hora, no minuto 07). Para limitar a frequência, use por exemplo:

```json
"agenda": {
  "intervalo_horas": 6,
  "fim_exclusivo": "2026-12-01T00:00:00-03:00"
}
```

`intervalo_horas` deve ser um divisor positivo de 24. `fim_exclusivo` é opcional, deve incluir fuso horário e só limita as execuções com `--scheduled`; se a data final também precisa valer em chamadas manuais, o executor deve impor essa regra. Não crie um workflow YAML por alerta.

## 6. Testes necessários

Adicione testes com fixtures e mocks, sem rede ou Discord reais. Cubra pelo menos:

- casos relevantes aceitos e casos limítrofes/irrelevantes rejeitados;
- parsing e validação dos campos exigidos pela regra;
- deduplicação na segunda execução, inclusive se a mesma ocorrência aparecer em outra URL;
- estado preservado em `dry-run` e `test`;
- falha de envio sem registrar a ocorrência como entregue;
- coleta vazia sem mensagem e sem alteração indevida do estado;
- preservação dos dados já existentes de outros alertas.

Execute a suíte e faça uma consulta simulada:

```sh
python -m unittest discover -s tests -v
python main.py --list
python main.py --alert meu_alerta --mode dry-run
```

`dry-run` pode consultar fontes reais e, dependendo da API, consumir cota. Para integrações pagas, use mocks/cache e documente claramente qualquer teste que faça chamadas externas.

## 7. Documentação e ativação

No README do escopo, documente propósito, ID, fontes, filtros, janela, agenda, limites, deduplicação, modos de execução, dependências, segredos e limitações. Atualize outros documentos somente quando a mudança afetar instruções gerais.

Antes de ativar, confirme:

- [ ] O módulo importa sem iniciar coleta ou enviar mensagens.
- [ ] O ID e o caminho de módulo no catálogo estão corretos e únicos.
- [ ] Os testes automatizados passam.
- [ ] O `dry-run` mostra apenas itens esperados.
- [ ] O modo `test` está marcado e não modifica estado de produção.
- [ ] Um envio confirmado é deduplicado em execução posterior.
- [ ] Segredos não aparecem no código, logs ou estado.
- [ ] Frequência, limites, cobertura e possíveis custos estão documentados.
- [ ] Estado existente é preservado.

Para validar pelo GitHub Actions, use **Actions → Executar alertas → Run workflow**, selecione o ID e rode primeiro `dry-run`, depois `test`. Use `live` após confirmar a regra e a mensagem. O workflow usa `DISCORD_WEBHOOK_URL` como repository secret; variáveis ou chaves adicionais devem ser configuradas e passadas explicitamente no workflow.

Ao publicar `ativo: true` na branch padrão, o alerta entra no agendamento compartilhado. O envio não é exatamente uma vez: pode haver repetição se o Discord confirmar a mensagem e a persistência do estado falhar depois.

## Referências rápidas

- [Tutorial completo com exemplo de Bolsa Família](README.md)
- [README principal e fluxo do workflow](../README.md)
- [Componentes compartilhados e estado](../core/README.md)
- [Convenções dos testes](../tests/README.md)
- [Workflow genérico](../.github/workflows/README.md)
