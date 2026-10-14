---

description: "Lista de tarefas: Canal Operacional Separado no Teams"
---

# Tasks: Canal Operacional Separado no Teams

**Input**: documentos de design em `specs/003-canal-operacional-teams/`

**Prerequisites**: plan.md, spec.md, research.md (R-001..R-008), data-model.md, contracts/, quickstart.md

**Tests**: INCLUÍDOS. A constituição (Fluxo de Desenvolvimento) exige testes automatizados com relógio
injetado e HTTP simulado, e os Princípios I e V exigem testes de persistência, migração e isolamento
entre canais.

**Organization**: tarefas agrupadas por user story (US1 e US2 são P1; US3 é P2).

## Format: `[ID] [P?] [Story] Descrição com caminho de arquivo`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência de tarefa incompleta)
- **[Story]**: US1..US3, conforme `spec.md`
- Código em `src/cato_monitor/`, testes em `tests/unit/` e `tests/integration/`
- Comentários, logs e textos de card em **português**, como no restante do projeto
- Executar testes com `python -m pytest tests -q` na raiz do repositório

---

## Phase 1: Setup

**Purpose**: confirmar a linha de base antes de mexer no estado e na fila

- [X] T001 Rodar `python -m pytest tests -q` na raiz e registrar que a suíte está verde antes das mudanças (linha de base; não editar arquivos)
- [X] T002 [P] Adicionar `TEAMS_WEBHOOK_OPERACIONAL_URL=https://exemplo.logic.azure.com/workflows/yyyy` em `.env.example`, logo após `TEAMS_WEBHOOK_URL`, com comentário em português dizendo que é o canal operacional (saúde do robô) e que `TEAMS_WEBHOOK_URL` passa a ser o canal de rede (conforme `contracts/configuracao.md`)

---

## Phase 2: Foundational (pré-requisitos bloqueantes)

**Purpose**: modelo de dados, mapeamento de canal, configuração e persistência v2, usados por todas as stories

**⚠️ CRITICAL**: nenhuma story começa antes desta fase. Ao final dela `teams.py` e `daemon.py` ainda usam
`pendente_envio` e a suíte só volta a ficar verde no fim da US1 (checkpoint abaixo).

