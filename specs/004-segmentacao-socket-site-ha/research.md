# Research: Aviso único por socket em sites HA

Fase 0 do plano. Cada item registra decisão, racional e alternativas. Não há `NEEDS CLARIFICATION`
em aberto.

## R-001 — Fonte do estado do socket

**Decisão**: `snapshot.py` passa a produzir, para cada site HA, um mapa `sockets` com uma
`ObservacaoSocket` por device. `conectado = device.connected` quando o campo é booleano. Sem o
campo (ou com valor não booleano), `conectado = False` só quando o socket tem ≥ 1 WAN observada e
todas estão offline. Sem WAN observada e sem o campo, `conectado = True` (não há evidência de queda).
Portas LAN, incluindo "HA link", não entram na decisão (FR-001).

**Racional**: `device.connected` já vem na query (`cato_client.QUERY`), então não há mudança na
consulta à Cato. Manter a decisão em `snapshot.py` preserva a regra de que só esse módulo conhece o
schema da Cato; o motor recebe apenas um booleano.

**Alternativas**: decidir no motor a partir dos links (rejeitado: o motor teria de conhecer a regra
de reserva e o campo da Cato); usar `haRole` (rejeitado: na conta real os dois sockets vêm `MASTER`).

## R-002 — Quando um site é HA

**Decisão**: site HA = `info.isHA is True` **ou** mais de um device na resposta. `ObservacaoSite.sockets`
só é preenchido para sites HA; para os demais fica vazio e nenhum código novo roda (FR-006). A mesma
regra passa a valer para o rótulo primário/secundário (`_rotulo_socket`).

**Racional**: hoje o HA é inferido só por `len(devices) > 1`. Se a Cato deixar de listar o device
desconectado, o site pareceria não-HA e o rótulo do socket restante se perderia. `info.isHA` já está
na query e cobre esse caso.

**Alternativas**: só `len(devices) > 1` (frágil, ver acima); só `isHA` (rejeitado: o campo pode vir
ausente em contas antigas).

**Verificação pendente na conta real** (quickstart §3): confirmar que o device desconectado continua
em `devices` com `connected=false`. Se ele sumir, a ausência é tratada como falta de observação
(Princípio II) e o socket é removido do inventário após `LIMITE_AUSENCIAS` ciclos, sem aviso; nesse
caso a feature precisa de ajuste antes de ir para produção.

## R-003 — Vínculo link → socket

**Decisão**: o socket de um link é o prefixo do id do link (`"<chave_socket>/<iid>"`, já gerado por
`_links_do_device`). Uma função pura `socket_do_link(link_id)` faz a extração. A chave do socket é
`socketInfo.id` (ou `device.id`), a mesma usada no prefixo.

**Racional**: o vínculo já existe nos ids persistidos; não exige campo novo em `Link` nem migração.

**Alternativas**: novo campo `socket_id` em `Link`/`ObservacaoLink` (rejeitado: duplica informação
já presente no id e exigiria tratar estados antigos sem o campo).

## R-004 — Máquina de estados do socket

**Decisão**: o socket é um terceiro tipo de item, com os mesmos estados (`ONLINE`,
`PENDENTE_OFFLINE`, `OFFLINE_NOTIFICADO`) e a mesma função `proximo_estado` (mesma tolerância e
regras de confirmação). A observação do socket só vale quando o site está `ONLINE` ou em
`PENDENTE_OFFLINE`. Quando o site está `PENDENTE_OFFLINE`, a QUEDA do socket é **adiada** (mesma
regra que já existe para links), evitando "SOCKET OFFLINE" seguido de "SITE OFFLINE" (US3).

**Racional**: reaproveita a tabela de transição testada e garante o anti-fadiga (Princípio IV) e a
proteção contra *flapping* sem regra nova.

**Alternativas**: estado booleano "socket offline" sem tolerância (rejeitado: avisaria oscilações
curtas e violaria o Princípio IV).

## R-005 — Interação socket × site (FR-005, FR-005a)

**Decisão**: o socket ganha o mesmo marcador `coberto_pelo_site` dos links.

- **QUEDA do site**: todo socket passa a `OFFLINE_NOTIFICADO` com `coberto_pelo_site = True` e
  `inicio_queda` preservado (ou o do site). Nenhum aviso de socket é emitido.
- **Site offline**: sockets não são avaliados.
- **Site online** (inclusive no ciclo do RETORNO do site): cada socket coberto e observado é
  resolvido. Conectado → volta a `ONLINE` sem aviso. Desconectado → `coberto_pelo_site = False`,
  permanece `OFFLINE_NOTIFICADO` e emite **um** `SOCKET_OFFLINE`, depois do `SITE_RETORNO` do mesmo
  ciclo. Sem observação → continua coberto até ser observado.

