# Contrato: avisos de socket no Teams (delta das features 001 e 003)

Base: [001 / teams-webhook](../../001-cato-socket/contracts/teams-webhook.md),
[003 / teams-canais](../../003-canal-operacional-teams/contracts/teams-canais.md).
Os textos dos avisos existentes não mudam, exceto onde indicado em "Ajustes".

## Roteamento

| Tipo | Canal |
|---|---|
| `SOCKET_OFFLINE` | rede |
| `SOCKET_RETORNO` | rede |

## Cards novos (Adaptive Card 1.4, mesmo envelope)

### 🟠 SOCKET OFFLINE (style `warning`)

- FactSet: **Site**, **Socket** (`primário` / `secundário`), **Desde** (`dd/mm/aaaa HH:MM`, Brasília).
- Texto: "O socket **{socket}** do site **{site}** está desconectado. O site continua funcionando
  pelo outro socket, sem redundância."

### 🟢 SOCKET DE VOLTA (style `good`)

- FactSet: **Site**, **Socket**, **Desde**, **Duração** (`X d Y h Z min`).
- Texto: "O socket {socket} voltou após {duração}. A redundância do site foi restabelecida."

Snapshots de referência: `tests/unit/snapshots/SOCKET_OFFLINE.json` e `SOCKET_RETORNO.json`.

## Ajustes em cards existentes

| Card | Mudança |
|---|---|
| PENDÊNCIAS DO DIA | Item `tipo = "SOCKET"`: coluna Porta mostra "Socket {rótulo} (inteiro)". Portas desse socket não aparecem. |
| MONITOR INICIADO | Item `tipo = "SOCKET"`: "Socket {rótulo} (inteiro)" na lista do site. |
| SITE DE VOLTA | "Ainda fora" não lista portas de socket que continua desconectado (o SOCKET OFFLINE seguinte as cobre). |

## Sequências garantidas (mesma fila, em ordem)

| Cenário | Avisos |
|---|---|
| Um socket cai, outro conectado | `SOCKET OFFLINE` |
| Socket volta | `SOCKET DE VOLTA` |
| Ambos caem | `SITE OFFLINE` (sem SOCKET OFFLINE, mesmo que um já tenha sido avisado) |
| Site volta com um socket | `SITE DE VOLTA`, depois `SOCKET OFFLINE` |
| Site volta com os dois | `SITE DE VOLTA` |
| Porta do socket offline cai/volta | nada |
| Site sem HA | inalterado |