- [X] T003 Em `src/cato_monitor/modelos.py`: (a) `SCHEMA_VERSION = 2`; (b) adicionar `TipoEvento.CANAL_SEM_ENTREGA = "CANAL_SEM_ENTREGA"` e `TipoEvento.CANAL_NORMALIZADO = "CANAL_NORMALIZADO"`; (c) criar `@dataclass SituacaoEntrega` com `falha_desde: datetime | None = None` e `aviso_emitido: bool = False`, com `para_dict`/`de_dict` (timestamps via `ts_para_str`/`str_para_ts`); (d) em `EstadoMonitor` remover `pendente_envio` e criar `filas: dict[str, list[EventoNotificacao]]` e `entrega: dict[str, SituacaoEntrega]`, ambos com `default_factory` contendo exatamente as chaves `"rede"` e `"operacional"` (constantes `CANAL_REDE = "rede"`, `CANAL_OPERACIONAL = "operacional"` e `NOMES_CANAIS = (CANAL_REDE, CANAL_OPERACIONAL)` no próprio `modelos.py`, para `modelos.py` NÃO importar `canais.py`); (e) `para_dict`/`de_dict` de `EstadoMonitor` passam a gravar/ler `filas` e `entrega` no lugar de `pendente_envio`; (f) `verificar_invariantes` ganha: as duas chaves existem em `filas` e `entrega`; "`aviso_emitido == true` ⇒ `falha_desde != null`"
- [X] T004 [P] Criar `src/cato_monitor/canais.py` (módulo puro, sem I/O): `class Canal(str, Enum)` com `REDE = "rede"` e `OPERACIONAL = "operacional"` e propriedade `outro`; tabela explícita `MAPA_CANAL: dict[TipoEvento, Canal]` SEM valor padrão — `LINK_OFFLINE`, `SITE_OFFLINE`, `LINK_RETORNO`, `SITE_RETORNO`, `LEMBRETE_DIARIO` → `REDE`; `MONITOR_FALHA`, `MONITOR_RECUPERADO`, `MONITOR_INICIADO` → `OPERACIONAL`; função `canal_do_evento(ev: EventoNotificacao) -> Canal` que, para `CANAL_SEM_ENTREGA` e `CANAL_NORMALIZADO`, devolve `Canal(ev.dados["canal_afetado"]).outro` e, para os demais, `MAPA_CANAL[ev.tipo]` (tipo sem mapeamento levanta `KeyError`, nunca cai em canal implícito — FR-004). Comentário curto: tipos da feature 002 (falha/normalização de gravação no banco) entram como `OPERACIONAL` quando forem criados
- [X] T005 [P] Em `src/cato_monitor/config.py`: adicionar o campo `teams_webhook_operacional_url: str` em `Config`; incluir `"TEAMS_WEBHOOK_OPERACIONAL_URL"` no laço de URLs obrigatórias (mensagens `"TEAMS_WEBHOOK_OPERACIONAL_URL ausente"` e `"TEAMS_WEBHOOK_OPERACIONAL_URL deve ser uma URL https://"`, acumuladas com os demais erros); incluir a URL em `Config.segredos()`; em `exibicao()` mostrar `"TEAMS_WEBHOOK_OPERACIONAL_URL": _host(...)`. As duas URLs iguais são aceitas
- [X] T006 Em `src/cato_monitor/estado_store.py` (depende de T003, T004): `carregar()` aceita `schema_version == 2` (constante `SCHEMA_VERSION`); `> SCHEMA_VERSION` continua `exit 1` com `schema_estado_futuro`; qualquer outro valor (incluindo 1, por ora) segue como estado inválido. Após `verificar_invariantes`, checar também que cada evento de `filas[nome]` está na fila de `canal_do_evento(ev).value` e tratar divergência como `ValueError` (estado inválido → linha de base)
- [X] T007 Atualizar a infraestrutura de testes para o modelo v2: `tests/helpers.py` (linha 66 usa `estado.pendente_envio.extend(eventos)`: distribuir cada evento pela fila de `canal_do_evento(ev).value`) e `tests/conftest.py` (variável de ambiente e `Config` de teste ganham `TEAMS_WEBHOOK_OPERACIONAL_URL=https://operacional.example.com/hook`, diferente da URL de rede de teste). Corrigir as referências a `pendente_envio` em `tests/unit/test_estado_store.py`, `tests/integration/test_teams.py` e `tests/integration/test_cenarios.py` para `estado.filas[...]` (rede, pois só usam eventos de rede ou de monitor conforme o caso — usar o canal correto de cada tipo)
- [X] T008 [P] Em `tests/unit/test_config.py`: casos para `TEAMS_WEBHOOK_OPERACIONAL_URL` ausente, `http://` (inválida), válida igual à URL de rede (aceita), e que `exibicao()` mostra só o host e `segredos()` contém a URL

**Checkpoint**: modelo, mapeamento, config e `carregar` v2 prontos. `teams.py`/`daemon.py` são adaptados na US1.

> **Regra de commit**: a Foundational e a US1 formam um único incremento. Não commitar entre a T003 e a
> T015: o primeiro commit dessas fases só é feito quando a T015 deixar a suíte inteira verde, para que
> nenhum commit da branch fique com a suíte quebrada.

---

## Phase 3: User Story 1 - Avisos de rede e avisos do robô em canais diferentes (Priority: P1) 🎯 MVP

**Goal**: cada tipo de aviso é entregue só no webhook do seu canal (FR-001..FR-004, FR-005, FR-011, FR-012).

**Independent Test**: com os dois webhooks configurados, uma queda de link vai só ao webhook de rede e
`MONITOR_FALHA`/`MONITOR_INICIADO` vão só ao webhook operacional; o heartbeat não gera POST no Teams.

### Tests for User Story 1

> Escrever primeiro e confirmar que FALHAM antes da implementação.

- [X] T009 [P] [US1] Criar `tests/unit/test_canais.py`: (a) parametrizado sobre **todos** os membros de `TipoEvento` (exceto os dois `CANAL_*`) verificando que `canal_do_evento` devolve o canal da tabela do `research.md` R-006 e que nenhum tipo fica sem mapeamento; (b) `CANAL_SEM_ENTREGA` com `dados["canal_afetado"]="rede"` → `OPERACIONAL`, e com `"operacional"` → `REDE`; mesma regra para `CANAL_NORMALIZADO`; (c) `Canal.REDE.outro is Canal.OPERACIONAL`
- [X] T010 [P] [US1] Em `tests/integration/test_teams.py`: com `responses`, uma fila de rede e uma operacional pendentes; verificar que o evento de rede é POSTado só na URL de rede, o operacional só na URL operacional, que os logs `envio_teams` trazem `canal` e que nenhuma URL aparece nos logs
- [X] T011 [P] [US1] Em `tests/integration/test_cenarios.py`: cenário com o `Daemon` — (a) queda de link além da tolerância → 1 POST só na URL de rede; (b) 5 falhas de consulta → `MONITOR_FALHA` só na URL operacional e `MONITOR_RECUPERADO` idem ao normalizar; (c) primeiro ciclo → `MONITOR_INICIADO` só na URL operacional; (d) o ping do heartbeat não gera nenhum POST para as URLs do Teams (FR-005); (e) texto/formato dos cards inalterados (reaproveitar os snapshots existentes, FR-012)

