import json
from pathlib import Path

import requests
import responses

from cato_monitor.cato_client import CatoClient
from cato_monitor.modelos import ConsultaFalhou, ConsultaOk

from ..conftest import TOKEN

FIXTURES = Path(__file__).parents[1] / "fixtures" / "cato"


def corpo(nome):
    return json.loads((FIXTURES / f"{nome}.json").read_text(encoding="utf-8"))


def cliente(cfg):
    esperas = []
    c = CatoClient(cfg, dormir=esperas.append)
    c.esperas = esperas
    return c


@responses.activate
def test_200_ok(cfg):
    responses.post(cfg.cato_api_url, json=corpo("todos_online"))
    r = cliente(cfg).consultar()
    assert isinstance(r, ConsultaOk) and set(r.snapshot.sites) == {"1", "2"}
    req = responses.calls[0].request
    assert req.headers["x-api-key"] == TOKEN
    assert json.loads(req.body)["variables"] == {"accountID": "1234567"}


@responses.activate
def test_corpo_so_tem_query_sem_mutation(cfg):
    responses.post(cfg.cato_api_url, json=corpo("todos_online"))
    cliente(cfg).consultar()
    enviado = json.loads(responses.calls[0].request.body)
    assert set(enviado) == {"query", "variables"}
    assert "mutation" not in enviado["query"].lower()
    assert enviado["query"].lstrip().startswith("query")


@responses.activate
def test_200_com_errors(cfg):
    responses.post(cfg.cato_api_url, json=corpo("graphql_errors"))
    assert cliente(cfg).consultar() == ConsultaFalhou("graphql_errors")


@responses.activate
def test_json_invalido(cfg):
    responses.post(cfg.cato_api_url, body="<html>nao e json</html>")
    assert cliente(cfg).consultar() == ConsultaFalhou("json_invalido")


@responses.activate
def test_timeout_retenta_e_falha_sem_excecao(cfg):
    responses.post(cfg.cato_api_url, body=requests.Timeout())
    c = cliente(cfg)
    assert c.consultar() == ConsultaFalhou("timeout")
    assert len(responses.calls) == 3 and len(c.esperas) == 2
    assert c.esperas[1] > c.esperas[0]  # backoff exponencial


@responses.activate
def test_erro_de_conexao(cfg):
    responses.post(cfg.cato_api_url, body=requests.ConnectionError())
    assert cliente(cfg).consultar() == ConsultaFalhou("conexao")


@responses.activate
def test_429_respeita_retry_after(cfg):
    responses.post(cfg.cato_api_url, status=429, headers={"Retry-After": "7"})
    responses.post(cfg.cato_api_url, json=corpo("todos_online"))
    c = cliente(cfg)
    assert isinstance(c.consultar(), ConsultaOk)
    assert c.esperas == [7.0]


@responses.activate
def test_retry_after_acima_do_teto_e_limitado(cfg):
    responses.post(cfg.cato_api_url, status=429, headers={"Retry-After": "500"})
    responses.post(cfg.cato_api_url, json=corpo("todos_online"))
    c = CatoClient(cfg, dormir=lambda s: None, monotonico=lambda: 0.0)
    # espera limitada a 30 s; como o orçamento do ciclo é 60 s, ainda cabe
    assert isinstance(c.consultar(), ConsultaOk)


@responses.activate
def test_5xx_seguido_de_sucesso(cfg):
    responses.post(cfg.cato_api_url, status=503)
    responses.post(cfg.cato_api_url, json=corpo("todos_online"))
    assert isinstance(cliente(cfg).consultar(), ConsultaOk)
    assert len(responses.calls) == 2


@responses.activate
def test_5xx_persistente(cfg):
    responses.post(cfg.cato_api_url, status=502)
    assert cliente(cfg).consultar() == ConsultaFalhou("http_502")


@responses.activate
def test_401_sem_retentativa(cfg, caplog):
    responses.post(cfg.cato_api_url, status=401)
    assert cliente(cfg).consultar() == ConsultaFalhou("http_401")
    assert len(responses.calls) == 1


@responses.activate
def test_lista_vazia_com_estado_conhecido_e_schema_invalido(cfg):
    responses.post(cfg.cato_api_url, json={"data": {"accountSnapshot": {"sites": []}}})
    assert cliente(cfg).consultar(estado_tem_sites=True) == ConsultaFalhou("schema_invalido")


@responses.activate
def test_excecao_inesperada_nao_propaga(cfg, monkeypatch):
    responses.post(cfg.cato_api_url, json=corpo("todos_online"))
    c = cliente(cfg)
    monkeypatch.setattr(c, "_classificar", lambda *a: 1 / 0)
    r = c.consultar()
    assert isinstance(r, ConsultaFalhou)
