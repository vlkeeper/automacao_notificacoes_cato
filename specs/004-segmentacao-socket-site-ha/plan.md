# Implementation Plan: Aviso único por socket em sites HA

**Branch**: `004-segmentacao-socket-site-ha` | **Date**: 2026-10-14 | **Spec**: [spec.md](spec.md)

**Input**: especificação da feature em `specs/004-segmentacao-socket-site-ha/spec.md`

## Summary

Hoje, em um site HA, a queda de um socket inteiro vira um `REDE OFFLINE` por porta. A feature
introduz o **socket** como terceiro tipo de item monitorado, só em sites HA. `snapshot.py` passa a
informar se cada socket está conectado (`device.connected`, com reserva em "todas as WANs offline").
O motor aplica a mesma `proximo_estado` (mesma tolerância) ao socket e emite **um** `SOCKET_OFFLINE`
e **um** `SOCKET_RETORNO` ("SOCKET DE VOLTA"). Enquanto o socket está fora, as portas dele ficam
silenciadas. A queda do site absorve os sockets (`coberto_pelo_site`, como já é feito com os links).
No retorno parcial do site, o motor emite "SITE DE VOLTA" seguido de "SOCKET OFFLINE". O estado do
socket é persistido em `Site.sockets` (campo aditivo, sem mudar `schema_version`). Os avisos novos
vão para o canal de rede, e o lembrete mostra uma linha por socket offline. Sites sem HA não
executam nenhum código novo.

## Technical Context

**Language/Version**: Python 3.12 (sem mudança).

**Primary Dependencies**: `requests`, `tzdata` (runtime); `pytest`, `responses` (dev). Nenhuma
dependência nova.

**Storage**: `${STATE_DIR}/state.json`, `schema_version: 2`, com o novo campo `sites.<id>.sockets`
(aditivo, [R-007](research.md)). A gravação atômica não muda.

**Testing**: pytest com relógio injetado; motor testado como função pura; `responses` nos cenários
de integração.

**Target Platform**: contêiner Docker Linux, instância única (sem mudança).

**Project Type**: daemon de linha de comando (projeto único).

**Performance Goals**: sem impacto mensurável. São alguns itens a mais por site HA, avaliados no
mesmo ciclo. O aviso chega no mesmo prazo dos demais (tolerância + 1 intervalo).

**Constraints**: a query da Cato não muda (`connected`, `isHA` e `socketInfo` já são consultados).
Lógica de transição pura (Princípio III). Sem acesso a banco (Princípio VIII).

**Scale/Scope**: pares HA primário/secundário. Mais de dois sockets está fora do escopo (spec,
Assumptions); o código trata N sockets de forma genérica, mas só o par é testado.

Não há `NEEDS CLARIFICATION`; as decisões estão em [research.md](research.md) (R-001..R-009).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Como o plano atende | Pré | Pós |
|---|---|---|---|
| I. Resiliência de Estado | O socket é persistido no `state.json` com a mesma gravação atômica. O campo aditivo carrega estados antigos como `{}` (R-007). As invariantes de `verificar_invariantes` passam a valer para sockets, e um socket inválido faz o estado ser tratado como corrompido (linha de base, um aviso). Um reinício com socket offline não duplica avisos (FR-008). | ✅ | ✅ |
| II. Falha de Observação ≠ Evento | Consulta com falha não muda sockets (o motor sai antes). Socket ausente numa resposta válida fica inalterado e só sai do inventário após `LIMITE_AUSENCIAS`, sem aviso. A reserva "todas as WANs offline" só vale com ≥ 1 WAN observada (R-001). | ✅ | ✅ |
| III. Máquina de Estados Explícita | Reusa `proximo_estado`, estendido ao tipo `Socket`. O motor continua puro e com relógio injetado. Cada linha das tabelas do [data-model §3](data-model.md) tem teste. Timestamps em UTC ISO 8601. | ✅ | ✅ |
| IV. Anti-Fadiga | Esta é a motivação da feature: troca N avisos por porta por um aviso de socket. A tolerância é a mesma. O retorno só é avisado se a queda foi avisada. Quando o site está pendente, a queda do socket espera para evitar SOCKET + SITE. A queda do site absorve os sockets. O lembrete mostra uma linha por socket. | ✅ | ✅ |
| V. Rede Defensiva / Sem Perda | Não alterado. Os eventos novos usam a fila persistida do canal de rede, na mesma ordem dos `SITE_*`/`LINK_*`. | ✅ | ✅ |
| VI. Segredos e Fail-Fast | Sem configuração nova. Nenhum segredo envolvido. | ✅ | ✅ |
| VII. Observabilidade | As transições de socket aparecem nos logs (`item: "socket"`), assim como inventário novo e removido. Heartbeat e healthcheck intactos. | ✅ | ✅ |
| VIII. Persistência em Banco é Secundária | Sem acesso a banco. A integração com o histórico da 002 (ainda não implementada) fica registrada como dependência dela (R-009). | ✅ | ✅ |

