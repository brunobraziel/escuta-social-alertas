# Workflow genérico

`monitorar.yml` → **Executar alertas**.

1. Prepara Python 3.12 e executa testes sem rede.
2. Restaura `state.json` da branch `alert-state` (ou inicializa estado vazio).
3. Chama `python main.py --alert "$ALERT" --mode "$MODE"`; no evento `schedule`, também passa `--scheduled`.
4. Em execução normal, salva entregas confirmadas, mesmo após falhas posteriores.

`mode`: `dry-run`, `live` ou `test`. `alert`: `all` ou um ID ativo de `alertas.json`. Testes exigem um único ID. Agendamentos usam `live` + `all` + `--scheduled`; sem secret, usam simulação.

Frequência única: `schedule.cron`, atualmente `7 * * * *`. Para 15 minutos: `7,22,37,52 * * * *`. Horários cron são UTC; os intervalos se mantêm em Fortaleza. Novos alertas entram pelo catálogo; não precisam de YAML próprio.

O grupo de concorrência único serializa execuções para preservar estado. O secret `DISCORD_WEBHOOK_URL` é de repositório. O token do workflow tem escrita apenas para persistir estado neste repositório. Não execute manualmente cópias antigas dos workflows removidos, pois poderiam publicar mensagens duplicadas.

## Registrar novos alertas

Não crie outro arquivo de workflow. O [tutorial](../../docs/README.md) explica a criação do módulo e a entrada em `alertas.json`. Após publicar na branch padrão com `ativo: true`, o novo ID participa do agendamento. Na execução manual, digite esse ID no campo `alert`; a lista não é fixa no YAML.

O workflow restaura e persiste o estado compartilhado; o executor deve preservar entradas existentes e gravar entregas confirmadas antes de retornar. Se a restauração falhar, a etapa de persistência não roda, evitando substituir o histórico. O cron base é comum, mas `agenda.intervalo_horas` e `agenda.fim_exclusivo` no catálogo limitam cada alerta nas execuções agendadas.

## Quando o job é disparado

- Automático: `schedule`, cron `7 * * * *`, uma vez por hora, no minuto 07. Usa `live` + `all` e a versão da branch padrão.
- Manual: `workflow_dispatch`, com modo e ID informados no botão Run workflow.
- Pushes e commits não são gatilhos deste YAML. Gravar `alert-state` não encadeia outra execução.

O agendamento inicia a consulta, não uma mensagem obrigatória. Os executores filtram os feeds e consultam o estado antes de chamar `send_discord`. Sem conteúdo elegível novo, não há mensagem no canal. Testes manuais solicitam uma mensagem identificada; simulações nunca notificam. Veja o [fluxo completo no README principal](../../README.md#fluxo-de-trigger-do-job-e-das-notificações).

Diagnóstico de Trends: `mode: probe` + `alert: tendencias_por_estado` executa uma tentativa isolada, inclusive quando o alerta está inativo. Não passa pelo envio nem grava estado. Os logs contêm apenas contagens, códigos HTTP e tipos de erro, sem termos privados. Outros IDs não aceitam `probe`.

Tendências usa SerpApi e recebe o repository secret `SERPAPI_API_KEY`. Sua agenda no catálogo prevê 00h07 de Fortaleza até o fim de 24/10/2026; os outros alertas não herdam essa agenda. O executor e o diagnóstico também bloqueiam consultas após o encerramento.

Cache de tendências: `replay` lê o snapshot sem nenhuma consulta externa nem envio; `recover` recupera comparações já arquivadas e atualiza RSS público uma vez, sem criar novas pesquisas SerpApi. Ambos exigem `alert: tendencias_por_estado`. O workflow exporta snapshots para `dados/tendencias/` na branch `alert-state` durante a persistência. Testes agora também salvam snapshots, sem marcar entrega na deduplicação de produção.
