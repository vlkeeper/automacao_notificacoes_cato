"""Renderização dos Adaptive Cards (v1.4) por tipo de evento. Puro: sem I/O nem relógio global.

Todo horário aparece em `tz` (Brasília) como `dd/mm/aaaa HH:MM`; durações como `X d Y h Z min`.
Textos em linguagem simples, sem jargão de rede e sem @menções (contracts/teams-webhook.md).
"""

from __future__ import annotations

from datetime import datetime, tzinfo
from typing import Any

from .modelos import EventoNotificacao, TipoEvento, str_para_ts

LIMITE_BYTES_CARD = 24 * 1024
SEP = chr(10) * 2  # quebra de linha entre itens num mesmo TextBlock

# tipo -> (emoji, título, style do Container)
ESTILOS: dict[TipoEvento, tuple[str, str, str]] = {
    TipoEvento.SITE_OFFLINE: ("🔴", "SITE OFFLINE", "attention"),
    TipoEvento.LINK_OFFLINE: ("🟠", "REDE OFFLINE", "warning"),
    TipoEvento.SITE_RETORNO: ("🟢", "SITE DE VOLTA", "good"),
    TipoEvento.LINK_RETORNO: ("🟢", "REDE DE VOLTA", "good"),
    TipoEvento.LEMBRETE_DIARIO: ("📋", "PENDÊNCIAS DO DIA", "accent"),
    TipoEvento.MONITOR_FALHA: ("⚙️", "MONITOR: SEM ACESSO À CATO", "emphasis"),
    TipoEvento.MONITOR_RECUPERADO: ("⚙️", "MONITOR: ACESSO NORMALIZADO", "emphasis"),
    TipoEvento.MONITOR_INICIADO: ("⚙️", "MONITOR INICIADO", "emphasis"),
}


# --------------------------------------------------------------------------- helpers


def formatar_horario(ts: datetime, tz: tzinfo) -> str:
    return ts.astimezone(tz).strftime("%d/%m/%Y %H:%M")