### Implementation for User Story 1

- [X] T012 [US1] Em `src/cato_monitor/teams.py`: `_enviar` passa a receber a URL de destino em vez de ler `cfg.teams_webhook_url`; criar `url_do_canal(cfg, canal) -> str` (REDE → `cfg.teams_webhook_url`, OPERACIONAL → `cfg.teams_webhook_operacional_url`); `drenar` vira `drenar_canal(estado, canal, cfg, salvar, sessao, dormir)` operando sobre `estado.filas[canal.value]`, mantendo *head-of-line*, `MAX_ENVIOS_POR_CICLO`, espaçamento e backoff; os logs `envio_teams` ganham `canal=canal.value`; devolve `(enviados, falhou)`. Adicionar `drenar_todos(...)` que, **por ora, chama os dois canais em sequência** (a paralelização é a T020 da US2) e devolve o total enviado
- [X] T013 [US1] Em `src/cato_monitor/daemon.py`: no lugar de `self.estado.pendente_envio.extend(eventos)`, distribuir cada evento por `canal_do_evento(e).value` em `self.estado.filas`; persistir ANTES de enviar (como hoje); chamar `teams.drenar_todos`; em `ciclo_concluido` trocar `fila_pendente` por `fila_rede` e `fila_operacional` (R-008), mantendo `enviados` como a soma
- [X] T014 [US1] Em `src/cato_monitor/__main__.py`: o log `estado_carregado` passa a informar `pendentes_rede` e `pendentes_operacional` (tamanho de cada fila) no lugar de `pendentes`
- [X] T015 [US1] Rodar `python -m pytest tests -q` e deixar a suíte inteira verde (inclui os ajustes da T007)

**Checkpoint**: User Story 1 funcional e testável sozinha (MVP). Falha de canal ainda é sequencial.

---

## Phase 4: User Story 2 - Um canal fora do ar não atrapalha o outro (Priority: P1)

**Goal**: falha num webhook não atrasa nem bloqueia o outro; falha contínua de 15 min é avisada no
outro canal, uma vez, com normalização (FR-004a, FR-006, FR-007, FR-008).

**Independent Test**: webhook operacional inválido + queda de link: a queda chega no prazo normal ao
canal de rede; após 15 min contínuos chega um único "CANAL OPERACIONAL SEM ENTREGA" ao canal de rede;
restaurado o webhook, os pendentes chegam em ordem, uma vez, e a normalização aparece.

### Tests for User Story 2

> Escrever primeiro e confirmar que FALHAM antes da implementação.

