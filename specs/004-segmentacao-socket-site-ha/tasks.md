# Tasks: Aviso único por socket em sites HA

**Input**: `specs/004-segmentacao-socket-site-ha/` (spec.md, plan.md, research.md, data-model.md, contracts/, quickstart.md)

**Prerequisites**: plan.md, spec.md

**Tests**: incluídos — o plano e o quickstart exigem um teste por linha das tabelas de transição (data-model §3), snapshots de cards e cenários de integração.

**Organization**: tarefas agrupadas por user story. Projeto único: `src/cato_monitor/`, `tests/` na raiz.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: paralelizável (arquivos diferentes, sem dependência pendente)
- **[Story]**: US1..US4 (spec.md)

---

## Phase 1: Setup

**Purpose**: Confirmar a base antes de alterar.

- [ ] T001 Rodar `python -m pytest tests -q` na branch e registrar que a suíte atual está verde (linha de base de regressão).
- [ ] T002 [P] Adicionar helpers `obs_socket(...)` e parâmetro `sockets=` em `obs_site(...)` em `tests/helpers.py` (usados por todos os testes novos; `conectado` padrão `True`, `nome` padrão `"primário"`).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Modelo, leitura da Cato e reuso da máquina de estados. Bloqueia todas as stories.

- [ ] T003 Em `src/cato_monitor/modelos.py`: criar dataclass `Socket` com os campos de data-model §2 (`nome`, `estado: EstadoItem`, `inicio_queda`, `notificado`, `coberto_pelo_site`, `origem`, `ausencias`) com `para_dict`/`de_dict` no mesmo padrão de `Link`.
- [ ] T004 Em `src/cato_monitor/modelos.py`: adicionar `Site.sockets: dict[str, Socket]` — sempre gravado em `para_dict`; em `de_dict`, chave ausente equivale a `{}` (R-007, `schema_version` continua 2).
- [ ] T005 Em `src/cato_monitor/modelos.py`: adicionar `TipoEvento.SOCKET_OFFLINE` e `TipoEvento.SOCKET_RETORNO`; criar `ObservacaoSocket(nome: str, conectado: bool)` e `ObservacaoSite.sockets: dict[str, ObservacaoSocket]` (vazio por padrão).
- [ ] T006 Em `src/cato_monitor/modelos.py`: estender `verificar_invariantes` para sockets com as mesmas invariantes de `Link` (ONLINE sem `inicio_queda`/`notificado`/`coberto_pelo_site`; fora de ONLINE com `inicio_queda`; OFFLINE_NOTIFICADO com `notificado`).
- [ ] T007 [P] Em `src/cato_monitor/transicoes.py`: fazer `Item`/`proximo_estado`/`_limpar` aceitarem `Socket` (zerar `coberto_pelo_site` como para `Link`). Teste em `tests/unit/test_transicoes.py`.
- [ ] T008 [P] Em `src/cato_monitor/canais.py`: mapear `SOCKET_OFFLINE` e `SOCKET_RETORNO` para `Canal.REDE` em `MAPA_CANAL`. Teste em `tests/unit/test_canais.py` (mapeamento completo inclui os tipos novos).
- [ ] T009 Em `src/cato_monitor/motor.py`: adicionar função pura `socket_do_link(link_id) = link_id.split("/", 1)[0]` e `_novo_socket(obs, agora)` análogo a `_novo_link`/`_novo_site` (linha de base: socket desconectado em site online entra `OFFLINE_NOTIFICADO`, `origem = linha_base`, R-008).
- [ ] T010 [P] Teste em `tests/unit/test_estado_store.py`: estado v2 sem `sockets` carrega como `{}`; socket com invariante violada faz o estado ser tratado como corrompido.

**Checkpoint**: modelo e utilitários prontos.

---

## Phase 3: User Story 1 - Um único aviso quando um socket inteiro cai (P1) 🎯 MVP

**Goal**: socket HA desconectado (com o outro conectado) gera um único `SOCKET OFFLINE`, sem `REDE OFFLINE` das portas dele.

**Independent Test**: site HA com um socket `connected=false` e outro conectado → 1 `SOCKET_OFFLINE` identificando primário/secundário, 0 `LINK_OFFLINE` dele; mudanças de porta durante a queda não geram aviso.

### Tests for US1

- [ ] T011 [P] [US1] Em `tests/unit/test_snapshot.py`: casos `connected` presente (true/false), ausente com todas as WANs offline → `conectado=False`, ausente sem WAN observada → `True`, LAN/"HA link" ignorados, `isHA=true` com um único device listado, site não-HA com `sockets == {}`.
- [ ] T012 [P] [US1] Criar `tests/unit/test_motor_socket.py` com: QUEDA após tolerância emite 1 `SOCKET_OFFLINE`; PENDENTE antes da tolerância não emite; links `PENDENTE_OFFLINE` do socket voltam a `ONLINE`; links `OFFLINE_NOTIFICADO` ficam inalterados e silenciados; queda/volta de porta com socket offline não emite nada; socket sem observação fica inalterado; QUEDA de socket adiada quando o site está `PENDENTE_OFFLINE`.
- [ ] T013 [P] [US1] Em `tests/unit/test_cards.py`: snapshot `tests/unit/snapshots/SOCKET_OFFLINE.json` (FactSet Site/Socket/Desde + texto de contracts/avisos-socket.md).

