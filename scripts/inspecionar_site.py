"""Mostra interfaces (destType) e estado das portas de um site na Cato. SOMENTE LEITURA.

Uso (raiz do projeto, lê CATO_API_KEY/CATO_ACCOUNT_ID/CATO_API_URL do .env):

    python scripts/inspecionar_site.py 955        # sites cujo nome contém "955"
    python scripts/inspecionar_site.py Cofco

Nunca imprime a chave de API.
"""

from __future__ import annotations

import sys
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parents[1]
URL_PADRAO = "https://api.catonetworks.com/api/v1/graphql2"
QUERY = """
query($accountID: ID!) {
  accountSnapshot(accountID: $accountID) {
    sites {
      id
      info { name isHA interfaces { id name destType wanRole } }
      devices {
        id haRole connected
        socketInfo { id isPrimary }
        interfaces { id name connected }
        interfacesLinkState { id up }
      }
    }
  }
}
"""


def ler_env() -> dict[str, str]:
    env: dict[str, str] = {}
    arq = RAIZ / ".env"
    if not arq.exists():
        sys.exit(f"Arquivo não encontrado: {arq}")
    for linha in arq.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        k, v = linha.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("Uso: python scripts/inspecionar_site.py <parte do nome do site>")
    filtro = sys.argv[1].lower()
    env = ler_env()
    for chave in ("CATO_API_KEY", "CATO_ACCOUNT_ID"):
        if not env.get(chave):
            sys.exit(f"{chave} ausente no .env")

    resp = requests.post(
        env.get("CATO_API_URL") or URL_PADRAO,
        headers={"x-api-key": env["CATO_API_KEY"], "Accept": "application/json"},
        json={"query": QUERY, "variables": {"accountID": env["CATO_ACCOUNT_ID"]}},
        timeout=30,
    )
    print(f"HTTP {resp.status_code}")
    try:
        dados = resp.json()
    except ValueError:
        sys.exit("Resposta não é JSON.")
    if dados.get("errors"):
        sys.exit(f"Erros da API: {dados['errors']}")

    sites = dados["data"]["accountSnapshot"]["sites"]
    achados = [s for s in sites if filtro in ((s.get("info") or {}).get("name") or "").lower()]
    if not achados:
        sys.exit(f"Nenhum site com '{sys.argv[1]}' no nome ({len(sites)} sites na conta).")

    for s in achados:
        info = s.get("info") or {}
        print(f"\n=== {info.get('name')} (id {s['id']}, isHA={info.get('isHA')}) ===")
        print("Interfaces do site (info.interfaces):")
        for i in info.get("interfaces") or []:
            print(f"  id={i['id']!s:<12} name={i.get('name')!s:<18} destType={i.get('destType')!s:<16} wanRole={i.get('wanRole')}")
        for d in s.get("devices") or []:
            si = d.get("socketInfo") or {}
            print(f"\n  Device {d['id']}: isPrimary={si.get('isPrimary')} haRole={d.get('haRole')} connected={d.get('connected')}")
            print("    WAN (interfaces):")
            for i in d.get("interfaces") or []:
                print(f"      id={i['id']!s:<12} name={i.get('name')!s:<22} connected={i.get('connected')}")
            print("    Portas físicas (interfacesLinkState):")
            for p in d.get("interfacesLinkState") or []:
                print(f"      id={p['id']!s:<12} up={p.get('up')}")


if __name__ == "__main__":
    main()
