from dataclasses import replace
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from cato_monitor.config import Config
from datetime import time

T0 = datetime(2026, 10, 6, 10, 0, 0, tzinfo=timezone.utc)

URL_TEAMS = "https://prod-00.brazilsouth.logic.azure.com/workflows/abc123/triggers/manual?sig=SEGREDO-TEAMS"
URL_HEARTBEAT = "https://hc-ping.com/11111111-2222-3333-4444-555555555555"
TOKEN = "token-secreto-abcd1234"


class RelogioFake:
    def __init__(self, inicio: datetime = T0):
        self._agora = inicio

    def agora(self) -> datetime:
        return self._agora

    def avancar(self, segundos: float) -> datetime:
        self._agora += timedelta(seconds=segundos)
        return self._agora


@pytest.fixture
def relogio():
    return RelogioFake()


def fazer_config(state_dir, **sobrescritas) -> Config:
    base = Config(
        cato_api_key=TOKEN,
        cato_account_id="1234567",
        cato_api_url="https://api.catonetworks.com/api/v1/graphql2",
        teams_webhook_url=URL_TEAMS,
        heartbeat_url=URL_HEARTBEAT,
        intervalo_segundos=60,
        tolerancia_segundos=180,
        lembrete_horario=time(8, 0),
        tz=ZoneInfo("America/Sao_Paulo"),
        tz_nome="America/Sao_Paulo",
        state_dir=state_dir,
        log_level="INFO",
    )
    return replace(base, **sobrescritas)


@pytest.fixture
def cfg(tmp_path):
    return fazer_config(tmp_path)


@pytest.fixture
def env_valido(tmp_path):
    return {
        "CATO_API_KEY": TOKEN,
        "CATO_ACCOUNT_ID": "1234567",
        "TEAMS_WEBHOOK_URL": URL_TEAMS,
        "HEARTBEAT_URL": URL_HEARTBEAT,
        "STATE_DIR": str(tmp_path),
    }
