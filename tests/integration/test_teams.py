import json

import requests
import responses

from cato_monitor import teams
from cato_monitor.modelos import EstadoMonitor, EventoNotificacao, TipoEvento

from ..conftest import T0, URL_TEAMS


def evento(n, tipo=TipoEvento.MONITOR_RECUPERADO):
    dados = {"desde": "2026-10-06T09:00:00+00:00", "recuperado_em": "2026-10-06T10:00:00+00:00", "falhas_total": 5}
    return EventoNotificacao(id=f"evt-{n:06d}", tipo=tipo, ocorrido_em=T0, criado_em=T0, dados=dados)


def estado_com(n):
    est = EstadoMonitor()
    est.pendente_envio = [evento(i) for i in range(1, n + 1)]
    return est


def drenar(est, cfg, esperas=None):
    salvos = []
    n = teams.drenar(est, cfg, lambda: salvos.append(len(est.pendente_envio)),
                     dormir=(esperas.append if esperas is not None else lambda s: None))
    return n, salvos


@responses.activate
def test_202_remove_da_fila_e_salva(cfg):
    responses.post(URL_TEAMS, status=202)
    est = estado_com(2)
    n, salvos = drenar(est, cfg)
    assert n == 2 and est.pendente_envio == [] and salvos == [1, 0]
    corpo = json.loads(responses.calls[0].request.body)
    assert corpo["type"] == "message"
    anexo = corpo["attachments"][0]
    assert anexo["contentType"] == "application/vnd.microsoft.card.adaptive"
    assert anexo["content"]["type"] == "AdaptiveCard"


@responses.activate
def test_falha_mantem_evento_incrementa_tentativas_e_interrompe(cfg):
    responses.post(URL_TEAMS, status=400)
    est = estado_com(3)
    n, _ = drenar(est, cfg)
    assert n == 0 and len(est.pendente_envio) == 3
    assert est.pendente_envio[0].tentativas == 1 and est.pendente_envio[0].ultimo_erro == "http_400"
    assert est.pendente_envio[1].tentativas == 0  # head-of-line: nem tentou o segundo
    assert len(responses.calls) == 1


@responses.activate
def test_reenvio_na_ordem_original_apos_canal_voltar(cfg):
    responses.post(URL_TEAMS, status=500)
    est = estado_com(3)
    drenar(est, cfg)
    responses.reset()
    responses.post(URL_TEAMS, status=202)
    n, _ = drenar(est, cfg)
    assert n == 3
    ids = [json.loads(c.request.body)["attachments"][0]["content"]["body"][-1]["text"] for c in responses.calls]
    assert ids == ["Ref. evt-000001", "Ref. evt-000002", "Ref. evt-000003"]


@responses.activate
def test_429_respeita_retry_after_e_depois_entrega(cfg):
    responses.post(URL_TEAMS, status=429, headers={"Retry-After": "5"})
    responses.post(URL_TEAMS, status=202)
    est = estado_com(1)
    esperas = []
    n, _ = drenar(est, cfg, esperas)
    assert n == 1 and esperas == [5.0]


@responses.activate
def test_5xx_persistente_tenta_no_maximo_duas_vezes(cfg):
    responses.post(URL_TEAMS, status=503)
    est = estado_com(1)
    drenar(est, cfg)
    assert len(responses.calls) == 2 and est.pendente_envio[0].ultimo_erro == "http_503"


@responses.activate
def test_url_ausente_do_ultimo_erro_e_dos_logs(cfg, caplog):
    responses.post(URL_TEAMS, body=requests.ConnectionError(f"falha em {URL_TEAMS}"))
    est = estado_com(1)
    with caplog.at_level("DEBUG"):
        drenar(est, cfg)
    assert est.pendente_envio[0].ultimo_erro == "conexao"
    assert URL_TEAMS not in json.dumps(est.para_dict())
    assert "SEGREDO-TEAMS" not in caplog.text


@responses.activate
def test_timeout(cfg):
    responses.post(URL_TEAMS, body=requests.Timeout())
    est = estado_com(1)
    drenar(est, cfg)
    assert est.pendente_envio[0].ultimo_erro == "timeout"


@responses.activate
def test_limite_de_20_envios_por_ciclo(cfg):
    responses.post(URL_TEAMS, status=202)
    est = estado_com(25)
    esperas = []
    n, _ = drenar(est, cfg, esperas)
    assert n == 20 and len(est.pendente_envio) == 5
    assert len(esperas) == 19  # 1 s entre envios
    n, _ = drenar(est, cfg)
    assert n == 5 and est.pendente_envio == []
