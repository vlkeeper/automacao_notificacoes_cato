"""Cenários ponta a ponta da feature 003 (canal operacional separado)."""

import json

import responses

from cato_monitor.modelos import EstadoMonitor, EventoNotificacao, TipoEvento

from ..conftest import URL_HEARTBEAT, URL_OPERACIONAL, URL_TEAMS
from .test_cenarios import Ambiente, duas_wans, registrar_http, sem_emoji, titulos


@responses.activate
def test_canal_operacional_fora_por_15_min_avisa_uma_vez_no_de_rede_e_normaliza(cfg, relogio):
    responses.get(URL_HEARTBEAT, status=200)
    responses.get(URL_HEARTBEAT + "/fail", status=200)
    responses.post(URL_TEAMS, status=202)
    responses.post(URL_OPERACIONAL, status=500)
    amb = Ambiente(cfg, relogio)
    for _ in range(17):  # o MONITOR_INICIADO fica preso; 15 min de falha contínua
        amb.ciclo(duas_wans())
    assert sem_emoji(titulos(URL_TEAMS)) == ["CANAL OPERACIONAL SEM ENTREGA"]
    for _ in range(3):
        amb.ciclo(duas_wans())
    assert len(titulos(URL_TEAMS)) == 1  # sem repetição

    amb.iniciar()  # reinício no meio da falha preserva o estado e não repete o aviso
    assert amb.estado.entrega["operacional"].aviso_emitido
    amb.ciclo(duas_wans())
    assert len(titulos(URL_TEAMS)) == 1

    responses.replace(responses.POST, URL_OPERACIONAL, status=202)
    amb.ciclo(duas_wans())  # entrega os pendentes e gera a normalização
    amb.ciclo(duas_wans())  # a normalização segue no canal de rede
    assert sem_emoji(titulos(URL_TEAMS)) == ["CANAL OPERACIONAL SEM ENTREGA",
                                             "CANAL OPERACIONAL NORMALIZADO"]
    assert amb.estado.filas == {"rede": [], "operacional": []}
    assert sem_emoji(titulos(URL_OPERACIONAL))[-1] == "MONITOR INICIADO"


@responses.activate
def test_estado_v1_pendente_e_migrado_e_entregue_uma_vez(cfg, relogio):
    registrar_http()
    dados = EstadoMonitor().para_dict()
    del dados["filas"], dados["entrega"]
    dados["schema_version"] = 1
    dados["monitor"]["proximo_seq"] = 3
    t = relogio.agora()
    dados["pendente_envio"] = [
        EventoNotificacao("evt-000001", TipoEvento.MONITOR_INICIADO, t, t,
                          {"sites_total": 1, "links_total": 2, "itens_offline": []}).para_dict(),
        EventoNotificacao("evt-000002", TipoEvento.MONITOR_FALHA, t, t,
                          {"falhas_consecutivas": 5, "desde": "2026-10-06T09:00:00+00:00",
                           "ultimo_motivo": "http_503"}).para_dict(),
    ]
    (cfg.state_dir / "state.json").write_text(json.dumps(dados), encoding="utf-8")
    amb = Ambiente(cfg, relogio)
    assert amb.motivo_carga is None
    amb.ciclo(duas_wans())
    assert sem_emoji(titulos(URL_OPERACIONAL))[:2] == ["MONITOR INICIADO", "MONITOR: SEM ACESSO À CATO"]
    assert all("OFFLINE" not in t for t in titulos(URL_TEAMS))
    antes = len(titulos(URL_OPERACIONAL))
    amb.iniciar()
    amb.ciclo(duas_wans())
    assert len(titulos(URL_OPERACIONAL)) == antes  # reiniciar não reenvia
