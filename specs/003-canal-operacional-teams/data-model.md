# Data Model: Canal Operacional Separado no Teams

Delta sobre [specs/001-cato-socket/data-model.md](../001-cato-socket/data-model.md). Entidades não
citadas aqui (Site, Link, SituacaoMonitor, EventoNotificacao) não mudam.

## Canal (`canais.Canal`)

| Valor | Webhook | Público |
|---|---|---|
| `rede` | `TEAMS_WEBHOOK_URL` | quem acompanha quedas e retornos |
| `operacional` | `TEAMS_WEBHOOK_OPERACIONAL_URL` | quem mantém o robô |

`Canal.outro` devolve o canal oposto (usado nos avisos de "sem entrega").

## Mapeamento tipo → canal

Função pura `canal_do_evento(evento) -> Canal`. Tabela em [research.md R-006](research.md). Regras:

- Todo `TipoEvento` DEVE estar na tabela; tipo sem mapeamento levanta `KeyError` (teste de
  cobertura impede isso).
- `CANAL_SEM_ENTREGA` e `CANAL_NORMALIZADO` vão para `dados["canal_afetado"].outro`.

## TipoEvento (novos valores)

| Tipo | Gerado por | `dados` |
|---|---|---|
| `CANAL_SEM_ENTREGA` | `avaliar_entrega` | `canal_afetado`, `desde` (ISO UTC), `pendentes` (int) |
| `CANAL_NORMALIZADO` | `avaliar_entrega` | `canal_afetado`, `desde` (ISO UTC), `duracao_s` (int) |

`ocorrido_em` = instante em que o limite foi atingido (sem entrega) ou da primeira entrega
bem-sucedida (normalização).

## SituacaoEntrega (por canal, persistida)

| Campo | Tipo | Significado |
|---|---|---|
| `falha_desde` | timestamp UTC ou `null` | início da sequência de falhas de entrega do canal |
| `aviso_emitido` | bool | o aviso de "sem entrega" desta sequência já foi enfileirado |

**Invariantes**:

- `aviso_emitido == true` ⇒ `falha_desde != null`.
- Uma entrega bem-sucedida zera os dois campos (depois de gerar a normalização, se havia aviso).
- No máximo um `CANAL_SEM_ENTREGA` por sequência; um `CANAL_NORMALIZADO` só existe se houve o
  aviso correspondente.

**Transições** (função `avaliar_entrega`, pura):

```text
sem falha ──tentativa falhou──▶ falhando(falha_desde=agora)
falhando ──agora-falha_desde ≥ 900 s, !aviso_emitido──▶ falhando + emite CANAL_SEM_ENTREGA
falhando ──entrega ok, !aviso_emitido──▶ sem falha            (sem aviso, oscilação curta)
falhando ──entrega ok, aviso_emitido──▶ sem falha + emite CANAL_NORMALIZADO
```

## EstadoMonitor (alterações)

| Campo | Antes (v1) | Depois (v2) |
|---|---|---|
| `pendente_envio` | `list[EventoNotificacao]` | removido |
| `filas` | — | `{"rede": [...], "operacional": [...]}` |
| `entrega` | — | `{"rede": SituacaoEntrega, "operacional": SituacaoEntrega}` |
| `SCHEMA_VERSION` | 1 | 2 |

**Invariantes novos** (`verificar_invariantes`): as duas chaves existem em `filas` e `entrega`;
cada evento está na fila do canal que `canal_do_evento` indica; invariante de `SituacaoEntrega`.

## Migração v1 → v2

1. Ler `state.json` v1 e validar com as regras v1.
2. Copiar o arquivo para `state.json.v1-<UTC>` (falha ao copiar → log e segue, a regravação é
   atômica de qualquer forma).
3. Para cada evento de `pendente_envio`, em ordem, anexar à fila de `canal_do_evento(evento)`.
4. `entrega` com `falha_desde=null`, `aviso_emitido=false` nos dois canais.
5. Gravar v2 de forma atômica e logar `estado_migrado`.

Efeito colateral aceito: `tentativas` e `ultimo_erro` dos eventos são preservados; eventos já
entregues não estão na fila, portanto não são reenviados.
