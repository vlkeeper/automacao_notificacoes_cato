import io
import json
import logging

from cato_monitor.logs import configurar_logging, evento

from ..conftest import TOKEN, URL_HEARTBEAT, URL_TEAMS


def _logger():
    saida = io.StringIO()
    log = configurar_logging("DEBUG", [TOKEN, URL_TEAMS, URL_HEARTBEAT], stream=saida)
    return log, saida


def test_formato_json_valido():
    log, saida = _logger()
    evento(log, logging.INFO, "ciclo_concluido", "ok", sites=3)
    linha = json.loads(saida.getvalue())
    assert linha["event"] == "ciclo_concluido"
    assert linha["level"] == "INFO"
    assert linha["sites"] == 3
    assert linha["ts"].endswith("+00:00")


def test_token_e_urls_nunca_aparecem():
    log, saida = _logger()
    log.error(f"falha com {TOKEN} em {URL_TEAMS} e {URL_HEARTBEAT}")
    evento(log, logging.WARNING, "envio_teams", "x", url=URL_TEAMS, detalhes={"k": [TOKEN]})
    texto = saida.getvalue()
    assert TOKEN not in texto
    assert "SEGREDO-TEAMS" not in texto
    assert "11111111-2222" not in texto
    assert "<redacted" in texto


def test_traceback_tambem_e_redigido():
    log, saida = _logger()
    try:
        raise RuntimeError(f"erro ao chamar {URL_TEAMS} com {TOKEN}")
    except RuntimeError:
        log.exception("quebrou")
    texto = saida.getvalue()
    assert TOKEN not in texto
    assert "SEGREDO-TEAMS" not in texto
    json.loads(texto)


def test_url_de_host_conhecido_e_redigida_mesmo_sem_ser_segredo_carregado():
    saida = io.StringIO()
    log = configurar_logging("INFO", [], stream=saida)
    log.info("GET https://outro.powerplatform.com/x?sig=abc falhou")
    assert "sig=abc" not in saida.getvalue()
