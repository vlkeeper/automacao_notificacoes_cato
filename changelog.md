# Changelog

## 0.1.0 — 2026-10-06

Primeira versão do monitor de sockets Cato com avisos no Teams.

- Consulta única `accountSnapshot` por ciclo, com timeouts, backoff e resultado tipado (falha ≠ queda).
- Máquina de estados pura (`ONLINE` → `PENDENTE_OFFLINE` → `OFFLINE_NOTIFICADO`) com tolerância por timestamp.
- Avisos: `LINK OFFLINE`, `SITE OFFLINE`, retornos, lembrete diário, e avisos do próprio monitor.
- Estado em JSON atômico com lock de instância única; fila de envio persistida e reenviada em ordem.
- Logs JSON com mascaramento de segredos, `HEALTHCHECK` e heartbeat externo.
- Contêiner multi-stage não-root, com `docker-compose.yml` endurecido.
- Pendente: verificação do schema real da Cato (T007) e validação ponta a ponta com Docker (T064).
