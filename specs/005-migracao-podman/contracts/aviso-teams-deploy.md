# Contrato: aviso de deploy no canal operacional

Destino: `TEAMS_WEBHOOK_OPERACIONAL_URL`. Envelope idêntico ao de `src/cato_monitor/teams.py`:

```json
{"type":"message","attachments":[{"contentType":"application/vnd.microsoft.card.adaptive",
 "contentUrl":null,"content":{"type":"AdaptiveCard","version":"1.4","body":[]}}]}
```

| Evento | Título do card | Fatos |
|---|---|---|
| Sucesso | `DEPLOY CONCLUÍDO` | Commit (`abc1234 — título`), Quando (America/Sao_Paulo), Observação (se o serviço estava parado à mão) |
| Falha | `DEPLOY FALHOU` | Commit (ou "indisponível" em `download`), Etapa (`download` \| `build` \| `início do serviço`), Detalhe (última linha de erro, sanitizada, ≤ 200 caracteres) |

Regras: um aviso de sucesso por commit implantado; um de falha por `<sha>:<etapa>` (FR-029);
`curl --max-time 10`, sem retentativa; título do commit e detalhe passam por `jq --arg`; nenhum
segredo ou URL no corpo. O texto do card segue o português já usado nos demais cards.
