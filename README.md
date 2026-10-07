# Monitor de Sockets Cato com avisos no Teams

Daemon Python 3.12 que consulta a API GraphQL da Cato a cada intervalo (padrão 60 s), detecta queda e
retorno de **links** e **sites** e avisa um canal do Microsoft Teams com cards em linguagem simples.

- **Queda**: só avisa depois da tolerância (padrão 180 s) e uma única vez por episódio. Distingue
  `LINK OFFLINE` (operação parcial) de `SITE OFFLINE` (todos os links fora ou site desconectado da Cato).
- **Retorno**: avisa só quando a queda foi comunicada, com a duração.
- **Lembrete diário** (padrão 08:00, horário de Brasília): lista o que continua fora; nunca repete no mesmo dia.
- **Saúde do próprio monitor**: após 5 falhas seguidas de consulta avisa `MONITOR: SEM ACESSO À CATO` e,
  quando normaliza, `ACESSO NORMALIZADO`. Falha de consulta **nunca** vira alerta de queda.
- **Estado persistido** em `/data/state.json` (gravação atômica): reiniciar o contêiner não repete avisos
  nem perde a contagem da tolerância. Eventos não entregues ao Teams ficam em fila e são reenviados na ordem.

> O monitor é **somente leitura** na Cato.

## Pré-requisitos

1. **Token da API Cato somente leitura** (Catopa → Resources → API Management). Dê a permissão mínima de
   leitura (visualizar sites/snapshot); não use token com permissão de escrita.
2. **ID da conta Cato** (`CATO_ACCOUNT_ID`, só dígitos).
3. **Fluxo do Teams** (uma vez): no canal de destino, `⋯ → Workflows → "Post to a channel when a webhook
   request is received"`, escolha equipe e canal e copie a URL gerada. Ela é um **segredo**.
4. **Heartbeat externo** (recomendado): uma checagem no [Healthchecks.io](https://healthchecks.io) ou
   compatível. Configure `Period` = `INTERVALO_SEGUNDOS` e `Grace` = 2 intervalos (ex.: 1 min e 2 min para
   o padrão de 60 s), com alerta para o responsável por um canal **diferente** do Teams.
5. Uma VM Linux com Docker Compose **fora da rede monitorada** (para que a queda do site onde o monitor
   roda não o derrube) e com **NTP ativo** (toda a lógica depende de timestamps).

## Configuração

Copie `.env.example` para `.env` e preencha. **Nunca versione o `.env`.**

| Variável | Obrig. | Padrão | Descrição |
|---|---|---|---|
| `CATO_API_KEY` | sim | — | token somente leitura (segredo) |
| `CATO_ACCOUNT_ID` | sim | — | id da conta (só dígitos) |
| `CATO_API_URL` | não | `https://api.catonetworks.com/api/v1/graphql2` | endpoint (https) |
| `TEAMS_WEBHOOK_URL` | sim | — | URL do fluxo do Teams (segredo, https) |
| `HEARTBEAT_URL` | sim | — | URL do heartbeat (segredo, https) |
| `INTERVALO_SEGUNDOS` | não | `60` | 30 a 120 |
| `TOLERANCIA_SEGUNDOS` | não | `180` | 60 a 3600 e ≥ intervalo |
| `LEMBRETE_HORARIO` | não | `08:00` | `HH:MM` no fuso `TZ` |
| `TZ` | não | `America/Sao_Paulo` | fuso de exibição e do lembrete |
| `STATE_DIR` | não | `/data` | diretório do estado (precisa ser gravável) |
| `LOG_LEVEL` | não | `INFO` | `DEBUG`/`INFO`/`WARNING`/`ERROR` |

Configuração inválida encerra o processo com `exit 1` e um log `config_invalida` (stderr) listando **todos**
os erros, sem exibir segredos. Detalhes em
[specs/001-cato-socket/contracts/configuracao.md](specs/001-cato-socket/contracts/configuracao.md).

## Execução (Docker Compose)

```bash
cp .env.example .env        # preencha os valores
docker compose up -d --build
docker compose logs -f monitor
```

- Na primeira execução (ou com estado corrompido) o monitor faz uma **linha de base**: registra os itens
  atuais e envia **um** card `MONITOR INICIADO`, sem alertas em massa.
- Uma única instância: o lock `/data/monitor.lock` faz uma segunda instância sair com `instancia_duplicada`.
- O `HEALTHCHECK` da imagem falha se o último ciclo tiver mais de `3 × INTERVALO + 30 s`.
- Todos os logs saem em JSON no stdout; token e URLs do Teams/heartbeat são mascarados.

## Desenvolvimento e testes

```bash
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest -q
```

Atualizar dependências (versões exatas com hashes): `pip-compile --generate-hashes requirements.in`
e `requirements-dev.in`.

Estrutura: `src/cato_monitor/` (código), `tests/unit` e `tests/integration` (testes),
`specs/001-cato-socket/` (especificação, plano, contratos e tarefas).

## Pendências conhecidas

- O parser de `snapshot.py` segue o contrato **candidato** da API Cato: o campo de papel LAN/WAN das portas
  e o comportamento de uma WAN caída precisam ser **verificados com a conta real** (tarefa T007) e as
  fixtures de `tests/fixtures/cato/` substituídas por payloads reais anonimizados.