- [X] T016 [P] [US2] Em `tests/unit/test_canais.py`: testes de `avaliar_entrega` com relógio injetado, um por transição de `data-model.md`: (a) 1ª falha define `falha_desde=agora` sem emitir; (b) falha com menos de 900 s não emite; (c) falha com `agora - falha_desde ≥ 900 s` emite exatamente 1 `CANAL_SEM_ENTREGA` no outro canal com `dados` `canal_afetado`, `desde` (ISO UTC) e `pendentes`, e marca `aviso_emitido`; (d) nova avaliação com falha continuando NÃO emite de novo; (e) entrega ok com `aviso_emitido` emite 1 `CANAL_NORMALIZADO` (`desde`, `duracao_s`) e zera `falha_desde`/`aviso_emitido`; (f) entrega ok sem aviso emitido só zera, sem evento; (g) entrega ok parcial seguida de nova falha recomeça a contagem (oscilação); (h) fila vazia sem tentativa não altera a situação; (i) os dois canais em falha geram um aviso para cada um
- [X] T017 [P] [US2] Em `tests/integration/test_teams.py`: (a) webhook operacional respondendo 500 e o de rede 200: o evento de rede é entregue e o operacional fica na fila com `tentativas` incrementado e `ultimo_erro="http_500"`; (b) isolamento temporal: a resposta do webhook operacional bloqueia num `threading.Event` e, enquanto bloqueada, o evento de rede já foi entregue (prova a drenagem paralela); (c) ordem dentro do canal: 3 eventos operacionais, o 1º falha → nenhum dos outros é enviado, e ao voltar saem 1, 2, 3; (d) uma exceção inesperada na drenagem de um canal é logada e não impede o outro canal
- [X] T018 [P] [US2] Em `tests/unit/test_cards.py` + novos snapshots `tests/unit/snapshots/CANAL_SEM_ENTREGA.json` e `tests/unit/snapshots/CANAL_NORMALIZADO.json` (nas duas variações de canal afetado): título `⚙️ CANAL DE REDE SEM ENTREGA` / `⚙️ CANAL OPERACIONAL SEM ENTREGA` / `⚙️ CANAL DE REDE NORMALIZADO` / `⚙️ CANAL OPERACIONAL NORMALIZADO`, estilo `emphasis`, fatos "Sem entrega desde" (horário de Brasília) e "Avisos pendentes" (sem entrega) ou "Duração da falha" (normalização)
- [X] T019 [P] [US2] Em `tests/integration/test_cenarios.py`: cenário com `Daemon` e relógio injetado — (a) webhook operacional 500 por 15 min: um único `CANAL_SEM_ENTREGA` entregue no canal de rede e nenhum novo nos ciclos seguintes; (b) webhook volta: pendentes operacionais entregues em ordem e `CANAL_NORMALIZADO` no canal de rede; (c) reinício (novo `Daemon` com `carregar` do estado salvo) no meio da falha, antes e depois do aviso: o aviso não é repetido e o `falha_desde` é preservado; (d) o canal de rede em falha gera "CANAL DE REDE SEM ENTREGA" na fila operacional; (e) os dois canais em falha: cada aviso fica pendente na fila do outro e é entregue quando este voltar

### Implementation for User Story 2

- [X] T020 [US2] Em `src/cato_monitor/teams.py`: `drenar_todos` passa a executar `drenar_canal` de cada canal em sua própria `threading.Thread` e aguardar as duas (`join`); cada thread só altera a própria fila; a chamada `salvar()` é protegida por um `threading.Lock` compartilhado criado em `drenar_todos`; exceção em uma thread é capturada, logada com `log.exception(..., extra={"event": "envio_teams_erro", "canal": ...})` e tratada como "falhou" sem propagar. Devolve, por canal, `(enviados, falhou)` (R-002)
- [X] T021 [US2] Em `src/cato_monitor/canais.py`: implementar `avaliar_entrega(estado, resultados, agora, limite_s=900) -> list[EventoNotificacao]` (puro; relógio por parâmetro) conforme `data-model.md` e R-003: `resultados` mapeia canal → `(enviados, falhou)`; atualiza `estado.entrega[canal]` (`falha_desde`, `aviso_emitido`) e devolve os eventos `CANAL_SEM_ENTREGA`/`CANAL_NORMALIZADO` destinados ao OUTRO canal, com `id` único (usar `monitor.proximo_seq` como o motor faz ao gerar `MONITOR_FALHA`), `ocorrido_em`/`criado_em` = `agora` e `dados` conforme `data-model.md`. Constante `LIMITE_SEM_ENTREGA_S = 900`
- [X] T022 [P] [US2] Em `src/cato_monitor/cards.py`: registrar renderizadores para `TipoEvento.CANAL_SEM_ENTREGA` e `TipoEvento.CANAL_NORMALIZADO` na tabela existente (mesmo envelope e estilo `emphasis` dos avisos do monitor), com o rótulo do canal afetado ("DE REDE" / "OPERACIONAL"), horários formatados com `formatar_horario` e duração com `formatar_duracao`; textos conforme `contracts/teams-canais.md`
- [X] T023 [US2] Em `src/cato_monitor/daemon.py`: depois de `drenar_todos`, chamar `avaliar_entrega`, anexar os eventos devolvidos à fila do canal de destino (`canal_do_evento`), persistir (`_salvar`) e logar `canal_sem_entrega` (WARNING: `canal`, `desde`, `pendentes`) e `canal_normalizado` (INFO: `canal`, `duracao_s`). Os avisos gerados no ciclo são enviados no ciclo seguinte (nova drenagem), sem segunda drenagem no mesmo ciclo
- [X] T024 [US2] Rodar `python -m pytest tests -q`, corrigir regressões e garantir que os testes T016..T019 passam

