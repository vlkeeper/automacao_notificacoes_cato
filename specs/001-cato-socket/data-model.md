# Data Model: Monitoramento de Sockets Cato com Avisos no Teams

**Plan**: [plan.md](plan.md) | **Research**: [research.md](research.md) | **Schema persistido**:
[contracts/state-file.schema.json](contracts/state-file.schema.json)

Este documento tem três partes: (1) as entidades **persistidas**, que formam o estado; (2) as
entidades **transitórias** de um ciclo, que são a observação e o resultado da consulta; e (3) as
regras de transição.

Convenções:
- Todo timestamp é `datetime` *aware* em UTC e é persistido em ISO 8601 com `+00:00` (Princípio III).
- A única data local é `ultimo_lembrete_data` (`YYYY-MM-DD` no fuso `TZ`), usada só para o lembrete.
- Os nomes de sites e links são guardados **exatamente** como vêm da Cato (US4).

---

## 1. Entidades persistidas (`state.json`)

### EstadoMonitor (raiz)

| Campo | Tipo | Regra |
|---|---|---|
| `schema_version` | int | `1`. Se for maior que o suportado, `exit 1`. Se estiver ausente ou inválido, nova linha de base |
| `atualizado_em` | ts UTC | momento da última gravação |
| `monitor` | SituacaoMonitor | — |
| `sites` | map `site_id → Site` | `site_id` é o id interno da Cato (string) |
| `pendente_envio` | list[EventoNotificacao] | fila **global ordenada** (FIFO) |

### SituacaoMonitor

| Campo | Tipo | Regra |
|---|---|---|
| `falhas_consecutivas` | int ≥ 0 | +1 a cada `ConsultaFalhou`; volta a 0 no primeiro sucesso |
| `alerta_falha_enviado` | bool | vira `true` ao gerar `MONITOR_FALHA` (quando o contador chega a 5); volta a `false` ao gerar `MONITOR_RECUPERADO` |
| `ultimo_ciclo_concluido_em` | ts UTC \| null | atualizado ao fim de todo ciclo (também gravado em `last_cycle`) |
| `ultima_consulta_ok_em` | ts UTC \| null | último `ConsultaOk` |
| `ultimo_lembrete_data` | `YYYY-MM-DD` \| null | data local (`TZ`) do último lembrete **avaliado** |
| `proximo_seq` | int ≥ 1 | gerador de `EventoNotificacao.id` |

### Site

| Campo | Tipo | Regra |
|---|---|---|
| `nome` | str | nome do portal, atualizado a cada observação válida |
| `estado` | `ONLINE` \| `PENDENTE_OFFLINE` \| `OFFLINE_NOTIFICADO` | — |
| `inicio_queda` | ts UTC \| null | preenchido somente fora de `ONLINE`; é preservado entre reinícios |
| `notificado` | bool | `true` só em `OFFLINE_NOTIFICADO` |
| `origem` | `observado` \| `linha_base` | `linha_base` quando o item já estava offline ao entrar no monitoramento |
| `ausencias` | int ≥ 0 | ciclos válidos consecutivos sem o item na resposta; com 3, o item é removido |
| `links` | map `link_id → Link` | `link_id = "<socket_id>/<interface_id>"` |

### Link

| Campo | Tipo | Regra |
|---|---|---|
| `nome` | str | nome da porta como no portal |
| `tipo` | `WAN` \| `LAN` | papel configurado da porta (R-001) |
| `socket` | str | serial ou papel (`primário`/`secundário`), mostrado só em sites HA |
| `estado` | igual ao de Site | — |
| `inicio_queda` | ts UTC \| null | idem |
| `notificado` | bool | `true` quando a queda foi comunicada por aviso de link **ou** pelo aviso do site |
| `coberto_pelo_site` | bool | `true` quando a queda está coberta pelo aviso `SITE_OFFLINE` |
| `origem` | `observado` \| `linha_base` | idem |
| `ausencias` | int ≥ 0 | idem; só conta enquanto o site está conectado |

