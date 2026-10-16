# Tendências de busca por estado

ID: `tendencias_por_estado`. Executor: `tendencias_busca.run`, com o mesmo contrato `run(argv=None)` dos demais alertas. **Está desativado no catálogo**: a comparação pública do Explore retornou HTTP 429 na validação real. Não foi enviado resumo real nem feita ativação automática.

## O que o post deve mostrar

Uma única mensagem do Discord, com duas seções (dois embeds no mesmo POST), cobrindo os 26 estados e o Distrito Federal:

1. **Assuntos em alta:** até dois destaques da lista pública de tendências por UF nas últimas 24 horas. Preserva a ordem do RSS; não representa o ranking absoluto de todas as buscas.
2. **Escuta Social:** consulta todos os termos revisados do documento, mesmo fora das tendências, e mostra até dois destaques de maior interesse relativo por UF. Não filtra somente termos que aparecem no RSS.

Se houver estado sem dados suficientes para comparar todos os termos, isso é informado em vez de inventar uma ordem. Se a comparação falhar inteiramente (429, CAPTCHA/formato inesperado etc.), não é enviado resumo parcial apresentado como completo. Ausência de interesse mensurável não significa ausência de buscas. Os dados não medem apoio, opinião pública, intenção de voto ou volume absoluto.

## Arquivos e chamadas

```text
main.py → alertas.json → tendencias_busca.run.run(argv)
                           → drive/termos.py: lista privada revisada
                           → google/coleta.py: RSS + Explore regional
                           → resumo.py: duas seções e fingerprint
                           → core.alerta.send_discord: um POST/tópico
```

- `run.py`: valida configuração, consulta comparações, reúne feeds e envia somente quando o conteúdo exibido muda.
- `estados.py`: códigos e nomes das 27 UFs.
- `drive/termos.py`: lê `ESCUTA_SOCIAL_TERMS_JSON`; não acessa o Drive automaticamente e não contém nomes privados no código.
- `google/coleta.py`: coleta e valida origem estadual dos feeds; compara os termos em lotes de até cinco, com um termo comum.
- `resumo.py`: mantém separadas as duas medidas, limita o tamanho da mensagem e calcula novidade sem timestamps ou variações pequenas de pontuação.

## Lista de termos e privacidade

A lista revisada com nove termos foi configurada, com autorização do responsável, no repository secret `ESCUTA_SOCIAL_TERMS_JSON`. Ela não está em arquivos versionados. Não grave os dados no código ou logs; o workflow público recebe a lista pelo ambiente.

A implementação espera este formato em `ESCUTA_SOCIAL_TERMS_JSON` (exemplo fictício):

```json
{
  "source_url": "https://docs.google.com/document/d/ID_DO_DOCUMENTO/edit",
  "source_modified": "2026-10-16T00:00:00Z",
  "terms": ["Tema A", "Tema B"]
}
```

O snapshot autorizado está armazenado como repository secret; o workflow já passa o secret ao executor. A lista deve ser revisada novamente quando o documento mudar. O post informa a versão usada. O acesso ao Drive por um conector externo **não concede acesso ao GitHub Actions**; sincronização automática do documento exigiria uma integração autenticada adicional, ainda não implementada.

## Comparabilidade

O primeiro termo é a referência comum entre lotes. Os valores de cada termo são divididos pelo valor dessa referência na mesma UF e depois reescalados em relação ao maior entre os monitorados naquela UF. Isso evita concatenar índices normalizados independentes sem referência. O método produz uma aproximação sensível à amostragem/arredondamento; não é uma contagem de pessoas ou buscas.

Se qualquer termo estiver sem valor positivo mensurável, ou a referência não puder ser medida, o estado fica como `dados insuficientes`: não se produz ranking de todos os termos com um subconjunto de dados. As comparações usam a mesma janela de 24 horas, tipo de pesquisa e abrangência Brasil. O corpo mostra apenas os destaques; os demais termos foram consultados, não omitidos da coleta. Os números do índice não são exibidos no post.

## Validação e ativação pendentes

A API oficial do Trends permanece em acesso antecipado: https://developers.google.com/search/apis/trends . A conta nova do Google Cloud não concede esse acesso. O coletor atual usa endpoints públicos **não oficiais**, sujeitos a mudanças e bloqueios. Não há rotação de IP, quebra de CAPTCHA ou retentativas automáticas em 429.

Antes de ativar:

1. Lista revisada do Drive: configurada como secret com autorização do responsável. Atualize-a quando a versão do documento mudar.
2. Validar o coletor de comparação com respostas reais; se o acesso público continuar bloqueado, integrar uma fonte autorizada/API com acesso disponível. O adapter oficial ainda não foi implementado; não basta fornecer uma chave.
3. Com o ambiente configurado, executar o módulo diretamente enquanto o catálogo estiver inativo:

```sh
python -m tendencias_busca.run --dry-run --states MG,SP
python -m tendencias_busca.run --dry-run
```

4. Somente após validação e revisão dos resultados, alterar `ativo` para `true`. O agendamento existente passa a consultá-lo uma vez por hora, sem criar outro workflow:

```sh
python main.py --alert tendencias_por_estado --mode dry-run
```

`--test` envia um resumo real identificado como teste e não grava deduplicação; não é uma prévia fictícia. Não o execute antes de haver dados reais válidos. Nesta entrega não houve teste de envio ao canal.

## Silêncio e estado

O estado compartilhado preserva `sent` e armazena apenas um hash adicional em `latest_trends`. Não grava consultas, nomes, índices ou o documento privado na branch de estado. A cada execução, compara com o último resumo entregue; se a lista/ordem dos destaques não mudou, fica em silêncio. Mudança apenas de horário, pontuação ou versão do documento sem mudança na lista não gera notificação.

`dry-run` imprime o conteúdo que seria enviado e não modifica o estado. **Não rode o dry-run com a lista privada em logs públicos sem autorização para divulgar os resultados.** O modo test ignora a deduplicação e não modifica o histórico. Erros ficam no status/log do job, sem mensagem ao Discord.
