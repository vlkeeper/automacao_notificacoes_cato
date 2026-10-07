# Research: Monitoramento de Sockets Cato com Avisos no Teams

**Feature**: `specs/001-cato-socket` | **Date**: 2026-10-06 | **Plan**: [plan.md](plan.md)

Cada item registra **Decisão**, **Justificativa** e **Alternativas consideradas**. Não há itens
`NEEDS CLARIFICATION` em aberto. O item R-001 tem uma **verificação obrigatória**: um passo de
desenvolvimento que confirma o schema real da Cato antes de implementar o parser. Ele não é uma
dúvida de requisito.

---

## R-001 — Fonte dos dados na Cato (query única) e campos de conectividade

**Decisão**: usar uma única query `accountSnapshot(accountID)` por ciclo, que traz todos os sites
com seus sockets (`devices`) e as interfaces de cada socket. O mapeamento é este:

| Conceito da spec | Campo candidato na Cato | Regra |
|---|---|---|
| Site conectado | `sites[].connectivityStatus` (`connected` / `disconnected`) | `disconnected` ⇒ site observado offline |
| Inventário de portas do socket | `sites[].devices[].interfacesLinkState[]` (`id`, `up`, ...) | lista todas as portas físicas; serve de inventário de links |
| Link WAN online | `sites[].devices[].interfaces[]` (`id`, `name`, `connected`, `tunnelUptime`, ...) | WAN online ⇔ túnel conectado à Cato (`connected == true`) |
| Link LAN online | `interfacesLinkState[].up` | LAN online ⇔ `up == true` (LAN não tem túnel com a Cato) |
| Papel da porta (LAN/WAN) e nome exibido | campo de papel/destino da interface no `info` do site ou da interface (ex.: `destType`/`wanRole`). **A confirmar** no schema | só são monitoradas as portas **configuradas** com papel LAN ou WAN; portas sem uso são ignoradas |
| Identificação do socket (HA) | `devices[].socketInfo { id serial isPrimary }` / `haRole` | chave do link = `<id do socket>/<id da interface>` |
| Desde quando (linha de base) | `sites[].lastConnected`, `devices[].lastConnected` | usado só como "desde" informativo na linha de base |

Endpoint: `POST https://api.catonetworks.com/api/v1/graphql2`, header `x-api-key`. A query é
somente leitura (FR-013).

**Verificação obrigatória (antes de escrever o parser)**:
1. Com o Cato CLI (`catocli`), apenas na máquina de desenvolvimento, executar a `accountSnapshot` da
   conta e inspecionar o schema (`catocli query accountSnapshot -h` e introspecção). Confirmar:
   (a) qual campo traz o papel LAN/WAN e o nome configurado da porta, exatamente como no portal;
   (b) se uma WAN caída **continua listada** em `devices[].interfaces` com `connected=false` ou
   **some** da lista; (c) o formato dos `id` de interface (ex.: `WAN1`, `LAN1`, `INT_5`).
2. Fixar a query validada em [contracts/cato-graphql.md](contracts/cato-graphql.md) e salvar 4
   payloads reais anonimizados em `tests/fixtures/cato/` (todos online, link WAN caído, site
   desconectado, site HA).
3. Se (b) mostrar que a WAN caída some de `interfaces`, a regra passa a ser esta: a porta está no
   inventário (`interfacesLinkState`) com papel WAN e não aparece em `interfaces` conectada, então é
   offline. Essa decisão fica toda dentro de `snapshot.py`. A máquina de estados não muda.

**Justificativa**: uma query por ciclo, em vez de uma por site, mantém o custo constante, reduz o
risco de 429 e dá uma "foto" consistente de toda a conta. A documentação da Cato diz que
`interfaces` indica a conexão da porta com a nuvem Cato e que `interfacesLinkState` indica o link
físico. A Cato marca o site como "degraded" quando um dos dois falha numa interface configurada.
Por isso usamos o túnel (`interfaces`) para a WAN e o link físico para a LAN.