### Implementation for US1

- [ ] T014 [US1] Em `src/cato_monitor/snapshot.py`: determinar site HA por `info.isHA is True` ou `len(devices) > 1` (R-002) e usar a mesma regra em `_rotulo_socket`; preencher `ObservacaoSite.sockets` por device (chave `socketInfo.id` ou `device.id`) com `conectado` conforme R-001; sites não-HA não preenchem nada.
- [ ] T015 [US1] Em `src/cato_monitor/motor.py` `_avaliar_site`: criar o passo de sockets (ordem de chave, após o passo do site e antes dos links): inventário (criar/atualizar `nome`/`ausencias`, remoção após `LIMITE_AUSENCIAS` sem aviso), `proximo_estado` com `obs_offline = not conectado`, emitir `SOCKET_OFFLINE` (`socket_id`, `socket`, `inicio_queda`) na QUEDA, e registrar em `det.transicoes` com `item: "socket"`/`socket_id`.
- [ ] T016 [US1] Em `src/cato_monitor/motor.py` `_avaliar_site`: no passo dos links, pular links cujo `socket_do_link` esteja `OFFLINE_NOTIFICADO`/coberto, adiar QUEDA de link se o socket está `PENDENTE_OFFLINE`, e na QUEDA do socket voltar links `PENDENTE_OFFLINE` a `ONLINE` (data-model §3 "Efeitos sobre os links").
- [ ] T017 [US1] Em `src/cato_monitor/motor.py`: adiar a QUEDA do socket quando o site está `PENDENTE_OFFLINE` (estado não aplicado, reavaliado no ciclo seguinte).
- [ ] T018 [P] [US1] Em `src/cato_monitor/cards.py`: `_socket_offline` (🟠 style `warning`, texto do contrato) registrado em `renderizar`.

**Checkpoint**: US1 funcional e testável sozinha (MVP).

---

## Phase 4: User Story 2 - Aviso único quando o socket retorna (P1)

**Goal**: retorno do socket gera um único `SOCKET DE VOLTA`, sem `REDE DE VOLTA` por porta.

**Independent Test**: após `SOCKET_OFFLINE`, socket volta → 1 `SOCKET_RETORNO`; portas que voltaram junto encerram sem aviso; a que segue fora continua aberta e seu retorno posterior gera `LINK_RETORNO` (FR-003a).

### Tests for US2

- [ ] T019 [P] [US2] Em `tests/unit/test_motor_socket.py`: RETORNO emite 1 `SOCKET_RETORNO` (`inicio_queda`, `retorno_em`); links `OFFLINE_NOTIFICADO` online agora → `ONLINE` sem aviso; link ainda offline continua aberto sem novo `LINK_OFFLINE` e seu retorno posterior emite `LINK_RETORNO`; link `ONLINE` offline no retorno segue PENDENTE → tolerância → `LINK_OFFLINE`.
- [ ] T020 [P] [US2] Em `tests/unit/test_cards.py`: snapshot `tests/unit/snapshots/SOCKET_RETORNO.json` (FactSet Site/Socket/Desde/Duração).

### Implementation for US2

- [ ] T021 [US2] Em `src/cato_monitor/motor.py` `_avaliar_site`: no RETORNO do socket emitir `SOCKET_RETORNO` (só se a queda foi avisada) e aplicar a regra de links do retorno (data-model §3, R-006) no mesmo ciclo.
- [ ] T022 [P] [US2] Em `src/cato_monitor/cards.py`: `_socket_retorno` (🟢 style `good`, `formatar_duracao`, texto do contrato) registrado em `renderizar`.

**Checkpoint**: US1 + US2 completas (ciclo queda/retorno do socket).

---

## Phase 5: User Story 3 - Site inteiro offline mantém apenas SITE OFFLINE (P2)

**Goal**: queda do site absorve sockets; retorno parcial do site gera `SITE DE VOLTA` e depois `SOCKET OFFLINE`.

**Independent Test**: ambos os sockets caem → só `SITE_OFFLINE`; um volta → `SITE_RETORNO` seguido de `SOCKET_OFFLINE` do que segue fora; o último volta → `SOCKET_RETORNO`.

### Tests for US3

- [ ] T023 [P] [US3] Em `tests/unit/test_motor_socket.py`: QUEDA do site marca todos os sockets `OFFLINE_NOTIFICADO` com `coberto_pelo_site=True` sem avisos de socket (inclui socket já avisado antes); site `OFFLINE_NOTIFICADO` não avalia sockets; retorno do site com socket coberto conectado → `ONLINE` sem aviso; com socket coberto desconectado → `coberto_pelo_site=False` e `SOCKET_OFFLINE` após `SITE_RETORNO` do mesmo ciclo; socket coberto sem observação segue coberto; `links_ainda_offline` do `SITE_RETORNO` omite links de sockets ainda desconectados.

### Implementation for US3

