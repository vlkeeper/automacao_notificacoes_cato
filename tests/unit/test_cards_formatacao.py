from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from cato_monitor.cards import formatar_duracao, formatar_horario

TZ = ZoneInfo("America/Sao_Paulo")


def test_horario_utc_para_brasilia():
    assert formatar_horario(datetime(2026, 10, 6, 14, 5, tzinfo=timezone.utc), TZ) == "06/10/2026 11:05"


def test_horario_com_virada_de_dia():
    assert formatar_horario(datetime(2026, 10, 7, 1, 30, tzinfo=timezone.utc), TZ) == "06/10/2026 22:30"
    assert formatar_horario(datetime(2026, 12, 31, 2, 59, tzinfo=timezone.utc), TZ) == "30/12/2026 23:59"


@pytest.mark.parametrize(
    "segundos,esperado",
    [
        (0, "0 min"),
        (59, "0 min"),
        (60, "1 min"),
        (12 * 60, "12 min"),
        (3600, "1 h 0 min"),
        (85 * 60, "1 h 25 min"),
        (86400, "1 d 0 h 0 min"),
        (86400 + 3 * 3600 + 7 * 60 + 45, "1 d 3 h 7 min"),
    ],
)
def test_duracao_sem_segundos(segundos, esperado):
    assert formatar_duracao(segundos) == esperado


def test_nomes_preservados_com_acentos_e_espacos():
    from cato_monitor.cards import renderizar
    from cato_monitor.modelos import EventoNotificacao, TipoEvento

    t0 = datetime(2026, 10, 6, 14, 25, tzinfo=timezone.utc)
    nome_site, nome_link = "  Matriz  São José – Térreo ", "WAN1 - Operadora Açaí"
    ev = EventoNotificacao(
        id="evt-000001", tipo=TipoEvento.LINK_OFFLINE, ocorrido_em=t0, criado_em=t0,
        dados=dict(site_id="1", site_nome=nome_site, link_id="x/y", link_nome=nome_link, link_tipo="WAN",
                   inicio_queda="2026-10-06T14:00:00+00:00", outros_links_online=0),
    )
    fatos = renderizar(ev, TZ)["body"][1]["facts"]
    assert fatos[0]["value"] == nome_site
    assert fatos[1]["value"] == f"{nome_link} (WAN)"
