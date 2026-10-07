---

description: "Lista de tarefas: Monitoramento de Sockets Cato com Avisos no Teams"
---

# Tasks: Monitoramento de Sockets Cato com Avisos no Teams

**Input**: documentos de design em `specs/001-cato-socket/`

**Prerequisites**: plan.md, spec.md, research.md (R-001..R-012), data-model.md, contracts/, quickstart.md

**Tests**: INCLUÍDOS. A constituição (Princípios I e III) e o research R-012 exigem testes: um por linha da
tabela de transições, interrupção na escrita, reinício na tolerância, estado corrompido e snapshot de cada card.

**Organization**: tarefas agrupadas por user story. A ordem das fases segue a prioridade da spec
(P1: US1, US2, US4 · P2: US3, US5).

## Format: `[ID] [P?] [Story] Descrição com caminho de arquivo`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência de tarefa incompleta)
- **[Story]**: US1..US5, conforme `spec.md`
- Código em `src/cato_monitor/`, testes em `tests/unit/` e `tests/integration/` (ver plan.md → Project Structure)
- Comentários, logs e textos de card em **português**, como no restante do projeto

---

## Phase 1: Setup (infraestrutura compartilhada)

**Purpose**: estrutura do projeto, segurança do repositório e dependências

- [x] T001 Recriar `.gitignore` e `.dockerignore` na raiz (ambos foram apagados no working tree). `.gitignore` deve ignorar `.env`, `.env.*` (exceto `.env.example`), `.venv/`, `__pycache__/`, `.pytest_cache/`, `*.egg-info/`, `state.json*`, `last_cycle`, `monitor.lock`; `.dockerignore` deve excluir `.env*`, `.git`, `tests/`, `specs/`, `.specify/`, `.claude/`, `.venv/`. **Primeira tarefa**: Princípio VI
- [ ] T002 Remover os arquivos legados vazios `main.py`, `src/__init__.py`, `src/cato_api.py`, `src/config.py`, `src/monitor.py`, `src/notifier.py`, `src/state.py` (substituídos pelo pacote `src/cato_monitor/`); conferir antes com `git diff --stat` que estão vazios (ignorar arquivos que já não existirem, como `src/__init__.py`) **[BLOQUEADA: remoção dos arquivos legados vazios negada pelo ambiente; apagar manualmente `main.py` e `src/{cato_api,config,monitor,notifier,state}.py`]**
- [x] T003 Criar `pyproject.toml` na raiz: pacote `cato_monitor` em `src/` (src layout), Python `>=3.12`, `[tool.pytest.ini_options]` com `testpaths=["tests"]` e `pythonpath=["src"]`
- [x] T004 [P] Criar `requirements.in` (`requests`, `tzdata`) e `requirements-dev.in` (`-r requirements.in`, `pytest`, `responses`); gerar `requirements.txt` e `requirements-dev.txt` com `pip-compile --generate-hashes` (versões exatas, R-011)
- [x] T005 [P] Criar `.env.example` na raiz com todas as variáveis de `contracts/configuracao.md` (valores de exemplo fictícios, nenhum segredo real) e comentários em português
- [x] T006 [P] Criar a estrutura de pacotes vazia: `src/cato_monitor/__init__.py` (com `__version__ = "0.1.0"`), `tests/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`, `tests/fixtures/cato/.gitkeep`

---

## Phase 2: Foundational (pré-requisitos bloqueantes)

**Purpose**: núcleo e I/O comuns a todas as histórias. Ao fim, o monitor roda um ciclo completo (consulta → estado → envio → heartbeat), ainda sem regras de negócio.

**⚠️ CRITICAL**: nenhuma user story começa antes desta fase.