def formatar_duracao(segundos: float) -> str:
    total_min = max(int(segundos // 60), 0)
    dias, resto = divmod(total_min, 24 * 60)
    horas, minutos = divmod(resto, 60)
    if dias:
        return f"{dias} d {horas} h {minutos} min"
    if horas:
        return f"{horas} h {minutos} min"
    return f"{minutos} min"


def _ts(valor: str) -> datetime:
    return str_para_ts(valor)


def _link_txt(nome: str, tipo: str) -> str:
    return f"{nome} ({tipo})"


def _fatos(*pares: tuple[str, str]) -> dict[str, Any]:
    return {"type": "FactSet", "facts": [{"title": t + ":", "value": v} for t, v in pares]}


def _texto(texto: str, **extra: Any) -> dict[str, Any]:
    return {"type": "TextBlock", "text": texto, "wrap": True, **extra}


def _envelope(evento: EventoNotificacao, corpo: list[dict[str, Any]]) -> dict[str, Any]:
    emoji, titulo, style = ESTILOS[evento.tipo]
    cabecalho = {
        "type": "Container",
        "style": style,
        "bleed": True,
        "items": [_texto(f"{emoji} {titulo}", size="Large", weight="Bolder")],
    }
    rodape = _texto(f"Ref. {evento.id}", isSubtle=True, size="Small")
    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "msteams": {"width": "Full"},
        "body": [cabecalho, *corpo, rodape],
    }


# --------------------------------------------------------------------------- templates


def _link_offline(e: EventoNotificacao, tz: tzinfo) -> list[dict[str, Any]]:
    d = e.dados
    inicio = _ts(d["inicio_queda"])
    return [
        _fatos(
            ("Site", d["site_nome"]),
            ("Porta", _link_txt(d["link_nome"], d["link_tipo"])),
            ("Desde", formatar_horario(inicio, tz)),
            ),
        _texto(
            f"Uma das redes do site **{d['site_nome']}** caiu. "
            "O site continua funcionando pelas demais redes (operação parcial)."
        ),
    ]


def _site_offline(e: EventoNotificacao, tz: tzinfo) -> list[dict[str, Any]]:
    d = e.dados
    inicio = _ts(d["inicio_queda"])
    corpo = [
        _fatos(
            ("Site", d["site_nome"]),
            ("Desde", formatar_horario(inicio, tz)),
        ),
        _texto(f"O site **{d['site_nome']}** está sem conexão. Todas as redes estão fora."),
    ]
    if d.get("links_afetados"):
        lista = ", ".join(_link_txt(n, t) for n, t in d["links_afetados"])
        corpo.append(_texto(f"Redes afetadas: {lista}", weight="Bolder"))
    return corpo


def _link_retorno(e: EventoNotificacao, tz: tzinfo) -> list[dict[str, Any]]:
    d = e.dados
    inicio, volta = _ts(d["inicio_queda"]), _ts(d["retorno_em"])
    duracao = formatar_duracao((volta - inicio).total_seconds())
    return [
        _fatos(
            ("Site", d["site_nome"]),
            ("Porta", _link_txt(d["link_nome"], d["link_tipo"])),
            ("Desde", formatar_horario(inicio, tz)),
            ("Duração", duracao),
        ),
        _texto(f"A porta voltou após {duracao}."),
    ]


def _site_retorno(e: EventoNotificacao, tz: tzinfo) -> list[dict[str, Any]]:
    d = e.dados
    inicio, volta = _ts(d["inicio_queda"]), _ts(d["retorno_em"])
    duracao = formatar_duracao((volta - inicio).total_seconds())
    corpo = [
        _fatos(
            ("Site", d["site_nome"]),
            ("Desde", formatar_horario(inicio, tz)),
            ("Duração", duracao),
        ),
        _texto(f"O site voltou após {duracao}."),
    ]
    if d.get("links_ainda_offline"):
        lista = ", ".join(_link_txt(n, t) for n, t, _ in d["links_ainda_offline"])
        corpo.append(_texto(f"Ainda fora: {lista}", weight="Bolder"))
    return corpo


def _coluna(texto: str, largura: str, **extra: Any) -> dict[str, Any]:
    return {"type": "Column", "width": largura, "items": [_texto(texto, size="Small", **extra)]}


def _tabela(cabecalhos: tuple[str, ...], linhas: list[tuple[str, ...]], larguras: tuple[str, ...]) -> list[dict[str, Any]]:
    """Tabela com colunas de largura proporcional fixa (as mesmas em todas as linhas, para alinhar)."""
    def linha(celulas: tuple[str, ...], **extra: Any) -> dict[str, Any]:
        return {"type": "ColumnSet", **extra.pop("conj", {}),
                "columns": [_coluna(c, w, **extra) for c, w in zip(celulas, larguras)]}

    return [
        linha(cabecalhos, weight="Bolder", conj={"style": "emphasis", "bleed": False}),
        *[linha(cel, conj={"separator": True}) for cel in linhas],
    ]


def _lembrete(e: EventoNotificacao, tz: tzinfo) -> list[dict[str, Any]]:
    d = e.dados
    pendencias = d["pendencias"]
    sufixo = f" (parte {d['parte']}/{d['total_partes']})" if d["total_partes"] > 1 else ""
    corpo = [_texto(f"Itens que continuam fora hoje ({len(pendencias)} nesta mensagem){sufixo}:")]
    linhas = []
    for p in pendencias:
        inicio = _ts(p["inicio_queda"])
        porta = _link_txt(p["link_nome"], p["tipo"]) if p["link_nome"] else "Site inteiro"
        linhas.append((p["site_nome"], porta, formatar_horario(inicio, tz),
                       formatar_duracao((e.ocorrido_em - inicio).total_seconds())))
    corpo += _tabela(("Site", "Porta", "Desde", "Há quanto tempo"), linhas, ("4", "4", "3", "3"))
    return corpo


def _hora(valor: str, tz: tzinfo) -> str:
    return _ts(valor).astimezone(tz).strftime("%H:%M")


def _monitor_falha(e: EventoNotificacao, tz: tzinfo) -> list[dict[str, Any]]:
    d = e.dados
    return [
        _fatos(
            ("Falhas seguidas", str(d["falhas_consecutivas"])),
            ("Desde", formatar_horario(_ts(d["desde"]), tz)),
            ("Último motivo", str(d["ultimo_motivo"])),
        ),
        _texto(
            f"O monitor não consegue consultar a Cato desde {_hora(d['desde'], tz)}. "
            "**Nenhum alerta de queda será emitido até normalizar.** "
            "Isso não significa que algum site caiu."
        ),
    ]


def _monitor_recuperado(e: EventoNotificacao, tz: tzinfo) -> list[dict[str, Any]]:
    d = e.dados
    return [
        _fatos(
            ("Sem acesso desde", formatar_horario(_ts(d["desde"]), tz)),
            ("Normalizado em", formatar_horario(_ts(d["recuperado_em"]), tz)),
            ("Falhas seguidas", str(d["falhas_total"])),
        ),
        _texto(f"A consulta à Cato voltou a funcionar às {_hora(d['recuperado_em'], tz)}."),
    ]


def _monitor_iniciado(e: EventoNotificacao, tz: tzinfo) -> list[dict[str, Any]]:
    d = e.dados
    texto = f"Monitorando {d['sites_total']} sites e {d['links_total']} links."
    corpo = [_texto(texto)]
    if d["itens_offline"]:
        # Agrupa por site (ordem de chegada): uma linha da tabela por site, com as portas offline.
        portas_por_site: dict[str, list[str]] = {}
        for i in d["itens_offline"]:
            portas = portas_por_site.setdefault(i["site_nome"], [])
            portas.append(_link_txt(i["link_nome"], i["tipo"]) if i["link_nome"] else "Site inteiro (todos os links)")
        corpo.append(_texto("Já estavam fora no início:", weight="Bolder"))
        corpo += _tabela(("Site", "Portas offline"),
                         [(site, SEP.join(portas)) for site, portas in portas_por_site.items()], ("1", "1"))
    return corpo


_TEMPLATES = {
    TipoEvento.LINK_OFFLINE: _link_offline,
    TipoEvento.SITE_OFFLINE: _site_offline,
    TipoEvento.LINK_RETORNO: _link_retorno,
    TipoEvento.SITE_RETORNO: _site_retorno,
    TipoEvento.LEMBRETE_DIARIO: _lembrete,
    TipoEvento.MONITOR_FALHA: _monitor_falha,
    TipoEvento.MONITOR_RECUPERADO: _monitor_recuperado,
    TipoEvento.MONITOR_INICIADO: _monitor_iniciado,
}


def renderizar(evento: EventoNotificacao, tz: tzinfo) -> dict[str, Any]:
    """Devolve o conteúdo do Adaptive Card do evento (sem o envelope de mensagem do Teams)."""
    return _envelope(evento, _TEMPLATES[evento.tipo](evento, tz))
