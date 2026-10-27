---

description: "Task list: Migração da execução de Docker para Podman"
---

# Tasks: Migração da execução de Docker para Podman

**Input**: Design documents from `/specs/005-migracao-podman/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (3 arquivos), quickstart.md

**Tests**: Incluídos. A spec exige (FR-023) substituir os testes de repositório que liam o compose, e o research R-011 define testes para a unidade Quadlet e para o script de deploy.

**Organization**: Tarefas agrupadas por user story. A definição Quadlet do monitor é compartilhada por US1, US2, US3 e US5, então é criada na Fase 2 (Foundational); cada story acrescenta o que é só dela (testes, script, documentação, validação na VM).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: pode rodar em paralelo (arquivos diferentes, sem dependência de tarefa incompleta)
- **[Story]**: US1..US5, conforme spec.md
- Tarefas marcadas **(VM)** são executadas por SSH na VM Ubuntu Server 26 com Podman 5.7.0; as demais rodam no ambiente de desenvolvimento (Windows, só Python/pytest).

## Path Conventions

Projeto único existente: `deploy/` (novo, artefatos instalados no host), `tests/unit/`, raiz do repositório (`README.md`, `changelog.md`, `Containerfile`, `.containerignore`). O código em `src/` **não muda** (FR-024).

---

## Phase 1: Setup

**Purpose**: decidir o ponto de risco da spec e preparar a estrutura.

- [X] T001 Criar a pasta `deploy/` na raiz do repositório e acrescentar a linha `deploy/` em `.containerignore` para que fique fora do contexto de build (research R-006).
- [X] T002 (VM) Executar o experimento de logs do research R-005: rodar um container de teste com `--log-driver journald` sob uma unidade com `LogNamespace=cato-monitor` e conferir com `journalctl --namespace=cato-monitor` e `journalctl` (padrão) em qual journal as linhas caem. Registrar o resultado e a escolha (`journald`+namespace, `passthrough`+namespace, ou teto global com emenda a FR-018) na seção R-005 de `specs/005-migracao-podman/research.md`.

**Checkpoint**: a estratégia de logs está decidida; T008, T009 e T014 dependem dela.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: unidades Quadlet do monitor e emenda da constituição. Nenhuma user story é validável sem elas.

**⚠️ CRITICAL**: nenhuma user story começa antes desta fase.

- [X] T003 [P] Criar `deploy/cato-monitor.volume` conforme contracts/quadlet-cato-monitor.md: seção `[Volume]` com `VolumeName=cato-monitor-data`, `User=10001` e `Group=10001`.
- [X] T004 [P] Criar `deploy/cato-monitor.container` com o conteúdo exato de contracts/quadlet-cato-monitor.md: `[Unit]` (`After`/`Wants=network-online.target`, `StartLimitIntervalSec=0`), `[Container]` (`ContainerName=cato-monitor`, `Image=localhost/cato-monitor:latest`, `Pull=never`, `RunInit=true`, `ReadOnly=true`, `Tmpfs=/tmp`, `DropCapability=ALL`, `NoNewPrivileges=true`, `EnvironmentFile=/etc/cato-monitor/.env`, `Environment=STATE_DIR=/data`, `Volume=cato-monitor.volume:/data`, `StopTimeout=30`, `LogDriver=journald` (valor provisório, confirmado ou ajustado por T002), `HealthCmd=python -m cato_monitor.healthcheck`, `HealthInterval=60s`, `HealthTimeout=5s`, `HealthStartPeriod=120s`, `HealthRetries=3`, `HealthOnFailure=none`), `[Service]` (`Restart=always`, `RestartSec=30`, `TimeoutStopSec=45`, mais `LogNamespace=cato-monitor` provisório, a ser removido se T002 não confirmar) e `[Install]` (`WantedBy=multi-user.target`). Sem `PublishPort`, sem `User=root`, sem valor de segredo em `Environment=`. Não depende de T002; se T002 mudar a estratégia, ajustar este arquivo e T008.
- [X] T005 [P] Atualizar `.specify/memory/constitution.md`: em "Restrições Adicionais", trocar "Python 3.12 em contêiner Docker" por "Python 3.12 em contêiner OCI executado com Podman"; subir a versão de 1.0.0 para 1.0.1, atualizar `Last Amended` no rodapé para a data da emenda (Governance exige versão e data) e registrar a emenda (PATCH, esclarecimento de runtime) no Sync Impact Report do topo do arquivo (research R-012).
- [X] T006 Criar `tests/unit/test_servico_repo.py` com helpers que leem `deploy/cato-monitor.container` e `deploy/cato-monitor.volume` (parse simples de seções INI com chaves repetidas) e reusam `PALAVRAS_SECRETAS` de `tests/unit/test_segredos_repo.py`. Neste momento incluir só: arquivos existem e `[Container]` não tem `PublishPort`. As demais verificações entram nas tarefas das stories (mesmo arquivo, portanto sem [P]). Depende de T003, T004.

**Checkpoint**: Quadlet do monitor escrito; `pytest -q tests/unit/test_servico_repo.py` passa.

---

## Phase 3: User Story 1 - Operar a automação só com Podman e systemd (Priority: P1) 🎯 MVP

**Goal**: instalar, subir, parar, ver logs e status de saúde só com Podman e systemd.

**Independent Test**: em VM sem Docker, seguir o README: serviço ativo e habilitado, logs JSON no `journalctl`, saúde `healthy` após 120 s, `unhealthy` sem reinício, `systemctl stop` em ≤ 30 s e permanece parado (quickstart cenários 1, 2, 3).

### Tests for User Story 1

- [X] T007 [US1] Em `tests/unit/test_servico_repo.py`, adicionar testes: `StopTimeout=30` e `RunInit=true` (FR-006); `HealthCmd`, `HealthInterval`, `HealthTimeout`, `HealthStartPeriod` e `HealthRetries` do Quadlet iguais aos do `HEALTHCHECK` do `Containerfile` e `HealthOnFailure=none` (FR-007, FR-009); `LogDriver` definido (FR-018); `TimeoutStopSec` maior que `StopTimeout`.

### Implementation for User Story 1

- [X] T037 [US1] Em `tests/unit/test_servico_repo.py`, adicionar testes sobre o `Containerfile` (FR-019, FR-020): `ARG PYTHON_IMAGE` fixado por `@sha256:`; `pip install` com `--require-hashes`; `USER monitor` (UID 10001 definido por `useradd --uid 10001`); `VOLUME /data`; `ENTRYPOINT ["python", "-m", "cato_monitor"]`; `WORKDIR /app`; `HEALTHCHECK` presente. Depende de T007 (mesmo arquivo).
- [X] T008 [P] [US1] Criar `deploy/journald@cato-monitor.conf` com `[Journal]`, `SystemMaxUse=50M` e `RuntimeMaxUse=50M` (FR-018, SC-009). Só entra em uso se T002 escolher o namespace; caso contrário ajustar conforme a decisão registrada.
- [X] T009 [US1] Criar `deploy/install.sh` (Bash, `set -eu -o pipefail`, exige root): copia `cato-monitor.container` e `cato-monitor.volume` para `/etc/containers/systemd/` e `journald@cato-monitor.conf` para `/etc/systemd/`; cria `/etc/cato-monitor/` (0755) e `/var/lib/cato-monitor/` (0700); roda `systemctl daemon-reload`; não sobrescreve `.env` nem `gitlab-credentials` existentes; não habilita nem inicia nada (o operador faz isso, quickstart passo 1). Depende de T008. As partes do deploy (script, units do timer) são acrescentadas em T025.
- [X] T010 [US1] Em `README.md`, substituir a seção de Docker Compose por "Execução (Podman + systemd)": pré-requisito Podman 5.7.0 e como conferir (`podman --version`), build manual com `podman build --format docker -t localhost/cato-monitor:latest -f Containerfile .`, uso do `deploy/install.sh`, `systemctl start|stop|restart|status|enable --now cato-monitor`, logs (`journalctl -u cato-monitor -f`, `podman logs`, `--namespace` se aplicável), consulta de saúde (`podman inspect --format '{{.State.Health.Status}}' cato-monitor`), permissão do `.env` (`chmod 600`, FR-016) e atualização do `.env` com restart sem rebuild. Remover toda menção a Docker (FR-023).
- [ ] T011 (VM) [US1] Validar no host: `systemd-analyze verify` e `/usr/lib/systemd/system-generators/podman-system-generator --dryrun` sobre as unidades de `deploy/`; executar os cenários 1, 2 e 3 do quickstart e registrar divergências em `research.md`.

**Checkpoint**: US1 funcional e demonstrável (MVP).

---

## Phase 4: User Story 2 - Recuperação automática após falha e reboot (Priority: P1)

**Goal**: o serviço volta sozinho após queda do processo e após reboot sem login, sem desistir nunca.

**Independent Test**: `pkill -9` volta em ≤ 2 min; `reboot` sem login volta a rodar ciclos em ≤ 5 min; `.env` inválido repete a cada 30 s (quickstart cenários 4, 5, 6).

### Tests for User Story 2

- [X] T012 [US2] Em `tests/unit/test_servico_repo.py`, adicionar testes: `Restart=always`, `RestartSec=30`, `StartLimitIntervalSec=0` na seção `[Unit]`, `WantedBy=multi-user.target` em `[Install]` (FR-003, FR-004) e `After`/`Wants=network-online.target`.

### Implementation for User Story 2

- [ ] T013 [US2] (VM) Executar os cenários 4, 5 e 6 do quickstart (kill -9, reboot sem login, `.env` inválido corrigido depois) e registrar tempos medidos (SC-002, SC-003) na seção de resultados de `specs/005-migracao-podman/quickstart.md`.
- [X] T014 [US2] Em `README.md`, documentar o comportamento de recuperação: reinício a cada 30 s sem limite, `systemctl stop` mantém parado, após reboot o serviço habilitado sobe mesmo se foi parado à mão (diferença aceita em relação ao `unless-stopped`), e o que fazer quando o `.env` está ausente ou inválido.

**Checkpoint**: US1 e US2 validadas na VM.

---

## Phase 5: User Story 3 - Primeira instalação com estado vazio e persistente (Priority: P1)

**Goal**: volume criado vazio com dono UID 10001, estado sobrevive a recriação do container e a reboot.

**Independent Test**: instalar em VM nova, conferir `ls -ln` no mountpoint (10001:10001), linha de base sem alertas em massa, recriar container/reiniciar VM e comparar o conteúdo de `/data` (quickstart cenário 10, SC-004, SC-005).

### Tests for User Story 3

- [X] T015 [US3] Em `tests/unit/test_servico_repo.py`, adicionar testes: `cato-monitor.volume` tem `User=10001`, `Group=10001`, `VolumeName=cato-monitor-data`; o `.container` monta `cato-monitor.volume:/data` e define `Environment=STATE_DIR=/data` (FR-011, FR-012, FR-017).

### Implementation for User Story 3

- [X] T016 [US3] Em `README.md`, escrever "Primeira instalação numa VM nova" (FR-022): instalar Podman/git/curl/jq, clonar o repositório em `/opt/cato-monitor/repo`, criar `/etc/cato-monitor/.env` a partir de `.env.example` com `chmod 600`, construir, habilitar, validar (saúde, logs); explicar a linha de base inicial esperada (um card `MONITOR INICIADO`, sem alertas de queda) e como corrigir dono do volume criado à mão (`podman volume inspect`, `chown 10001:10001` no mountpoint).
- [X] T017 [US3] Em `README.md`, escrever "Desinstalação" (FR-013): parar e desabilitar `cato-monitor` e `cato-deploy.timer`, remover unidades; apagar o estado só por `podman volume rm cato-monitor-data`, descrito como passo explícito e destrutivo.
- [ ] T018 (VM) [US3] Executar o cenário 10 do quickstart (recriar container e reiniciar a VM comparando `ls -ln` e conteúdo de `/data`) e verificar que um `monitor.lock` residual não impede o start (US3-3).

**Checkpoint**: US1–US3 validadas; a instalação inicial está documentada.

---

## Phase 6: User Story 4 - Deploy automático a partir da branch principal (Priority: P2)

**Goal**: commit novo na branch principal entra em execução em ≤ 15 min, com aviso único no canal operacional do Teams.

**Independent Test**: commit válido → novo commit em execução + card `DEPLOY CONCLUÍDO`; commit que quebra o build → versão anterior segue + um único `DEPLOY FALHOU`; monitor parado à mão não é iniciado (quickstart cenários 11–15).

### Tests for User Story 4

> Escrever primeiro e confirmar que falham. Usam `git` real em repositório temporário (`tmp_path`) e `podman`, `systemctl`, `curl` falsos no `PATH` que gravam cada chamada em um arquivo de log. O script lê diretórios por variáveis de ambiente (ver T021) para poder ser testado sem root.

- [X] T019 [US4] Criar `tests/unit/test_deploy_script.py` com a infraestrutura de teste: fixture que cria repositório git de origem com 1 commit, diretórios temporários de estado/config/clone, scripts falsos de `podman`/`systemctl`/`curl` em um `bin/` no início do `PATH` (cada um registra os argumentos e obedece variáveis de ambiente que forçam falha), `.env` temporário com `TEAMS_WEBHOOK_OPERACIONAL_URL`, e função `rodar_deploy()` que chama `bash deploy/cato-deploy.sh` via `subprocess` com `CATO_*` apontando para os diretórios temporários. Pular a suíte no Windows sem `bash`/`flock` (`pytest.skip`).
- [X] T020 [US4] Em `tests/unit/test_deploy_script.py`, escrever os casos do contrato deploy-automatico.md e aviso-teams-deploy.md: (a) sem commit novo → sai 0, só atualiza `last-check`, nenhuma chamada a `podman build`; (b) sucesso → `podman build --format docker --label org.opencontainers.image.revision=<sha>` com tag `<sha12>`, `podman tag … :latest` depois do build, `systemctl try-restart cato-monitor.service`, grava `deployed-commit` e `last-deploy`, apaga `failed-commit`, um `curl` com card `DEPLOY CONCLUÍDO` (JSON válido com `type: message` e `AdaptiveCard`); (c) falha de build → exit 1, `latest` não movida, `failed-commit=<sha>:build`, um aviso `DEPLOY FALHOU`; segunda execução com mesmo commit → nenhum aviso novo; (d) falha de início → `<sha>:inicio`; (e) serviço parado à mão (`is-active` falso) → sem espera, sucesso com nota no card; (f) webhook ausente no `.env` → deploy segue sem `curl`; (g) falha do `curl` não altera o exit code; (h) falha de `git ls-remote` → etapa `download`, aviso dedupado por causa; (i) saída/arquivo de log nunca contém o webhook nem `://usuario:senha@`; (j) `flock` ocupado → sai 0 sem fazer nada; (k) o `curl` falso registra seu `argv` e o teste confere que a URL do webhook não aparece nele.

