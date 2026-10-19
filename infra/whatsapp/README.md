# WhatsApp: espelhamento dos alertas do Discord

O envio usa um projeto Google Cloud exclusivo, sem consultar BigQuery e sem
reutilizar BQ_CRED. A implementação permanece inativa enquanto WHATSAPP_TOPIC
não estiver configurada nos repositórios.

## Componentes

- `whatsapp_bridge.py` na raiz de ambos os repositórios: converte a mensagem
  confirmada pelo Discord, cria outbox local e publica no Pub/Sub.
- `worker.py`: confirma a fila somente depois da gravação SQLite. Uma repetição
  do mesmo evento não cria outra entrega. Mensagens longas são divididas e cada
  parte confirmada é registrada.
- `compose.yaml`: WAHA NOWEB com sessão persistente, API somente localhost,
  painel desativado, chave SHA512 e serviço de envio.
- `bootstrap.sh`: prepara Docker e desligamento em 25/10/2026 às 03h UTC
  (fim de 24/10 em Fortaleza).

## Configuração Google Cloud

Projeto dedicado, região us-central1, VM e2-standard-2 com 30 GB pd-standard.
Rede exclusiva, entrada SSH apenas por IAP (35.235.240.0/20), sem porta 3000
aberta na internet. Usar IP efêmero: ele é liberado ao parar a VM.

Criar tópico `discord-mirror` e assinatura `whatsapp-worker` com retenção de
sete dias. A conta de serviço da VM recebe somente subscriber nessa assinatura
e acesso somente à chave WAHA no Secret Manager. Não criar chaves JSON.

Configurar Workload Identity Federation para GitHub OIDC. Restringir por
repository_owner_id, IDs dos dois repositórios e ref refs/heads/main.
Cada repositório utiliza uma conta publisher distinta, autorizada somente no
tópico. Registrar nas variables GitHub:

- WHATSAPP_TOPIC: projects/PROJECT/topics/discord-mirror
- WHATSAPP_WIF_PROVIDER: projects/NUMBER/locations/global/workloadIdentityPools/POOL/providers/github
- WHATSAPP_PUBLISHER_SA: publisher@PROJECT.iam.gserviceaccount.com

No host, guardar o segredo da API em
`/etc/escuta-whatsapp/secrets/waha_api_key` (root:root 0600).
O webhook Discord continua exclusivamente no GitHub: o worker publica avisos
operacionais em `whatsapp-health` e o workflow `Saúde WhatsApp` os entrega ao
Discord a cada dez minutos, somente quando há eventos. Configurar a variable
WHATSAPP_HEALTH_SUBSCRIPTION com a assinatura `whatsapp-health-discord`.
A conta da VM publica somente no tópico operacional; a conta GitHub de alertas
lê somente essa assinatura. Nenhum publicador pode modificar segredos.

Montar a chave somente no worker. O WAHA recebe apenas o hash SHA512.
O grupo autorizado vai em `config/group_id`, no formato ID@g.us. O evento da
fila nunca escolhe o destinatário.

Copiar esta pasta para `/opt/escuta-whatsapp` e criar `.env` com WAHA_IMAGE
(digest imutável obtido do registro oficial), WAHA_API_KEY_HASH e
PUBSUB_SUBSCRIPTION e HEALTH_TOPIC. Subir com `docker-compose -f compose.yaml up -d --build`.

## Operação e verificação

1. Conectar ao host por IAP e abrir túnel local à porta 3000.
2. Conectar sessão default por QR; adicionar o número ao grupo e configurar ID.
3. Confirmar sessão WORKING e enviar um evento TESTE de cada categoria.
4. Repetir event_id e conferir uma única entrega.
5. Reiniciar containers/host e confirmar persistência da sessão e da fila.
6. Desconectar a sessão, publicar evento, reconectar e conferir recuperação.

Falha de publicação preserva `.whatsapp-outbox` como artifact GitHub por sete
dias e deixa uma etapa do workflow em falha, sem repetir o envio Discord.
O workflow manual `Recuperar WhatsApp` republica esse artifact sem nova
ingestão nem novas consultas SerpAPI.

Um timeout após o envio ao WAHA é ambíguo: o status fica `uncertain` e não é
reenviado automaticamente. Conferir a conversa e os recibos antes de alterar
o status. O SQLite registra recibos da API; isso não garante leitura por todos
os integrantes do grupo. O protocolo não promete entrega exatamente uma vez.

## Custos e encerramento

Estimativa até 24/10: US$13–18; reserva US$30. Orçamento configurado: R$150 em reais, com avisos 50/80/100%,
excluindo os créditos do cálculo para medir o consumo bruto. Orçamento não é um limite automático para Compute Engine.
Verificar saldo e validade dos créditos na conta de faturamento correta.

Após desligamento, disco e secrets continuam existindo e podem ter cobrança.
Preservar backup somente pelo prazo necessário e excluir recursos exclusivos
quando a operação encerrar. Não excluir o projeto sem avaliar a necessidade
de reter os registros de entrega e sessão.

## Testes locais

`python -m unittest discover -s tests -q` no repositório de alertas.
`python -m pytest -q` no ETL.

Alterações em whatsapp_bridge.py devem ser copiadas para o outro repositório;
ambas as cópias precisam ter o mesmo hash e passar pelos testes.

## Implantação em 18/10/2026

- Projeto: escuta-whatsapp-261018 (conta brunobraziel@gmail.com).
- VM: escuta-waha, zona us-central1-a.
- WAHA NOWEB: digest sha256:be61f8cd7774ab22bd1b755cbc539f98d71d81d5ca83555fdddfa4fddd7924e1.
- BigQuery permanece em outro projeto e não participa desta integração.
