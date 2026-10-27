# Research: Migração para Podman

Nenhum `NEEDS CLARIFICATION` ficou aberto na spec. Os itens abaixo fixam decisões técnicas e marcam o
que precisa de **validação na VM** (não foi possível executar Podman neste ambiente Windows).

## R-001 — Como o systemd gerencia o container: Quadlet

- **Decision**: unidade Quadlet `.container` em `/etc/containers/systemd/` (rootful), gerando
  `cato-monitor.service`. Volume em `cato-monitor.volume`.
- **Rationale**: é o mecanismo suportado no Podman 5.x; substitui `podman generate systemd` (obsoleto).
  O serviço é de sistema, sobe no boot sem login, e o container é recriado a cada start (`--rm`), o
  que casa com "atualizar = reconstruir imagem + restart".
- **Alternatives**: `podman generate systemd` (obsoleto); `podman-restart.service` +
  `--restart=always` (reinicia após `systemctl stop`? não, mas perde os logs/status por unidade e o
  `RestartSec`); unidade escrita à mão com `podman run` (duplica o que o Quadlet já faz).

## R-002 — Mapeamento compose → Quadlet

| Compose | Quadlet / systemd |
|---|---|
| `restart: unless-stopped` | `[Service] Restart=always`, `RestartSec=30`; `[Unit] StartLimitIntervalSec=0`; `[Install] WantedBy=multi-user.target` |
| `init: true` | `RunInit=true` |
| `read_only: true` | `ReadOnly=true` |
| `tmpfs: /tmp` | `Tmpfs=/tmp` |
| `cap_drop: ALL` | `DropCapability=ALL` |
| `no-new-privileges` | `NoNewPrivileges=true` |
| `env_file: .env` | `EnvironmentFile=/etc/cato-monitor/.env` |
| `STATE_DIR=/data` | `Environment=STATE_DIR=/data` |
| `monitor-data:/data` | `Volume=cato-monitor-data.volume:/data` |
| `stop_grace_period: 30s` | `StopTimeout=30` + `[Service] TimeoutStopSec=45` (margem sobre o 30 s) |
| `healthcheck` | `HealthCmd`, `HealthInterval=60s`, `HealthTimeout=5s`, `HealthStartPeriod=120s`, `HealthRetries=3`, `HealthOnFailure=none` |
| `logging` | `LogDriver=journald` (ver R-005) |
| instância única | lock em `/data/monitor.lock` + `ContainerName=cato-monitor` (um nome fixo impede um 2º container) |

`Restart=always` (e não `on-failure`): cobre também uma saída com código 0 inesperada; `systemctl stop`
continua mantendo parado (FR-005). `StartLimitIntervalSec=0` remove o limite de tentativas (FR-004).

## R-003 — HEALTHCHECK na imagem

- **Decision**: manter `HEALTHCHECK` no `Containerfile` **e** declarar os mesmos parâmetros no Quadlet;
  construir com `podman build --format docker`.
- **Rationale**: o formato OCI padrão do `podman build` descarta `HEALTHCHECK`; com `--format docker` a
  instrução fica nos metadados (FR-020). Declarar no Quadlet torna o serviço independente do formato
  da imagem; os dois valores são testados para ficarem iguais.
- **Alternatives**: só no Quadlet (perde FR-020); só na imagem (frágil a quem construir sem a flag).
- `HealthOnFailure=none` garante FR-009 (só registrar). Consulta: `podman healthcheck run
  cato-monitor` e `podman inspect --format '{{.State.Health.Status}}' cato-monitor`.

## R-004 — Volume e dono UID 10001

- **Decision**: `cato-monitor.volume` com `User=10001` e `Group=10001`. Rootful, sem mapeamento de
  usuários, o UID 10001 do container é o UID 10001 do host.
- **Rationale**: volume vazio criado já com o dono certo (FR-012), sem passo manual. O Podman também
  copia o dono de `/data` da imagem para volumes novos; o `User=`/`Group=` explicita e não depende
  desse efeito.
- **Validação na VM**: `podman volume inspect` mostra as opções; `ls -ln` no mountpoint mostra
  10001:10001.

