# Changelog

## Não lançado — feature 003: canal operacional separado

- Avisos de rede e avisos do robô vão a webhooks diferentes (`TEAMS_WEBHOOK_URL` = rede,
  `TEAMS_WEBHOOK_OPERACIONAL_URL` = operacional).
- **Exige ação na atualização:** a nova variável é obrigatória.
- Uma fila persistida por canal, drenadas em paralelo; falha de um canal não atrasa o outro.
- Aviso único "CANAL … SEM ENTREGA" (15 min) no outro canal, com normalização.
- `state.json` passa para `schema_version` 2; v1 é migrado sem perda, com cópia `state.json.v1-<UTC>`.

## 0.1.0 — 2026-10-06

Primeira versão do monitor de sockets Cato com avisos no Teams.

- Consulta única `accountSnapshot` por ciclo, com timeouts, backoff e resultado tipado (falha ≠ queda).
- Máquina de estados pura (`ONLINE` → `PENDENTE_OFFLINE` → `OFFLINE_NOTIFICADO`) com tolerância por timestamp.
- Avisos: `LINK OFFLINE`, `SITE OFFLINE`, retornos, lembrete diário, e avisos do próprio monitor.
- Estado em JSON atômico com lock de instância única; fila de envio persistida e reenviada em ordem.
- Logs JSON com mascaramento de segredos, `HEALTHCHECK` e heartbeat externo.
- Contêiner multi-stage não-root, com `docker-compose.yml` endurecido.
- Pendente: verificação do schema real da Cato (T007) e validação ponta a ponta com Docker (T064).
