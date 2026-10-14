"""Roteamento e isolamento entre os canais do Teams."""

import logging

import responses

from cato_monitor import teams
from cato_monitor.canais import Canal
from cato_monitor.modelos import EstadoMonitor

from ..conftest import URL_OPERACIONAL, URL_TEAMS
from .test_teams import evento


def _nada(_s):
    return None


@responses.activate
def test_roteamento_por_canal_e_log_sem_url(cfg, caplog):
    responses.post(URL_TEAMS, status=202)
    responses.post(URL_OPERACIONAL, status=202)
    est = EstadoMonitor()
    est.filas["rede"] = [evento(1)]
    est.filas["operacional"] = [evento(2)]
    with caplog.at_level(logging.INFO):
        res = teams.drenar_todos(est, cfg, lambda: None, dormir=_nada)
    assert res == {Canal.REDE: (1, False), Canal.OPERACIONAL: (1, False)}
    assert sorted(c.request.url for c in responses.calls) == sorted([URL_TEAMS, URL_OPERACIONAL])
    assert est.filas == {"rede": [], "operacional": []}
    assert "SEGREDO" not in caplog.text
    canais = {r.canal for r in caplog.records if getattr(r, "event", "") == "envio_teams"}
    assert canais == {"rede", "operacional"}


@responses.activate
def test_canal_operacional_falhando_nao_atrapalha_o_de_rede(cfg):
    responses.post(URL_TEAMS, status=202)
    responses.post(URL_OPERACIONAL, status=500)
    est = EstadoMonitor()
    est.filas["rede"] = [evento(1)]
    est.filas["operacional"] = [evento(2), evento(3)]
    res = teams.drenar_todos(est, cfg, lambda: None, dormir=_nada)
    assert res[Canal.REDE] == (1, False) and res[Canal.OPERACIONAL] == (0, True)
    assert est.filas["rede"] == []
    assert [e.id for e in est.filas["operacional"]] == ["evt-000002", "evt-000003"]
    assert est.filas["operacional"][0].ultimo_erro == "http_500"
    assert est.filas["operacional"][1].tentativas == 0  # head-of-line dentro do canal


def test_excecao_em_um_canal_nao_impede_o_outro(cfg, monkeypatch):
    chamados = []

    def falso(estado, canal, *a, **k):
        chamados.append(canal)
        if canal is Canal.REDE:
            raise RuntimeError("boom")
        return 1, False

    monkeypatch.setattr(teams, "drenar_canal", falso)
    res = teams.drenar_todos(EstadoMonitor(), cfg, lambda: None)
    assert res == {Canal.REDE: (0, True), Canal.OPERACIONAL: (1, False)}
    assert set(chamados) == {Canal.REDE, Canal.OPERACIONAL}
