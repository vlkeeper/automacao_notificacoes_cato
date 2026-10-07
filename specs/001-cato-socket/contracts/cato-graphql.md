# Contrato: Cato GraphQL API (consumido, somente leitura)

> **Status**: *candidato*. É preciso validar com o Cato CLI contra o schema da conta antes de
> implementar o parser (ver [research.md R-001](../research.md)). Depois da validação, atualize os
> campos marcados com ⚠ e remova este aviso.

## Requisição

```http
POST https://api.catonetworks.com/api/v1/graphql2
Content-Type: application/json
Accept: application/json
x-api-key: <CATO_API_KEY>        # token somente leitura; nunca logado
```

Timeout `(5 s connect, 20 s read)`. Retentativa só em timeout, erro de conexão, 429 e 5xx (ver R-002).

```graphql
query MonitorSnapshot($accountID: ID!) {
  accountSnapshot(accountID: $accountID) {
    id
    timestamp
    sites {
      id
      connectivityStatus          # connected | disconnected
      operationalStatus           # informativo (active, disabled, ...)
      lastConnected
      info {
        name                      # nome exibido no portal
        isHA
        # ⚠ confirmar: campo com o papel/nome configurado de cada porta (LAN/WAN)
        #   ex.: interfaces { id name destType wanRole }
      }
      devices {
        id
        haRole
        connected
        socketInfo { id serial isPrimary }
        interfaces {              # túneis WAN para a Cato
          id                      # ⚠ formato (WAN1, INT_5...)
          name
          connected
          tunnelUptime
        }
        interfacesLinkState {     # estado físico de todas as portas
          id
          up
        }
      }
    }
  }
}
```

Variáveis: `{"accountID": "<CATO_ACCOUNT_ID>"}`.

## Resposta: classificação pelo cliente

| Condição | Resultado |
|---|---|
| HTTP 200, sem `errors`, `data.accountSnapshot.sites` é uma lista válida | `ConsultaOk` |
| HTTP 200 com `errors` não vazio (mesmo que `data` venha parcial) | `ConsultaFalhou("graphql_errors")` |
| Corpo não é JSON | `ConsultaFalhou("json_invalido")` |
| Estrutura fora do esperado (ver data-model §2) | `ConsultaFalhou("schema_invalido")` |
| 429 / 5xx, depois de esgotar as retentativas | `ConsultaFalhou("http_<status>")` |
| 401 / 403 / outros 4xx (sem retentativa) | `ConsultaFalhou("http_<status>")` e log `ERROR` "verifique CATO_API_KEY/permissões" |
| Timeout / erro de conexão | `ConsultaFalhou("timeout" \| "conexao")` |

## Normalização (`snapshot.py`)

- `site.nome = info.name`, e `site.conectado = connectivityStatus == "connected"`.
- `link_id = f"{socketInfo.id or device.id}/{interface_id}"`.
- Portas monitoradas são só as que têm papel configurado **WAN** ou **LAN** (⚠ campo de papel).
- WAN: `online = interfaces[id].connected is True`. Se a validação mostrar que a WAN caída **some**
  de `interfaces`, a regra passa a ser "presente no inventário com papel WAN e ausente/desconectada
  em `interfaces`" ⇒ offline.
- LAN: `online = interfacesLinkState[id].up is True`.
- Site desconectado sem `devices`: os links ficam **sem observação** (o estado deles não muda). O
  site, por sua vez, é observado offline.

## Fixtures exigidas (`tests/fixtures/cato/`, anonimizadas)

| Arquivo | Conteúdo |
|---|---|
| `todos_online.json` | ≥ 2 sites, cada um com ≥ 1 WAN e ≥ 1 LAN online |
| `link_wan_offline.json` | igual ao anterior, com 1 WAN de um site caída |
| `site_desconectado.json` | 1 site com `connectivityStatus=disconnected` |
| `site_ha.json` | site com 2 sockets (primário/secundário) |
| `graphql_errors.json` | resposta 200 com `errors` |

Anonimização: ids trocados por valores sequenciais estáveis, nomes trocados por `Site A`/`WAN1 -
Operadora X`, e IPs e seriais removidos. A estrutura e os nomes de campos ficam intactos.
