# Contrato: deploy automático

## Unidades

| Unidade | Tipo | Pontos principais |
|---|---|---|
| `cato-deploy.timer` | timer | `OnBootSec=2min`, `OnUnitActiveSec=5min`, `Persistent=true`, `WantedBy=timers.target` |
| `cato-deploy.service` | oneshot | `ExecStart=/usr/local/lib/cato-monitor/cato-deploy.sh`, `TimeoutStartSec=20min`, roda como root, `After=network-online.target` |

## Configuração do host

- `/etc/cato-monitor/repo.conf`: `REPO_URL=https://gitlab.empresa/grupo/monitor.git`, `BRANCH=main`.
- `/etc/cato-monitor/gitlab-credentials` (0600): linha do `git credential store`.
- `/etc/cato-monitor/.env` (0600): lido só para `TEAMS_WEBHOOK_OPERACIONAL_URL`.

## Algoritmo de `cato-deploy.sh`

1. `flock -n` em `/run/cato-deploy.lock`; se ocupado, sai com 0.
2. Grava `last-check`.
3. `git ls-remote REPO_URL refs/heads/BRANCH` → `novo`. Falha → etapa `download`, causa resumida.
4. Se `novo == deployed-commit`, sai com 0.
5. `git fetch` + `git reset --hard FETCH_HEAD` no clone (clona se não existir). Falha → `download`.
6. `podman build --format docker --label org.opencontainers.image.revision=$novo -t localhost/cato-monitor:${novo:0:12} .`
   Falha → `build`. Sucesso → `podman tag … :latest`.
7. Registra se o monitor estava ativo; `systemctl try-restart cato-monitor.service`; se estava ativo,
   aguarda até 60 s por `is-active` e 10 s de estabilidade. Se estava parado à mão, pula a espera e
   conta como sucesso com nota. Falha → `inicio`.
8. Sucesso: grava `deployed-commit`, `last-deploy`, apaga `failed-commit`; poda imagens antigas; avisa.
9. Falha: se `<sha>:<etapa>` ≠ `failed-commit`, avisa e grava; sai com 1 (a unidade fica `failed`).

## Códigos de saída

`0` sem novidade ou sucesso · `1` falha de deploy (qualquer etapa). O aviso do Teams nunca altera o
código.

## Interface do operador (FR-031)

| Necessidade | Comando |
|---|---|
| Commit em execução | `cat /var/lib/cato-monitor/deployed-commit` ou `podman inspect cato-monitor --format '{{index .Config.Labels "org.opencontainers.image.revision"}}'` |
| Última verificação / deploy | `cat /var/lib/cato-monitor/{last-check,last-deploy}` · `systemctl list-timers cato-deploy.timer` |
| Forçar agora | `sudo systemctl start cato-deploy.service` |
| Pausar / retomar | `sudo systemctl stop cato-deploy.timer` / `sudo systemctl start cato-deploy.timer` |
| Ver falha | `systemctl status cato-deploy.service` · `journalctl -u cato-deploy.service` |

## Segurança

Nenhuma saída contém token nem URL do webhook; erros do `git` e do `curl` passam por filtro que remove
`://usuario:senha@` e a URL do webhook. O script usa `set -u -o pipefail` e nunca faz `source` no `.env`.
