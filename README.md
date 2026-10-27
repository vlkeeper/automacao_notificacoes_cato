# Monitor de Sockets Cato com avisos no Teams

Daemon Python 3.12 que consulta a API GraphQL da Cato a cada intervalo (padrão 60 s), detecta queda e
retorno de **links** e **sites** e avisa um canal do Microsoft Teams com cards em linguagem simples.

- **Queda**: só avisa depois da tolerância (padrão 180 s) e uma única vez por episódio. Distingue
  `LINK OFFLINE` (operação parcial) de `SITE OFFLINE` (todos os links fora ou site desconectado da Cato).
- **Sites HA**: a queda de um socket inteiro gera um único `SOCKET OFFLINE` (e `SOCKET DE VOLTA` no retorno),
  sem um `REDE OFFLINE` por porta; se o site inteiro cai, só o `SITE OFFLINE` é avisado.
- **Retorno**: avisa só quando a queda foi comunicada, com a duração.
- **Lembrete diário** (padrão 08:00, horário de Brasília): lista o que continua fora; nunca repete no mesmo dia.
- **Saúde do próprio monitor**: após 5 falhas seguidas de consulta avisa `MONITOR: SEM ACESSO À CATO` e,
  quando normaliza, `ACESSO NORMALIZADO`. Falha de consulta **nunca** vira alerta de queda.
- **Estado persistido** em `/data/state.json` (gravação atômica): reiniciar o serviço não repete avisos
  nem perde a contagem da tolerância. Eventos não entregues ao Teams ficam em fila e são reenviados na ordem.

> O monitor é **somente leitura** na Cato.

## Pré-requisitos

1. **Token da API Cato somente leitura** (Catopa → Resources → API Management). Dê a permissão mínima de
   leitura (visualizar sites/snapshot); não use token com permissão de escrita.
2. **ID da conta Cato** (`CATO_ACCOUNT_ID`, só dígitos).
3. **Fluxo do Teams** (uma vez): no canal de destino, `⋯ → Workflows → "Post to a channel when a webhook
   request is received"`, escolha equipe e canal e copie a URL gerada. Ela é um **segredo**.