**Racional**: implementa FR-005a ("SITE DE VOLTA" e depois "SOCKET OFFLINE") e US3.2 (socket já
avisado é absorvido pelo site) com o mesmo padrão já usado para links. Um socket que caiu antes do
site e continua fora recebe novo "SOCKET OFFLINE", porque o "SITE DE VOLTA" encerra o episódio
anterior para o operador.

**Alternativas**: zerar o socket na queda do site (rejeitado: perde o `inicio_queda` original);
manter o socket notificado sem novo aviso após o retorno do site (rejeitado: contraria FR-005a).

## R-006 — Links de um socket offline (FR-003, FR-003a)

**Decisão**:

- **QUEDA do socket**: links do socket em `PENDENTE_OFFLINE` voltam a `ONLINE` (a queda pendente é
  absorvida pelo socket). Links `OFFLINE_NOTIFICADO` ficam como estão (queda aberta, silenciada).
- **Socket `OFFLINE_NOTIFICADO` ou coberto**: os links dele não são avaliados (sem transição e sem
  aviso). Enquanto o socket estiver `PENDENTE_OFFLINE`, a QUEDA dos links dele é adiada.
- **RETORNO do socket**: links do socket em `OFFLINE_NOTIFICADO` que estão online agora voltam a
  `ONLINE` **sem aviso**. Os que seguem offline continuam abertos; o retorno posterior gera
  `LINK_RETORNO`. Links `ONLINE` que estão offline seguem a regra atual (`PENDENTE_OFFLINE` →
  tolerância → `LINK_OFFLINE`).
- **SITE_RETORNO**: `links_ainda_offline` não lista links de sockets que continuam desconectados (o
  `SOCKET_OFFLINE` seguinte cobre esses links).

**Racional**: no retorno do socket, todo link notificado dele foi avisado antes da queda do socket
(FR-003a) ou junto com a queda do site. Nos dois casos o fechamento silencioso é o pedido na spec
(US2.2), então a regra não precisa de marcador novo por link.

**Alternativas**: marcador `coberto_pelo_socket` por link (rejeitado: não muda o resultado e aumenta
o estado); atualizar silenciosamente os links durante a queda do socket, como em
`_links_sob_site_offline` (rejeitado: um device desconectado não informa `interfacesLinkState`, então
essa atualização teria pouca informação e mais casos de borda).

## R-007 — Persistência (FR-008)

**Decisão**: `Site` ganha o campo `sockets` (mapa chave → `Socket`). O campo é **aditivo**: é sempre
gravado; na leitura, ausente equivale a `{}`. `schema_version` continua `2`, sem migração.

**Racional**: estados v2 atuais carregam sem alteração, e `Site.de_dict` da versão anterior ignora a
chave nova. A gravação continua atômica (Princípio I). Socket persistido evita aviso duplicado e
perda do aviso de retorno após reinício.

**Alternativas**: subir para `schema_version: 3` com migração (rejeitado: a migração seria só
"acrescentar `sockets: {}`", com custo de código e de testes sem ganho de segurança).

**Efeito colateral aceito**: voltar para a versão anterior do robô com eventos `SOCKET_*` ainda na
fila faz o estado ser tratado como inválido (tipo desconhecido) e gera nova linha de base com um
único aviso. A volta de versão já não é suportada desde a feature 003.

## R-008 — Linha de base e lembrete (FR-007a)

**Decisão**: na linha de base (estado novo ou corrompido e site novo), um socket desconectado de um
site online entra como `OFFLINE_NOTIFICADO` (`origem = linha_base`). Em `MONITOR_INICIADO` e em
`LEMBRETE_DIARIO`, cada socket notificado e não coberto gera **uma** linha `tipo = "SOCKET"`, e os
links desse socket são omitidos. Com o site offline, sockets cobertos não aparecem (a linha "Site
inteiro" cobre).

**Racional**: mantém a regra de "uma pendência por causa real" também no resumo de início, que usa
a mesma estrutura de itens do lembrete.

## R-009 — Canal e histórico (FR-007)

**Decisão**: `SOCKET_OFFLINE` e `SOCKET_RETORNO` vão para o canal **rede** (`MAPA_CANAL`), na mesma
fila dos `LINK_*`/`SITE_*`, o que preserva a ordem queda → retorno. Os dados do evento seguem o mesmo
formato dos eventos de link (`site_id`, `inicio_queda`, `retorno_em`), com `socket_id` como alvo.

**Histórico**: a feature 002 (SQL Server) ainda não está implementada. Quando for, o mapeamento dela
deve tratar `SOCKET_OFFLINE`/`SOCKET_RETORNO` como abertura e fechamento de queda com alvo do tipo
socket. Fica registrado como dependência no plano da 002; esta feature não acessa banco
(Princípio VIII).
