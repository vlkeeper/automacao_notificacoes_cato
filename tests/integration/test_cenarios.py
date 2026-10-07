"""Ciclos completos do daemon (consulta falsa → motor → fila → Teams/heartbeat mockados)."""

import json
from datetime import datetime, timedelta, timezone

import responses

from cato_monitor import estado_store as store
from cato_monitor.daemon import Daemon
from cato_monitor.modelos import ConsultaFalhou, EstadoItem

from ..conftest import URL_HEARTBEAT, URL_TEAMS, RelogioFake
from ..helpers import obs_site, ok


class ClienteFalso:
    def __init__(self):
        self.proximo = None
        self.chamadas = 0

    def consultar(self, estado_tem_sites=False):
        self.chamadas += 1
        return self.proximo


class Ambiente:
    def __init__(self, cfg, relogio):
        self.cfg, self.relogio = cfg, relogio
        self.cliente = ClienteFalso()
        self.iniciar()

    def iniciar(self):
        """(Re)inicia o daemon a partir do que está em disco, como um reinício do contêiner."""
        estado, self.motivo_carga = store.carregar(self.cfg.state_dir, self.relogio.agora())
        self.daemon = Daemon(self.cfg, estado, self.cliente, self.relogio, dormir=lambda s: None)

    def ciclo(self, resultado, avancar=60):
        self.relogio.avancar(avancar)
        self.cliente.proximo = resultado
        self.daemon.executar_ciclo()

    @property
    def estado(self):
        return self.daemon.estado


def titulos():
    """Títulos dos cards entregues ao Teams, em ordem."""
    saida = []
    for c in responses.calls:
        if c.request.url == URL_TEAMS:
            card = json.loads(c.request.body)["attachments"][0]["content"]
            saida.append(card["body"][0]["items"][0]["text"])
    return saida


def sem_emoji(lista):
    return [t.split(" ", 1)[1] for t in lista]


def registrar_http():
    responses.post(URL_TEAMS, status=202)
    responses.get(URL_HEARTBEAT, status=200)
    responses.get(URL_HEARTBEAT + "/fail", status=200)


def duas_wans(w1=True, w2=True, conectado=True):
    return ok(A=obs_site("Site A", conectado=conectado, W1=w1, W2=w2))


def base(amb):
    """Linha de base com tudo online (1 aviso MONITOR_INICIADO)."""
    amb.ciclo(duas_wans())
    assert sem_emoji(titulos()) == ["MONITOR INICIADO"]


# ---------------------------------------------------------------- parte 1 (US1)


@responses.activate
def test_oscilacao_dentro_da_tolerancia_nao_avisa(cfg, relogio):
    registrar_http()
    amb = Ambiente(cfg, relogio)
    base(amb)
    amb.ciclo(duas_wans(w1=False))
    amb.ciclo(duas_wans(w1=False))
    amb.ciclo(duas_wans(w1=True))
    for _ in range(5):
        amb.ciclo(duas_wans())
    assert len(titulos()) == 1


@responses.activate
def test_queda_apos_tolerancia_avisa_uma_vez(cfg, relogio):
    registrar_http()
    amb = Ambiente(cfg, relogio)
    base(amb)
    for _ in range(8):
        amb.ciclo(duas_wans(w1=False))
    assert sem_emoji(titulos()) == ["MONITOR INICIADO", "LINK OFFLINE"]
    assert amb.estado.pendente_envio == []


@responses.activate
def test_site_offline_com_tres_links_avisa_so_o_site(cfg, relogio):
    registrar_http()
    amb = Ambiente(cfg, relogio)
    amb.ciclo(ok(A=obs_site("Site A", W1=True, W2=True, L1=True)))
    for _ in range(6):
        amb.ciclo(ok(A=obs_site("Site A", W1=False, W2=False, L1=False)))
    assert sem_emoji(titulos()) == ["MONITOR INICIADO", "SITE OFFLINE"]


@responses.activate
def test_reinicio_durante_a_tolerancia_notifica_no_prazo_sem_duplicar(cfg, relogio):
    registrar_http()
    amb = Ambiente(cfg, relogio)
    base(amb)
    amb.ciclo(duas_wans(w1=False))   # PENDENTE (t+0)
    inicio = amb.estado.sites["A"].links["W1"].inicio_queda
    amb.ciclo(duas_wans(w1=False))   # +60 s
    amb.iniciar()                    # reinício do processo
    assert amb.motivo_carga is None
    assert amb.estado.sites["A"].links["W1"].inicio_queda == inicio
    amb.ciclo(duas_wans(w1=False))   # +120 s: ainda dentro
    assert len(titulos()) == 1
    amb.ciclo(duas_wans(w1=False))   # +180 s: tolerância cumprida
    assert sem_emoji(titulos())[-1] == "LINK OFFLINE"
    amb.iniciar()
    amb.ciclo(duas_wans(w1=False))
    assert sem_emoji(titulos()).count("LINK OFFLINE") == 1


