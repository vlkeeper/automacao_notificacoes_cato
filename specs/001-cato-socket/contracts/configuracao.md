# Contrato: Configuração (variáveis de ambiente)

A configuração é validada inteira na inicialização. **Todos** os erros são reportados numa
mensagem só, e o processo sai com `exit 1` (Princípio VI). A configuração efetiva é logada com os
segredos mascarados.

| Variável | Obrig. | Padrão | Validação | Segredo | Exibição no log |
|---|---|---|---|---|---|
| `CATO_API_KEY` | sim | — | não vazia, sem espaços | **sim** | `****abcd` (4 últimos) |
| `CATO_ACCOUNT_ID` | sim | — | só dígitos | não | valor |
| `CATO_API_URL` | não | `https://api.catonetworks.com/api/v1/graphql2` | URL `https://` | não | valor |
| `TEAMS_WEBHOOK_URL` | sim | — | URL `https://` | **sim** | só o host |
| `HEARTBEAT_URL` | sim | — | URL `https://` | **sim** | só o host |
| `INTERVALO_SEGUNDOS` | não | `60` | inteiro entre 30 e 120 | não | valor |
| `TOLERANCIA_SEGUNDOS` | não | `180` | inteiro entre 60 e 3600 e ≥ `INTERVALO_SEGUNDOS` | não | valor |
| `LEMBRETE_HORARIO` | não | `08:00` | `HH:MM` válido (24 h) | não | valor |
| `TZ` | não | `America/Sao_Paulo` | aceito por `zoneinfo.ZoneInfo` | não | valor |
| `STATE_DIR` | não | `/data` | diretório existente e gravável | não | valor |
| `LOG_LEVEL` | não | `INFO` | `DEBUG`/`INFO`/`WARNING`/`ERROR` | não | valor |

Constantes **não configuráveis**, definidas pela constituição: 5 falhas consecutivas para o
`MONITOR_FALHA` e 3 ciclos válidos de ausência para remover um item.

Exemplo de mensagem de erro (stderr, JSON):

```json
{"level":"ERROR","event":"config_invalida","erros":["CATO_API_KEY ausente","INTERVALO_SEGUNDOS=10 abaixo do mínimo 30"]}
```

Códigos de saída do processo:

| Código | Situação |
|---|---|
| 0 | parada solicitada (SIGTERM/SIGINT), com estado gravado |
| 1 | configuração inválida, outra instância com o lock ou `schema_version` do estado mais novo que o suportado |