**Alternativas consideradas**:
- Uma query `accountSnapshot(siteIDs: [x])` por site. Rejeitada: N chamadas por ciclo, mais 429 e
  fotos inconsistentes entre sites.
- `accountMetrics` (séries de throughput e perda). Rejeitada: é métrica de desempenho (fora do
  escopo) e não traz o estado atual.
- Eventos/auditoria da Cato (`eventsFeed`). Rejeitada: exige marcador de leitura e reprocessamento;
  o estado atual é mais simples e robusto a reinícios.
- Executar o Cato CLI em produção. Rejeitada por decisão do usuário: ele traz dependência extra e o
  `requests` já basta.

---

## R-002 — Cliente HTTP: timeout, backoff e resultado tipado

**Decisão**: `requests.Session` com timeout `(connect=5 s, read=20 s)` para a Cato e
`(5 s, 10 s)` para Teams e heartbeat. Respostas 429, 5xx, timeout e erro de conexão acionam backoff
exponencial com jitter: base 2 s, fator 2, teto de 30 s por espera, no máximo 3 tentativas por
chamada. O header `Retry-After` é respeitado até o teto. O tempo total de retentativas da Cato num
ciclo fica limitado a `min(60 s, INTERVALO)`. O cliente nunca levanta exceção para o laço. Ele
retorna `ConsultaOk(snapshot)` ou `ConsultaFalhou(motivo)`. Resposta HTTP 200 com `errors` no corpo
GraphQL, JSON inválido ou falha de validação do snapshot também é `ConsultaFalhou`. Respostas 4xx
diferentes de 429 (como 401 e 403) não têm retentativa.

**Justificativa**: Princípios II e V. O resultado tipado impede que a máquina de estados receba uma
falha como se fosse "offline".

**Alternativas consideradas**: `urllib3.Retry` montado no adapter. Rejeitada: esconde as
tentativas dos logs e não diferencia erro GraphQL dentro de um HTTP 200. `httpx` ou `tenacity`
também foram rejeitadas: seriam dependências extras sem ganho real.

---

## R-003 — Máquina de estados pura e o motor do ciclo

**Decisão**: há duas camadas puras, sem I/O e sem relógio global.
1. `proximo_estado(estado_item, observacao, agora, tolerancia) -> (novo_estado_item, acoes)` é a
   tabela de transições da spec aplicada a **um** item (site ou link). Ela tem um teste por linha.
2. `avaliar_ciclo(estado, resultado_consulta, agora, cfg) -> (novo_estado, eventos)` orquestra o
   ciclo inteiro: falha de consulta, linha de base, avaliação do site e depois dos links, supressão,
   reavaliação no retorno do site, lembrete diário e alerta do monitor.

Regras derivadas, que não estão explícitas na spec mas são coerentes com ela:
- **Adiamento de link enquanto o site está pendente**: se o site está `PENDENTE_OFFLINE`, os links
  dele que atingem a tolerância **não** geram aviso naquele ciclo. Se o site virar
  `OFFLINE_NOTIFICADO`, os links são marcados como `coberto_pelo_site`. Se o site voltar, cada link
  segue sua própria transição. Isso evita a sequência "link offline" seguida de "site offline" numa
  queda total cujos links caíram segundos antes do site. O atraso máximo é de uma tolerância.
- **Retorno do site**: links cobertos que voltaram junto vão para `ONLINE` sem aviso próprio. Links
  cobertos que continuam inativos vão para `OFFLINE_NOTIFICADO`, são citados no aviso de retorno do
  site e entram no lembrete.
- **Consulta falhou**: nada muda nos itens. Só o contador do monitor se altera. Quando a consulta
  volta, o tempo de queda é calculado por timestamps (Princípio III). Assim, um item que já estava
  `PENDENTE_OFFLINE` antes da falha e continua offline depois pode ser notificado no primeiro ciclo
  bom. Isso não é "avançar" a tolerância durante a falha: é medir o tempo real entre duas
  observações válidas.
