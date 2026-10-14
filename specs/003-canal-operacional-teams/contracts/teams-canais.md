# Contrato: Canais do Teams (delta da feature 003)

Complementa [001 / teams-webhook.md](../../001-cato-socket/contracts/teams-webhook.md). O formato
do POST (mensagem com Adaptive Card), os timeouts e o backoff **não mudam**; só muda o destino.

## Roteamento

| Tipo de aviso | Canal |
|---|---|
| Link/site offline, link/site de volta, pendências do dia | rede |
| Monitor sem acesso à Cato, acesso normalizado, monitor iniciado | operacional |
| Falha/normalização da gravação no banco (feature 002, quando existir) | operacional |
| Canal de rede sem entrega / normalizado | operacional |
| Canal operacional sem entrega / normalizado | rede |

Heartbeat externo: não passa pelo Teams.

## Garantias de entrega

- Uma fila persistida por canal; envio em ordem **dentro** do canal, parando na primeira falha.
- Falha num canal não atrasa nem bloqueia o outro (drenagem independente).
- Ordem **entre** canais não é garantida.
- Evento só deixa a fila após resposta 2xx do webhook do seu canal.

## Novos cards

| Tipo | Título | Fatos |
|---|---|---|
| `CANAL_SEM_ENTREGA` | `⚙️ CANAL DE REDE SEM ENTREGA` ou `⚙️ CANAL OPERACIONAL SEM ENTREGA` | Sem entrega desde (Brasília), Avisos pendentes |
| `CANAL_NORMALIZADO` | `⚙️ CANAL DE REDE NORMALIZADO` ou `⚙️ CANAL OPERACIONAL NORMALIZADO` | Sem entrega desde, Duração da falha |

Estilo `emphasis`. O texto dos demais cards permanece idêntico (FR-012).

## Logs

| Evento | Nível | Campos |
|---|---|---|
| `envio_teams` | INFO/WARNING | `canal`, `id`, `tipo`, `status`, `tentativas` |
| `canal_sem_entrega` | WARNING | `canal`, `desde`, `pendentes` |
| `canal_normalizado` | INFO | `canal`, `duracao_s` |
| `estado_migrado` | INFO | `de_versao`, `rede`, `operacional` |

Nenhum log contém a URL do webhook.
