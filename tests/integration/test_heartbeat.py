import requests
import responses

from cato_monitor import heartbeat

from ..conftest import URL_HEARTBEAT


@responses.activate
def test_ping_ok_vai_na_url_base(cfg):
    responses.get(URL_HEARTBEAT, status=200)
    assert heartbeat.ping(cfg, ok=True) is True
    assert responses.calls[0].request.url == URL_HEARTBEAT


@responses.activate
def test_fail_vai_em_url_fail(cfg):
    responses.get(URL_HEARTBEAT + "/fail", status=200)
    assert heartbeat.ping(cfg, ok=False) is True


@responses.activate
def test_falha_do_heartbeat_nao_propaga(cfg):
    responses.get(URL_HEARTBEAT, body=requests.ConnectionError("x"))
    assert heartbeat.ping(cfg, ok=True) is False


@responses.activate
def test_status_http_ruim_so_loga(cfg, caplog):
    responses.get(URL_HEARTBEAT, status=500)
    with caplog.at_level("WARNING"):
        assert heartbeat.ping(cfg, ok=True) is False
    assert any(r.__dict__.get("event") == "heartbeat" for r in caplog.records)
