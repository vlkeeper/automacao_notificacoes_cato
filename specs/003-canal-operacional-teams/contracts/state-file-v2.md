# Contrato: `state.json` v2 (delta da feature 003)

Base: [001 / state-file.schema.json](../../001-cato-socket/contracts/state-file.schema.json) (v1).
Campos `monitor` e `sites` **não mudam**.

## Diferenças

| Chave raiz | v1 | v2 |
|---|---|---|
| `schema_version` | `1` | `2` |
| `pendente_envio` | array de eventos | **removida** |
| `filas` | — | objeto com `rede` e `operacional`, cada um array de eventos (mesmo formato) |
| `entrega` | — | objeto com `rede` e `operacional`, cada um `{falha_desde, aviso_emitido}` |

## Trecho do schema (v2)

```json
{
  "required": ["schema_version", "atualizado_em", "monitor", "sites", "filas", "entrega"],
  "properties": {
    "schema_version": { "const": 2 },
    "filas": {
      "type": "object",
      "required": ["rede", "operacional"],
      "additionalProperties": false,
      "properties": {
        "rede": { "type": "array", "items": { "$ref": "#/$defs/evento" } },
        "operacional": { "type": "array", "items": { "$ref": "#/$defs/evento" } }
      }
    },
    "entrega": {
      "type": "object",
      "required": ["rede", "operacional"],
      "additionalProperties": false,
      "properties": {
        "rede": { "$ref": "#/$defs/situacao_entrega" },
        "operacional": { "$ref": "#/$defs/situacao_entrega" }
      }
    }
  },
  "$defs": {
    "situacao_entrega": {
      "type": "object",
      "required": ["falha_desde", "aviso_emitido"],
      "additionalProperties": false,
      "properties": {
        "falha_desde": { "$ref": "#/$defs/ts_ou_null" },
        "aviso_emitido": { "type": "boolean" }
      }
    }
  }
}
```

`evento.tipo` ganha os valores `CANAL_SEM_ENTREGA` e `CANAL_NORMALIZADO`; `dados` conforme o
[data-model](../data-model.md).

## Compatibilidade

- Leitura: v1 é migrado para v2 na carga ([data-model, Migração](../data-model.md)); v2 carrega
  direto; versão > 2 encerra com `exit 1`.
- Escrita: sempre v2. Volta para a versão anterior do robô **não é suportada** após a migração
  (a cópia `state.json.v1-<UTC>` permite o retorno manual).
- Arquivos auxiliares `last_cycle` e `monitor.lock` não mudam.
