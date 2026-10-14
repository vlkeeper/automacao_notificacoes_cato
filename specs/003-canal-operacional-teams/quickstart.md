# Quickstart: validação do canal operacional

Roteiro para provar a feature ponta a ponta. Contratos: [configuracao](contracts/configuracao.md),
[teams-canais](contracts/teams-canais.md), [state-file-v2](contracts/state-file-v2.md).

## Pré-requisitos

- Dois fluxos do Teams Workflows ("Post to a channel when a webhook request is received"), um por
  canal, e as duas URLs.
- `.env` com `TEAMS_WEBHOOK_URL` (rede) e `TEAMS_WEBHOOK_OPERACIONAL_URL` (operacional), além das
  variáveis atuais.
- Ambiente de teste: `pip install -r requirements-dev.txt`.

## 1. Testes automatizados

```powershell
python -m pytest tests -q
```

Esperado: tudo verde, incluindo `test_canais.py` (mapeamento completo e `avaliar_entrega`),
migração em `test_estado_store.py` e isolamento entre canais em `test_teams.py`.

## 2. Roteamento (US1)

1. Subir o robô com os dois webhooks válidos (`docker compose up -d --build`).
2. Conferir no canal operacional o aviso `MONITOR INICIADO`.
3. Provocar falha de acesso à Cato (token inválido por alguns ciclos): `MONITOR: SEM ACESSO À CATO`
   chega **só** ao canal operacional; ao restaurar, `ACESSO NORMALIZADO` também.
4. Provocar queda de link/site além da tolerância: o aviso chega **só** ao canal de rede.
5. Conferir que o heartbeat (Healthchecks.io) segue recebendo pings e que nada novo aparece no Teams
   por causa dele.

## 3. Isolamento (US2)

1. Trocar `TEAMS_WEBHOOK_OPERACIONAL_URL` por uma URL inválida e reiniciar.
2. Provocar queda de link: chega ao canal de rede no prazo normal (≤ 1 intervalo + 1 min após a
   tolerância).
3. Em `docker compose logs`, os eventos `envio_teams` do canal operacional aparecem com
   `canal: operacional` e status de erro, sem a URL.
4. Aguardar 15 min contínuos: chega ao canal de rede um único `CANAL OPERACIONAL SEM ENTREGA`.
5. Restaurar o webhook e reiniciar: os avisos pendentes chegam na ordem, uma vez, e o aviso de
   normalização aparece no canal de rede.

## 4. Atualização de instalação existente (US3)

1. Com a versão anterior, deixar avisos pendentes (webhook de rede inválido).
2. Adicionar `TEAMS_WEBHOOK_OPERACIONAL_URL` e atualizar o robô.
3. Verificar o log `estado_migrado`, o arquivo `state.json.v1-<UTC>` no volume e `schema_version: 2`
   no `state.json`.
4. Reiniciar de novo: nada é migrado nem reenviado.

## 5. Falha de configuração

Remover `TEAMS_WEBHOOK_OPERACIONAL_URL` e subir: o processo encerra com `exit 1`, listando
"TEAMS_WEBHOOK_OPERACIONAL_URL ausente" sem expor segredos.
