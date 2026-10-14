# Contrato: Configuração (delta da feature 003)

Complementa [001 / configuracao.md](../../001-cato-socket/contracts/configuracao.md). A validação
continua acumulando **todos** os erros e saindo com `exit 1`.

| Variável | Obrig. | Padrão | Validação | Segredo | Exibição no log |
|---|---|---|---|---|---|
| `TEAMS_WEBHOOK_URL` | sim | — | URL `https://` | **sim** | só o host |
| `TEAMS_WEBHOOK_OPERACIONAL_URL` | **sim (novo)** | — | URL `https://` | **sim** | só o host |

Observações:

- `TEAMS_WEBHOOK_URL` mantém o nome e passa a ser o **canal de rede**.
- As duas URLs podem ser iguais; as filas continuam separadas.
- `Config.segredos()` inclui a nova URL, para o filtro de redação dos logs.
- Constante **não configurável**: 15 min (900 s) de falha contínua para o aviso de "sem entrega".

Erros possíveis (junto dos demais, na mesma mensagem):

```json
{"level":"ERROR","event":"config_invalida","erros":["TEAMS_WEBHOOK_OPERACIONAL_URL ausente"]}
{"level":"ERROR","event":"config_invalida","erros":["TEAMS_WEBHOOK_OPERACIONAL_URL deve ser uma URL https://"]}
```

`.env.example` ganha:

```text
# --- Teams, canal operacional (saúde do robô): outro fluxo "Post to a channel when a webhook request is received" ---
TEAMS_WEBHOOK_OPERACIONAL_URL=https://exemplo.logic.azure.com/workflows/yyyy
```