### Implementation for User Story 4

- [X] T021 [US4] Criar `deploy/cato-deploy.sh` (Bash, `set -u -o pipefail`, sem `source` no `.env`) seguindo o algoritmo de contracts/deploy-automatico.md, passos 1–9. Diretórios configuráveis por variável de ambiente com padrão de produção (`CATO_CONFIG_DIR=/etc/cato-monitor`, `CATO_STATE_DIR=/var/lib/cato-monitor`, `CATO_REPO_DIR=/opt/cato-monitor/repo`, `CATO_LOCK_FILE=/run/cato-deploy.lock`). Pontos obrigatórios: `flock -n`; `repo.conf` com `REPO_URL`/`BRANCH`; `git -c credential.helper='store --file=$CATO_CONFIG_DIR/gitlab-credentials'` com URL sem credencial; `git ls-remote` → `fetch` → `reset --hard FETCH_HEAD` (clona se faltar); `podman build --format docker --label org.opencontainers.image.revision=$novo -t localhost/cato-monitor:${novo:0:12} -f Containerfile .` e `podman tag` para `latest` só após sucesso; `systemctl try-restart cato-monitor.service`, espera de até 60 s por `is-active` e 10 s de estabilidade apenas se estava ativo; escrita atômica (`.tmp` + `mv`) de `deployed-commit`, `failed-commit`, `last-check`, `last-deploy` com timestamps UTC ISO 8601 (data-model.md); dedup `failed-commit=<sha>:<etapa>` com etapas `download|build|inicio`; poda: `podman image prune -f` e manter só as 2 últimas tags `<sha12>`; exit 0 em sem novidade/sucesso, 1 em falha; filtro `sed` que remove `://…@` de mensagens do `git`. Depende de T019, T020.
- [X] T022 [US4] Em `deploy/cato-deploy.sh`, implementar a função de aviso (contracts/aviso-teams-deploy.md): ler só `TEAMS_WEBHOOK_OPERACIONAL_URL` do `/etc/cato-monitor/.env` com `grep '^TEAMS_WEBHOOK_OPERACIONAL_URL='`; montar o envelope com `jq -n --arg` (título do commit e detalhe nunca interpolados crus); card `DEPLOY CONCLUÍDO` (Commit `abc1234 — título`, Quando em America/Sao_Paulo, Observação se estava parado à mão) e `DEPLOY FALHOU` (Commit ou "indisponível", Etapa `download|build|início do serviço`, Detalhe sanitizado ≤ 200 caracteres); `curl --max-time 10` sem retentativa; falha só vai ao journal; sem webhook, registra e segue. O `curl` MUST receber a URL do webhook por configuração em stdin (`curl --config -` com `url = "..."` via `printf`) ou arquivo 0600, nunca como argumento de linha de comando (evita expor o segredo em `ps` e `/proc`). Mesmo arquivo que T021, depois dele.
- [X] T023 [P] [US4] Criar `deploy/cato-deploy.service`: `Type=oneshot`, `ExecStart=/usr/local/lib/cato-monitor/cato-deploy.sh`, `TimeoutStartSec=20min`, `After=network-online.target`, `Wants=network-online.target`, roda como root.
- [X] T024 [P] [US4] Criar `deploy/cato-deploy.timer`: `OnBootSec=2min`, `OnUnitActiveSec=5min`, `Persistent=true`, `WantedBy=timers.target`.
- [X] T025 [US4] Atualizar `deploy/install.sh` (criado em T009): copiar `cato-deploy.service`/`cato-deploy.timer` para `/etc/systemd/system/` e `cato-deploy.sh` para `/usr/local/lib/cato-monitor/` (0755); criar `/etc/cato-monitor/repo.conf` (0644, `REPO_URL=` e `BRANCH=main`) só se ainda não existir; criar `gitlab-credentials` vazio (0600) só se não existir; `daemon-reload`. Depende de T021–T024.
- [X] T026 [P] [US4] Em `.env.example`, ajustar o comentário de `TEAMS_WEBHOOK_OPERACIONAL_URL` para informar que também recebe os avisos de deploy.
- [X] T027 [US4] Em `README.md`, escrever "Deploy automático" (FR-021): criar o *deploy token* somente leitura (`read_repository`) no GitLab, formato de `/etc/cato-monitor/gitlab-credentials` e `repo.conf`, ligar o timer, comandos de FR-031 (commit em execução, `last-check`/`last-deploy`, `systemctl list-timers`, forçar com `systemctl start cato-deploy.service`, pausar com `systemctl stop cato-deploy.timer`, ver falhas), semântica do monitor parado à mão, ausência de rollback automático (correção por revert) e a recomendação de proteger a branch principal com pipeline de testes. Incluir também atualização de `.env` e de `certs/` (rebuild).
- [ ] T028 (VM) [US4] Executar os cenários 11–15 do quickstart (deploy bem-sucedido, build quebrado com 3 verificações, commit de correção, monitor parado à mão, token revogado) e registrar o resultado.

