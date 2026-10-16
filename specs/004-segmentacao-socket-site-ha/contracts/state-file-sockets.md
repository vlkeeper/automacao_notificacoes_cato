# Contrato: `state.json` — sockets por site (delta da feature 004)

Base: [003 / state-file-v2](../../003-canal-operacional-teams/contracts/state-file-v2.md).
`schema_version` continua **2**; o campo novo é aditivo (research R-007).

## Diferenças

| Local | Antes | Depois |
|---|---|---|
| `sites.<id>.sockets` | — | objeto chave → socket; sempre gravado (`{}` em sites não-HA) |
| `filas.*[].tipo` | — | aceita `SOCKET_OFFLINE` e `SOCKET_RETORNO` |

## Trecho do schema

```json
{
  "$defs": {
    "socket": {
      "allOf": [{ "$ref": "#/$defs/item_base" }],
      "required": ["coberto_pelo_site"],
      "properties": { "coberto_pelo_site": { "type": "boolean" } }
    },
    "site": {
      "properties": {
        "sockets": { "type": "object", "additionalProperties": { "$ref": "#/$defs/socket" } }
      }
    }
  }
}
```

## Exemplo

```json
"sockets": {
  "s-77": { "nome": "primário", "estado": "ONLINE", "inicio_queda": null, "notificado": false,
            "coberto_pelo_site": false, "origem": "observado", "ausencias": 0 },
  "s-78": { "nome": "secundário", "estado": "OFFLINE_NOTIFICADO",
            "inicio_queda": "2026-10-14T13:05:00+00:00", "notificado": true,
            "coberto_pelo_site": false, "origem": "observado", "ausencias": 0 }
}
```

## Compatibilidade

- Leitura de estado sem `sockets`: equivale a `{}`; nada é avisado até haver observação.
- Leitura pela versão anterior: `sockets` é ignorado. Eventos `SOCKET_*` na fila fazem a versão
  anterior tratar o estado como inválido (nova linha de base, um aviso). Volta de versão não é
  suportada.
- `last_cycle` e `monitor.lock` não mudam.
