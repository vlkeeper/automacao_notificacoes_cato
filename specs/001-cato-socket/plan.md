# Implementation Plan: Monitoramento de Sockets Cato com Avisos no Teams

**Branch**: `001-cato-socket` (diretório da feature: `specs/001-cato-socket`) | **Date**: 2026-10-06 | **Spec**: [spec.md](spec.md)

**Input**: especificação da feature em `specs/001-cato-socket/spec.md`

## Summary

O monitor é um daemon Python 3.12 em contêiner. Ele consulta periodicamente a API GraphQL da Cato
com **uma única** query `accountSnapshot` (todos os sites, sockets e portas LAN/WAN), normaliza a
resposta num `Snapshot` validado e alimenta uma **máquina de estados pura** (`ONLINE`,
`PENDENTE_OFFLINE`, `OFFLINE_NOTIFICADO`) com relógio injetável. As transições geram eventos que vão
para uma fila persistida (`pendente_envio`). A fila é drenada em ordem para um fluxo do **Teams
Workflows**, como Adaptive Cards. O estado fica num JSON gravado de forma atômica num volume, com
lock de instância única. Uma falha de consulta nunca altera itens: ela só conta para o alerta do
monitor (5 falhas). A observabilidade tem três partes: logs JSON mascarados, healthcheck pela idade
do último ciclo e heartbeat externo (Healthchecks.io).

## Technical Context

**Language/Version**: Python 3.12 (imagem `python:3.12.x-slim-bookworm` fixada por digest)

**Primary Dependencies**: runtime `requests` e `tzdata`; dev `pytest` e `responses`. Versões exatas
com hashes via `pip-compile` (R-011). Sem framework web.

**Storage**: arquivo JSON `${STATE_DIR}/state.json` (`schema_version: 1`), com escrita `.tmp`,
`fsync` e `os.replace`; mais `last_cycle` (healthcheck) e `monitor.lock` (`flock`), tudo num único
volume.

**Testing**: pytest, relógio injetado, `responses` para HTTP e payloads reais anonimizados da Cato
em `tests/fixtures/cato/`.

**Target Platform**: Linux (contêiner Docker) numa VM com Docker Compose, **fora da rede
monitorada** e com NTP ativo.

**Project Type**: daemon/serviço de linha de comando (projeto único).

**Performance Goals**: ciclo de ≤ 60 s (padrão). Aviso no Teams em ≤ 1 intervalo + 1 min após o fim da tolerância
(≤ 2 min no padrão de 60 s; SC-002). Uma requisição à Cato por ciclo.

**Constraints**: somente leitura na Cato. Timeouts explícitos em toda chamada. Backoff limitado com
`Retry-After`. Intervalo de 30 a 120 s. Usuário não-root, FS raiz *read-only* e uma única réplica.
Memória < 128 MB.

**Scale/Scope**: dezenas de sites e centenas de links numa conta Cato, e um canal do Teams.

Não há `NEEDS CLARIFICATION`. O schema exato dos campos de papel da porta (LAN/WAN) é um **passo
de verificação** com o Cato CLI, descrito em [research.md R-001](research.md) e isolado em
`snapshot.py`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Como o plano atende | Pré | Pós |
|---|---|---|---|
| I. Resiliência de Estado | JSON atômico (`.tmp` + `fsync` + `os.replace`) no volume `/data`, relido no start. Evento marcado "enviado" só após 2xx. Estado corrompido gera linha de base com 1 `MONITOR_INICIADO` (R-004, R-006). Testes de interrupção na escrita, reinício na tolerância e arquivo corrompido. | ✅ | ✅ |
| II. Falha de Observação ≠ Evento | O cliente retorna `ConsultaOk`/`ConsultaFalhou`, e só o sucesso alimenta transições. Item ausente é observação inválida (remoção só após 3 ausências). Contador persistido; `MONITOR_FALHA` 1x por sequência + `MONITOR_RECUPERADO` (R-002, data-model §3.2). | ✅ | ✅ |
| III. Máquina de Estados Explícita | `proximo_estado` e `avaliar_ciclo` são puras, sem I/O nem relógio global. UTC interno em ISO 8601 `+00:00`. `America/Sao_Paulo` só no lembrete e na exibição. Durações por timestamp. Um teste por linha da tabela (R-003). | ✅ | ✅ |
| IV. Anti-Fadiga | Tolerância de 180 s. Queda 1x por episódio. Distinção `LINK OFFLINE`/`SITE OFFLINE`. Supressão e adiamento de links enquanto o site está pendente ou offline. Reavaliação no retorno do site. Lembrete 1x/dia só com pendências, com data persistida (R-003, R-005). | ✅ | ✅ |
| V. Rede Defensiva / Sem Perda | Timeouts `(5, 20)` e `(5, 10)`. Backoff exponencial com teto e `Retry-After`. Fila global `pendente_envio` persistida e ordenada, com *head-of-line*. Intervalo com piso de 30 s. Nenhuma exceção de rede encerra o laço (R-002, R-007). | ✅ | ✅ |
| VI. Segredos e Fail-Fast | Segredos só via env. Filtro de redação nos logs (incluindo tracebacks). Validação completa com `exit 1`. Token somente leitura. `.env` no `.gitignore` e no `.dockerignore`. `Dockerfile` sem `ENV`/`ARG` de segredo (R-008, R-009). | ✅ | ✅ |
| VII. Observabilidade | Log `ciclo_concluido` estruturado. `HEALTHCHECK` pela idade de `last_cycle` (3 × intervalo + 30 s). Heartbeat após cada ciclo, com `/fail` após 5 falhas; a falha do heartbeat não interrompe o monitor (R-010). | ✅ | ✅ |