**Invariantes** (verificadas por teste e na leitura do estado):
- `estado == ONLINE` ⇒ `inicio_queda == null`, `notificado == false` e `coberto_pelo_site == false`.
- `estado == OFFLINE_NOTIFICADO` ⇒ `notificado == true`.
- `coberto_pelo_site == true` ⇒ o site está `OFFLINE_NOTIFICADO`, ou estava nesse estado no ciclo em
  que o link foi coberto. Quando o site volta, a flag é zerada.

### EventoNotificacao

| Campo | Tipo | Regra |
|---|---|---|
| `id` | str | `evt-<seq 6 dígitos>`, único e monotônico |
| `tipo` | enum (abaixo) | — |
| `ocorrido_em` | ts UTC | momento da **transição**. É o horário mostrado no aviso (com "desde" e "há quanto tempo") |
| `criado_em` | ts UTC | momento da enfileiração |
| `tentativas` | int ≥ 0 | incrementado a cada envio falho |
| `ultimo_erro` | str \| null | motivo sanitizado (status HTTP ou tipo de erro), **nunca** a URL |
| `dados` | objeto | dados para renderizar o card (abaixo). O card é renderizado no envio |

`tipo` e `dados` correspondentes:

| tipo | dados |
|---|---|
| `LINK_OFFLINE` | `site_id`, `site_nome`, `link_id`, `link_nome`, `link_tipo`, `inicio_queda`, `outros_links_online` (int) |
| `SITE_OFFLINE` | `site_id`, `site_nome`, `inicio_queda`, `motivo` (`desconectado_cato` \| `todos_links_inativos`), `links_afetados` [nome, tipo] |
| `LINK_RETORNO` | `site_id`, `site_nome`, `link_id`, `link_nome`, `link_tipo`, `inicio_queda`, `retorno_em` |
| `SITE_RETORNO` | `site_id`, `site_nome`, `inicio_queda`, `retorno_em`, `links_ainda_offline` [nome, tipo, inicio_queda] |
| `LEMBRETE_DIARIO` | `data_local`, `pendencias` [site_nome, link_nome \| null, tipo, inicio_queda], `parte`, `total_partes` |
| `MONITOR_FALHA` | `falhas_consecutivas`, `desde` (início da sequência), `ultimo_motivo` |
| `MONITOR_RECUPERADO` | `desde`, `recuperado_em`, `falhas_total` |
| `MONITOR_INICIADO` | `sites_total`, `links_total`, `itens_offline` [site_nome, link_nome \| null, tipo] |

Ciclo de vida: o evento é criado, entra na fila e é persistido. Depois é enviado. Com 2xx, sai da
fila e o estado é persistido. Em qualquer falha, `tentativas` é incrementado, o evento continua na
fila e a drenagem para (*head-of-line*). Não há descarte.

---

## 2. Entidades transitórias (por ciclo)

### ResultadoConsulta

```text
ConsultaOk(snapshot: Snapshot, recebido_em: ts)
ConsultaFalhou(motivo: "timeout" | "conexao" | "http_<status>" | "graphql_errors" | "json_invalido" | "schema_invalido")
```

### Snapshot (já validado e normalizado por `snapshot.py`)

```text
Snapshot.sites: map site_id -> ObservacaoSite
ObservacaoSite: nome, conectado: bool, links: map link_id -> ObservacaoLink
ObservacaoLink: nome, tipo (WAN|LAN), socket, online: bool
```

Regras de validação, cuja violação leva a `ConsultaFalhou("schema_invalido")` para a resposta
inteira:
- `data.accountSnapshot.sites` precisa existir e ser uma lista. Uma lista **vazia**, quando o estado
  tem sites, é considerada inválida: uma conta não perde todos os sites de uma vez.
- Cada site precisa ter `id` e `connectivityStatus` reconhecido.

Uma violação **local**, como um site sem `devices` estando conectado ou uma interface sem id, só
torna inválida a observação **daquele item**. O item é omitido do Snapshot e o estado dele fica
inalterado (Princípio II).