## R-005 — Logs no journal limitados a ~50 MB  ⚠ risco principal

- **Decision (validada na VM em 2026-10-27, Podman 5.7.0)**: `LogDriver=journald` + `LogNamespace=cato-monitor` no `[Service]` +
  `/etc/systemd/journald@cato-monitor.conf` com `SystemMaxUse=50M` (e `RuntimeMaxUse=50M`).
  Leitura: `journalctl --namespace=cato-monitor -u cato-monitor` e `podman logs cato-monitor`.
- **Rationale**: o namespace de journal é a forma de dar um teto próprio aos logs do serviço, sem
  mexer no limite global do host (FR-018, SC-009).
- **Resultado do experimento (T002)**: `systemd-run -p LogNamespace=cato-teste podman run --log-driver journald …`
  gravou a linha de teste **somente** em `journalctl --namespace=cato-teste`; `journalctl CONTAINER_NAME=…` no journal
  padrão não achou nada. O risco abaixo não se confirmou: ficam `journald` + `LogNamespace`, sem fallback e sem
  emenda a FR-018. (A linha apareceu duas vezes porque o teste rodou `podman run` em primeiro plano; o serviço Quadlet
  roda desacoplado.)
- **Risco**: com `--log-driver journald`, quem grava no journal é o `conmon`, e ele envia ao socket do
  namespace **padrão**, não ao do `LogNamespace` da unidade. Se for o caso, as linhas caem no journal
  global e o teto de 50 MB não vale.
- **Ordem de fallback (decidir após o experimento T-spike)**:
  1. `LogDriver=passthrough` com `LogNamespace`: stdout/stderr vão direto ao fluxo da unidade, que
     respeita o namespace. Perde `podman logs`; documentar `journalctl --namespace=…` como o caminho.
  2. Manter `journald` no namespace padrão com `SystemMaxUse` global e deixar a spec ajustar FR-018
     (teto global, não por serviço). Exige emenda na spec.
  Primeira tarefa de implementação = experimento de 15 min na VM para escolher.

## R-006 — Build na VM

- **Decision**: `podman build --format docker -t localhost/cato-monitor:<sha12> -f Containerfile .`
  seguido de `podman tag … localhost/cato-monitor:latest` só após o build passar. O Quadlet usa
  `Image=localhost/cato-monitor:latest`, com `Pull=never`. O build recebe
  `--label org.opencontainers.image.revision=<sha>`.
- **Rationale**: a tag `latest` só se move quando o build deu certo, então uma falha de build não
  afeta o container em execução (FR-028). A label permite ver o commit em execução (FR-031) por
  `podman inspect`. `--format docker` também preserva o `HEALTHCHECK`.
- **Containerfile**: sem mudança de conteúdo. A base continua fixada por digest, `--require-hashes` e
  o bloco de `certs/` ficam como estão. `.containerignore` ganha `deploy/`.
- Limpeza: após o deploy, `podman image prune -f` e manter as 2 últimas tags `<sha12>`, para o disco
  não crescer (rollback manual possível por `podman tag`).

## R-007 — Deploy por polling

- **Decision**: `cato-deploy.timer` (`OnBootSec=2min`, `OnUnitActiveSec=5min`, `Persistent=true`)
  dispara `cato-deploy.service` (`Type=oneshot`), que executa `cato-deploy.sh`.
- **Rationale**: sem conexão de entrada (FR-027); pausar = `systemctl stop cato-deploy.timer`; forçar =
  `systemctl start cato-deploy.service`; falha visível = unidade em `failed` (FR-028, FR-031).
  `OnUnitActiveSec` mede a partir do fim da execução anterior, então builds longos não se sobrepõem;
  `flock` no script protege contra execução manual concorrente.
- **Fluxo do script** (detalhe em [contracts/deploy-automatico.md](contracts/deploy-automatico.md)):
  `git ls-remote origin main` → se igual a `deployed-commit`, sai → `git fetch` +
  `git reset --hard FETCH_HEAD` → build → tag → `systemctl try-restart cato-monitor` →
  espera e confere `is-active` → grava `deployed-commit` → avisa.
