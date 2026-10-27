# Contrato: unidades Quadlet do monitor

Arquivos em `deploy/`, instalados em `/etc/containers/systemd/`. O gerador do Podman produz
`cato-monitor.service` e `cato-monitor-volume.service`. Este contrato é o que
`tests/unit/test_servico_repo.py` verifica.

## `cato-monitor.volume`

```ini
[Volume]
VolumeName=cato-monitor-data
User=10001
Group=10001
Group=10001
```

## `cato-monitor.container`

```ini
[Unit]
Description=Monitor de Sockets Cato
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=0

[Container]
ContainerName=cato-monitor
Image=localhost/cato-monitor:latest
Pull=never
ReadOnly=true
Tmpfs=/tmp
DropCapability=ALL
NoNewPrivileges=true
User=10001
EnvironmentFile=/etc/cato-monitor/.env
Environment=STATE_DIR=/data
Volume=cato-monitor.volume:/data
StopTimeout=30
LogDriver=journald
HealthCmd=python -m cato_monitor.healthcheck
HealthInterval=60s
HealthTimeout=5s
HealthStartPeriod=120s
HealthRetries=3
HealthOnFailure=none

[Service]
Restart=always
RestartSec=30
TimeoutStopSec=45
# sem LogNamespace=: quebra o podman stop (R-005); teto de logs em journald-cato-monitor.conf

[Install]
WantedBy=multi-user.target
```

## Invariantes

| Regra | Requisito |
|---|---|
| Nenhum valor de segredo em `Environment=`; segredos só via `EnvironmentFile` | FR-015 |
| `ReadOnly`, `Tmpfs=/tmp`, `DropCapability=ALL`, `NoNewPrivileges=true` presentes | FR-014 |
| Usuário do processo = UID numérico 10001 (`User=10001`, igual ao da imagem); nunca root. Numérico porque o Podman 5.7 não resolve o nome `monitor` no healthcheck/exec | FR-014 |
| `StopTimeout=30`; **sem** `RunInit` (com `NoNewPrivileges=true` o init não repassa o SIGTERM no Podman 5.7.0; o monitor trata o sinal como PID 1 e não cria processos filhos) | FR-006 |
| Parâmetros de saúde iguais aos do `HEALTHCHECK` do `Containerfile`; `HealthOnFailure=none` | FR-007, FR-009 |
| `Restart=always`, `RestartSec=30`, `StartLimitIntervalSec=0` | FR-004 |
| `ContainerName` fixo; sem `Scale`/réplicas | FR-010 |
| Sem `PublishPort` | Assumptions |
| `Image=` aponta para tag local com `Pull=never` | FR-019a |

## Interface do operador

- `sudo systemctl {start|stop|restart|status} cato-monitor` (sem `enable`: unidade gerada; o `[Install]` é aplicado pelo gerador)
- `journalctl -u cato-monitor -f` (teto global de 50 MB, ver R-005)
- `sudo podman logs -f cato-monitor`
- `sudo podman inspect --format '{{.State.Health.Status}}' cato-monitor`
