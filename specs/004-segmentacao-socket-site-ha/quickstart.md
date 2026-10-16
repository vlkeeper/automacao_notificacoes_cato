# Quickstart: validação do aviso único por socket

Roteiro para provar a feature ponta a ponta. Referências: [data-model](data-model.md),
[avisos-socket](contracts/avisos-socket.md), [state-file-sockets](contracts/state-file-sockets.md).

## Pré-requisitos

- Ambiente de teste: `pip install -r requirements-dev.txt`.
- Para os passos manuais: um site HA de teste na Cato, com acesso físico ou remoto para desligar
  um socket, e o robô configurado como hoje (`.env` com os dois webhooks).

## 1. Testes automatizados

```powershell
python -m pytest tests -q
```

Esperado: tudo verde, incluindo:

- `test_snapshot.py`: `connected` presente/ausente, reserva "todas as WANs offline", LAN/HA link
  ignorados, `isHA` com um único device listado, site não-HA sem `sockets`.
- `test_motor_socket.py`: cada linha das tabelas de transição do [data-model §3](data-model.md).
- `test_cenarios.py`: as sequências de [avisos-socket](contracts/avisos-socket.md#sequências-garantidas-mesma-fila-em-ordem),
  reinício com socket offline (sem duplicar, com retorno avisado) e regressão de site sem HA.
- `test_cards.py`: snapshots `SOCKET_OFFLINE.json` e `SOCKET_RETORNO.json`.
- `test_lembrete.py`: 1 pendência por socket offline e nenhuma porta dele.
- `test_canais.py`: mapeamento completo inclui os tipos novos.

## 2. Socket cai e volta (US1, US2)

1. Com o site HA estável, desligar o socket **secundário**.
2. Após a tolerância + 1 intervalo: chega ao canal de rede **um** `SOCKET OFFLINE` com
   "Socket: secundário" e nenhum `REDE OFFLINE` das portas dele.
3. Em `state.json`, `sites.<id>.sockets.<chave>.estado = "OFFLINE_NOTIFICADO"`.
4. Reiniciar o robô (`docker compose restart`): nenhum aviso repetido.
5. Religar o socket: chega **um** `SOCKET DE VOLTA` com a duração e nenhum `REDE DE VOLTA`.
6. Repetir com o socket **primário**.

## 3. Verificação da resposta da Cato (R-002)

Com um socket desligado, consultar a API (mesma query de `cato_client.QUERY`) e confirmar que o
device desligado continua em `devices` com `connected: false`. Se ele não aparecer, parar e revisar
R-002 antes de publicar.

## 4. Site inteiro (US3)

1. Desligar um socket e esperar o `SOCKET OFFLINE`.
2. Desligar o outro: chega só `SITE OFFLINE`.
3. Religar apenas um: chegam `SITE DE VOLTA` e, em seguida, `SOCKET OFFLINE` do que segue fora.
4. Religar o último: `SOCKET DE VOLTA`.

## 5. Lembrete diário

Com um socket offline, ajustar `LEMBRETE_HORARIO` para o próximo minuto e reiniciar: `PENDÊNCIAS
DO DIA` mostra uma linha "Socket secundário (inteiro)" e nenhuma porta desse socket.

## 6. Regressão sem HA (US4)

Em um site de socket único, derrubar uma WAN: `REDE OFFLINE` e `REDE DE VOLTA` iguais aos de antes.