- **`try-restart`** só reinicia se o serviço estiver ativo; com o monitor parado à mão a imagem é
  reconstruída e o container não é iniciado (edge case da spec). Nesse caso o deploy conta como
  sucesso e o aviso diz "imagem atualizada, serviço parado manualmente".
- **Alternatives**: webhook do GitLab (exige entrada na VM, vetado); GitLab Runner (infra extra);
  `podman auto-update` (exige registro de imagens; fora do modelo "build na VM").

## R-008 — Credencial do GitLab

- **Decision**: *deploy token* somente leitura (`read_repository`), em
  `/etc/cato-monitor/gitlab-credentials` (0600, root), no formato do `git credential store`
  (`https://<usuario>:<token>@gitlab.empresa/`). O clone usa a URL sem credencial e
  `-c credential.helper='store --file=/etc/cato-monitor/gitlab-credentials'`.
- **Rationale**: nada de token na linha de comando, no `.git/config` ou em `ps`. Chave de deploy SSH é
  alternativa equivalente; HTTPS foi escolhido por usar a mesma saída que o build já exige.
- O script nunca imprime a URL com credencial; mensagens de erro do `git` passam por `sed` que remove
  `://…@`.

## R-009 — Aviso no Teams a partir do script

- **Decision**: `curl --max-time 10` com o mesmo envelope usado por `teams.py` (`type: message` +
  `attachments` com Adaptive Card). O JSON é montado com `jq -n --arg` (sem interpolar texto cru). O
  webhook é lido do `.env` com `grep '^TEAMS_WEBHOOK_OPERACIONAL_URL='` — o arquivo nunca é
  carregado com `source`, para não executar nem exportar os demais segredos.
- **Dedup**: `failed-commit` guarda `<sha>:<etapa>`; falha com mesmo valor não reavisa (FR-029). Falha
  em outra etapa do mesmo commit é um novo valor e avisa. Sucesso limpa `failed-commit`.
- **Falha do aviso** só vai para o journal; o código de saída do deploy não muda. Se o webhook
  operacional não estiver no `.env`, o deploy segue sem aviso e registra isso.
- Falha na etapa "download" por causa do GitLab/token também vira aviso único, dedupada por causa
  (`download:<resumo>`) e não por commit, pois o commit nem é conhecido (edge case da spec).

## R-010 — Rootful e SELinux/AppArmor

- Ubuntu usa AppArmor; o perfil padrão do Podman (`containers-default`) é aplicado sem ajuste.
  Sem bind mounts do host (só volume nomeado e `EnvironmentFile`, lido pelo systemd, não pelo
  container), não há rótulo `:Z` a tratar.

## R-011 — Testes sem rodar Podman no CI local

- `tests/unit/test_servico_repo.py` lê `deploy/cato-monitor.container` e verifica: `EnvironmentFile`
  presente; nenhuma `Environment=` com palavra secreta (reusa `PALAVRAS_SECRETAS`); hardening
  completo; `StopTimeout=30`; healthcheck igual ao do `Containerfile`; ausência de `Scale`/réplicas e
  presença de `ContainerName`; `Restart=always`, `RestartSec=30`, `StartLimitIntervalSec=0`;
  `LogDriver` definido.
- Testes do script de deploy: `git` real com repositório local temporário; `podman`, `systemctl` e
  `curl` substituídos por scripts falsos no `PATH` que registram as chamadas. Cobrem: sem commit novo,
  sucesso, falha de build, falha de início, aviso único por commit, serviço parado à mão, webhook
  ausente.
- Validações de sintaxe fora do pytest, no quickstart: `systemd-analyze verify` e
  `/usr/lib/systemd/system-generators/podman-system-generator --dryrun`.

## R-012 — Emenda da constituição

- "Python 3.12 em contêiner Docker" → "Python 3.12 em contêiner OCI executado com Podman". Versão
  1.0.0 → 1.0.1 (PATCH, esclarecimento de runtime). Registrar no relatório de impacto do arquivo.