- **Item ausente numa resposta válida**: é uma observação inválida, e o estado fica inalterado. Se o
  item continuar ausente por **3 ciclos válidos consecutivos** (e, no caso de link, com o site
  conectado), ele é tratado como removido da Cato e sai do estado com log `item_removido`, sem
  aviso. O contador `ausencias` é persistido.
- **Item novo**: entra com o estado observado como linha de base individual, sem aviso. Se já
  estiver offline, entra como `OFFLINE_NOTIFICADO` com `origem=linha_base` e aparece no próximo
  lembrete.

**Justificativa**: Princípio III (função pura e uma transição documentada por teste) e Princípio IV
(anti-fadiga).

**Alternativas**: uma biblioteca de FSM (`transitions`). Rejeitada: a tabela é pequena e a
biblioteca traz estado mutável e callbacks com I/O, o que contraria o Princípio III.

---

## R-004 — Linha de base (primeira execução ou estado corrompido)

**Decisão**: quando o arquivo de estado está ausente, ilegível, com `schema_version` desconhecido ou
inválido no schema, o arquivo ruim é preservado como `state.json.corrompido-<UTC>` (se existir), e o
primeiro ciclo bem-sucedido registra todos os itens. Itens online entram como `ONLINE`. Itens
offline entram como `OFFLINE_NOTIFICADO` com `origem=linha_base` e `inicio_queda` igual ao momento da
linha de base. O `lastConnected` da Cato é guardado só como informação. Em seguida é gerado **um
único** evento `MONITOR_INICIADO`, que resume quantos sites e links estão sendo monitorados e lista
os itens já offline. Se a linha de base ocorrer depois do horário do lembrete, `ultimo_lembrete_data`
recebe a data de hoje, para que o resumo não seja seguido de um lembrete idêntico.

**Justificativa**: Princípio I ("nova linha de base sem alertas em massa"). Com o resumo, os itens
offline da linha de base passam a ser de fato "notificados". Por isso o aviso de retorno deles é
coerente com FR-003 e a equipe não recebe um "voltou" de algo que nunca viu cair.

**Alternativas**: (a) linha de base silenciosa, com o retorno também silencioso para esses itens.
Rejeitada: a equipe nunca saberia do retorno. (b) Um aviso de queda por item offline na linha de
base. Rejeitada: seria um alerta em massa.

---

## R-005 — Lembrete diário

**Decisão**: o lembrete é avaliado no fim de cada ciclo **bem-sucedido**. Se
`agora.astimezone(TZ).time() >= LEMBRETE_HORARIO` e `ultimo_lembrete_data != data_local_de_hoje`,
então `ultimo_lembrete_data` recebe a data de hoje (persistida como `YYYY-MM-DD` local). Um evento
`LEMBRETE_DIARIO` só é gerado se houver sites ou links em `OFFLINE_NOTIFICADO`. Ele lista cada um
com o "desde" (em Brasília) e a duração. Se não houver pendências, a data é marcada mesmo assim:
"até as 08:00" significa uma avaliação por dia, e não um lembrete às 10:00 porque algo caiu às 09:00.

**Justificativa**: FR-005 e o Princípio IV (no máximo uma vez por dia, mesmo após reinício, porque a
data é persistida). Também cobre o caso "monitor parado às 08:00": o lembrete sai no primeiro ciclo
bom após o horário, ainda no mesmo dia.

**Alternativas**: usar um agendador (`schedule`, cron dentro do contêiner). Rejeitada: duplica a
fonte de tempo e não cobre a recuperação após uma parada.

---

## R-006 — Estado persistido: formato, gravação atômica e lock

