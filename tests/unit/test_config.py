import json

import pytest

from cato_monitor.config import ConfigInvalida, carregar_config, ler_config


def test_config_valida_usa_padroes(env_valido):
    cfg = ler_config(env_valido)
    assert cfg.intervalo_segundos == 60
    assert cfg.tolerancia_segundos == 180
    assert cfg.tz_nome == "America/Sao_Paulo"
    assert cfg.lembrete_horario.strftime("%H:%M") == "08:00"
    assert cfg.log_level == "INFO"


@pytest.mark.parametrize("variavel", ["CATO_API_KEY", "CATO_ACCOUNT_ID", "TEAMS_WEBHOOK_URL", "HEARTBEAT_URL"])
def test_variavel_obrigatoria_ausente(env_valido, variavel):
    del env_valido[variavel]
    with pytest.raises(ConfigInvalida) as exc:
        ler_config(env_valido)
    assert any(variavel in e for e in exc.value.erros)


@pytest.mark.parametrize(
    "variavel,valor",
    [
        ("CATO_API_KEY", "com espaco"),
        ("CATO_ACCOUNT_ID", "12ab"),
        ("CATO_API_URL", "http://inseguro.example"),
        ("TEAMS_WEBHOOK_URL", "http://teams.example/x"),
        ("HEARTBEAT_URL", "ftp://x"),
        ("INTERVALO_SEGUNDOS", "10"),
        ("INTERVALO_SEGUNDOS", "121"),
        ("INTERVALO_SEGUNDOS", "abc"),
        ("TOLERANCIA_SEGUNDOS", "30"),
        ("TOLERANCIA_SEGUNDOS", "7200"),
        ("LEMBRETE_HORARIO", "25:00"),
        ("LEMBRETE_HORARIO", "8h"),
        ("TZ", "Marte/Olimpo"),
        ("LOG_LEVEL", "VERBOSE"),
    ],
)
def test_valor_invalido(env_valido, variavel, valor):
    env_valido[variavel] = valor
    with pytest.raises(ConfigInvalida) as exc:
        ler_config(env_valido)
    assert any(variavel in e for e in exc.value.erros)


def test_state_dir_inexistente(env_valido, tmp_path):
    env_valido["STATE_DIR"] = str(tmp_path / "nao-existe")
    with pytest.raises(ConfigInvalida) as exc:
        ler_config(env_valido)
    assert any("STATE_DIR" in e for e in exc.value.erros)


def test_tolerancia_menor_que_intervalo_recusada(env_valido):
    env_valido["INTERVALO_SEGUNDOS"] = "120"
    env_valido["TOLERANCIA_SEGUNDOS"] = "100"
    with pytest.raises(ConfigInvalida) as exc:
        ler_config(env_valido)
    assert any("TOLERANCIA_SEGUNDOS" in e for e in exc.value.erros)


def test_limites_aceitos(env_valido):
    env_valido["INTERVALO_SEGUNDOS"] = "120"
    env_valido["TOLERANCIA_SEGUNDOS"] = "120"
    cfg = ler_config(env_valido)
    assert (cfg.intervalo_segundos, cfg.tolerancia_segundos) == (120, 120)


def test_acumula_multiplos_erros(env_valido):
    del env_valido["CATO_API_KEY"]
    env_valido["INTERVALO_SEGUNDOS"] = "10"
    with pytest.raises(ConfigInvalida) as exc:
        ler_config(env_valido)
    assert len(exc.value.erros) >= 2


def test_exit_1_com_log_json_em_stderr(env_valido, capsys):
    env_valido["INTERVALO_SEGUNDOS"] = "10"
    del env_valido["CATO_API_KEY"]
    with pytest.raises(SystemExit) as exc:
        carregar_config(env_valido)
    assert exc.value.code == 1
    linha = json.loads(capsys.readouterr().err.strip())
    assert linha["event"] == "config_invalida"
    assert len(linha["erros"]) == 2


def test_segredos_mascarados_na_exibicao(env_valido):
    cfg = ler_config(env_valido)
    exibicao = json.dumps(cfg.exibicao())
    assert cfg.cato_api_key not in exibicao
    assert cfg.teams_webhook_url not in exibicao
    assert cfg.heartbeat_url not in exibicao
    assert "****1234" in exibicao
    assert "logic.azure.com" in exibicao  # só o host
    assert "SEGREDO-TEAMS" not in exibicao
