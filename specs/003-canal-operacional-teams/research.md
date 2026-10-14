# Research: Canal Operacional Separado no Teams

Todas as decisões abaixo resolvem os pontos abertos do plano. Não restam `NEEDS CLARIFICATION`.

## R-001 — Estrutura das filas

- **Decisão**: `EstadoMonitor.filas: dict[str, list[EventoNotificacao]]` com chaves `"rede"` e
  `"operacional"`, no lugar de `pendente_envio`. O canal é uma `Enum` (`Canal`) em `canais.py`.
- **Racional**: a fila por canal permite *head-of-line* independente (FR-006) e mantém o formato de
  evento, tentativas e último erro já existente.
- **Alternativas**: (a) manter uma fila única com campo `canal` e pular itens do canal bloqueado.
  Rejeitada: quebra a regra de "para na primeira falha" e complica a ordem. (b) dois arquivos de
  estado. Rejeitada: perde atomicidade entre filas e estado dos itens.

## R-002 — Drenagem independente dos canais

- **Decisão**: `teams.drenar_todos` dispara uma thread por canal (`threading.Thread`), cada uma
  executando o laço atual de `drenar` sobre a sua fila, e aguarda as duas. As threads só mutam a
  própria fila; a chamada `salvar()` é protegida por um `threading.Lock` compartilhado. Exceção em
  uma thread é capturada e logada, sem afetar a outra nem o laço.
- **Racional**: o pior caso de um envio que falha hoje é ~32 s (2 tentativas × timeout 15 s +
  backoff). Sequencial, isso atrasaria o canal saudável a cada ciclo (viola SC-002 e o cenário 2
  da US2). Threads resolvem sem dependência nova e com concorrência mínima (2).
- **Alternativas**: envio sequencial com o canal "rede" primeiro (o operacional ainda atrasaria
  quando a rede cai; rejeitado). `asyncio`/`aiohttp` (dependência nova e reescrita; rejeitado).
  Processo separado por canal (viola instância única; rejeitado).

## R-003 — Aviso de "sem entrega"

- **Decisão**: por canal, `SituacaoEntrega(falha_desde, aviso_emitido)`. `avaliar_entrega(estado,
  agora, limite=900 s, pendentes)`:
  - tentativa falhou e `falha_desde is None` → `falha_desde = agora`;
  - entrega bem-sucedida → se `aviso_emitido`, gera `CANAL_NORMALIZADO` no outro canal; zera
    `falha_desde` e `aviso_emitido`;
  - `falha_desde` definido, `agora - falha_desde ≥ 15 min` e não `aviso_emitido` → gera
    `CANAL_SEM_ENTREGA` no outro canal e marca `aviso_emitido`.
  O limite de 15 min é constante (spec), não configurável.
- **Racional**: reproduz o padrão do `MONITOR_FALHA`/`MONITOR_RECUPERADO` (1 aviso por sequência,
  com normalização). Persistir os dois campos cobre reinício durante a falha (Edge Case).
- **Detalhes**: `falha_desde` guarda o instante da **primeira falha** da sequência, e o card informa
  esse horário e o número de pendentes no momento da emissão. Fila vazia sem tentativa não altera a
  situação. Os avisos entram no fim da fila do outro canal, como qualquer evento.
- **Alternativas**: contar ciclos em vez de timestamp (rejeitado pelo Princípio III: durações por
  timestamp). Emitir no primeiro erro (rejeitado: ruído; a spec fixa 15 min).

## R-004 — Migração do estado v1 → v2

- **Decisão**: em `estado_store.carregar`, `schema_version == 1` não é mais "inválido": o JSON é
  convertido em memória (`pendente_envio` → `filas` pelo `canal_do_evento`, mantendo a ordem
  relativa; `entrega` zerado) e regravado imediatamente como v2. Antes da regravação, o arquivo v1
  é copiado para `state.json.v1-<UTC>`. `schema_version == 2` carrega direto; `> 2` sai com
  `exit 1`; qualquer outro valor segue a regra de estado inválido.
- **Racional**: idempotência vem do próprio `schema_version` (FR-010, "uma única vez"). A cópia
  protege contra defeito de migração, pois a fila é o único lugar que guarda avisos ainda não
  entregues.
- **Alternativas**: migrar só em memória sem regravar (risco de reprocessar; rejeitado). Descartar
  a fila antiga (perda de avisos; viola SC-003).

## R-005 — Configuração do novo webhook

- **Decisão**: variável `TEAMS_WEBHOOK_OPERACIONAL_URL`, obrigatória, `https://`, segredo, exibida
  só pelo host. `TEAMS_WEBHOOK_URL` mantém o nome e passa a ser o canal de rede (spec, Assumptions).
  Valores iguais são aceitos (spec, Edge Cases).
- **Racional**: o nome explicita o destino sem renomear a variável atual, e a obrigatoriedade
  segue a regra de falha rápida (FR-009a, Princípio VI).
- **Alternativas**: renomear a atual para `TEAMS_WEBHOOK_REDE_URL` (quebra instalações; rejeitado).
  Operacional opcional com fallback para o de rede (o operador esqueceria de configurar e voltaria o
  ruído; a clarificação da spec exige recusar iniciar).

## R-006 — Mapeamento tipo → canal

- **Decisão**: tabela explícita `dict[TipoEvento, Canal]` em `canais.py`, sem valor padrão. Um teste
  garante que **todo** `TipoEvento` está mapeado (FR-004). Mapa:

  | Tipo | Canal |
  |---|---|
  | `LINK_OFFLINE`, `SITE_OFFLINE`, `LINK_RETORNO`, `SITE_RETORNO`, `LEMBRETE_DIARIO` | rede |
  | `MONITOR_FALHA`, `MONITOR_RECUPERADO`, `MONITOR_INICIADO` | operacional |
  | `CANAL_SEM_ENTREGA`, `CANAL_NORMALIZADO` | o **outro** canal (`dados["canal_afetado"]`) |

  Os tipos de falha de gravação em banco da feature 002 entram como `operacional` quando essa
  feature criar o `TipoEvento` (a tabela e o teste de cobertura falham sem isso, de propósito).
- **Racional**: roteamento por tipo e não por chamador evita que um novo aviso caia num canal
  implícito.
- **Alternativas**: campo `canal` gravado no evento (redundante; a migração teria que inventá-lo).

## R-007 — Formato dos novos cards

- **Decisão**: dois tipos novos em `cards.py`, no mesmo envelope dos demais (título + fatos):
  `⚙️ CANAL DE REDE SEM ENTREGA` / `⚙️ CANAL OPERACIONAL SEM ENTREGA` e as respectivas
  normalizações (`… NORMALIZADO`). Fatos: "Sem entrega desde" (Brasília), "Avisos pendentes" e, na
  normalização, "Duração da falha". Estilo `emphasis`, como os avisos do monitor.
- **Racional**: reaproveita a aparência dos avisos operacionais; sem novo componente. Os textos
  existentes não mudam (FR-012).

## R-008 — Logs e observabilidade

- **Decisão**: `envio_teams` ganha `canal` (`rede` | `operacional`). `ciclo_concluido` troca
  `fila_pendente` por `fila_rede` e `fila_operacional` e mantém `enviados` como a soma. Eventos
  novos: `canal_sem_entrega` (WARNING), `canal_normalizado` (INFO) e `estado_migrado` (INFO, com
  quantos avisos foram para cada fila). A URL nunca é logada (FR-011).
- **Racional**: permite diagnosticar qual webhook falha sem expor o segredo.
