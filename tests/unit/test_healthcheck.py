from datetime import timedelta

from cato_monitor import estado_store as store
from cato_monitor import healthcheck

from ..conftest import T0


def test_arquivo_ausente_nao_saudavel(tmp_path):
    assert healthcheck.saudavel(tmp_path, 60, T0) is False


def test_idade_dentro_do_limite(tmp_path):
    store.gravar_last_cycle(tmp_path, T0)
    limite = 3 * 60 + 30
    assert healthcheck.saudavel(tmp_path, 60, T0 + timedelta(seconds=limite)) is True
    assert healthcheck.saudavel(tmp_path, 60, T0 + timedelta(seconds=limite + 1)) is False


def test_conteudo_invalido_nao_saudavel(tmp_path):
    (tmp_path / "last_cycle").write_text("lixo")
    assert healthcheck.saudavel(tmp_path, 60, T0) is False


def test_main_usa_env(tmp_path, monkeypatch):
    from datetime import datetime, timezone

    store.gravar_last_cycle(tmp_path, datetime.now(timezone.utc))
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    monkeypatch.setenv("INTERVALO_SEGUNDOS", "60")
    assert healthcheck.main() == 0
    monkeypatch.setenv("STATE_DIR", str(tmp_path / "outro"))
    assert healthcheck.main() == 1
