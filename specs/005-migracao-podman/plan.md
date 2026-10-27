# Implementation Plan: Migração da execução de Docker para Podman

**Branch**: `005-migracao-podman` | **Date**: 2026-10-27 | **Spec**: [spec.md](spec.md)

**Input**: especificação da feature em `specs/005-migracao-podman/spec.md`

## Summary

A automação passa a rodar na VM Ubuntu Server 26 só com Podman 5.7.0 (rootful), gerenciada pelo
systemd. O `docker-compose.yml` é substituído por uma unidade **Quadlet** (`cato-monitor.container`
+ `cato-monitor.volume`) que o gerador do Podman converte em `cato-monitor.service`; ela carrega o
mesmo hardening, o mesmo healthcheck, `init`, `stop_grace_period` de 30 s, `Restart=always` com
`RestartSec=30` e sem limite de tentativas. Os logs vão para o journal (driver `journald`) com teto de
~50 MB por namespace de journal. O deploy automático é um par `cato-deploy.timer`/`cato-deploy.service`
(a cada 5 min) que roda um script shell: compara o commit remoto com o implantado, baixa, constrói a
imagem na VM, reinicia o monitor (`try-restart`, respeitando um `stop` manual) e avisa o canal
operacional do Teams uma vez por commit. O código Python não muda (FR-024); só mudam os testes de
repositório que liam o compose (nova verificação sobre a unidade Quadlet).

## Technical Context

**Language/Version**: Python 3.12 (sem mudança); scripts de deploy em Bash (POSIX + `flock`, `curl`,
`git`, `jq`, todos nos pacotes do Ubuntu).

**Primary Dependencies**: Podman 5.7.0 (com Quadlet), systemd 259, git, curl, jq. Nenhuma dependência
Python nova.

**Storage**: volume nomeado do Podman `cato-monitor-data` montado em `/data`; estado do deploy em
`/var/lib/cato-monitor/` (`deployed-commit`, `failed-commit`, `last-check`, `last-deploy`).

**Testing**: pytest (testes de repositório sobre `deploy/*`), `systemd-analyze verify`, `podman-system-generator --dryrun` (valida o Quadlet) e roteiro manual na VM em [quickstart.md](quickstart.md). O script de deploy é testado por `pytest` via `subprocess`, com `git` local real e `podman`, `systemctl` e `curl` simulados no `PATH`.

**Target Platform**: VM Ubuntu Server 26, sem GUI, via SSH. Windows do desenvolvedor só roda pytest.

**Project Type**: serviço de longa duração em container (single project) + artefatos de implantação.

**Performance Goals**: deploy visível em até 15 min (SC-012); volta após falha em até 2 min (SC-003).

**Constraints**: sem Docker; sem conexão de entrada na VM; segredos só no `.env` do host e na credencial
do GitLab (0600, fora da imagem); `systemctl stop` encerra em ≤ 30 s.

**Scale/Scope**: uma VM, uma instância, um repositório.

## Constitution Check

*GATE: passa antes da Fase 0 e é reavaliado após a Fase 1.*

| Princípio | Avaliação |
|-----------|-----------|
| I. Resiliência de Estado | OK. Volume nomeado persistente; `systemctl stop` dá 30 s ao SIGTERM; reboot no meio de ciclo coberto pela gravação atômica existente. |
| II. Falha ≠ Evento | OK. Sem mudança de código. O deploy falho não toca o estado. |
| III. Máquina de Estados | N/A (sem mudança de código). |
| IV. Anti-Fadiga | OK por analogia: o aviso de deploy é único por commit (FR-029). |
| V. Rede Defensiva / Sem Perda | OK. A fila segue em `/data`. O `curl` do aviso tem `--max-time` e a falha dele não afeta o deploy. |
| VI. Segredos e Fail-Fast | OK. Segredos só em `EnvironmentFile` (`/etc/cato-monitor/.env`, 0600); credencial do GitLab em arquivo 0600; o script lê só `TEAMS_WEBHOOK_OPERACIONAL_URL` por `grep` (não faz `source`) e nunca a imprime. Config inválida: `exit 1` + `RestartSec=30`. |
| VII. Observabilidade | OK. Logs JSON no journal; healthcheck idêntico. |
| VIII. Banco secundário | N/A. |
| Restrições Adicionais | **Desvio documentado**: "contêiner Docker" → "contêiner OCI executado com Podman". Emenda PATCH 1.0.1 na constituição, feita nesta feature (tarefa própria). Demais restrições (não-root, instância única, hashes) mantidas. |

Sem violações que exijam Complexity Tracking. **Reavaliação pós-design**: mantida; nenhuma decisão da
Fase 1 abre exceção.

## Project Structure

### Documentation (this feature)

```text
specs/005-migracao-podman/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── quadlet-cato-monitor.md
│   ├── deploy-automatico.md
│   └── aviso-teams-deploy.md
├── checklists/requirements.md
└── tasks.md             # gerado por /speckit-tasks
```

### Source Code (repository root)

```text
Containerfile                      # já renomeado; sem mudança de conteúdo (R-003 só exige --format docker no build)
.containerignore                   # já renomeado; passa a excluir deploy/
deploy/
├── cato-monitor.container         # Quadlet do monitor → /etc/containers/systemd/
├── cato-monitor.volume            # Quadlet do volume de estado
├── cato-deploy.service            # oneshot: roda o script de deploy
├── cato-deploy.timer              # OnBootSec=2min, OnUnitActiveSec=5min
├── cato-deploy.sh                 # lógica de deploy (instalado em /usr/local/lib/cato-monitor/)
├── journald@cato-monitor.conf     # SystemMaxUse=50M para o namespace de logs
└── install.sh                     # copia os arquivos, cria diretórios/permissões, habilita
tests/unit/
├── test_segredos_repo.py          # já ajustado aos novos nomes
└── test_servico_repo.py           # NOVO: verifica deploy/cato-monitor.container (substitui o teste do compose)
README.md                          # seção "Execução (Podman + systemd)" no lugar de Docker Compose
changelog.md                       # entrada da troca de runtime
.specify/memory/constitution.md    # emenda PATCH 1.0.1
certs/README.md                    # já ajustado
```

**Structure Decision**: projeto único existente; a nova pasta `deploy/` concentra tudo que é instalado
no host e fica fora do contexto de build (`.containerignore`). O `docker-compose.yml` já foi removido
no working tree.

## Complexity Tracking

Sem violações a justificar.
