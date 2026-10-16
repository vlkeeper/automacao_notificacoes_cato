# Data Model: Aviso único por socket em sites HA

Delta sobre [001 / data-model](../001-cato-socket/data-model.md) e
[003 / data-model](../003-canal-operacional-teams/data-model.md). Só o que muda está aqui.

## 1. Observação (transitória)

### `ObservacaoSocket` (nova, `modelos.py`)

| Campo | Tipo | Regra |
|---|---|---|
| `nome` | str | Rótulo para exibição: `"primário"`/`"secundário"` (R-002); sem rótulo, `serial`; sem serial, a chave. |
| `conectado` | bool | `device.connected`; sem o campo, `False` só se ≥ 1 WAN observada e todas offline (R-001). |

### `ObservacaoSite` (alterada)

| Campo | Mudança |
|---|---|
| `sockets: dict[str, ObservacaoSocket]` | **novo**, chave = `socketInfo.id` ou `device.id`. Vazio em sites não-HA. |

Link → socket: `socket_do_link(link_id) = link_id.split("/", 1)[0]` (R-003).

## 2. Persistido (`state.json`, `schema_version: 2`)

### `Socket` (nova entidade, dentro de `Site.sockets`)

Mesmos campos-base de site/link:

| Campo | Tipo | Observação |
|---|---|---|
| `nome` | str | Rótulo atual (atualizado a cada observação). |
| `estado` | `EstadoItem` | `ONLINE` / `PENDENTE_OFFLINE` / `OFFLINE_NOTIFICADO`. |
| `inicio_queda` | ts \| null | UTC ISO 8601. |
| `notificado` | bool | |
| `coberto_pelo_site` | bool | Queda absorvida pelo `SITE_OFFLINE` (R-005). |
| `origem` | `observado` \| `linha_base` | |
| `ausencias` | int | Inventário: removido após `LIMITE_AUSENCIAS` ciclos ausente com o site conectado, sem aviso. |

**Invariantes**: as mesmas de `Link` em `verificar_invariantes` (ONLINE sem `inicio_queda`, sem
`notificado` e sem `coberto_pelo_site`; fora de ONLINE com `inicio_queda`; OFFLINE_NOTIFICADO com
`notificado`). Sites não-HA têm `sockets == {}`.

### `Site` (alterada)

| Campo | Mudança |
|---|---|
| `sockets: dict[str, Socket]` | **novo**; sempre gravado; ausente na leitura = `{}` (R-007). |

## 3. Transições do socket

Usa `proximo_estado` (tolerância igual à de site e link). `obs_offline = not ObservacaoSocket.conectado`.

| Situação do site no ciclo | Socket | Efeito |
|---|---|---|
| Site QUEDA (confirmada agora) | qualquer | `OFFLINE_NOTIFICADO`, `notificado`, `coberto_pelo_site = True`, `inicio_queda` mantido ou o do site. Sem aviso. |
| Site `OFFLINE_NOTIFICADO` | qualquer | Não avaliado. |
| Site online, socket coberto, observado conectado | coberto | → `ONLINE` sem aviso. |
| Site online, socket coberto, observado desconectado | coberto | `coberto_pelo_site = False`; emite `SOCKET_OFFLINE` (após `SITE_RETORNO` do ciclo, se houver). |
| Site online/pendente, socket não coberto | — | `proximo_estado`. QUEDA → `SOCKET_OFFLINE`; RETORNO → `SOCKET_RETORNO`. |
| Site `PENDENTE_OFFLINE` | QUEDA calculada | Adiada (estado não aplicado); reavaliada no ciclo seguinte. |
| Socket sem observação | — | Inalterado (Princípio II). |

### Efeitos sobre os links do socket (R-006)

| Gatilho | Links do socket |
|---|---|
| QUEDA do socket | `PENDENTE_OFFLINE` → `ONLINE`; `OFFLINE_NOTIFICADO` inalterado. |
| Socket `PENDENTE_OFFLINE` | QUEDA de link adiada. |
| Socket `OFFLINE_NOTIFICADO` (coberto ou não) | Não avaliados. |
| RETORNO do socket | `OFFLINE_NOTIFICADO` + online agora → `ONLINE` sem aviso; demais seguem a regra atual no mesmo ciclo. |
| `SITE_RETORNO` com socket ainda desconectado | Links desse socket ficam fora de `links_ainda_offline`. |

### Ordem dentro de `_avaliar_site`

1. Inventário de links e de sockets.
2. Site (`proximo_estado`, QUEDA/RETORNO como hoje, com os ajustes acima).
3. Se o site está `OFFLINE_NOTIFICADO`: termina (como hoje).
4. Sockets, em ordem de chave.
5. Links, em ordem de id, pulando os tratados e os de sockets offline/cobertos.

## 4. Eventos novos

Canal: **rede** (R-009). Formato de `EventoNotificacao` inalterado.

### `SOCKET_OFFLINE`

| Campo de `dados` | Tipo |
|---|---|
| `site_id`, `site_nome` | str |
| `socket_id` | str (chave do socket) |
| `socket` | str (rótulo: primário/secundário) |
| `inicio_queda` | ts |

### `SOCKET_RETORNO`

| Campo de `dados` | Tipo |
|---|---|
| `site_id`, `site_nome`, `socket_id`, `socket` | str |
| `inicio_queda`, `retorno_em` | ts |

### Itens de pendência (`LEMBRETE_DIARIO`, `MONITOR_INICIADO`)

Nova forma de item: `{"site_nome", "link_nome": null, "tipo": "SOCKET", "socket": <rótulo>,
"inicio_queda"}` (`inicio_queda` só no lembrete). Links de sockets notificados e não cobertos são
omitidos.

## 5. Log (Detalhes)

`det.transicoes` ganha `item: "socket"` com `socket_id` no lugar de `link_id`. `det.registros`
ganha `item_novo`/`item_removido` com `socket_id`.
