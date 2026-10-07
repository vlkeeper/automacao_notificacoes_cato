"""Renderização dos Adaptive Cards (v1.4) por tipo de evento. Puro: sem I/O nem relógio global.

Todo horário aparece em `tz` (Brasília) como `dd/mm/aaaa HH:MM`; durações como `X d Y h Z min`.
Textos em linguagem simples, sem jargão de rede e sem @menções (contracts/teams-webhook.md).
"""

from __future__ import annotations

from datetime import datetime, tzinfo
from typing import Any

from .modelos import EventoNotificacao, TipoEvento, str_para_ts

LIMITE_BYTES_CARD = 24 * 1024

# tipo -> (emoji, título, style do Container)
ESTILOS: dict[TipoEvento, tuple[str, str, str]] = {
    TipoEvento.SITE_OFFLINE: ("🔴", "SITE OFFLINE", "attention"),
    TipoEvento.LINK_OFFLINE: ("🟠", "LINK OFFLINE", "warning"),
    TipoEvento.SITE_RETORNO: ("🟢", "SITE DE VOLTA", "good"),
    TipoEvento.LINK_RETORNO: ("🟢", "LINK DE VOLTA", "good"),
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
            ("Link", _link_txt(d["link_nome"], d["link_tipo"])),
            ("Desde", formatar_horario(inicio, tz)),
            ("Há quanto tempo", formatar_duracao((e.ocorrido_em - inicio).total_seconds())),
        ),
        _texto(
            f"Um dos links do site **{d['site_nome']}** caiu. "
            "O site continua funcionando pelos outros links (operação parcial)."
        ),
    ]


def _site_offline(e: EventoNotificacao, tz: tzinfo) -> list[dict[str, Any]]:
    d = e.dados
    inicio = _ts(d["inicio_queda"])
    corpo = [
        _fatos(
            ("Site", d["site_nome"]),
            ("Desde", formatar_horario(inicio, tz)),
            ("Há quanto tempo", formatar_duracao((e.ocorrido_em - inicio).total_seconds())),
        ),
        _texto(f"O site **{d['site_nome']}** está sem conexão. Todos os links estão fora."),
    ]
    if d.get("links_afetados"):
        lista = ", ".join(_link_txt(n, t) for n, t in d["links_afetados"])
        corpo.append(_texto(f"Links afetados: {lista}", isSubtle=True))
    return corpo


def _link_retorno(e: EventoNotificacao, tz: tzinfo) -> list[dict[str, Any]]:
    d = e.dados
    inicio, volta = _ts(d["inicio_queda"]), _ts(d["retorno_em"])
    duracao = formatar_duracao((volta - inicio).total_seconds())
    return [
        _fatos(
            ("Site", d["site_nome"]),
            ("Link", _link_txt(d["link_nome"], d["link_tipo"])),
            ("Desde", formatar_horario(inicio, tz)),
            ("Duração", duracao),
        ),
        _texto(f"O link voltou após {duracao}."),
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


def _lembrete(e: EventoNotificacao, tz: tzinfo) -> list[dict[str, Any]]:
    d = e.dados
    pendencias = d["pendencias"]
    sufixo = f" (parte {d['parte']}/{d['total_partes']})" if d["total_partes"] > 1 else ""
    corpo = [
        _texto(f"Itens que continuam fora hoje ({len(pendencias)} nesta mensagem){sufixo}:"),
        {
            "type": "ColumnSet",
            "columns": [_coluna(t, l, weight="Bolder")
                        for t, l in (("Site", "stretch"), ("Link", "stretch"), ("Desde", "auto"), ("Há quanto tempo", "auto"))],
        },
    ]
    for p in pendencias:
        inicio = _ts(p["inicio_queda"])
        link = _link_txt(p["link_nome"], p["tipo"]) if p["link_nome"] else "Site inteiro"
        corpo.append({
            "type": "ColumnSet",
            "separator": True,
            "columns": [
                _coluna(p["site_nome"], "stretch"),
                _coluna(link, "stretch"),
                _coluna(formatar_horario(inicio, tz), "auto"),
                _coluna(formatar_duracao((e.ocorrido_em - inicio).total_seconds()), "auto"),
            ],
        })
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
        itens = ", ".join(
            f"{i['site_nome']}" + (f" / {_link_txt(i['link_nome'], i['tipo'])}" if i["link_nome"] else " (site inteiro)")
            for i in d["itens_offline"]
        )
        corpo.append(_texto(f"Já estavam fora no início: {itens}"))
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