**Resultado**: aprovado antes e depois do design. Sem desvios.

**Ponto de atenção (não é violação)**: a feature supõe que a Cato mantém o device desconectado em
`devices` com `connected=false`. Isso precisa ser confirmado na conta real antes de publicar
([quickstart §3](quickstart.md)).

## Project Structure

### Documentation (this feature)

```text
specs/004-segmentacao-socket-site-ha/
├── plan.md                      # Este arquivo
├── research.md                  # Fase 0 — decisões R-001..R-009
├── data-model.md                # Fase 1 — Socket, ObservacaoSocket, transições, eventos
├── quickstart.md                # Fase 1 — roteiro de validação
├── contracts/
│   ├── avisos-socket.md         # cards SOCKET OFFLINE / SOCKET DE VOLTA, roteamento, sequências
│   └── state-file-sockets.md    # campo aditivo sites.<id>.sockets
└── tasks.md                     # Fase 2 (/speckit-tasks — não criado aqui)
```

### Source Code (repository root)

```text
src/cato_monitor/
├── modelos.py         # + Socket, ObservacaoSocket, Site.sockets (leitura tolerante),
│                      #   ObservacaoSite.sockets, TipoEvento.SOCKET_OFFLINE/SOCKET_RETORNO,
│                      #   invariantes de socket
├── snapshot.py        # + sockets por device em site HA (connected + reserva WAN), HA via isHA
├── transicoes.py      # Item aceita Socket; _limpar zera coberto_pelo_site de Socket
├── motor.py           # + socket_do_link, avaliação de sockets, silêncio dos links, cobertura
│                      #   pelo site, pendências/linha de base com tipo SOCKET
├── cards.py           # + cards SOCKET_OFFLINE e SOCKET_RETORNO; linha SOCKET no lembrete e no
│                      #   MONITOR INICIADO
└── canais.py          # + SOCKET_OFFLINE/SOCKET_RETORNO → Canal.REDE

tests/
├── unit/test_motor_socket.py      # NOVO: transições de socket e efeitos nos links
├── unit/test_snapshot.py          # + connected/reserva/isHA/LAN ignorada/site não-HA
├── unit/test_transicoes.py        # + Socket em proximo_estado
├── unit/test_estado_store.py      # + estado sem sockets carrega como {}; invariante de socket
├── unit/test_cards.py + snapshots/SOCKET_OFFLINE.json, SOCKET_RETORNO.json
├── unit/test_lembrete.py          # + 1 pendência por socket, portas omitidas
├── unit/test_canais.py            # + mapeamento dos tipos novos
├── integration/test_cenarios.py   # + sequências do contrato, reinício, regressão não-HA
└── helpers.py                     # + obs_socket / sockets em obs_site

README.md, changelog.md, specs/001-cato-socket/contracts/teams-webhook.md (nota de que o 004 altera)
```

**Structure Decision**: projeto único existente. Nenhum módulo novo. A regra fica em `motor.py`
(puro) e a leitura do campo da Cato fica em `snapshot.py`, mantendo a separação atual.
`daemon.py`, `teams.py`, `estado_store.py` e `cato_client.py` não mudam. O `estado_store` só herda
a leitura tolerante via `Site.de_dict`.

## Complexity Tracking

Sem violações da constituição a justificar. A complexidade nova se concentra em `_avaliar_site`
(sockets entre o passo do site e o dos links). Ela é contida pela reutilização de `proximo_estado` e
do padrão `coberto_pelo_site` já existente.