- [ ] T007 **Verificação obrigatória do schema Cato (R-001)**: com `catocli` num venv separado (fora da imagem), executar `accountSnapshot` da conta e responder (a) qual campo traz o papel LAN/WAN e o nome da porta, (b) se WAN caída continua em `devices[].interfaces` com `connected=false` ou some, (c) formato dos `id` de interface. Atualizar `specs/001-cato-socket/contracts/cato-graphql.md` (campos ⚠, remover aviso "candidato") e `research.md` R-001. Se não houver acesso à conta, parar e pedir ao usuário os payloads **[PENDENTE: exige acesso à conta Cato]**
- [ ] T008 Criar 5 fixtures anonimizadas em `tests/fixtures/cato/` (`todos_online.json`, `link_wan_offline.json`, `site_desconectado.json`, `site_ha.json`, `graphql_errors.json`) a partir de T007, seguindo a anonimização de `contracts/cato-graphql.md` (ids sequenciais, `Site A`, `WAN1 - Operadora X`, sem IPs/seriais) (depende de T007) **[PENDENTE: existem fixtures SINTÉTICAS em `tests/fixtures/cato/`; substituir por payloads reais após T007]**
- [x] T009 [P] Implementar `src/cato_monitor/relogio.py`: `Protocol Relogio` com `agora() -> datetime` (aware, UTC) e `RelogioSistema`
- [x] T010 [P] Implementar `src/cato_monitor/modelos.py`: dataclasses e enums de `data-model.md` — `EstadoItem` (`ONLINE`/`PENDENTE_OFFLINE`/`OFFLINE_NOTIFICADO`), `Link`, `Site`, `SituacaoMonitor`, `EstadoMonitor`, `EventoNotificacao` (tipos `LINK_OFFLINE`, `SITE_OFFLINE`, `LINK_RETORNO`, `SITE_RETORNO`, `LEMBRETE_DIARIO`, `MONITOR_FALHA`, `MONITOR_RECUPERADO`, `MONITOR_INICIADO`), `Snapshot`/`ObservacaoSite`/`ObservacaoLink`, `ConsultaOk`/`ConsultaFalhou`. Constantes: `LIMITE_FALHAS=5`, `LIMITE_AUSENCIAS=3`. Invariantes: `ONLINE ⇒ inicio_queda==null, notificado==false, coberto_pelo_site==false`; `OFFLINE_NOTIFICADO ⇒ notificado==true`. Timestamps UTC aware; nomes guardados exatamente como vêm da Cato
- [x] T011 [P] Implementar `src/cato_monitor/config.py`: `Config` imutável (frozen dataclass), leitura/validação de todas as variáveis de `contracts/configuracao.md` acumulando **todos** os erros; `INTERVALO_SEGUNDOS` 30–120 (padrão 60), `TOLERANCIA_SEGUNDOS` 60–3600 e ≥ intervalo (padrão 180), `LEMBRETE_HORARIO` `HH:MM` (padrão 08:00), `TZ` validado por `zoneinfo` (padrão `America/Sao_Paulo`), `STATE_DIR` existente e gravável (padrão `/data`), URLs `https://`, `CATO_ACCOUNT_ID` só dígitos; método de exibição mascarada (4 últimos do token, só host das URLs); `exit 1` com log JSON `config_invalida` em stderr
- [x] T012 [P] Implementar `src/cato_monitor/logs.py`: `JsonFormatter` (uma linha JSON no stdout: `ts` UTC, `level`, `event`, `msg` + extras) e `RedactingFilter` (substitui valores literais dos segredos e URLs de `*.logic.azure.com`, `*.powerplatform.com`, `hc-ping.com` por `<redacted:host>`, inclusive em `exc_info`/tracebacks)
- [x] T013 [P] Teste `tests/conftest.py`: `RelogioFake` (`avancar(segundos)`), fábrica de `Config` de teste e fixture `tmp_path` como `STATE_DIR`
- [x] T014 [P] Testes `tests/unit/test_config.py`: um teste por variável inválida/ausente com `exit 1` e mensagem acumulando múltiplos erros; segredos mascarados na exibição; `TOLERANCIA < INTERVALO` recusada; `INTERVALO_SEGUNDOS=121` recusado
- [x] T015 [P] Testes `tests/unit/test_logs.py`: token e URL do Teams/heartbeat nunca aparecem, inclusive em traceback; formato JSON válido
- [x] T016 Implementar `src/cato_monitor/estado_store.py`: `carregar()`/`salvar()` de `${STATE_DIR}/state.json` com `schema_version: 1`, gravação atômica (`state.json.tmp` + `flush` + `os.fsync` + `os.replace` + `fsync` do diretório), serialização ISO 8601 `+00:00` conforme `contracts/state-file.schema.json`; ausente/ilegível/inválido/`schema_version` ausente ⇒ preserva arquivo ruim como `state.json.corrompido-<UTC>` e devolve estado vazio (linha de base, R-004); `schema_version` maior que o suportado ⇒ `exit 1`; verificação das invariantes de `data-model.md` na leitura; `gravar_last_cycle()` atômico; lock `monitor.lock` com `fcntl.flock(LOCK_EX|LOCK_NB)` mantido aberto (fallback `msvcrt.locking` no Windows), falha ⇒ log `instancia_duplicada` e `exit 1` (depende de T010)
- [x] T017 [P] Testes `tests/unit/test_estado_store.py`: ida e volta (salvar/carregar); falha simulada entre `.tmp` e `replace` mantém o arquivo anterior íntegro; corrompido gera estado vazio + arquivo `.corrompido-*`; `schema_version` futuro ⇒ `SystemExit(1)`; segundo lock ⇒ `exit 1`; JSON válido contra `state-file.schema.json` (depende de T016)
- [ ] T018 Implementar `src/cato_monitor/snapshot.py`: `normalizar(resposta_json) -> Snapshot` conforme `contracts/cato-graphql.md` e data-model §2 usando os achados de T007 — `site.conectado = connectivityStatus=="connected"`, `link_id = "<socketInfo.id or device.id>/<interface_id>"`, WAN online por `interfaces[].connected is True`, LAN por `interfacesLinkState[].up is True`, só portas com papel LAN/WAN; `data.accountSnapshot.sites` ausente, não-lista ou **vazia quando o estado tem sites** ⇒ `ConsultaFalhou("schema_invalido")`; violação local (site sem `devices` estando conectado, interface sem id) ⇒ item omitido (observação inválida); site desconectado sem `devices` ⇒ links sem observação. **Único ponto que conhece o schema da Cato** (depende de T008, T010) **[Implementado de forma PROVISÓRIA conforme o contrato candidato; revisar papel LAN/WAN e 'WAN caída some?' após T007]**
- [ ] T019 [P] Testes `tests/unit/test_snapshot.py` com as 5 fixtures: todos online; WAN offline; site desconectado; HA (chave do link por socket); lista de sites vazia ⇒ schema inválido; interface sem id omitida (depende de T018) **[Testes passam com fixtures sintéticas; reexecutar após T007/T008]**
- [x] T020 Implementar `src/cato_monitor/cato_client.py`: `requests.Session`, `POST` em `CATO_API_URL` com `x-api-key`, timeout `(5, 20)`, backoff exponencial com jitter (base 2 s, fator 2, teto 30 s, máx. 3 tentativas, respeita `Retry-After` até o teto, tempo total do ciclo ≤ `min(60 s, INTERVALO)`), sem retentativa em 4xx ≠ 429 (401/403 ⇒ log ERROR "verifique CATO_API_KEY/permissões"); **nunca levanta exceção**: retorna `ConsultaOk(snapshot)` ou `ConsultaFalhou(motivo)` com motivos `timeout|conexao|http_<status>|graphql_errors|json_invalido|schema_invalido`; query somente leitura (FR-013); log `consulta_cato` (depende de T018, T012)
- [x] T021 [P] Testes `tests/integration/test_cato_client.py` com `responses` e fixtures: 200 ok; 200 com `errors` ⇒ `graphql_errors`; JSON inválido; timeout; 429 com `Retry-After`; 5xx seguido de sucesso; 401 sem retentativa; a falha nunca propaga exceção; o corpo da requisição contém apenas `query` e nenhuma `mutation` (FR-013; o README indica a permissão mínima do token) (depende de T020)
- [x] T022 [P] Implementar `src/cato_monitor/heartbeat.py`: `ping(ok|fail)` com `GET HEARTBEAT_URL` (ou `/fail`), timeout 10 s, 1 tentativa, falha só logada (`heartbeat` WARNING), nunca interrompe o laço
- [x] T023 [P] Implementar `src/cato_monitor/healthcheck.py`: `python -m cato_monitor.healthcheck` lê `${STATE_DIR}/last_cycle`, `exit 0` se idade ≤ `3 × INTERVALO + 30 s`, `exit 1` se maior ou ausente
- [x] T024 [P] Testes `tests/integration/test_heartbeat.py` e `tests/unit/test_healthcheck.py`: `/fail` com `falhas_consecutivas ≥ 5`; falha do heartbeat não propaga; idade limite e arquivo ausente (depende de T022, T023)
- [x] T025 Implementar `src/cato_monitor/cards.py` (base): helpers puros `formatar_horario(ts, tz)` (`dd/mm/aaaa HH:MM`), `formatar_duracao(segundos)` (`X d Y h Z min`, sem segundos), montagem do envelope Adaptive Card 1.4 (`msteams.width="Full"`, Container com `style`, FactSet, frase, rodapé `Ref. evt-NNNNNN`) e `renderizar(evento, tz) -> dict` que despacha por tipo (templates por tipo entram nas histórias) conforme `contracts/teams-webhook.md`; sem menções (@) (depende de T010)
- [x] T026 Implementar `src/cato_monitor/teams.py`: `drenar(estado, cfg, salvar)` — `POST` com `{"type":"message","attachments":[{"contentType":"application/vnd.microsoft.card.adaptive","content":card}]}`, timeout `(5, 10)`, 2xx = entregue ⇒ remove da fila e **salva o estado**; qualquer falha ⇒ `tentativas += 1`, `ultimo_erro` sanitizado (status/tipo, **nunca a URL**) e **para** (head-of-line); 429/5xx com backoff e `Retry-After` (máx. 2 tentativas); máx. 20 envios por ciclo com 1 s de espaço; card renderizado no envio com o horário original; log `envio_teams` (depende de T025, T016)
- [x] T027 [P] Testes `tests/integration/test_teams.py`: 202 remove da fila; falha mantém o evento, incrementa `tentativas` e interrompe; reenvio na ordem original após o canal voltar; 429 com `Retry-After`; URL ausente do `ultimo_erro` e dos logs; limite de 20 por ciclo (depende de T026)
- [x] T028 Implementar `src/cato_monitor/motor.py` (esqueleto) com `avaliar_ciclo(estado, resultado, agora, cfg) -> (estado, eventos)` **pura** (sem I/O, sem relógio global) devolvendo o estado inalterado e `[]`; as regras entram por história (depende de T010)
- [x] T029 Implementar `src/cato_monitor/daemon.py` e `src/cato_monitor/__main__.py`: fluxo de `plan.md` — `agora` → `consultar()` → `avaliar_ciclo` → `pendente_envio += eventos` (ids `evt-000001`, `proximo_seq`) e `salvar` **antes** de enviar → `teams.drenar` → atualiza `ultimo_ciclo_concluido_em`, salva, grava `last_cycle` e `heartbeat.ping` → log `ciclo_concluido` (campos de `contracts/observabilidade.md`) → dorme até `inicio + INTERVALO` (relógio monotônico); SIGTERM/SIGINT interrompem a espera, terminam o ciclo, gravam o estado e saem com 0; nenhuma exceção de rede encerra o laço; `__main__`: config → logging → lock → estado → `daemon.run()`, logs `monitor_iniciando`, `estado_carregado`/`linha_base`, `monitor_encerrando` (depende de T011, T012, T016, T020, T022, T026, T028)
- [x] T030 [P] Criar `Dockerfile` multi-stage (builder e runtime `python:3.12.x-slim-bookworm` fixado por digest; venv em `/opt/venv`; `pip install --require-hashes`; usuário `monitor` UID 10001; `WORKDIR /app`; `VOLUME /data`; `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1`; `HEALTHCHECK --interval=60s --timeout=5s --start-period=120s --retries=3 CMD python -m cato_monitor.healthcheck`; `ENTRYPOINT ["python","-m","cato_monitor"]`; **sem `ENV`/`ARG` de segredo**) e `docker-compose.yml` (1 serviço sem `replicas`, `restart: unless-stopped`, `init: true`, `read_only: true`, `tmpfs: /tmp`, `cap_drop: [ALL]`, `no-new-privileges:true`, `env_file: .env`, volume `monitor-data:/data`, `stop_grace_period: 30s`, log `json-file` 10m×5)