**Checkpoint**: deploy automático validado ponta a ponta.

---

## Phase 7: User Story 5 - Hardening e instância única preservados (Priority: P2)

**Goal**: nenhuma regressão de segurança nem de instância única em relação ao Docker.

**Independent Test**: inspeção do container em execução (raiz somente leitura, tmpfs, sem capabilities, no-new-privileges, UID 10001), segunda instância recusada pelo lock, nenhum segredo na imagem (quickstart cenários 7, 8, 9).

### Tests for User Story 5

- [X] T029 [US5] Em `tests/unit/test_servico_repo.py`, adicionar testes: `ReadOnly=true`, `Tmpfs=/tmp`, `DropCapability=ALL`, `NoNewPrivileges=true` (FR-014); ausência de `User=root` e de `PublishPort`; `ContainerName=cato-monitor` fixo e ausência de `Scale`; `EnvironmentFile=/etc/cato-monitor/.env` presente; nenhuma linha `Environment=` casando `PALAVRAS_SECRETAS` (FR-015); `Image=localhost/cato-monitor:latest` com `Pull=never`.
- [X] T030 [P] [US5] Em `tests/unit/test_segredos_repo.py`, acrescentar verificação de que `deploy/` não contém valores de `.env` nem URL de webhook/credencial literal (reusar `_valores_do_env`), e que `deploy/cato-deploy.sh` não faz `source`/`.` do `.env` nem imprime a variável do webhook (`echo`/`printf` sobre ela), e que não a passa como argumento do `curl`.