@responses.activate
def test_falha_da_api_nao_avanca_nem_reinicia_a_tolerancia(cfg, relogio):
    registrar_http()
    amb = Ambiente(cfg, relogio)
    base(amb)
    amb.ciclo(duas_wans(w1=False))
    inicio = amb.estado.sites["A"].links["W1"].inicio_queda
    for _ in range(3):
        amb.ciclo(ConsultaFalhou("timeout"))
        link = amb.estado.sites["A"].links["W1"]
        assert link.estado == EstadoItem.PENDENTE_OFFLINE and link.inicio_queda == inicio
    assert len(titulos()) == 1  # nenhuma queda durante as falhas
    amb.ciclo(duas_wans(w1=True))  # voltou: silêncio
    assert amb.estado.sites["A"].links["W1"].estado == EstadoItem.ONLINE
    assert len(titulos()) == 1


# ---------------------------------------------------------------- parte 2 (US2)


@responses.activate
def test_queda_e_retorno_com_duracao_correta(cfg, relogio):
    registrar_http()
    amb = Ambiente(cfg, relogio)
    base(amb)
    for _ in range(8):
        amb.ciclo(duas_wans(w1=False))
    amb.ciclo(duas_wans(), avancar=300)
    assert sem_emoji(titulos()) == ["MONITOR INICIADO", "LINK OFFLINE", "LINK DE VOLTA"]
    entregas = [c for c in responses.calls if c.request.url == URL_TEAMS]
    card = json.loads(entregas[-1].request.body)
    fatos = card["attachments"][0]["content"]["body"][1]["facts"]
    # queda observada no 1º ciclo; 7 ciclos de 60 s depois + 300 s => 12 min
    assert any(f["title"] == "Duração:" and f["value"] == "12 min" for f in fatos)


@responses.activate
def test_site_volta_com_link_fora(cfg, relogio):
    registrar_http()
    amb = Ambiente(cfg, relogio)
    base(amb)
    for _ in range(6):
        amb.ciclo(duas_wans(w1=False, w2=False))
    amb.ciclo(duas_wans(w1=True, w2=False))
    assert sem_emoji(titulos())[-1] == "SITE DE VOLTA"
    ultimo = json.loads([c for c in responses.calls if c.request.url == URL_TEAMS][-1].request.body)
    textos = json.dumps(ultimo, ensure_ascii=False)
    assert "Ainda fora: W2 (WAN)" in textos


@responses.activate
def test_teams_fora_reenvia_na_ordem_original_com_horario_original(cfg, relogio):
    responses.get(URL_HEARTBEAT, status=200)
    responses.post(URL_TEAMS, status=500)
    amb = Ambiente(cfg, relogio)
    amb.ciclo(duas_wans())  # linha de base: MONITOR_INICIADO fica na fila
    for _ in range(8):
        amb.ciclo(duas_wans(w1=False))
    assert [e.tipo.value for e in amb.estado.pendente_envio] == ["MONITOR_INICIADO", "LINK_OFFLINE"]
    amb.ciclo(duas_wans(w1=False), avancar=3600)  # uma hora depois
    responses.replace(responses.POST, URL_TEAMS, status=202)
    amb.ciclo(duas_wans(w1=False))
    assert amb.estado.pendente_envio == []
    cards = [json.loads(c.request.body)["attachments"][0]["content"]
             for c in responses.calls if c.request.url == URL_TEAMS and c.response.status_code == 202]
    # reenvio na ordem original: INICIADO (1), LINK_OFFLINE (2), depois o lembrete das 8h (3)
    assert [c["body"][-1]["text"] for c in cards] == ["Ref. evt-000001", "Ref. evt-000002", "Ref. evt-000003"]
    corpo = cards[1]
    desde = [f for f in corpo["body"][1]["facts"] if f["title"] == "Desde:"][0]["value"]
    assert desde == amb.estado.sites["A"].links["W1"].inicio_queda.astimezone(cfg.tz).strftime("%d/%m/%Y %H:%M")


@responses.activate
def test_reinicio_nao_repete_avisos(cfg, relogio):
    registrar_http()
    amb = Ambiente(cfg, relogio)
    base(amb)
    for _ in range(8):
        amb.ciclo(duas_wans(w1=False))
    antes = len(titulos())
    for _ in range(3):
        amb.iniciar()
        amb.ciclo(duas_wans(w1=False))
    assert len(titulos()) == antes


# ---------------------------------------------------------------- parte 3 (US3)


