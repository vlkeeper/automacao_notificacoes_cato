# Contrato: Microsoft Teams via Workflows (produzido pelo monitor)

## Configuração do fluxo (feita uma vez, no Teams)

1. No canal de destino: **⋯ → Workflows → "Post to a channel when a webhook request is
   received"**.
2. Escolha a equipe e o canal e copie a URL gerada. Ela vira `TEAMS_WEBHOOK_URL` e deve ser tratada
   como **segredo**.

## Requisição

```http
POST <TEAMS_WEBHOOK_URL>
Content-Type: application/json
```

```json
{
  "type": "message",
  "attachments": [
    {
      "contentType": "application/vnd.microsoft.card.adaptive",
      "contentUrl": null,
      "content": { "...Adaptive Card 1.4..." }
    }
  ]
}
```

Timeout `(5 s, 10 s)`. **Sucesso = qualquer 2xx** (normalmente `202 Accepted`). Qualquer outro
resultado conta como falha: o evento fica em `pendente_envio` e a drenagem para (ver
[research.md R-007](../research.md)). Em 429 e 5xx há backoff dentro do ciclo, com no máximo 2
tentativas e respeito ao `Retry-After`.

## Estrutura do card (todos os tipos)

```text
AdaptiveCard v1.4, msteams.width = "Full"
└─ Container (style por tipo, bleed)
   └─ TextBlock  "<emoji> <TÍTULO>"            (size Large, weight Bolder)
└─ FactSet
   ├─ Site:            <nome exato do portal>
   ├─ Link:            <nome da porta> (<WAN|LAN>)      ← quando aplicável
   ├─ Desde:           dd/mm/aaaa HH:MM (Brasília)
   └─ Há quanto tempo: "1 h 25 min" | Duração: "...", no retorno
└─ TextBlock  frase em linguagem simples (ver tabela)
└─ TextBlock  "Ref. evt-000123", isSubtle, size Small
```

| tipo | Emoji / título | `style` | Frase (exemplo) |
|---|---|---|---|
| `SITE_OFFLINE` | 🔴 SITE OFFLINE | `attention` | "O site **Filial X** está sem conexão. Todos os links estão fora." |
| `LINK_OFFLINE` | 🟠 LINK OFFLINE | `warning` | "Um dos links do site **Filial X** caiu. O site continua funcionando pelos outros links (operação parcial)." |
| `SITE_RETORNO` | 🟢 SITE DE VOLTA | `good` | "O site voltou após 1 h 25 min." + lista "Ainda fora: ..." quando houver |
| `LINK_RETORNO` | 🟢 LINK DE VOLTA | `good` | "O link voltou após 12 min." |
| `LEMBRETE_DIARIO` | 📋 PENDÊNCIAS DO DIA | `accent` | tabela (site, link, desde, há quanto tempo) e "(parte 1/2)" quando houver divisão |
| `MONITOR_FALHA` | ⚙️ MONITOR: SEM ACESSO À CATO | `emphasis` | "O monitor não consegue consultar a Cato desde HH:MM. **Nenhum alerta de queda será emitido até normalizar.** Isso não significa que algum site caiu." |
| `MONITOR_RECUPERADO` | ⚙️ MONITOR: ACESSO NORMALIZADO | `emphasis` | "A consulta à Cato voltou a funcionar às HH:MM." |
| `MONITOR_INICIADO` | ⚙️ MONITOR INICIADO | `emphasis` | "Monitorando N sites e M links. Já estavam fora no início: ..." |

Regras:
- Todo horário aparece em `TZ` (Brasília), no formato `dd/mm/aaaa HH:MM`. As durações aparecem como
  `X d Y h Z min`, sem segundos.
- Não há `@menções` (Clarifications).
- Cada card precisa ter no máximo 24 KB serializado. O lembrete é dividido em partes se passar
  disso.
- Cada tipo de evento tem um *snapshot test* do JSON do card.