### Implementation for User Story 5

- [ ] T031 (VM) [US5] Executar os cenários 7, 8 e 9 do quickstart (`podman inspect` do hardening, segundo container sobre o mesmo volume recusado pelo lock, busca de valores do `.env` em `podman history --no-trunc`/`inspect` da imagem) e registrar o resultado.

**Checkpoint**: todas as stories validadas.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T032 [P] Atualizar `changelog.md` com a entrada da troca de runtime (Docker → Podman + Quadlet, deploy automático por timer, logs no journal, `Dockerfile`→`Containerfile`, remoção do compose, emenda 1.0.1 da constituição).
- [X] T033 [P] Em `.gitignore`, remover/ajustar qualquer entrada específica de Docker que sobrar e garantir que `deploy/` é versionado.
- [X] T034 Varredura final: `grep -rIni "docker" --exclude-dir=.git --exclude-dir=specs --exclude-dir=.venv --exclude-dir=.specify --exclude-dir=.claude .` não deve achar nada além do changelog histórico; corrigir o que restar em `README.md` e `certs/README.md` (FR-023).
- [X] T035 Rodar `pytest -q` na raiz e confirmar que toda a suíte passa sem alterar `src/` (FR-024, SC-011); `git diff --stat src/` deve estar vazio.
- [ ] T036 (VM) Rodar o quickstart completo (cenário 16 de teto de logs ≤ ~50 MB incluído, SC-009) e marcar `specs/005-migracao-podman/checklists/requirements.md` com o resultado.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Fase 1)**: sem dependências; T002 (VM) decide o `LogDriver` usado em T004 e T008.
- **Foundational (Fase 2)**: T003, T004 e T005 podem começar já; T002 apenas confirma ou ajusta o LogDriver/LogNamespace. **Bloqueia** todas as stories.
- **US1, US2, US3 (P1)**: dependem da Fase 2; entre si são independentes na escrita, mas as validações (VM) usam o que US1 deixa instalado (`install.sh`).
- **US4 (P2)**: depende da Fase 2 (precisa de `cato-monitor.service` e do `install.sh` de T009).
- **US5 (P2)**: depende da Fase 2; independente das demais.
- **Polish**: depois das stories desejadas.