4. **Heartbeat externo** (recomendado): uma checagem no [Healthchecks.io](https://healthchecks.io) ou
   compatível. Configure `Period` = `INTERVALO_SEGUNDOS` e `Grace` = 2 intervalos (ex.: 1 min e 2 min para
   o padrão de 60 s), com alerta para o responsável por um canal **diferente** do Teams.
5. Uma VM Linux com Podman 5.7.0 e systemd **fora da rede monitorada** (para que a queda do site onde o monitor
   roda não o derrube) e com **NTP ativo** (toda a lógica depende de timestamps).

## Configuração

Copie `.env.example` para `.env` e preencha. **Nunca versione o `.env`.**

| Variável | Obrig. | Padrão | Descrição |
|---|---|---|---|
| `CATO_API_KEY` | sim | — | token somente leitura (segredo) |
| `CATO_ACCOUNT_ID` | sim | — | id da conta (só dígitos) |
| `CATO_API_URL` | não | `https://api.catonetworks.com/api/v1/graphql2` | endpoint (https) |
| `TEAMS_WEBHOOK_URL` | sim | — | URL do fluxo do Teams do **canal de rede**: quedas, retornos e pendências do dia (segredo, https) |
| `TEAMS_WEBHOOK_OPERACIONAL_URL` | sim | — | URL do fluxo do Teams do **canal operacional**: saúde do robô (segredo, https). Pode ser igual à de rede |
| `HEARTBEAT_URL` | sim | — | URL do heartbeat (segredo, https) |
| `INTERVALO_SEGUNDOS` | não | `60` | 30 a 120 |
| `TOLERANCIA_SEGUNDOS` | não | `180` | 60 a 3600 e ≥ intervalo |
| `LEMBRETE_HORARIO` | não | `08:00` | `HH:MM` no fuso `TZ` |
| `TZ` | não | `America/Sao_Paulo` | fuso de exibição e do lembrete |
| `STATE_DIR` | não | `/data` | diretório do estado (precisa ser gravável) |
| `LOG_LEVEL` | não | `INFO` | `DEBUG`/`INFO`/`WARNING`/`ERROR` |

Configuração inválida encerra o processo com `exit 1` e um log `config_invalida` (stderr) listando **todos**
os erros, sem exibir segredos. Detalhes em
[specs/001-cato-socket/contracts/configuracao.md](specs/001-cato-socket/contracts/configuracao.md).

### Canais do Teams

| Aviso | Canal |
|---|---|
| Link/socket/site offline, de volta, pendências do dia | rede (`TEAMS_WEBHOOK_URL`) |
| Monitor sem acesso à Cato, normalizado, iniciado | operacional (`TEAMS_WEBHOOK_OPERACIONAL_URL`) |
| Canal de rede sem entrega / normalizado | operacional |
| Canal operacional sem entrega / normalizado | rede |

Cada canal tem sua própria fila persistida; um canal fora do ar não atrasa o outro. Após 15 min de
falha contínua de entrega, um único aviso "CANAL … SEM ENTREGA" vai ao outro canal (e a normalização
depois). **Atualização:** configure `TEAMS_WEBHOOK_OPERACIONAL_URL` antes de subir a nova versão. O
`state.json` v1 é migrado automaticamente; `state.json.v1-<UTC>` é a cópia de segurança.

## Execução (Podman + systemd)

O monitor roda como um contêiner OCI sob **Podman 5.7.0 (rootful)**, gerenciado pelo systemd por uma
unidade Quadlet. Confira a versão com `podman --version`. Os arquivos ficam em [deploy/](deploy/).

```bash
sudo ./deploy/install.sh                       # instala as unidades; não inicia nada
sudo install -m 0600 .env.example /etc/cato-monitor/.env   # e preencha os valores
sudo podman build --format docker -t localhost/cato-monitor:latest -f Containerfile .
sudo systemctl start cato-monitor
```

O `cato-monitor.service` é gerado pelo Quadlet: não use `systemctl enable` nele (falha com "transient or generated"). O `WantedBy=` do `.container` já o liga ao boot, então ele sobe sozinho após reiniciar a VM.

`--format docker` é necessário para a imagem manter o `HEALTHCHECK`.

| Ação | Comando |
|---|---|
| Iniciar / parar / reiniciar | `sudo systemctl start\|stop\|restart cato-monitor` |
| Estado | `systemctl status cato-monitor` |
| Logs (JSON) | `journalctl --namespace=cato-monitor -u cato-monitor -f` · `sudo podman logs -f cato-monitor` |
| Saúde | `sudo podman inspect --format '{{.State.Health.Status}}' cato-monitor` |

- O `.env` fica em `/etc/cato-monitor/.env` com `chmod 600` (só root). Para alterá-lo basta editar e rodar
  `sudo systemctl restart cato-monitor`, sem reconstruir a imagem. Já os certificados em `certs/` entram na
  imagem: após mudá-los, reconstrua (comando acima) e reinicie.
- Na primeira execução (ou com estado corrompido) o monitor faz uma **linha de base**: registra os itens
  atuais e envia **um** card `MONITOR INICIADO`, sem alertas em massa.
- Uma única instância: o nome fixo do contêiner e o lock `/data/monitor.lock` impedem uma segunda
  (`instancia_duplicada`).
- A saúde fica `unhealthy` se o último ciclo tiver mais de `3 × INTERVALO + 30 s`; isso só é registrado,
  não reinicia o serviço. O primeiro status confiável aparece após 120 s.
- Todos os logs saem em JSON no stdout (vão ao journal); token e URLs do Teams/heartbeat são mascarados.
  O journal do serviço fica limitado a ~50 MB pelo namespace `cato-monitor`
  (sem `--namespace` o `journalctl` não mostra os logs do monitor; ver `deploy/journald@cato-monitor.conf`).

### Recuperação automática

- Se o processo cair, o systemd o reinicia a cada 30 s, **sem limite de tentativas**.
- Após reboot da VM o serviço habilitado sobe sozinho, sem login. Isso vale mesmo para um serviço parado
  à mão antes do reboot (diferença aceita em relação ao `unless-stopped` do Compose); `systemctl stop`
  mantém parado até o próximo reboot.
- Com o `.env` ausente ou inválido o serviço falha e é retentado a cada 30 s (veja `journalctl --namespace=cato-monitor -u
  cato-monitor`); corrija o arquivo e ele sobe sozinho na próxima tentativa.

### Primeira instalação numa VM nova

1. Instale Podman 5.7.0, `git`, `curl` e `jq`; garanta NTP ativo.
2. Clone o repositório em `/opt/cato-monitor/repo` e entre nele.
3. `sudo ./deploy/install.sh`, depois `sudo install -m 0600 .env.example /etc/cato-monitor/.env` e preencha.
4. Construa a imagem (comando acima) e `sudo systemctl start cato-monitor`.
5. Valide: `systemctl status cato-monitor`, `journalctl --namespace=cato-monitor -u cato-monitor -f` e, depois de 120 s, a saúde
   `healthy`.

O volume `cato-monitor-data` é criado vazio, com dono `10001:10001`. O primeiro ciclo faz a linha de base:
espere **um** card `MONITOR INICIADO` e nenhum alerta de queda. Se criar o volume à mão, ajuste o dono:
`sudo podman volume inspect cato-monitor-data` (campo `Mountpoint`) e `sudo chown 10001:10001 <mountpoint>`.

### Deploy automático

Um timer (`cato-deploy.timer`) consulta o GitLab a cada 5 min; havendo commit novo na branch configurada,
reconstrói a imagem e reinicia o serviço (em até ~15 min do commit). Cada deploy gera um card
`DEPLOY CONCLUÍDO` ou `DEPLOY FALHOU` (um por commit/etapa) no canal operacional.

1. No GitLab crie um *deploy token* somente leitura (`read_repository`).
2. Em `/etc/cato-monitor/gitlab-credentials` (0600) coloque `https://<usuario>:<token>@gitlab.empresa/`.
3. Em `/etc/cato-monitor/repo.conf` informe `REPO_URL=https://gitlab.empresa/grupo/monitor.git` e `BRANCH=main`.
4. `sudo systemctl enable --now cato-deploy.timer`.

| Necessidade | Comando |
|---|---|
| Commit em execução | `cat /var/lib/cato-monitor/deployed-commit` |
| Última verificação / deploy | `cat /var/lib/cato-monitor/{last-check,last-deploy}` · `systemctl list-timers cato-deploy.timer` |
| Forçar agora | `sudo systemctl start cato-deploy.service` |
| Pausar / retomar | `sudo systemctl stop\|start cato-deploy.timer` |
| Ver falhas | `systemctl status cato-deploy.service` · `journalctl -u cato-deploy.service` |

- Falha de build ou de início **não derruba** a versão em execução e não há rollback automático: corrija com
  um novo commit (ou `revert`).
- Com o monitor parado à mão, o deploy atualiza a imagem mas **não** o inicia (o card avisa).
- Proteja a branch principal com um pipeline de testes: tudo que entra nela é implantado.

### Desinstalação

```bash
sudo systemctl stop cato-monitor
sudo systemctl disable --now cato-deploy.timer
sudo rm /etc/containers/systemd/cato-monitor.{container,volume} /etc/systemd/system/cato-deploy.{service,timer}
sudo systemctl daemon-reload
```

Isso **preserva** o estado. Apagá-lo é um passo explícito e destrutivo: `sudo podman volume rm cato-monitor-data`.

## Desenvolvimento e testes

```bash
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest -q
```

Atualizar dependências (versões exatas com hashes): `pip-compile --generate-hashes requirements.in`
e `requirements-dev.in`.

Estrutura: `src/cato_monitor/` (código), `tests/unit` e `tests/integration` (testes),
`specs/001-cato-socket/` (especificação, plano, contratos e tarefas).

## Pendências conhecidas

- O parser de `snapshot.py` segue o contrato **candidato** da API Cato: o campo de papel LAN/WAN das portas
  e o comportamento de uma WAN caída precisam ser **verificados com a conta real** (tarefa T007) e as
  fixtures de `tests/fixtures/cato/` substituídas por payloads reais anonimizados.