**Decisão**:
- O estado fica num arquivo JSON único, `${STATE_DIR}/state.json`, com `schema_version: 1`. O schema
  está em [contracts/state-file.schema.json](contracts/state-file.schema.json).
- **Gravação atômica**: escrever em `state.json.tmp` no mesmo diretório, chamar `flush` e
  `os.fsync`, depois `os.replace` para `state.json` e `fsync` do diretório. O estado é gravado
  **depois** de anexar os eventos à fila e **antes** de enviar; também é regravado após cada envio
  confirmado.
- **Migração**: um `schema_version` maior que o suportado faz o processo encerrar com `exit 1`, para
  não sobrescrever o estado de uma versão mais nova. Um valor menor passa por migração explícita
  (inexistente na v1). Um valor ausente ou inválido gera uma linha de base (R-004).
- **Lock de instância única**: `${STATE_DIR}/monitor.lock` com `fcntl.flock(LOCK_EX | LOCK_NB)`,
  mantido aberto durante toda a vida do processo. Se o lock falhar, o log é `instancia_duplicada` e
  o processo sai com `exit 1`. O kernel libera o lock quando o processo morre, então não sobra lock
  "velho". Em Windows (desenvolvimento local) há fallback com `msvcrt.locking`.

**Ajuste em relação ao pedido**: o pedido citou "pendente_envio e data do último lembrete" **por
site e por link**. No modelo, os dois são **globais**:
- `pendente_envio` é **uma fila global ordenada**, porque FR-009 exige preservar a ordem entre
  eventos de itens diferentes (por exemplo, a queda do site A antes do retorno do link B). Filas por
  item não preservam essa ordem.
- `ultimo_lembrete_data` é **global**, porque o lembrete é uma única mensagem diária com todas as
  pendências.

Por item ficam `estado`, `inicio_queda`, `notificado`, `coberto_pelo_site`, `origem` e `ausencias`.
Se for necessário saber "este item tem aviso pendente?", basta consultar a fila pelo `item_id`.

**Alternativas**: SQLite. Rejeitada: o volume de dados é pequeno (dezenas de sites), e o JSON é
legível na hora de diagnosticar e atende ao contrato atômico com `os.replace`. Lock por arquivo PID
com `O_EXCL` também foi rejeitado: deixa lock órfão após `kill -9`.

---

## R-007 — Entrega no Teams (Workflows / Power Automate)

**Decisão**: o fluxo do Teams usa o modelo **"Post to a channel when a webhook request is
received"**, com o gatilho *When a Teams webhook request is received* e a ação *Post card in a chat
or channel*. O monitor faz `POST` com o corpo
`{"type":"message","attachments":[{"contentType":"application/vnd.microsoft.card.adaptive","content":<card>}]}`.
O card é Adaptive Card **1.4**, a versão aceita com segurança pelo cliente Teams nos fluxos. Uma
resposta **2xx** (normalmente `202 Accepted`) conta como entregue, e o evento só sai da fila nesse
caso. A fila é drenada em ordem e **para na primeira falha** (*head-of-line*), o que preserva a
ordem. No máximo 20 envios são feitos por ciclo, com 1 s de espaçamento, para respeitar o
*throttling* do Power Automate. O card é renderizado **no envio**, a partir dos dados do evento, com
o horário original do evento.

- **Distinção visual por tipo**: cada tipo tem título, emoji e `Container.style` próprios: 🔴
  `attention` para SITE OFFLINE, 🟠 `warning` para LINK OFFLINE, 🟢 `good` para retorno, 📋 `accent`
  para lembrete e ⚙️ `emphasis` para avisos do monitor. Não há menções (decisão de Clarifications).
- **Tamanho**: o lembrete com muitas pendências é dividido em partes ("1/2", "2/2") para que cada
  card fique abaixo de ~24 KB, já que o limite do Teams é ~28 KB.