**Checkpoint**: o daemon executa ciclos completos de ponta a ponta (sem regras de transição). As histórias podem começar.

---

## Phase 3: User Story 1 - Ser avisado quando um link ou site cair (P1) 🎯 MVP

**Goal**: aviso único de queda após a tolerância, com distinção `LINK OFFLINE` × `SITE OFFLINE` e supressão dos links quando o site inteiro cai.

**Independent Test**: simular link online → offline por ≥ tolerância ⇒ exatamente 1 `LINK_OFFLINE`; offline < tolerância ⇒ 0 eventos; queda de todos os links (ou site desconectado) ⇒ 1 `SITE_OFFLINE` e 0 `LINK_OFFLINE`; reinício no meio da tolerância ⇒ aviso em `inicio_queda + tolerância`, sem repetir.

### Tests for User Story 1 ⚠️ (escrever primeiro; devem FALHAR)

- [x] T031 [P] [US1] `tests/unit/test_transicoes.py`: um teste por linha da tabela (ONLINE×online, ONLINE×offline, PENDENTE×offline<tol, PENDENTE×offline≥tol ⇒ `QUEDA`, PENDENTE×online, NOTIFICADO×offline, NOTIFICADO×online ⇒ `RETORNO` com duração, qualquer×`None`) com `RelogioFake`; limite exato `agora - inicio_queda == tol` notifica
- [x] T032 [P] [US1] `tests/unit/test_motor_queda.py`: site online + 1 link caído ⇒ `LINK_OFFLINE` com `outros_links_online`; todos os links offline ⇒ `SITE_OFFLINE` motivo `todos_links_inativos` e links `coberto_pelo_site`; `connectivityStatus=disconnected` ⇒ `SITE_OFFLINE` motivo `desconectado_cato`; site `PENDENTE_OFFLINE` **adia** `QUEDA` de link (data-model §3.2 passo 6); link com site `PENDENTE_OFFLINE` não gera aviso até o site ser decidido (adiamento, ver spec Edge Cases); site sem links monitorados não vira offline por "todos inativos"; **link ausente com site desconectado não incrementa `ausencias`**, e com site conectado remove-se após 3 ausências; ordem determinística por `site_id`; um aviso por episódio
- [x] T033 [P] [US1] `tests/integration/test_cenarios.py` (parte 1): oscilação dentro da tolerância ⇒ 0 eventos; queda ≥ tolerância ⇒ 1 `LINK_OFFLINE`; site offline com 3 links ⇒ 1 `SITE_OFFLINE`, 0 `LINK_OFFLINE`; **reinício durante a tolerância** (recria o daemon com o mesmo `STATE_DIR`) ⇒ aviso em `inicio_queda + tolerância`, sem duplicar; falha da API não avança nem reinicia a tolerância (SC-003)