**Site observado offline** ⇔ `conectado == false` **ou** (o site tem ≥ 1 link monitorado **e**
todos os links estão `online == false`) (Clarifications / FR-004).

---

## 3. Transições

### 3.1 Por item: `proximo_estado(item, obs_offline: bool | None, agora, tolerancia)`

`obs_offline=None` significa consulta falha ou item ausente. Nesse caso nada muda. A tabela é a da
spec:

| Estado | Observação | Novo estado | Ação emitida |
|---|---|---|---|
| ONLINE | online | ONLINE | — |
| ONLINE | offline | PENDENTE_OFFLINE, `inicio_queda=agora` | — |
| PENDENTE_OFFLINE | offline, `agora - inicio_queda < tol` | PENDENTE_OFFLINE | — |
| PENDENTE_OFFLINE | offline, `≥ tol` | OFFLINE_NOTIFICADO | `QUEDA` |
| PENDENTE_OFFLINE | online | ONLINE (limpa campos) | — |
| OFFLINE_NOTIFICADO | offline | OFFLINE_NOTIFICADO | — |
| OFFLINE_NOTIFICADO | online | ONLINE (limpa campos) | `RETORNO(duração = agora - inicio_queda)` |
| qualquer | `None` | inalterado | — |

### 3.2 Composição no ciclo: `avaliar_ciclo(estado, resultado, agora, cfg)`

Ordem determinística:

1. **`ConsultaFalhou`**: `falhas_consecutivas += 1`. Se o contador chegar a 5 e
   `alerta_falha_enviado == false`, o ciclo emite `MONITOR_FALHA`. Nenhum item muda. Fim.
2. **`ConsultaOk`**: se `alerta_falha_enviado`, emite `MONITOR_RECUPERADO`. Depois zera o contador e
   a flag.
3. **Linha de base**: se o estado não tem sites (é novo ou corrompido), registra tudo (R-004),
   emite `MONITOR_INICIADO` e segue para o passo 7.
4. **Inventário**: itens novos entram como linha de base individual, sem aviso. Itens ausentes
   recebem `ausencias += 1`; com 3, são removidos (log). Itens presentes voltam `ausencias = 0`.
5. **Sites, em ordem de `site_id`**: o site passa por `proximo_estado`.
   - `QUEDA` do site gera `SITE_OFFLINE`. Todos os links que não estão `ONLINE`, ou que estão
     offline nesta observação, passam a `OFFLINE_NOTIFICADO`, com `coberto_pelo_site=true` e
     `notificado=true`. O `inicio_queda` é mantido quando já existe; senão recebe o do site.
   - `RETORNO` do site gera `SITE_RETORNO`. Os links cobertos que estão online voltam a `ONLINE` em
     silêncio. Os que estão offline ficam `OFFLINE_NOTIFICADO` (com `coberto_pelo_site=false`) e
     entram em `links_ainda_offline`.
6. **Links do site**, só se o site **não** está `OFFLINE_NOTIFICADO`: cada link passa por
   `proximo_estado`.
   - Se o site está `PENDENTE_OFFLINE`, uma ação `QUEDA` de link é **adiada**: o link fica
     `PENDENTE_OFFLINE` e é reavaliado no próximo ciclo (R-003).
   - Senão, `QUEDA` gera `LINK_OFFLINE` e `RETORNO` gera `LINK_RETORNO`.
   - Quando o site está `OFFLINE_NOTIFICADO`, os links só têm o estado atualizado (cobertos), sem
     ações.
7. **Lembrete** (R-005).
8. Os eventos recebem `id` em ordem e são anexados ao **fim** da fila.

Diagrama de estados (por item):

```text
            offline                      offline ≥ tolerância
  ONLINE ───────────► PENDENTE_OFFLINE ─────────────────────► OFFLINE_NOTIFICADO
    ▲                     │ online (silêncio)                       │ online
    └─────────────────────┘◄────────────── RETORNO (aviso) ─────────┘
```
