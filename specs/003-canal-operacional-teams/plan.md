# Implementation Plan: Canal Operacional Separado no Teams

**Branch**: `003-canal-operacional-teams` | **Date**: 2026-10-14 | **Spec**: [spec.md](spec.md)

**Input**: especificação da feature em `specs/003-canal-operacional-teams/spec.md`

## Summary

Hoje existe **uma** fila global `pendente_envio` drenada para **um** webhook (`teams.drenar`, com
*head-of-line*). A feature troca isso por **duas filas persistidas** (`rede` e `operacional`), cada
uma com seu webhook. Um **mapeamento fixo tipo → canal** (módulo puro `canais.py`) decide o destino
no momento em que o evento é gerado. A drenagem dos dois canais roda em **paralelo** (uma thread por
canal) para que um canal lento ou fora do ar não atrase o outro. Uma função pura avalia, por canal,
há quanto tempo a entrega falha e gera os avisos únicos "CANAL … SEM ENTREGA" e normalização no
**outro** canal. O `state.json` sobe para `schema_version: 2` e a migração v1 → v2 distribui a fila
antiga pelo tipo do evento, uma única vez, com cópia de segurança do arquivo v1. A máquina de
estados, o motor e o heartbeat não mudam.

## Technical Context

**Language/Version**: Python 3.12 (sem mudança).

**Primary Dependencies**: `requests`, `tzdata` (runtime); `pytest`, `responses` (dev). Nenhuma
dependência nova: a paralelização usa `threading` da biblioteca padrão.

**Storage**: `${STATE_DIR}/state.json`, agora `schema_version: 2` (campos `filas` e `entrega`),
mesma gravação atômica (`.tmp` + `fsync` + `os.replace`). Cópia `state.json.v1-<UTC>` criada antes da
migração.

**Testing**: pytest, relógio injetado, `responses` para HTTP, em `tests/unit` e `tests/integration`.

**Target Platform**: contêiner Docker Linux, instância única (sem mudança).

**Project Type**: daemon de linha de comando (projeto único, sem mudança).

**Performance Goals**: com um canal indisponível, o outro entrega no prazo atual (SC-002). Aviso de
"sem entrega" em até 15 min + 1 intervalo (SC-005).

**Constraints**: timeouts `(5, 10)` e backoff com `Retry-After` por canal, como hoje. Máximo de 20
envios por canal por ciclo. Princípio VIII: nenhuma dependência de banco nesta feature.

**Scale/Scope**: poucos avisos operacionais por dia; avisos de rede como hoje.

Não há `NEEDS CLARIFICATION`; as decisões abertas estão resolvidas em [research.md](research.md).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Como o plano atende | Pré | Pós |
|---|---|---|---|
| I. Resiliência de Estado | Cada fila é persistida de forma atômica. O evento só sai da fila após 2xx do **seu** canal. A migração v1 → v2 é gravada atomicamente, idempotente (a versão 2 não migra de novo) e precedida de cópia do v1 (R-004). Estado corrompido segue a regra atual (linha de base, 1 aviso). `schema_version` > 2 sai com `exit 1`. | ✅ | ✅ |
| II. Falha de Observação ≠ Evento | Não alterado. O canal só muda o destino do aviso `MONITOR_FALHA`/`MONITOR_RECUPERADO`. A falha de **entrega** de um canal não altera nenhum item monitorado. | ✅ | ✅ |
| III. Máquina de Estados Explícita | `transicoes.py` e `motor.py` intactos. O mapeamento tipo → canal e `avaliar_entrega` são funções puras com relógio injetado. Timestamps UTC ISO 8601. | ✅ | ✅ |
| IV. Anti-Fadiga | "Sem entrega" é emitido uma única vez por sequência de falha e a normalização uma única vez (`aviso_emitido`). Falhas com menos de 15 min não geram nada (R-003). Os textos dos avisos existentes não mudam (FR-012). | ✅ | ✅ |
| V. Rede Defensiva / Sem Perda | Timeouts, backoff e `Retry-After` por canal. Nenhum evento é descartado. Cada fila é ordenada e reenviada em ordem (*head-of-line* **por canal**). Exceção em uma thread de envio é capturada e não derruba o laço (R-002). | ✅ | ✅ |
| VI. Segredos e Fail-Fast | O novo webhook é env, validado `https://`, mascarado (host) e incluído em `Config.segredos()`. Ausente ou inválido → `exit 1` junto dos demais erros (R-005). | ✅ | ✅ |
| VII. Observabilidade | Log `envio_teams` ganha o campo `canal`. Novos eventos `canal_sem_entrega` e `canal_normalizado`. Heartbeat e healthcheck intactos; heartbeat não envia nada ao Teams (FR-005). | ✅ | ✅ |
| VIII. Persistência em Banco é Secundária | Fora do escopo, sem acesso a banco. Os avisos de falha de gravação da feature 002 só precisam ser **registrados** no mapeamento como canal operacional (R-006). A falha do canal operacional não bloqueia o canal de rede. | ✅ | ✅ |