### Implementation for User Story 1

- [x] T034 [US1] Implementar `src/cato_monitor/transicoes.py`: `proximo_estado(item, obs_offline: bool | None, agora, tolerancia) -> (novo_item, acoes)` **pura** conforme data-model §3.1; limpa `inicio_queda`/`notificado`/`coberto_pelo_site` ao voltar para `ONLINE`; `None` ⇒ inalterado; ações `QUEDA`/`RETORNO(duracao)`
- [x] T035 [US1] Em `src/cato_monitor/motor.py`: inventário (item novo ⇒ linha de base individual sem aviso; ausente ⇒ `ausencias += 1`, 3 ⇒ remoção com log `item_removido` (para **link**, a contagem só avança enquanto o site está `conectado`; site desconectado ⇒ `ausencias` do link inalterado, data-model §2); presente ⇒ `ausencias = 0`; `item_novo` logado) e avaliação de sites e links na ordem do data-model §3.2 passos 4–6 para `QUEDA`: `SITE_OFFLINE` com `links_afetados` e supressão (`coberto_pelo_site=true`, `notificado=true`, `inicio_queda` preservado), `LINK_OFFLINE` com adiamento quando o site está pendente; "site offline" = `conectado==false` OU (≥1 link monitorado e todos offline) (depende de T034)
- [x] T036 [US1] Em `src/cato_monitor/motor.py`: log `transicao` (`item`, `site_id`, `link_id`, `de`, `para`) e contagem de transições para o `ciclo_concluido`
- [x] T037 [P] [US1] Em `src/cato_monitor/cards.py`: templates `LINK_OFFLINE` (🟠, `warning`, "Um dos links do site **X** caiu. O site continua funcionando pelos outros links (operação parcial).") e `SITE_OFFLINE` (🔴, `attention`, "O site **X** está sem conexão. Todos os links estão fora."), campos Site/Link (tipo)/Desde (Brasília)/Há quanto tempo, nomes exatos do portal
- [x] T038 [US1] Garantir que `tests/unit/test_transicoes.py`, `test_motor_queda.py` e a parte 1 de `test_cenarios.py` passam; ajustar o `daemon.py` apenas se o fluxo de ciclo precisar (ex.: transições para o log `ciclo_concluido`)

