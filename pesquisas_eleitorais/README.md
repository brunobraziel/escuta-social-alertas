# Pesquisas eleitorais — presidente

ID `pesquisa_presidente`; executor `pesquisas_eleitorais.run.run(argv)`. O workflow único consulta de hora em hora, no minuto 07, e só notifica pesquisas ainda não enviadas. Não depende de SerpApi ou IA.

## Institutos e descoberta

**Não há lista fechada de institutos autorizados.** O catálogo de nomes em `parser.py` ajuda a reconhecer títulos: inclui Datafolha, PoderData, Quaest, AtlasIntel, Ipsos/Ipec, Paraná Pesquisas, Real Time Big Data, Futura, Veritá, Ipespe, MDA, Sensus, Ideia, Vox Populi e outros. Um instituto novo explicitamente identificado em um título `Pesquisa Nome: ...` também pode ser processado sem alteração nessa lista. Não é possível prometer que uma lista enumere todas as empresas existentes; a cobertura depende das fontes e formatos disponíveis.

O problema anterior tinha três causas: PoderData ausente dos nomes reconhecidos, parser limitado a votos totais no formato G1 e seleção somente da matéria mais recente, que podia já ter sido enviada. A versão atual aceita votos válidos de forma separada e seleciona ocorrências inéditas antes de limitar envios.

Fontes:

- G1 e CNN: RSS dos últimos sete dias; até seis matérias candidatas por portal podem ter o HTML lido quando o RSS não permite extrair os dados.
- Poder360: editoria pública PoderData, descoberta de links e leitura de até seis matérias candidatas. O feed dessa editoria pode não conter os artigos recentes, por isso a página é usada diretamente.

Os leitores só aceitam HTTPS/hosts configurados, limitam resposta e timeout, removem scripts/estilos e não contornam bloqueios, login ou CAPTCHA. Páginas indisponíveis podem limitar a coleta. O RSS não garante cobertura integral nem sete dias completos de notícias. Não há busca em todos os sites/institutos ou garantia de identificar a última pesquisa do país.

## Percentuais e limites

Escopo: **presidente, Brasil, segundo turno**. Cargos estaduais/municipais permanecem fora deste alerta.

- **Votos totais:** tabela explícita com candidatos/partidos, brancos/nulos/indecisos e soma próxima de 100%, além dos metadados. Formato textual inicial do G1.
- **Votos válidos:** tabela explícita de dois candidatos que soma aproximadamente 100%, uma frase explícita de empate em 50% para cada um, ou dois percentuais atuais no título associados inequivocamente aos nomes/partidos explícitos no corpo. Exige base de votos válidos declarada; não calcula valores a partir de totais.
- Ambos exigem instituto, registro BR, período, amostra, margem de erro e confiança para publicar números. O parser não confunde percentuais históricos e atuais, totais e válidos, nem aprovação/rejeição e intenção de voto. Formatos não suportados não geram percentuais inferidos.
- Se a notícia presidencial de segundo turno tem registro BR, mas não permite validar a tabela, envia **aviso sem percentuais**, com link e informação de que a extração ficou incompleta. Isso reduz silêncio em formatos novos. Se existir tabela válida para o mesmo registro na coleta, ela tem preferência sobre o aviso.

A mensagem identifica a base e ordena nomes alfabeticamente. Registro e metadados são transcritos da fonte; não são verificados automaticamente no PesqEle/TSE. Não há comparação, previsão ou interpretação de vantagem. O cadastro de nomes não atesta qualidade ou credenciamento de um instituto.

## Arquivos e execução

- `run.py`: reúne fontes, completa texto quando necessário, valida, deduplica por registro/eleição/base e envia até cinco ocorrências inéditas por execução.
- `parser.py`: reconhecimento amplo, validação de totais/válidos, aviso sem números e mensagem.
- `web.py`: descoberta HTML, texto sem scripts/estilos, metadados de publicação e validação de hosts/data.
- `{site}/presidente.py`: feed ou página de descoberta e hosts permitidos.

```sh
python main.py --alert pesquisa_presidente --mode dry-run
python main.py --alert pesquisa_presidente --mode test
python main.py --alert pesquisa_presidente --mode live
```

Em Actions → Executar alertas, escolha o ID `pesquisa_presidente`. `test` envia uma pesquisa real marcada `[TESTE]`, sem marcar entrega de produção; prefere uma tabela extraída a um aviso sem números. `live` envia ocorrências inéditas e persiste a deduplicação; `dry-run` lê as fontes e mostra o conteúdo sem enviar. Nenhum desses modos chama Trends/SerpApi quando este ID é selecionado.

O estado compartilhado é preservado. A última entrega normal é salva em `poll_last_delivery`, além dos hashes em `sent`. A mesma pesquisa/base em URLs diferentes não repete o alerta. Após confirmação de cada envio, o estado é gravado imediatamente; falha posterior não perde entregas anteriores. Uma pesquisa antiga ainda inédita não é ocultada pela notícia mais recente já enviada.

Para adicionar fonte, crie sua pasta/configuração, inclua o site no executor e valide o formato antes de publicar números. Use o workflow único; não crie YAML por site. Veja o [tutorial](../docs/README.md).