@responses.activate
def test_lembrete_as_oito_e_reinicio_as_oito_e_cinco_enviam_um_so(cfg):
    registrar_http()
    relogio = RelogioFake(datetime(2026, 10, 6, 10, 0, tzinfo=timezone.utc))  # 07:00 locais
    amb = Ambiente(cfg, relogio)
    amb.ciclo(duas_wans(w1=False), avancar=0)  # linha de base com W1 já fora
    amb.relogio._agora = datetime(2026, 10, 6, 11, 0, tzinfo=timezone.utc)  # 08:00 locais
    amb.ciclo(duas_wans(w1=False), avancar=0)
    assert sem_emoji(titulos()).count("PENDÊNCIAS DO DIA") == 1
    amb.relogio.avancar(300)
    amb.iniciar()
    amb.ciclo(duas_wans(w1=False), avancar=0)
    assert sem_emoji(titulos()).count("PENDÊNCIAS DO DIA") == 1


# ---------------------------------------------------------------- parte 4 (US5)


@responses.activate
def test_cinco_falhas_avisam_o_monitor_e_a_recuperacao(cfg, relogio):
    registrar_http()
    amb = Ambiente(cfg, relogio)
    base(amb)
    for _ in range(7):
        amb.ciclo(ConsultaFalhou("http_503"))
    assert sem_emoji(titulos()) == ["MONITOR INICIADO", "MONITOR: SEM ACESSO À CATO"]
    amb.ciclo(duas_wans())
    assert sem_emoji(titulos())[-1] == "MONITOR: ACESSO NORMALIZADO"
    assert not any("QUEDA" in t or "OFFLINE" in t for t in titulos())


@responses.activate
def test_heartbeat_fail_com_cinco_falhas_ou_mais(cfg, relogio):
    registrar_http()
    amb = Ambiente(cfg, relogio)
    base(amb)
    for _ in range(4):
        amb.ciclo(ConsultaFalhou("timeout"))
    urls = [c.request.url for c in responses.calls if "hc-ping" in c.request.url]
    assert all(not u.endswith("/fail") for u in urls)
    amb.ciclo(ConsultaFalhou("timeout"))
    amb.ciclo(ConsultaFalhou("timeout"))
    urls = [c.request.url for c in responses.calls if "hc-ping" in c.request.url]
    assert urls[-1].endswith("/fail") and urls[-2].endswith("/fail")
    amb.ciclo(duas_wans())
    urls = [c.request.url for c in responses.calls if "hc-ping" in c.request.url]
    assert not urls[-1].endswith("/fail")


@responses.activate
def test_falha_do_heartbeat_nao_interrompe_o_ciclo(cfg, relogio):
    responses.post(URL_TEAMS, status=202)
    responses.get(URL_HEARTBEAT, status=500)
    amb = Ambiente(cfg, relogio)
    amb.ciclo(duas_wans())
    assert (cfg.state_dir / "last_cycle").exists()


@responses.activate
def test_estado_corrompido_gera_monitor_iniciado_e_nenhuma_queda(cfg, relogio):
    registrar_http()
    amb = Ambiente(cfg, relogio)
    base(amb)
    (cfg.state_dir / "state.json").write_text("{corrompido", encoding="utf-8")
    amb.iniciar()
    assert amb.motivo_carga is not None
    amb.ciclo(duas_wans(w1=False))
    assert sem_emoji(titulos()) == ["MONITOR INICIADO", "MONITOR INICIADO"]
    assert list(cfg.state_dir.glob("state.json.corrompido-*"))
    assert not any("LINK" in t for t in titulos())


@responses.activate
def test_item_ausente_por_3_ciclos_e_removido_sem_aviso_e_item_novo_entra_em_silencio(cfg, relogio):
    registrar_http()
    amb = Ambiente(cfg, relogio)
    base(amb)
    for _ in range(3):
        amb.ciclo(ok(A=obs_site("Site A", W1=True)))
    assert "W2" not in amb.estado.sites["A"].links
    amb.ciclo(ok(A=obs_site("Site A", W1=True), B=obs_site("Site B", W1=True)))
    assert "B" in amb.estado.sites
    assert len(titulos()) == 1


@responses.activate
def test_ciclo_grava_estado_last_cycle_e_loga(cfg, relogio, caplog):
    registrar_http()
    amb = Ambiente(cfg, relogio)
    with caplog.at_level("INFO", logger="cato_monitor"):
        amb.ciclo(duas_wans())
    assert (cfg.state_dir / "last_cycle").exists() and (cfg.state_dir / "state.json").exists()
    registro = [r for r in caplog.records if r.__dict__.get("event") == "ciclo_concluido"]
    assert registro and registro[0].consulta == "ok" and registro[0].enviados == 1
    assert registro[0].falhas_consecutivas == 0 and registro[0].fila_pendente == 0