**Resultado**: aprovado antes e depois do design.

**Desvio registrado (não viola a constituição)**: o Princípio V pede reenvio "na ordem". A ordem
passa a ser garantida **por canal**, não globalmente (spec, Edge Cases). Isso é intencional: uma fila
global faria um canal fora do ar bloquear o outro. Os pares que dependem de ordem (queda → retorno,
falha → normalização) sempre caem no mesmo canal.

## Project Structure

### Documentation (this feature)

```text
specs/003-canal-operacional-teams/
├── plan.md                  # Este arquivo
├── research.md              # Fase 0 — decisões R-001..R-008
├── data-model.md            # Fase 1 — canais, filas, situação de entrega, migração
├── quickstart.md            # Fase 1 — roteiro de validação
├── contracts/
│   ├── configuracao.md      # nova variável TEAMS_WEBHOOK_OPERACIONAL_URL (delta do 001)
│   ├── teams-canais.md      # roteamento tipo → canal e avisos "sem entrega" (delta do 001)
│   └── state-file-v2.md     # mudanças do state.json v1 → v2
└── tasks.md                 # Fase 2 (/speckit-tasks — não criado aqui)
```

### Source Code (repository root)

```text
src/cato_monitor/
├── canais.py          # NOVO: Canal, canal_do_evento(), avaliar_entrega() — puro
├── modelos.py         # + TipoEvento.CANAL_SEM_ENTREGA/CANAL_NORMALIZADO, SituacaoEntrega,
│                      #   EstadoMonitor.filas/entrega (substitui pendente_envio), SCHEMA_VERSION=2
├── estado_store.py    # carregar(): migração v1 → v2 com cópia de segurança
├── config.py          # + teams_webhook_operacional_url (obrigatório, segredo)
├── cards.py           # + cards CANAL_SEM_ENTREGA e CANAL_NORMALIZADO
├── teams.py           # drenar_canal(canal) + drenar_todos() com uma thread por canal
├── daemon.py          # distribui eventos por canal, drena, avalia entrega, persiste
└── __main__.py        # só ajusta o log de `pendentes` (soma das filas)

tests/
├── unit/test_canais.py            # NOVO: mapeamento completo e avaliar_entrega
├── unit/test_estado_store.py      # + migração v1 → v2, idempotência, v3 → exit 1
├── unit/test_config.py            # + webhook operacional ausente/inválido/mascarado
├── unit/test_cards.py + snapshots/CANAL_SEM_ENTREGA.json, CANAL_NORMALIZADO.json
├── integration/test_teams.py      # + isolamento entre canais, ordem por canal
├── integration/test_cenarios.py   # + roteamento ponta a ponta, reinício sem duplicar
└── helpers.py / conftest.py       # filas por canal e webhook operacional de teste

.env.example, README.md, changelog.md, specs/001-cato-socket/contracts/* (nota de que o 003 altera)
```

**Structure Decision**: projeto único existente. Um módulo novo pequeno (`canais.py`) concentra a
regra de roteamento e a avaliação de entrega, mantendo `teams.py` só com HTTP e drenagem. Nenhum
serviço, processo ou dependência novos.

## Complexity Tracking

Sem violações da constituição a justificar. A única complexidade nova é a drenagem em duas threads
([R-002](research.md)); a alternativa sequencial foi rejeitada por atrasar o canal saudável em até
~32 s por ciclo quando o outro está fora.