**Checkpoint**: US1 funcional e testável sozinha (MVP: já avisa quedas de forma única e anti-fadiga).

---

## Phase 4: User Story 2 - Ser avisado quando a conexão voltar (P1)

**Goal**: aviso de retorno só se a queda foi notificada, com a duração; retorno do site reavalia links ainda inativos.

**Independent Test**: queda notificada seguida de retorno ⇒ 1 `LINK_RETORNO` com duração correta; queda não notificada ⇒ 0 eventos; site volta com 1 link ainda fora ⇒ `SITE_RETORNO` com `links_ainda_offline`=1 e o link continua pendência.

### Tests for User Story 2 ⚠️

- [x] T039 [P] [US2] `tests/unit/test_motor_retorno.py`: `LINK_RETORNO` com `inicio_queda` e `retorno_em`; sem aviso se a queda não foi notificada (oscilação); `SITE_RETORNO`; links cobertos que voltaram ⇒ `ONLINE` em silêncio; links cobertos ainda offline ⇒ `OFFLINE_NOTIFICADO` com `coberto_pelo_site=false` e listados em `links_ainda_offline`; item de `origem=linha_base` offline que volta ⇒ gera retorno (R-004)
- [x] T040 [P] [US2] `tests/integration/test_cenarios.py` (parte 2): queda e retorno ⇒ 1 `LINK_OFFLINE` + 1 `LINK_RETORNO` com duração correta; retorno do site com 1 link fora ⇒ `SITE_RETORNO` com `links_ainda_offline`=1; Teams fora e depois de volta ⇒ eventos reenviados na ordem original com o horário original (SC-007); reinício não repete avisos (SC-006)

### Implementation for User Story 2

- [x] T041 [US2] Em `src/cato_monitor/motor.py`: tratar a ação `RETORNO` — `SITE_RETORNO` (reavaliação dos links cobertos conforme data-model §3.2 passo 5) e `LINK_RETORNO` (passo 6); zerar `coberto_pelo_site` ao voltar o site; `links_ainda_offline` com [nome, tipo, inicio_queda]
- [x] T042 [P] [US2] Em `src/cato_monitor/cards.py`: templates `LINK_RETORNO` (🟢, `good`, "O link voltou após 12 min.") e `SITE_RETORNO` (🟢, `good`, "O site voltou após 1 h 25 min." + lista "Ainda fora: ..." quando houver); rótulo "Duração" no lugar de "Há quanto tempo"
- [x] T043 [US2] Garantir que os testes de T039–T040 passam

**Checkpoint**: US1 + US2 entregam o ciclo completo queda → retorno.

---

## Phase 5: User Story 3 - Receber lembrete diário de pendências (P2)

**Goal**: um único lembrete por dia, na primeira verificação bem-sucedida a partir do horário configurado, só se houver pendências, sem repetir após reinício.

**Independent Test**: com links offline no horário ⇒ 1 `LEMBRETE_DIARIO` listando cada pendência e o "desde"; sem pendências ⇒ nada; reinício após o envio ⇒ sem reenvio no mesmo dia; monitor parado às 08:00 ⇒ lembrete no primeiro ciclo bom, no mesmo dia.

### Tests for User Story 3 ⚠️