### Dentro das stories

- Testes antes da implementação (US4: T019/T020 antes de T021).
- `deploy/cato-deploy.sh`: T021 → T022 (mesmo arquivo).
- `deploy/install.sh`: T009 → T025.
- `tests/unit/test_servico_repo.py` e `README.md` são tocados por várias tarefas: executá-las em sequência (T006 → T007 → T037 → T012 → T015 → T029; T010 → T014 → T016 → T017 → T027).

### Parallel Opportunities

- Fase 2: T003 ‖ T004 ‖ T005.
- US1: T008 em paralelo com T007.
- US4: T023 ‖ T024 ‖ T026 enquanto T019–T022 avançam; T027 (README) depois de T021 e na ordem da nota de arquivos compartilhados.
- US5: T030 em paralelo com T029.
- Polish: T032 ‖ T033.
- US2/US3/US5 podem ser conduzidas por pessoas diferentes depois da Fase 2, desde que os arquivos compartilhados (test_servico_repo.py, README.md) sejam mesclados em sequência.

### Parallel Example: Fase 2

```text
Task: "Criar deploy/cato-monitor.volume (T003)"
Task: "Criar deploy/cato-monitor.container (T004)"
Task: "Emenda 1.0.1 em .specify/memory/constitution.md (T005)"
```

