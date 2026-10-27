# Quickstart: validar a migração na VM

Pré-requisito: VM Ubuntu Server 26, acesso `sudo`, saída HTTPS ao GitLab, ao registro da imagem base e
ao PyPI (build) e aos webhooks. Detalhes de cada artefato nos [contratos](contracts/).

## 0. Experimento de logs (antes de implementar, ver R-005)

Rodar um container de teste com `--log-driver journald` sob uma unidade com `LogNamespace=` e conferir
em qual journal as linhas caem (`journalctl --namespace=…` ou o padrão). Registrar a decisão em
[research.md](research.md).

## 1. Instalação

```bash
podman --version            # 5.7.0
git clone <REPO_URL> /opt/cato-monitor/repo && cd /opt/cato-monitor/repo
sudo deploy/install.sh      # copia unidades e script, cria /etc/cato-monitor e /var/lib/cato-monitor
sudo cp .env.example /etc/cato-monitor/.env && sudoedit /etc/cato-monitor/.env && sudo chmod 600 /etc/cato-monitor/.env
sudoedit /etc/cato-monitor/gitlab-credentials   # 0600
sudo systemctl start cato-deploy.service        # 1º build + tag latest
sudo systemctl enable --now cato-monitor.service cato-deploy.timer
```

Esperado: `systemctl status cato-monitor` ativo; um card `MONITOR INICIADO`; sem alertas em massa (SC-005).

## 2. Cenários

| # | Verificação | Resultado esperado |
|---|---|---|
| 1 | `journalctl -u cato-monitor -f` e `sudo podman logs cato-monitor` | logs JSON em tempo real (US1-2) |
| 2 | Após 2 min: `podman inspect … .State.Health.Status` | `healthy`; parar o ciclo (ex.: apagar `last_cycle` no volume) → `unhealthy` após 3 falhas e **sem** reinício (US1-3/4) |
| 3 | `sudo systemctl stop cato-monitor` | encerra em ≤ 30 s e continua parado (US1-5, SC-008) |
| 4 | `sudo pkill -9 -f cato_monitor` | volta em ≤ 2 min (US2-1, SC-003) |
| 5 | `sudo reboot` sem login | monitor executa ciclos em ≤ 5 min (US2-2, SC-002) |
| 6 | `.env` inválido + restart | falha a cada 30 s, erro no journal; corrigir → sobe sozinho (edge case) |
| 7 | `sudo podman inspect cato-monitor` | read-only, tmpfs `/tmp`, `CapDrop=ALL`, `no-new-privileges`, user 10001 (SC-006) |
| 8 | 2º container sobre o mesmo volume (`podman run --rm -v cato-monitor-data:/data localhost/cato-monitor:latest`) | recusado pelo lock (SC-007) |
| 9 | `podman history --no-trunc` e `inspect` da imagem, buscando valores do `.env` | nenhum encontrado (SC-010) |
| 10 | Recriar container / reboot e comparar `ls -ln` e conteúdo de `/data` | arquivos e fila intactos, sem nova linha de base (SC-004) |
| 11 | Commit na branch principal | em ≤ 15 min: novo commit em execução + card `DEPLOY CONCLUÍDO` (SC-012) |
| 12 | Commit que quebra o build, esperar 3 verificações | versão anterior segue; 1 único card `DEPLOY FALHOU` (SC-013) |
| 13 | Commit de correção | card de sucesso |
| 14 | `systemctl stop cato-monitor` + commit novo | imagem reconstruída, monitor continua parado |
| 15 | Revogar o token | falha `download` avisada uma vez; monitor intacto |
| 16 | Gerar logs por horas (ou `SystemMaxUse` baixo em teste) | journal do serviço ≤ ~50 MB (SC-009) |

## 3. Validação estática (sem subir container)

```bash
systemd-analyze verify /etc/systemd/system/cato-deploy.service /etc/systemd/system/cato-deploy.timer
/usr/lib/systemd/system-generators/podman-system-generator --dryrun
pytest -q                  # no desenvolvimento, em qualquer SO
```