- [x] T048 [P] [US3] `tests/unit/test_lembrete.py`: com pendências ⇒ 1 evento com site, link, tipo, `inicio_queda`; sem pendências ⇒ 0 eventos mas `ultimo_lembrete_data` marcada; antes do horário ⇒ nada; após reinício (estado recarregado) ⇒ sem duplicar; monitor parado às 08:00 e voltando às 10:00 ⇒ 1 lembrete no mesmo dia; virada de dia em `America/Sao_Paulo` (UTC ≠ data local); ciclo com `ConsultaFalhou` **não** avalia o lembrete; item removido sai da lista; itens de linha de base offline entram; divisão em `parte`/`total_partes` quando passar de ~24 KB
- [x] T049 [P] [US3] `tests/integration/test_cenarios.py` (parte 3): lembrete 08:00 + reinício às 08:05 ⇒ 1 lembrete só

### Implementation for User Story 3

- [x] T050 [US3] Em `src/cato_monitor/motor.py`: passo 7 do data-model — ao fim de cada ciclo **bem-sucedido**, se `agora.astimezone(TZ).time() >= LEMBRETE_HORARIO` e `ultimo_lembrete_data != hoje_local`, atribuir `ultimo_lembrete_data = hoje_local` (`YYYY-MM-DD`) e gerar `LEMBRETE_DIARIO` somente se houver site ou link em `OFFLINE_NOTIFICADO`; dividir em partes por tamanho (R-007)
- [x] T051 [P] [US3] Em `src/cato_monitor/cards.py`: template `LEMBRETE_DIARIO` (📋 PENDÊNCIAS DO DIA, `accent`, tabela site/link/desde/há quanto tempo, "(parte 1/2)" quando dividido; cada card ≤ 24 KB)
- [x] T052 [US3] Garantir que os testes de T048–T049 passam

**Checkpoint**: US3 funcional sem afetar US1/US2.

---

## Phase 6: User Story 5 - Saber que o próprio monitor está funcionando (P2)

**Goal**: aviso do monitor após 5 falhas consecutivas (1x por sequência), aviso de recuperação, linha de base com resumo e heartbeat externo; falhas nunca alteram itens.

**Independent Test**: 5 consultas falhas ⇒ 1 `MONITOR_FALHA` e nenhuma transição de item; sucesso seguinte ⇒ 1 `MONITOR_RECUPERADO`; estado corrompido ⇒ 1 `MONITOR_INICIADO` e 0 avisos de queda; parada do monitor ⇒ heartbeat externo para de chegar.

### Tests for User Story 5 ⚠️

- [x] T053 [P] [US5] `tests/unit/test_motor_monitor.py`: 4 falhas ⇒ nada; 5ª ⇒ `MONITOR_FALHA` (`falhas_consecutivas`, `desde`, `ultimo_motivo`); 6ª em diante ⇒ nada (1x por sequência); sucesso ⇒ `MONITOR_RECUPERADO` e zera contador e flag; falha **nunca** muda `estado`/`inicio_queda` de itens; contador persistido entre reinícios; linha de base (estado vazio) ⇒ itens online `ONLINE`, offline `OFFLINE_NOTIFICADO` com `origem=linha_base`, 1 `MONITOR_INICIADO` com `itens_offline`, 0 avisos de queda, `ultimo_lembrete_data` = hoje se passou do horário (R-004)
- [x] T054 [P] [US5] `tests/integration/test_cenarios.py` (parte 4): 5 falhas da API ⇒ 1 `MONITOR_FALHA`, depois sucesso ⇒ 1 `MONITOR_RECUPERADO`; `/fail` no heartbeat com ≥ 5 falhas; estado corrompido ⇒ `MONITOR_INICIADO` e 0 quedas; item ausente por 3 ciclos válidos ⇒ removido sem aviso; item novo ⇒ linha de base individual sem aviso

### Implementation for User Story 5

- [x] T055 [US5] Em `src/cato_monitor/motor.py`: passos 1–3 do data-model §3.2 — `ConsultaFalhou` (`falhas_consecutivas += 1`; ao chegar a 5 e `alerta_falha_enviado==false` ⇒ `MONITOR_FALHA`; itens intocados), `ConsultaOk` (`MONITOR_RECUPERADO` se `alerta_falha_enviado`; zera contador e flag; atualiza `ultima_consulta_ok_em`) e linha de base (R-004) com `MONITOR_INICIADO`
- [x] T056 [P] [US5] Em `src/cato_monitor/cards.py`: templates `MONITOR_FALHA` (⚙️ MONITOR: SEM ACESSO À CATO, `emphasis`, "…**Nenhum alerta de queda será emitido até normalizar.** Isso não significa que algum site caiu."), `MONITOR_RECUPERADO` (⚙️ MONITOR: ACESSO NORMALIZADO) e `MONITOR_INICIADO` (⚙️ MONITOR INICIADO, "Monitorando N sites e M links. Já estavam fora no início: ...")
- [x] T057 [US5] Em `src/cato_monitor/daemon.py`: passar `falhas_consecutivas` ao `heartbeat.ping` (`/fail` com ≥ 5) e preencher `falhas_consecutivas` no log `ciclo_concluido`
- [x] T058 [US5] Garantir que os testes de T053–T054 passam