- **Entrega "pelo menos uma vez"**: se o processo morrer entre o 202 e a gravação do estado, o
  evento é reenviado. Assumimos esse risco raro de duplicata porque é melhor do que perder um alerta
  (Princípio V). Cada card leva um `id` de evento no rodapé, para rastreio.

**Alternativas**: o conector "Incoming Webhook" do Office 365 (MessageCard). Rejeitada: foi
descontinuado pela Microsoft em favor de Workflows. Microsoft Graph (`chatMessage`) também foi
rejeitado: exige um app registrado no Entra ID e permissões delegadas, o que é desproporcional para
este caso.

---

## R-008 — Configuração e fail-fast

**Decisão**: o módulo `config.py` lê variáveis de ambiente, valida todas e acumula **todos** os
erros numa única mensagem clara antes do `exit 1`. As variáveis estão em
[contracts/configuracao.md](contracts/configuracao.md). A exibição da configuração na inicialização
mascara os segredos: só os 4 últimos caracteres do token e só o host das URLs. O piso do intervalo
é de 30 s e o teto de 120 s (o teto limita o atraso do aviso, SC-002). A tolerância vai de 60 s a 3600 s
e precisa ser maior ou igual ao intervalo. O fuso vem de `TZ` (padrão `America/Sao_Paulo`) e é
validado com `zoneinfo`.

**Alternativas**: arquivo YAML ou TOML. Rejeitada: a constituição exige variáveis de ambiente.
`pydantic-settings` também foi rejeitado: é uma dependência grande para cerca de 10 variáveis.

---

## R-009 — Logs estruturados e mascaramento

**Decisão**: usar o `logging` da biblioteca padrão com um `JsonFormatter` próprio (uma linha JSON por
evento no stdout, com campos `ts` (UTC), `level`, `event`, `msg` e extras). Um `RedactingFilter`
substitui (1) os valores literais dos segredos carregados e (2) qualquer URL dos hosts
`*.logic.azure.com`, `*.powerplatform.com` e `hc-ping.com` por `<redacted:host>`, inclusive em
`exc_info`. A cada ciclo é emitido `event=ciclo_concluido`, com `duracao_ms`, `sites`, `links`,
`consulta` (`ok`/`falhou`), `transicoes`, `eventos_gerados`, `fila_pendente` e `enviados`.

**Alternativas**: `python-json-logger` ou `structlog`. Rejeitadas: a implementação própria tem
menos de 60 linhas e evita dependências.

---

## R-010 — Healthcheck e heartbeat

**Decisão**:
- **Healthcheck do contêiner**: ao fim de cada ciclo, o monitor grava `${STATE_DIR}/last_cycle` com
  o timestamp UTC. O `HEALTHCHECK` roda `python -m cato_monitor.healthcheck`, que falha quando a
  idade do arquivo passa de `3 × INTERVALO_SEGUNDOS + 30 s`, com `start-period` de 120 s. Um ciclo
  em que a Cato falhou ainda conta como "concluído", porque o laço está vivo. A falha da Cato é
  reportada pelo aviso do monitor (Princípio II).
- **Heartbeat externo** (Healthchecks.io ou compatível): um `GET` em `HEARTBEAT_URL` ao fim de cada
  ciclo concluído. Quando `falhas_consecutivas >= 5`, a chamada vai para `HEARTBEAT_URL + "/fail"`.
  Isso dá um segundo canal de alerta caso a Cato e o Teams estejam fora ao mesmo tempo. A
  configuração sugerida no Healthchecks é período de 1 min e *grace* de 2 min, o que atende ao
  SC-008 (≤ 3 intervalos). Uma falha do heartbeat é só logada, com 1 tentativa e timeout de 10 s.

**Alternativas**: um endpoint HTTP `/health` no contêiner. Rejeitada: obrigaria a ter um servidor
web, o que o usuário pediu para evitar.

---

## R-011 — Empacotamento, contêiner e hospedagem

**Decisão**:
- Usar o layout `src/cato_monitor/` com `pyproject.toml`. O ponto de entrada é
  `python -m cato_monitor`.