**Checkpoint**: US1 e US2 funcionam; um canal fora do ar não afeta o outro e a falha é comunicada.

---

## Phase 5: User Story 3 - Atualizar uma instalação existente sem perder avisos (Priority: P2)

**Goal**: o `state.json` v1 com fila única vira v2 com filas por canal, sem perda, sem duplicidade e
uma única vez (FR-010, SC-003).

**Independent Test**: `state.json` v1 com avisos de rede e do robô pendentes → ao iniciar, cada aviso
está na fila do seu canal na ordem original, o v1 foi copiado, e um novo início não migra de novo.

### Tests for User Story 3

> Escrever primeiro e confirmar que FALHAM antes da implementação.

- [X] T025 [P] [US3] Em `tests/unit/test_estado_store.py`: (a) v1 com `pendente_envio` misto (`LINK_OFFLINE`, `MONITOR_INICIADO`, `SITE_RETORNO`, `MONITOR_FALHA`) → `carregar` devolve `filas["rede"]` = [LINK_OFFLINE, SITE_RETORNO] e `filas["operacional"]` = [MONITOR_INICIADO, MONITOR_FALHA], ordem relativa preservada, `tentativas`/`ultimo_erro` preservados, `entrega` zerada; (b) o arquivo em disco passa a ter `schema_version: 2` e a cópia `state.json.v1-<UTC>` existe com o conteúdo original; (c) segundo `carregar` não migra de novo (não cria nova cópia, mesmo conteúdo); (d) v1 com `pendente_envio` vazio migra normalmente; (e) v1 corrompido ou com invariantes violadas segue a regra de estado corrompido (linha de base, `state.json.corrompido-<UTC>`); (f) `schema_version: 3` → `SystemExit(1)`; (g) falha ao criar a cópia (diretório somente leitura simulado) não impede a migração nem perde avisos
- [X] T026 [P] [US3] Em `tests/integration/test_cenarios.py`: estado v1 pendente em disco + `Daemon` iniciado → cada aviso é entregue uma única vez, no webhook correto e na ordem original dentro do canal; reiniciar em seguida não reenvia nenhum

### Implementation for User Story 3

- [X] T027 [US3] Em `src/cato_monitor/estado_store.py`: em `carregar`, tratar `schema_version == 1` como migrável: validar com `verificar_invariantes` de itens (as regras de sites/links não mudaram), copiar o arquivo para `state.json.v1-<UTC>` (mesmo formato de marca de `_preservar_corrompido`; falha de cópia só loga `WARNING`), converter em memória (`pendente_envio` → `filas` por `canal_do_evento(...).value` em ordem; `entrega` zerada; `monitor`/`sites` iguais), gravar o v2 com `_gravar_atomico` imediatamente e logar `estado_migrado` (INFO: `de_versao=1`, `rede=<n>`, `operacional=<n>`). Tipo de evento desconhecido no v1 → estado inválido (linha de base)
- [X] T028 [US3] Em `src/cato_monitor/__main__.py`: quando `carregar` migrar, o log `estado_carregado` já reflete as filas migradas (nenhuma lógica nova além de confirmar a T014); confirmar na `data-model.md` que `de_dict` de v2 não aceita a chave `pendente_envio`
- [X] T029 [US3] Rodar `python -m pytest tests -q` e garantir que T025 e T026 passam sem regressão