**Checkpoint**: todas as 5 histórias funcionam de forma independente.

---

## Phase 7: User Story 4 - Entender o aviso sem conhecimento técnico (P1)

**Goal**: avisos em linguagem simples e padronizada, visualmente distintos por tipo, em horário de Brasília e com nomes exatos do portal. Os templates por tipo são criados em US1, US2, US3 e US5; esta fase fica por último entre as histórias (depende de T037, T042, T051 e T056) e garante o conjunto.

**Independent Test**: snapshot test do JSON de cada um dos 8 tipos de card; todos contêm site, link (quando aplicável), tipo do evento, desde quando e há quanto tempo; títulos/emoji/`style` distintos; ≤ 24 KB.

- [x] T044 [P] [US4] `tests/unit/test_cards.py`: snapshot do JSON de **cada um dos 8 tipos** (`tests/unit/snapshots/*.json`); campos obrigatórios presentes (Site, Link quando aplicável, Desde, Há quanto tempo/Duração, `Ref. evt-NNNNNN`); título, emoji e `style` únicos por tipo (🔴 attention, 🟠 warning, 🟢 good, 📋 accent, ⚙️ emphasis); nenhuma menção `<at>`/`@`
- [x] T045 [P] [US4] `tests/unit/test_cards_formatacao.py`: horários convertidos de UTC para `America/Sao_Paulo` em `dd/mm/aaaa HH:MM` (inclui virada de dia); durações `X d Y h Z min` sem segundos; nomes de site e link idênticos aos do portal (acentos e espaços preservados)
- [x] T046 [US4] Revisar `src/cato_monitor/cards.py` contra os testes de T044–T045 e `contracts/teams-webhook.md` (estrutura do card, frases em linguagem simples, sem jargão de rede); corrigir divergências; limite de 24 KB por card (a divisão do lembrete é feita em US3)
- [ ] T047 [US4] Gerar o conjunto dos 8 cards renderizados (JSON ou imagem enviada ao canal de teste) para o aceite de SC-004 e registrar o roteiro em `specs/001-cato-socket/quickstart.md` §6 se faltar algum passo (aceite com usuários é manual, ≥ 90%) **[PENDENTE: aceite manual no canal de teste]**

**Checkpoint**: todos os avisos são padronizados e distinguíveis.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [x] T059 [P] Escrever `README.md` na raiz em português: o que faz, pré-requisitos, como criar o fluxo do Teams, variáveis (`contracts/configuracao.md`), execução com Docker Compose, testes, hospedagem fora da rede monitorada com NTP, configuração do Healthchecks (`period` = `INTERVALO_SEGUNDOS`, `grace` = 2 intervalos; ex.: 1 min e 2 min para o padrão de 60 s)
- [x] T060 [P] Criar `changelog.md` na raiz com a entrada da versão `0.1.0`
- [x] T061 [P] Teste de arquitetura `tests/unit/test_pureza.py`: `transicoes.py`, `motor.py`, `cards.py` e `snapshot.py` não importam `requests`, `os`, `socket`, `time` nem `datetime.now`/`utcnow` (Princípio III)
- [x] T062 [P] Teste de segurança `tests/unit/test_segredos_repo.py`: `Dockerfile` sem `ENV`/`ARG` de segredo; `.gitignore` e `.dockerignore` contêm `.env`; nenhum valor de `.env` presente em arquivos versionados, pulando essa verificação (`pytest.skip`) se `.env` não existir, como no CI (Princípio VI)
- [x] T063 Executar a suíte completa (`pytest -q`) e corrigir falhas; conferir cobertura de cada linha da tabela de transições e dos 9 cenários do `quickstart.md` §2
- [ ] T064 Validar `quickstart.md` §3–§5 com Docker: `INTERVALO_SEGUNDOS=10` ⇒ `exit=1` com `config_invalida` sem segredos; `docker compose up -d --build` ⇒ `MONITOR INICIADO`, `ciclo_concluido` a cada ~60 s, container `healthy`; `--scale monitor=2` ⇒ `instancia_duplicada`; `restart` sem cards repetidos; `grep` de token/URL nos logs sem ocorrências ; medir no canal de teste o tempo entre o fim da tolerância e a entrega do card (≤ 1 intervalo + 1 min, ou seja, ≤ 2 min no padrão de 60 s; SC-002); no Healthchecks.io configurar `period` = intervalo e `grace` = 2 intervalos, para o alerta ocorrer em até 3 intervalos (SC-008) (requer credenciais e canal de teste do usuário) **[PENDENTE: exige Docker em execução, credenciais e canal de teste]**
- [ ] T065 Revisão final contra a constituição v2.0.0 (7 princípios) e atualização do status em `spec.md` (Draft ⇒ Implementado) se aprovado **[PENDENTE: depende de T007 e T064]**

---

## Verificação de Conformidade com a Constituição (v2.0.0)