### Parallel Example: User Story 4

```text
Task: "Criar deploy/cato-deploy.service (T023)"
Task: "Criar deploy/cato-deploy.timer (T024)"
Task: "Ajustar comentário em .env.example (T026)"
```

---

## Implementation Strategy

### MVP First (US1)

1. Fase 1 (T001–T002) e Fase 2 (T003–T006).
2. Fase 3 (US1): testes do Quadlet, `install.sh`, README de operação, validação na VM.
3. **Parar e validar**: o monitor roda sob systemd com Podman, logs no journal, saúde consultável. Já é entregável, com atualização manual (build + restart).

### Incremental Delivery

1. + US2 (recuperação) e US3 (primeira instalação documentada): fecha o P1 e a instalação reproduzível.
2. + US4 (deploy automático): entrega contínua com aviso no Teams.
3. + US5 (verificações de hardening e segredos): trava as garantias contra regressão.
4. Polish: changelog, varredura de "docker", suíte completa e quickstart integral.

---

## Notes

- Não há suporte a Podman no ambiente Windows de desenvolvimento: tudo que depende de Podman/systemd é validação (VM) manual, apoiada por testes de arquivo e do script com binários falsos.
- Se T002 mostrar que o teto de 50 MB por serviço não é viável com `journald`, o fallback 2 do research R-005 exige emendar FR-018 e SC-009 na spec antes de fechar T008.
- Commit após cada tarefa ou grupo lógico; verificar os testes novos falhando antes da implementação em US4.