**Checkpoint**: as três stories funcionam e uma instalação v1 atualiza sem perda.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T030 [P] Atualizar `README.md`: seção de configuração com `TEAMS_WEBHOOK_OPERACIONAL_URL` (obrigatória; `TEAMS_WEBHOOK_URL` é o canal de rede), tabela de roteamento tipo → canal, aviso de "sem entrega" (15 min) e passo de atualização ("configurar a nova variável antes de subir a nova versão; `state.json.v1-<UTC>` é a cópia de segurança")
- [X] T031 [P] Atualizar `changelog.md` com a entrada da feature 003 (canal operacional, filas por canal, `schema_version` 2, nova variável obrigatória — mudança que exige ação na atualização)
- [X] T032 [P] Adicionar em `specs/001-cato-socket/contracts/configuracao.md` e `specs/001-cato-socket/contracts/teams-webhook.md` uma nota curta apontando para `specs/003-canal-operacional-teams/contracts/` (a nova variável e o roteamento por canal) e, em `specs/001-cato-socket/contracts/state-file.schema.json`, o campo `description` do `schema_version` indicando que a v2 está em `specs/003-canal-operacional-teams/contracts/state-file-v2.md`
- [X] T033 Verificar `docker-compose.yml` (já usa `env_file: .env`, então a nova variável chega ao contêiner) e `Dockerfile`: confirmar que nenhum `ENV`/`ARG` precisa mudar e que nenhum segredo foi adicionado
- [X] T034 Conferir os logs de uma execução de teste e garantir que nenhuma URL de webhook aparece (grep pelos hosts de teste nos logs capturados em `tests/unit/test_logs.py`; estender o teste de redação para a nova URL em `Config.segredos()`)
- [X] T035 Executar o roteiro de `specs/003-canal-operacional-teams/quickstart.md` (seções 1 a 5) em ambiente de teste e registrar o resultado no PR

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sem dependências.
- **Foundational (Phase 2)**: depende do Setup; BLOQUEIA todas as stories. Ordem: T003 → (T004 ∥ T005) → T006 → T007; T008 após T005.
- **US1 (Phase 3)**: depende da Foundational. MVP.
- **US2 (Phase 4)**: depende da US1 (usa `drenar_canal`/`drenar_todos` e a distribuição por canal no daemon).
- **US3 (Phase 5)**: depende apenas da Foundational (T006) e pode ser feita em paralelo à US2 em arquivos distintos; a T026 usa o `Daemon` da US1.
- **Polish (Phase 6)**: depende das stories desejadas.

### Within Each User Story

- Testes escritos e falhando antes da implementação.
- `canais.py`/modelos antes de `teams.py`, `teams.py` antes de `daemon.py`.
- `T020`, `T021` e `T023` compartilham `teams.py`/`canais.py`/`daemon.py`: executar nesta ordem (T020, T021, T022 podem ser paralelas entre si; T023 por último).

### Parallel Opportunities

- Foundational: T004 ∥ T005; T008 ∥ T006.
- US1: T009 ∥ T010 ∥ T011.
- US2: T016 ∥ T017 ∥ T018 ∥ T019; depois T020 ∥ T021 ∥ T022.
- US3: T025 ∥ T026; a US3 inteira pode andar em paralelo à US2.
- Polish: T030 ∥ T031 ∥ T032.

---

## Parallel Example: User Story 2

```text
# Testes da US2 juntos:
Task: "Testes de avaliar_entrega em tests/unit/test_canais.py"
Task: "Isolamento entre canais em tests/integration/test_teams.py"
Task: "Snapshots dos cards CANAL_* em tests/unit/test_cards.py"
Task: "Cenários de 15 min e reinício em tests/integration/test_cenarios.py"

# Implementação em arquivos distintos:
Task: "Drenagem paralela em src/cato_monitor/teams.py"
Task: "avaliar_entrega em src/cato_monitor/canais.py"
Task: "Cards CANAL_* em src/cato_monitor/cards.py"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Setup + Foundational (T001..T008).
2. US1 (T009..T015): avisos separados por canal.
3. **PARAR e validar** a US1 (quickstart seção 2). Ainda não deployar em produção sem a US3: instalações v1 precisam da migração.

### Incremental Delivery

1. US1 → roteamento correto.
2. US2 → isolamento e aviso de canal sem entrega.
3. US3 → atualização segura da instalação existente. **O release só vai a produção com as três stories**: US1 sem US3 trataria o `state.json` v1 como corrompido e perderia a fila pendente.

> **Gate de release**: a branch `003-canal-operacional-teams` só pode ser mergeada em `main` e
> publicada (build/deploy da imagem) depois que a T029 estiver concluída e a suíte verde. Antes disso,
> qualquer build desta branch é apenas para teste e não deve ser usado numa instalação com `state.json`
> v1 em produção.
4. Polish → documentação e validação ponta a ponta.

---

## Notes

- Constituição: Princípio I (migração atômica e idempotente), V (por canal, sem descarte), VI (nova URL
  como segredo) e VII (`canal` nos logs) são cobertos pelos testes T010, T017, T019, T025 e T034.
- Tipos de aviso da feature 002 (falha/normalização de gravação no banco) NÃO são criados aqui; quando
  existirem, devem ser adicionados a `MAPA_CANAL` como `OPERACIONAL` (o teste T009(a) falhará se não forem).
- Commits pequenos, por tarefa ou grupo lógico, sem segredos reais em `.env.example`.