| Princípio | Tarefas |
|---|---|
| I. Resiliência de Estado | T016, T017, T033 (reinício na tolerância), T048 |
| II. Falha de Observação | T020, T021, T053–T055 |
| III. Máquina de Estados | T031, T034, T061 |
| IV. Anti-Fadiga | T032, T033, T048–T051 |
| V. Rede Defensiva | T020, T021, T026, T027 |
| VI. Segredos e Fail-Fast | T001, T011, T012, T014, T015, T062 |
| VII. Observabilidade | T022–T024, T029, T057 |

Nenhuma exceção identificada.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sem dependências. T001 primeiro.
- **Foundational (Phase 2)**: depende do Setup; **bloqueia** todas as histórias. T007 → T008 → T018; T016 antes de T026/T029; T028 antes de T029.
- **US1 (Phase 3)**: depende da Foundational. **MVP.**
- **US2 (Phase 4)**: depende da Foundational; reutiliza `motor.py`/`transicoes.py` de US1 (a ação `RETORNO` já existe em `transicoes.py`), por isso é executada **depois** de US1.
- **US4 (Phase 7)**: depende dos templates de US1/US2/US3/US5 (T037, T042, T051, T056) para o snapshot completo; por isso fica depois das Phases 3–6. Os testes T044–T045 podem ser escritos antes, mas falham até os 8 templates existirem.
- **US3 (Phase 5)**: depende da Foundational e de US1 (`OFFLINE_NOTIFICADO` populado).
- **US5 (Phase 6)**: depende da Foundational; a linha de base usa o inventário de US1 (T035).
- **Polish (Phase 8)**: depende das histórias desejadas.

### User Story Dependencies

- **US1 (P1)**: independente após a Foundational.
- **US2 (P1)**: após US1 (mesmo `motor.py`); testável isoladamente com estado pré-populado.
- **US4 (P1)**: transversal; valida o conjunto de cards.
- **US3 (P2)** e **US5 (P2)**: independentes entre si; ambos alteram `motor.py` e `cards.py`, então não devem rodar em paralelo no mesmo arquivo.

### Within Each User Story

- Testes escritos primeiro e **falhando** antes da implementação
- `transicoes.py` → `motor.py` → `cards.py`
- Mudanças em `motor.py` e `cards.py` são sequenciais entre histórias (mesmo arquivo)

### Parallel Opportunities

- Setup: T004, T005, T006
- Foundational: T009–T015 juntos; T017, T019, T021, T022–T024, T027, T030 depois de suas dependências
- Testes de uma história (marcados [P]) em paralelo
- Templates de card (`cards.py`) por história são tarefas [P] apenas em relação a testes/outros arquivos, não entre si

---

## Parallel Example: Foundational

```bash
Task: "Implementar src/cato_monitor/relogio.py (T009)"
Task: "Implementar src/cato_monitor/modelos.py (T010)"
Task: "Implementar src/cato_monitor/config.py (T011)"
Task: "Implementar src/cato_monitor/logs.py (T012)"
```

## Parallel Example: User Story 1 (testes)

```bash
Task: "tests/unit/test_transicoes.py (T031)"
Task: "tests/unit/test_motor_queda.py (T032)"
Task: "tests/integration/test_cenarios.py parte 1 (T033)"
```

---

## Implementation Strategy

### MVP First (US1)

1. Phase 1 (Setup) e Phase 2 (Foundational), incluindo a **verificação do schema (T007)**
2. Phase 3 (US1): avisos únicos de queda de link e de site
3. **PARAR e VALIDAR**: `pytest -q` e um ciclo real contra o canal de teste
4. Publicar o contêiner se aprovado

### Incremental Delivery

1. Setup + Foundational → daemon roda ciclos
2. US1 → quedas avisadas (MVP)
3. US2 → retornos avisados
4. US3 → lembrete diário
5. US5 → avisos do monitor e linha de base
6. US4 → cards revisados e distinguíveis (aceite SC-004)
7. Polish → README, validação Docker, revisão da constituição

---

## Notes

- [P] = arquivos diferentes, sem dependência pendente
- O rótulo [Story] mapeia a tarefa à história para rastreabilidade
- **T007 depende do acesso à conta Cato** e é pré-requisito da Phase 2: sem os payloads reais o parser (T018) não deve ser escrito. Sem acesso à conta, adiar a Phase 2 e avançar apenas com T001–T006 e os módulos independentes do schema (T009–T017, T022–T024)
- **Estado atual**: o usuário ainda não forneceu a chave da API Cato; portanto T007 e tudo que depende dele (T008, T018–T021, T029, T033 e demais testes de integração com fixtures) ficam bloqueados. Executar primeiro T002–T006, T009–T017, T022–T028, T030 e os testes/implementações puros (T031, T034, T037…) que não dependem do formato real da resposta
- `motor.py` e `cards.py` são tocados por várias histórias; evitar edições simultâneas
- Commits por tarefa ou grupo lógico; parar em qualquer checkpoint para validar
