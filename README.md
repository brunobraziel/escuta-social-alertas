# Escuta Social Alertas

Alerta de notícias sobre **próximos passos da escala 6x1**, sem classificação de fake news. Código público, sem lista interna do Drive e sem credenciais.

## Fontes e cobertura

G1 e CNN Brasil: RSS público, sem acesso ao texto completo das matérias. Os feeds responderam com XML válido na validação inicial. Isso não representa licença irrestrita: reavalie termos de uso antes da operação contínua e suspenda a fonte se houver restrição. Use somente título, link e descrição breve disponível no feed; não reproduza artigos.

O conector UOL está reservado na estrutura, mas desabilitado: a URL candidata não retornou XML válido. BBC, Metrópoles e Brasil Paralelo não estão incluídos nesta primeira versão.

Filtro: variantes de “escala 6x1”, “escala 6 por 1” ou “fim da 6x1”, junto de termos de promulgação, vigência, transição ou publicação. Exige o tema no título para evitar menções incidentais; busca os termos de próximos passos no título e na descrição; pode deixar matérias relevantes de fora. “Publicação” pode produzir ruído; ajuste após observar resultados. Uma correspondência não confirma mudança legislativa.

Matérias com data válida nas últimas 48 horas; até três envios por execução. RSS é uma janela limitada e não garante recuperação de todas as matérias das últimas 48 horas. Ausência de correspondências é uma execução válida; falha de coleta produz erro, distinguindo as duas situações.

## Uso local

Python 3.12; nenhuma dependência externa.

```sh
python -m unittest discover -s tests -v
python main.py --dry-run
python main.py --dry-run --test
python main.py --site g1 --dry-run
```

Para envio real, forneça `DISCORD_WEBHOOK_URL` pelo ambiente, sem inserir o valor em arquivos ou commits. `python main.py --test` envia um exemplo fictício identificado como teste; `python main.py` coleta e envia notícias reais.

## GitHub Actions e Discord

1. No canal do Discord, crie um webhook em Integrações.
2. No repositório: Settings → Secrets and variables → Actions → New repository secret. Nome: `DISCORD_WEBHOOK_URL`; valor: URL do webhook.
Em canais de fórum, o envio cria um novo tópico por alerta. Em canais de texto, envia a mensagem diretamente. Um `thread_id` já presente na URL é preservado.

3. Em Actions → Monitorar escala 6x1 → Run workflow, selecione `test` para conferir a mensagem fictícia.
4. Selecione `live` para notícias reais; `dry-run` apenas registra as correspondências.

Agendamento: minutos 7 e 37 de cada hora (UTC; periodicidade igual em Fortaleza). Sem o secret, o agendamento roda em dry-run e exibe aviso. Adicionar o secret ativa envios nas próximas execuções. O modo `test` exige o secret e ignora coleta/deduplicação.

O workflow guarda somente hashes SHA-256 das URLs enviadas na branch pública `alert-state`, após confirmação do Discord. Não apague essa branch: isso permite reenvios. As execuções são serializadas. A persistência usa `contents: write` restrita ao token do repositório. Proteções de branch devem permitir ao bot atualizar `alert-state`.

Em uma falha entre envio e persistência, ou resposta de rede incerta, pode ocorrer duplicação; não existe garantia de entrega exatamente uma vez. Retentativas automáticas do Discord ocorrem apenas em HTTP 429. Datas inválidas são ignoradas. URLs de matérias precisam pertencer aos hosts configurados.

GitHub pode atrasar agendamentos e desativá-los após 60 dias sem atividade em repositórios públicos. Verifique a saúde do workflow periodicamente; esta versão não inclui monitor externo de inatividade. Logs de dry-run são públicos e contêm metadados públicos das matérias. Não registre segredos ou documentos internos.
