"""Snapshot test do JSON de cada um dos 8 tipos de card.

Para regenerar os snapshots depois de uma mudança intencional: `UPDATE_SNAPSHOTS=1 pytest`.
"""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from cato_monitor.cards import ESTILOS, LIMITE_BYTES_CARD, renderizar
from cato_monitor.modelos import EventoNotificacao, TipoEvento

TZ = ZoneInfo("America/Sao_Paulo")
SNAPS = Path(__file__).parent / "snapshots"
# 06/10/2026 14:25 UTC = 11:25 em Brasília
OCORRIDO = datetime(2026, 10, 6, 14, 25, tzinfo=timezone.utc)
INICIO = "2026-10-06T13:00:00+00:00"  # 10:00 em Brasília, 1 h 25 min antes

DADOS = {
    TipoEvento.LINK_OFFLINE: dict(site_id="1", site_nome="Filial Campinas", link_id="s-1/WAN2",
                                  link_nome="WAN2 - Operadora B", link_tipo="WAN",
                                  inicio_queda=INICIO, outros_links_online=1),
    TipoEvento.SITE_OFFLINE: dict(site_id="1", site_nome="Filial Campinas", inicio_queda=INICIO,
                                  motivo="todos_links_inativos",
                                  links_afetados=[["WAN1 - Operadora A", "WAN"], ["LAN1", "LAN"]]),
    TipoEvento.LINK_RETORNO: dict(site_id="1", site_nome="Filial Campinas", link_id="s-1/WAN2",
                                  link_nome="WAN2 - Operadora B", link_tipo="WAN",
                                  inicio_queda="2026-10-06T14:13:00+00:00",
                                  retorno_em="2026-10-06T14:25:00+00:00"),
    TipoEvento.SITE_RETORNO: dict(site_id="1", site_nome="Filial Campinas", inicio_queda=INICIO,
                                  retorno_em="2026-10-06T14:25:00+00:00",
                                  links_ainda_offline=[["WAN2 - Operadora B", "WAN", INICIO]]),
    TipoEvento.LEMBRETE_DIARIO: dict(data_local="2026-10-06", parte=1, total_partes=2, pendencias=[
        {"site_nome": "Filial Campinas", "link_nome": "WAN2 - Operadora B", "tipo": "WAN", "inicio_queda": INICIO},
        {"site_nome": "Matriz São Paulo", "link_nome": None, "tipo": "SITE", "inicio_queda": "2026-10-04T13:00:00+00:00"},
    ]),
    TipoEvento.MONITOR_FALHA: dict(falhas_consecutivas=5, desde="2026-10-06T14:20:00+00:00", ultimo_motivo="http_503"),
    TipoEvento.MONITOR_RECUPERADO: dict(desde="2026-10-06T14:20:00+00:00",
                                        recuperado_em="2026-10-06T14:25:00+00:00", falhas_total=6),
    TipoEvento.MONITOR_INICIADO: dict(sites_total=12, links_total=31, itens_offline=[
        {"site_nome": "Filial Campinas", "link_nome": "WAN2 - Operadora B", "tipo": "WAN"},
        {"site_nome": "Filial Recife", "link_nome": None, "tipo": "SITE"}]),
}


def evento(tipo, **dados):
    return EventoNotificacao(id="evt-000123", tipo=tipo, ocorrido_em=OCORRIDO, criado_em=OCORRIDO,
                             dados=dados or DADOS[tipo])


def textos(no):
    """Todos os textos de um card, em ordem."""
    achados = []
    if isinstance(no, dict):
        if no.get("type") == "TextBlock":
            achados.append(no["text"])
        if no.get("type") == "FactSet":
            achados += [f"{f['title']} {f['value']}" for f in no["facts"]]
        for v in no.values():
            achados += textos(v)
    elif isinstance(no, list):
        for v in no:
            achados += textos(v)
    return achados


@pytest.mark.parametrize("tipo", list(TipoEvento))
def test_snapshot_do_card(tipo):
    card = renderizar(evento(tipo), TZ)
    arquivo = SNAPS / f"{tipo.value}.json"
    texto = json.dumps(card, ensure_ascii=False, indent=2) + "\n"
    if os.environ.get("UPDATE_SNAPSHOTS"):
        SNAPS.mkdir(exist_ok=True)
        arquivo.write_text(texto, encoding="utf-8")
    assert arquivo.exists(), f"snapshot ausente: rode UPDATE_SNAPSHOTS=1 pytest ({arquivo.name})"
    assert card == json.loads(arquivo.read_text(encoding="utf-8"))