- As dependências ficam em `requirements.in` e `requirements-dev.in`, compiladas com `pip-compile
  --generate-hashes` para `requirements.txt` e `requirements-dev.txt`, com versões **exatas** e
  hashes. A instalação usa `--require-hashes`. Dependências de runtime: `requests` e `tzdata`. O
  `tzdata` dá ao `zoneinfo` uma base de fusos independente do sistema operacional da imagem.
  Dependências de desenvolvimento: `pytest` e `responses`.
- O `Dockerfile` é multi-stage. O estágio `builder` usa `python:3.12.x-slim-bookworm`, fixado por
  digest, e cria o venv em `/opt/venv`. O estágio `runtime` é a mesma base: copia o venv e `src`,
  cria o usuário `monitor` (UID 10001), usa `WORKDIR /app`, `VOLUME /data` e define
  `PYTHONDONTWRITEBYTECODE=1` e `PYTHONUNBUFFERED=1`. Também tem `HEALTHCHECK` e `ENTRYPOINT
  ["python","-m","cato_monitor"]`. Não há `ENV` nem `ARG` com segredos.
- O `docker-compose.yml` tem um único serviço sem `deploy.replicas`, com `restart: unless-stopped`,
  `init: true` (para repassar o SIGTERM), `read_only: true`, `tmpfs: /tmp`, `cap_drop: [ALL]`,
  `security_opt: [no-new-privileges:true]`, `env_file: .env`, o volume nomeado `monitor-data:/data`,
  `stop_grace_period: 30s` e log `json-file` com rotação (`max-size: 10m`, `max-file: 5`).
- No SIGTERM ou SIGINT, o monitor termina o ciclo atual (ou interrompe a espera), grava o estado e
  sai com código 0.
- **Hospedagem**: uma VM Linux **fora da rede monitorada**, por exemplo em nuvem, para que a queda do
  link do site onde o monitor roda não o derrube. A VM precisa de NTP ativo, porque toda a lógica
  depende de timestamps.

**Alternativas**: Kubernetes ou Container Apps. Rejeitado por ser desproporcional para uma instância
única. Imagem *distroless* também foi rejeitada: complica o healthcheck em Python e a depuração, sem
ganho relevante.

---

## R-012 — Estratégia de testes

**Decisão**: `pytest` com relógio injetado (a classe `RelogioFake`, com `avancar(segundos)`) e
`responses` para mockar o `requests`. Os testes ficam em três camadas:
- `tests/unit/`: transições, uma por linha da tabela; motor do ciclo (supressão, adiamento,
  retorno do site com link inativo, item ausente ou removido, item novo, linha de base); lembrete
  (com e sem pendências, após reinício, monitor parado às 08:00, virada de dia em Brasília); config
  (`exit 1` por variável); mascaramento de logs; estado atômico (falha simulada entre `.tmp` e
  `replace`, corrompido gera linha de base, `schema_version` futuro gera `exit 1`); lock.
- `tests/integration/`: cliente Cato com as fixtures reais anonimizadas (200 ok, 200 com `errors`,
  timeout, 429 com `Retry-After`, 5xx seguido de sucesso, 401); envio ao Teams (202, falha seguida
  de reenvio em ordem, *head-of-line*); heartbeat (`/fail` após 5 falhas).
- `tests/integration/test_cenarios.py`: ciclos completos do `daemon` com fakes, cobrindo os cenários
  pedidos: oscilação dentro da tolerância, queda e retorno, site offline com links suprimidos,
  reinício durante um episódio (recria o daemon a partir do mesmo `STATE_DIR`), falha da API (5
  falhas, depois o aviso, depois a recuperação) e lembrete diário sem duplicar.

**Alternativas**: `freezegun`. Rejeitada: o relógio injetado é exigido pela constituição e torna o
`freezegun` desnecessário.
