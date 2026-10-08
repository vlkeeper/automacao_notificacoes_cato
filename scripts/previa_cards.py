"""Gera cards FALSOS para visualizar a formatação (nada é consultado na Cato nem gravado no estado).

Uso (a partir da raiz do projeto, com o venv ou o Python local com `requests`):

    python scripts/previa_cards.py                      # grava um JSON por tipo em previas/
    python scripts/previa_cards.py LINK_OFFLINE SITE_OFFLINE
    python scripts/previa_cards.py --enviar             # envia ao TEAMS_WEBHOOK_URL do .env (canal de TESTE!)

Os JSONs podem ser colados no designer https://adaptivecards.io/designer (host: Microsoft Teams).
Os dados de exemplo são os mesmos dos testes (tests/unit/test_cards.py).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(RAIZ / "src"), str(RAIZ)]

from cato_monitor.cards import renderizar  # noqa: E402
from cato_monitor.modelos import EventoNotificacao, TipoEvento  # noqa: E402
from cato_monitor.teams import _mensagem  # noqa: E402
from tests.unit.test_cards import DADOS, OCORRIDO  # noqa: E402


def _url_do_env() -> str:
    if os.environ.get("TEAMS_WEBHOOK_URL"):
        return os.environ["TEAMS_WEBHOOK_URL"]
    for linha in (RAIZ / ".env").read_text(encoding="utf-8").splitlines():
        chave, _, valor = linha.partition("=")
        if chave.strip() == "TEAMS_WEBHOOK_URL":
            return valor.strip().strip("\"'")
    sys.exit("TEAMS_WEBHOOK_URL não encontrada no ambiente nem no .env")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tipos", nargs="*", help="tipos a gerar (padrão: todos): " + ", ".join(t.name for t in TipoEvento))
    ap.add_argument("--enviar", action="store_true", help="envia os cards ao webhook do Teams")
    ap.add_argument("--tz", default="America/Sao_Paulo")
    args = ap.parse_args()

    tipos = [TipoEvento[t.upper()] for t in args.tipos] if args.tipos else list(DADOS)
    tz = ZoneInfo(args.tz)
    saida = RAIZ / "previas"
    saida.mkdir(exist_ok=True)

    sessao = None
    if args.enviar:
        import requests
        sessao, url = requests.Session(), _url_do_env()

    for n, tipo in enumerate(tipos, 1):
        ev = EventoNotificacao(id=f"evt-9{n:05d}", tipo=tipo, ocorrido_em=OCORRIDO,
                               criado_em=OCORRIDO, dados=DADOS[tipo])
        card = renderizar(ev, tz)
        arq = saida / f"{tipo.name}.json"
        arq.write_text(json.dumps(card, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"gravado {arq.relative_to(RAIZ)}")
        if sessao:
            r = sessao.post(url, json=_mensagem(card), timeout=(5, 15))
            print(f"  enviado {tipo.name}: HTTP {r.status_code}")
            time.sleep(1)


if __name__ == "__main__":
    main()