**Resultado**: aprovado antes e depois do design, sem exceções.

**Desvio registrado em relação ao pedido (não à constituição)**: `pendente_envio` e a data do
último lembrete são **globais**, não por site/link, para preservar a ordem entre itens (FR-009) e
porque o lembrete é uma mensagem única. A justificativa está em [research.md R-006](research.md).

**Alerta de repositório**: o `.gitignore` e o `.dockerignore` aparecem **apagados** no working tree,
e há um `.env` não rastreado. Recriar os dois arquivos é a **primeira tarefa** da implementação, para
não violar o Princípio VI.

## Project Structure

### Documentation (this feature)

```text
specs/001-cato-socket/
├── plan.md              # Este arquivo
├── research.md          # Fase 0 — decisões R-001..R-012
├── data-model.md        # Fase 1 — entidades, invariantes, transições
├── quickstart.md        # Fase 1 — roteiro de validação ponta a ponta
├── contracts/
│   ├── cato-graphql.md          # query/resposta da Cato (consumido)
│   ├── teams-webhook.md         # payload Adaptive Card (produzido)
│   ├── configuracao.md          # variáveis de ambiente e códigos de saída
│   ├── observabilidade.md       # logs, healthcheck, heartbeat
│   └── state-file.schema.json   # JSON Schema do state.json v1
└── tasks.md             # Fase 2 (/speckit-tasks — não criado aqui)
```

### Source Code (repository root)

```text
pyproject.toml                 # metadados, pacote src/cato_monitor, config do pytest
requirements.in / requirements.txt          # runtime (pip-compile --generate-hashes)
requirements-dev.in / requirements-dev.txt  # pytest, responses
Dockerfile                     # multi-stage, não-root, HEALTHCHECK
docker-compose.yml             # 1 serviço, volume monitor-data:/data, restart
.env.example  .gitignore  .dockerignore

src/cato_monitor/
├── __init__.py
├── __main__.py        # entrada: config → logging → lock → estado → daemon.run()
├── config.py          # leitura/validação de env, mascaramento (Config imutável)
├── logs.py            # JsonFormatter + RedactingFilter
├── relogio.py         # Protocol Relogio, RelogioSistema (UTC)
├── modelos.py         # dataclasses: EstadoMonitor, Site, Link, Evento, Snapshot, ResultadoConsulta
├── cato_client.py     # requests + backoff → ConsultaOk/ConsultaFalhou
├── snapshot.py        # resposta GraphQL → Snapshot normalizado (único ponto que conhece o schema Cato)
├── transicoes.py      # proximo_estado() — pura
├── motor.py           # avaliar_ciclo() — pura (supressão, linha de base, lembrete, monitor)
├── estado_store.py    # load/save atômico, schema_version, corrompido→linha de base, lock
├── cards.py           # Evento → Adaptive Card (pura; textos e formatação Brasília)
├── teams.py           # envio + drenagem da fila (head-of-line)
├── heartbeat.py       # ping ok/fail
├── healthcheck.py     # `python -m cato_monitor.healthcheck`
└── daemon.py          # laço: consulta → motor → persistir → enviar → last_cycle → heartbeat → dormir

tests/
├── conftest.py        # RelogioFake, fábrica de Config, tmp STATE_DIR
├── fixtures/cato/     # payloads reais anonimizados (ver contracts/cato-graphql.md)
├── unit/              # transicoes, motor, lembrete, config, logs, estado_store, cards, snapshot
└── integration/       # cato_client, teams, heartbeat, test_cenarios (ciclos completos)
```

**Structure Decision**: projeto único com *src layout* (`src/cato_monitor/`). Os arquivos atuais
`main.py` e `src/{cato_api,config,monitor,notifier,state}.py` estão **vazios** e serão removidos em
favor do pacote acima. O núcleo puro (`transicoes`, `motor`, `cards`, `snapshot`) fica separado dos
módulos com I/O (`cato_client`, `teams`, `heartbeat`, `estado_store`, `daemon`), e o laço é o único
lugar que executa efeitos (Princípio III).

### Fluxo de um ciclo (`daemon.py`)

1. `agora = relogio.agora()`
2. `resultado = cato_client.consultar()`, que nunca levanta exceção
3. `estado, eventos = motor.avaliar_ciclo(estado, resultado, agora, cfg)`
4. `estado.pendente_envio += eventos` e `estado_store.salvar(estado)` (**antes** de enviar)
5. `teams.drenar(estado, ...)`: a cada 2xx, remove o evento e salva; na primeira falha, para
6. Atualiza `ultimo_ciclo_concluido_em`, salva, grava `last_cycle` e chama `heartbeat.ping(ok|fail)`
7. Registra `ciclo_concluido` e dorme até `inicio + INTERVALO` (relógio monotônico; SIGTERM
   interrompe a espera)

## Complexity Tracking

Nenhuma violação da constituição a justificar.
