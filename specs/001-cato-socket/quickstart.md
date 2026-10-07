# Quickstart: validação ponta a ponta

**Plan**: [plan.md](plan.md). Este guia mostra como provar que a feature funciona. Os detalhes de
contrato estão em [contracts/](contracts/) e os do modelo em [data-model.md](data-model.md).

## Pré-requisitos

- Python 3.12 (desenvolvimento) e Docker com Compose v2 (execução).
- Um token da Cato **somente leitura** e o Account ID.
- Um fluxo do Teams criado num **canal de teste** (ver
  [contracts/teams-webhook.md](contracts/teams-webhook.md)).
- Uma checagem no Healthchecks.io (Period 1 min, Grace 2 min) e a URL de ping dela.
- Os arquivos `.env` listados no `.gitignore` e no `.dockerignore`.

## 1. Validar o schema da Cato (só em desenvolvimento, com o Cato CLI)

```bash
pip install catocli            # em um venv separado, fora da imagem
catocli configure              # informa token e account ID
catocli query accountSnapshot -h
catocli query accountSnapshot '{"accountID": "<ID>"}' > /tmp/snapshot.json
```

**Esperado**: confirmar os campos marcados com ⚠ em
[contracts/cato-graphql.md](contracts/cato-graphql.md) e respondê-los em
[research.md R-001](research.md) (papel da porta, comportamento da WAN caída e formato dos ids).
Depois, salvar as fixtures anonimizadas em `tests/fixtures/cato/`.

## 2. Testes automatizados

```bash
python -m venv .venv && . .venv/bin/activate
pip install --require-hashes -r requirements-dev.txt
pip install -e . --no-deps
pytest -q
```

**Esperado**: todos verdes, incluindo os cenários de `tests/integration/test_cenarios.py`:

| Cenário | Resultado esperado |
|---|---|
| Oscilação dentro da tolerância | 0 eventos |
| Queda ≥ tolerância e retorno | 1 `LINK_OFFLINE` e 1 `LINK_RETORNO` com a duração correta |
| Site offline com 3 links | 1 `SITE_OFFLINE`, 0 `LINK_OFFLINE` |
| Retorno do site com 1 link ainda fora | `SITE_RETORNO` com `links_ainda_offline` = 1; o link aparece no lembrete seguinte |
| Reinício no meio da tolerância | o aviso sai em `inicio_queda + tolerância` (não reinicia); nenhum aviso repetido |
| 5 falhas da API | 1 `MONITOR_FALHA`, nenhuma transição de item; no sucesso seguinte, 1 `MONITOR_RECUPERADO` |
| Teams fora e depois de volta | eventos reenviados na ordem original, com o horário original |
| Lembrete 08:00 + reinício às 08:05 | 1 lembrete só |
| Estado corrompido | `MONITOR_INICIADO` e 0 avisos de queda |

## 3. Fail-fast da configuração

```bash
docker compose run --rm -e INTERVALO_SEGUNDOS=10 monitor ; echo "exit=$?"
```

**Esperado**: `exit=1` e um log `config_invalida` que cita `INTERVALO_SEGUNDOS`, **sem** token nem
URLs.

## 4. Execução real (canal de teste)

```bash
cp .env.example .env    # preencher os valores
docker compose up -d --build
docker compose logs -f monitor
```

**Esperado**:
1. O primeiro ciclo gera `linha_base` e **um** card ⚙️ MONITOR INICIADO no canal de teste.
2. `ciclo_concluido` aparece a cada ~60 s, e a checagem do Healthchecks fica "up".
3. `docker inspect --format '{{.State.Health.Status}}' <container>` responde `healthy` após ~2 min.
4. `docker compose up -d --scale monitor=2`: a segunda instância sai com `instancia_duplicada`
   (`exit 1`).

## 5. Verificações de resiliência

| Ação | Esperado |
|---|---|
| `docker compose restart monitor` | sem cards repetidos, e `estado_carregado` com os mesmos pendentes |
| Pausar o fluxo no Power Automate e provocar um evento (ou usar um teste) | `envio_teams` com WARNING; o evento fica na fila; ao reativar o fluxo, o card chega com o horário original |
| `docker compose stop monitor` por 4 min | o Healthchecks alerta "down" em até 3 min |
| Usar uma `CATO_API_KEY` inválida | `http_401` nos logs; após 5 ciclos, card ⚙️ MONITOR: SEM ACESSO À CATO e heartbeat `/fail` |
| `grep` por token ou URL do webhook nos logs | nenhuma ocorrência |

## 6. Aceite com usuários (SC-004)

Mostre a usuários sem formação em redes os 8 tipos de card renderizados pelos *snapshot tests* (ou
os enviados ao canal de teste). Meta: pelo menos 90% identificam o site, o link e o "desde quando"
sem ajuda.