def test_ha_um_estilo_para_cada_tipo_e_sao_distintos():
    assert set(ESTILOS) == set(TipoEvento)
    titulos = [t for _, t, _ in ESTILOS.values()]
    assert len(set(titulos)) == len(TipoEvento)
    assert {e for e, _, _ in ESTILOS.values()} == {"🔴", "🟠", "🟢", "📋", "⚙️"}


@pytest.mark.parametrize("tipo", list(TipoEvento))
def test_envelope_padrao(tipo):
    card = renderizar(evento(tipo), TZ)
    emoji, titulo, style = ESTILOS[tipo]
    assert card["type"] == "AdaptiveCard" and card["version"] == "1.4"
    assert card["msteams"] == {"width": "Full"}
    cab = card["body"][0]
    assert cab["type"] == "Container" and cab["style"] == style
    assert cab["items"][0]["text"] == f"{emoji} {titulo}"
    assert card["body"][-1]["text"] == "Ref. evt-000123"


@pytest.mark.parametrize("tipo", list(TipoEvento))
def test_sem_mencoes_e_dentro_do_limite(tipo):
    card = renderizar(evento(tipo), TZ)
    bruto = json.dumps(card, ensure_ascii=False)
    assert "<at>" not in bruto and "@" not in " ".join(textos(card))
    assert len(bruto.encode("utf-8")) <= LIMITE_BYTES_CARD


def test_campos_obrigatorios_de_queda_de_link():
    t = "\n".join(textos(renderizar(evento(TipoEvento.LINK_OFFLINE), TZ)))
    assert "Site: Filial Campinas" in t
    assert "Link: WAN2 - Operadora B (WAN)" in t
    assert "Desde: 06/10/2026 10:00" in t
    assert "Há quanto tempo: 1 h 25 min" in t
    assert "operação parcial" in t


def test_campos_obrigatorios_de_site_offline():
    t = "\n".join(textos(renderizar(evento(TipoEvento.SITE_OFFLINE), TZ)))
    assert "Site: Filial Campinas" in t and "Há quanto tempo: 1 h 25 min" in t
    assert "Todos os links estão fora" in t


def test_retorno_usa_duracao():
    t = "\n".join(textos(renderizar(evento(TipoEvento.LINK_RETORNO), TZ)))
    assert "Duração: 12 min" in t and "O link voltou após 12 min." in t
    t = "\n".join(textos(renderizar(evento(TipoEvento.SITE_RETORNO), TZ)))
    assert "Duração: 1 h 25 min" in t and "Ainda fora: WAN2 - Operadora B (WAN)" in t


def test_monitor_falha_deixa_claro_que_nao_e_queda():
    t = "\n".join(textos(renderizar(evento(TipoEvento.MONITOR_FALHA), TZ)))
    assert "Nenhum alerta de queda será emitido até normalizar." in t
    assert "Isso não significa que algum site caiu." in t
    assert "desde 11:20" in t


def test_lembrete_dividido_pelo_motor_cabe_no_limite_com_nomes_longos():
    from cato_monitor.motor import _dividir_pendencias

    pend = [{"site_nome": f"Filial com um nome bem comprido número {i} " + "x" * 80,
             "link_nome": f"WAN{i} - Operadora Telecom Longa " + "y" * 60,
             "tipo": "WAN", "inicio_queda": INICIO} for i in range(200)]
    partes = _dividir_pendencias(pend)
    assert len(partes) > 1 and sum(len(p) for p in partes) == 200
    for n, parte in enumerate(partes, 1):
        ev = evento(TipoEvento.LEMBRETE_DIARIO, data_local="2026-10-06", parte=n,
                    total_partes=len(partes), pendencias=parte)
        card = renderizar(ev, TZ)
        assert f"(parte {n}/{len(partes)})" in " ".join(textos(card))
        assert len(json.dumps(card, ensure_ascii=False).encode("utf-8")) <= LIMITE_BYTES_CARD
