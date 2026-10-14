import pytest

from cato_monitor.config import ConfigInvalida, ler_config


def test_webhook_operacional_ausente(env_valido):
    del env_valido["TEAMS_WEBHOOK_OPERACIONAL_URL"]
    with pytest.raises(ConfigInvalida) as exc:
        ler_config(env_valido)
    assert "TEAMS_WEBHOOK_OPERACIONAL_URL ausente" in exc.value.erros


def test_webhook_operacional_http_e_invalido(env_valido):
    env_valido["TEAMS_WEBHOOK_OPERACIONAL_URL"] = "http://x.example/y"
    with pytest.raises(ConfigInvalida) as exc:
        ler_config(env_valido)
    assert any("TEAMS_WEBHOOK_OPERACIONAL_URL deve ser" in e for e in exc.value.erros)


def test_webhook_operacional_igual_ao_de_rede_e_aceito(env_valido):
    env_valido["TEAMS_WEBHOOK_OPERACIONAL_URL"] = env_valido["TEAMS_WEBHOOK_URL"]
    cfg = ler_config(env_valido)
    assert cfg.teams_webhook_operacional_url == cfg.teams_webhook_url


def test_webhook_operacional_mascarado_e_segredo(env_valido):
    cfg = ler_config(env_valido)
    assert cfg.exibicao()["TEAMS_WEBHOOK_OPERACIONAL_URL"] == "prod-01.brazilsouth.logic.azure.com"
    assert cfg.teams_webhook_operacional_url in cfg.segredos()
