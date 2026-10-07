# Contrato: Observabilidade (logs, healthcheck, heartbeat)

## Logs (stdout, uma linha JSON por registro)

Campos comuns: `ts` (UTC ISO 8601), `level`, `event`, `msg`. Os segredos são mascarados pelo filtro
de redação (R-009). Nenhuma URL de Teams ou heartbeat e nenhum token aparece, nem dentro de
tracebacks.

| `event` | Nível | Campos extras |
|---|---|---|
| `monitor_iniciando` | INFO | `versao`, `config` (mascarada) |
| `estado_carregado` / `linha_base` | INFO / WARNING | `sites`, `links`, `pendentes` / `motivo` |
| `consulta_cato` | INFO / WARNING | `resultado` (`ok`/`falhou`), `motivo`, `tentativas`, `duracao_ms` |
| `transicao` | INFO | `item` (`site`/`link`), `site_id`, `link_id`, `de`, `para` |
| `evento_enfileirado` | INFO | `id`, `tipo` |
| `envio_teams` | INFO / WARNING | `id`, `tipo`, `status` (HTTP ou erro), `tentativas` |
| `item_removido` / `item_novo` | INFO | `site_id`, `link_id` |
| `heartbeat` | DEBUG / WARNING | `rota` (`ok`/`fail`), `status` |
| `ciclo_concluido` | INFO | `duracao_ms`, `sites`, `links`, `consulta`, `transicoes`, `eventos_gerados`, `fila_pendente`, `enviados`, `falhas_consecutivas` |
| `instancia_duplicada` | ERROR | `lock` |
| `monitor_encerrando` | INFO | `sinal` |

## Healthcheck do contêiner

- Arquivo: `${STATE_DIR}/last_cycle`, com um timestamp UTC ISO 8601. É regravado de forma atômica
  ao fim de cada ciclo.
- Comando: `python -m cato_monitor.healthcheck` → `exit 0` quando a idade é `≤ 3 × INTERVALO + 30 s`,
  e `exit 1` quando passa disso ou o arquivo está ausente.
- Docker: `--interval=60s --timeout=5s --start-period=120s --retries=3`.

## Heartbeat externo (Healthchecks.io ou compatível)

- Ao fim de cada ciclo concluído, faz `GET <HEARTBEAT_URL>`. Quando `falhas_consecutivas ≥ 5`, faz
  `GET <HEARTBEAT_URL>/fail`.
- Timeout de 10 s, 1 tentativa. Se falhar, registra log `WARNING` e o monitoramento continua.
- Configuração recomendada da checagem: **Period 1 min, Grace 2 min**, com integração de alerta para
  o responsável (e-mail ou outro canal **diferente** do monitor), atendendo ao SC-008.