- [ ] T024 [US3] Em `src/cato_monitor/motor.py`: na QUEDA confirmada do site, marcar todos os sockets como `OFFLINE_NOTIFICADO`, `notificado=True`, `coberto_pelo_site=True`, preservando `inicio_queda` do socket (ou o do site), sem evento (R-005).
- [ ] T025 [US3] Em `src/cato_monitor/motor.py`: no ciclo do RETORNO do site (e em ciclos seguintes com site online), resolver sockets cobertos conforme a tabela data-model §3, emitindo `SOCKET_OFFLINE` depois do `SITE_RETORNO`; excluir de `links_ainda_offline` os links de sockets ainda desconectados.
- [ ] T026 [P] [US3] Em `src/cato_monitor/transicoes.py`/`modelos.py`: garantir que `coberto_pelo_site` de `Socket` é zerado ao voltar para `ONLINE` (verificado pelas invariantes de T006).

**Checkpoint**: US1–US3 completas.

---

## Phase 6: User Story 4 - Sites sem HA inalterados + lembrete (P2)

**Goal**: nenhum código novo roda em site sem HA; lembrete e MONITOR INICIADO mostram uma linha por socket offline.

**Independent Test**: site de socket único com WAN offline → `REDE OFFLINE`/`REDE DE VOLTA` idênticos aos de antes; com socket offline, `PENDÊNCIAS DO DIA` lista 1 linha "Socket {rótulo} (inteiro)" e nenhuma porta dele.

### Tests for US4

- [ ] T027 [P] [US4] Em `tests/integration/test_cenarios.py`: regressão de site não-HA (`sockets == {}` no estado, avisos idênticos aos de antes).
- [ ] T028 [P] [US4] Em `tests/unit/test_lembrete.py`: 1 pendência `tipo="SOCKET"` por socket offline notificado e não coberto; portas desse socket omitidas; socket coberto não aparece com site offline.

### Implementation for US4

- [ ] T029 [US4] Em `src/cato_monitor/motor.py` `_pendencias`: emitir item `{"site_nome", "link_nome": None, "tipo": "SOCKET", "socket": <rótulo>, "inicio_queda"}` por socket `OFFLINE_NOTIFICADO` não coberto e omitir links desses sockets (R-008); manter divisão por `_dividir_pendencias`.
- [ ] T030 [US4] Em `src/cato_monitor/cards.py` (`_lembrete` e `_monitor_iniciado`): renderizar item `tipo="SOCKET"` como "Socket {rótulo} (inteiro)" na coluna Porta/lista do site.
- [ ] T031 [US4] Em `src/cato_monitor/motor.py`: garantir que a linha de base (estado novo/corrompido, site novo) cria sockets desconectados de site online como `OFFLINE_NOTIFICADO` (`linha_base`) usando `_novo_socket` (T009), sem aviso por socket além do resumo MONITOR INICIADO.

**Checkpoint**: todas as stories completas.

---

## Phase 7: Polish & Cross-Cutting

- [ ] T032 [P] Em `tests/integration/test_cenarios.py`: sequências de contracts/avisos-socket.md (socket cai/volta; ambos caem; site volta com um; site volta com os dois; porta de socket offline cai/volta; reinício com socket offline sem duplicar e com retorno avisado — FR-008).
- [ ] T033 [P] Atualizar `README.md` e `changelog.md` (feature 004) e adicionar nota em `specs/001-cato-socket/contracts/teams-webhook.md` de que a 004 acrescenta os cards de socket.
- [ ] T034 Rodar `python -m pytest tests -q` completo e corrigir regressões.
- [ ] T035 Executar o roteiro de `specs/004-segmentacao-socket-site-ha/quickstart.md` §2–§6 contra um site HA de teste, confirmando em §3 que o device desconectado segue em `devices` com `connected: false` (R-002) antes de publicar.

---

## Dependencies & Execution Order

- **Phase 1** → **Phase 2** (bloqueia tudo) → US1 → US2 → US3 → US4 → Polish.
- US2 depende de US1 (mesmo passo de sockets em `motor.py`). US3 depende de US1/US2 (cobertura e retorno). US4 (T029–T031) depende de US1; T027/T028 podem ser escritos desde cedo.
- Tarefas em `motor.py` (T009, T015–T017, T021, T024, T025, T029, T031) editam o mesmo arquivo: executar em sequência.
- Dentro de cada story: testes [P] antes da implementação (devem falhar), depois snapshot → motor → cards.

## Parallel Opportunities

- Foundational: T007, T008, T010 em paralelo após T003–T005.
- US1: T011, T012, T013 e T018 em paralelo (arquivos distintos).
- US2: T019, T020, T022 em paralelo.
- US4: T027, T028 em paralelo.
- Polish: T032, T033 em paralelo.

## Implementation Strategy

- **MVP**: Phases 1–3 (US1) entregam o aviso único de queda; validar com T011–T013 e quickstart §2 (passos 1–3).
- **Incremental**: US2 fecha o ciclo (retorno); US3 evita duplicidade com SITE OFFLINE (necessário antes de produção); US4 cobre lembrete e regressão. Publicar só após T035.
