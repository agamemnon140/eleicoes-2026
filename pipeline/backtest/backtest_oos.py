"""Backtest OUT-OF-SAMPLE do momentum (2018), com dados raspados da Wikipedia PT.

Para cada estado com série de pesquisas + resultado: pega a pesquisa FINAL e uma de ~3
semanas antes (momentum REAL, sem hindsight), e os 2 eleitos (top-2 por votos). Testa se
prever por (pesquisa final + peso·momentum) acerta mais que a pesquisa final pura.

Uso: py -m pipeline.backtest.backtest_oos
"""
from __future__ import annotations

import requests

from pipeline.backtest import scrape_history as sh
from pipeline.sources.base import strip_accents

SEATS = 2   # 2018: 2 vagas por estado
ESTADOS = ["São Paulo", "Minas Gerais", "Rio Grande do Sul", "Bahia", "Paraná", "Rio de Janeiro",
           "Pernambuco", "Ceará", "Goiás", "Santa Catarina", "Pará", "Maranhão", "Espírito Santo",
           "Amazonas", "Mato Grosso", "Rio Grande do Norte", "Paraíba", "Piauí", "Alagoas", "Sergipe",
           "Mato Grosso do Sul", "Rondônia", "Tocantins", "Acre", "Amapá", "Roraima"]
POLLSTERS = ("ibope", "datafolha", "doxa", "parana pesquisas", "methodus", "real time",
             "instituto", "quaest", "vox")


def _doy(k):
    return k[0] * 31 + k[1]


def build_case(estado, session):
    html = sh.fetch_state(estado, 2018, session)
    if not html:
        return None
    polls = sh.parse_senate_polls(html)
    if not polls or len(polls["series"]) < 1:
        return None
    cands = [c for c in polls["candidates"] if strip_accents(c).lower() not in POLLSTERS]
    if len(cands) < SEATS + 1:
        return None
    winners = sh.parse_senate_results(html, SEATS)   # nomes completos, top-N por votos
    if not winners or len(set(winners)) < SEATS:
        return None
    series = sorted(polls["series"], key=lambda r: _doy(r["key"]))
    final = series[-1]
    earlier = next((p for p in reversed(series[:-1]) if _doy(final["key"]) - _doy(p["key"]) >= 14), None)
    mom = {}
    for c in cands:
        fp = final["pcts"].get(c)
        if fp is None:
            continue
        ep = earlier["pcts"].get(c) if earlier else fp
        mom[c] = fp - (ep if ep is not None else fp)
    return {"uf": estado, "cands": cands, "final": final["pcts"], "mom": mom,
            "winners": [strip_accents(w).lower() for w in winners], "npolls": len(series),
            "has_mom": earlier is not None}


def _key(name):
    return strip_accents(name).lower()


def predict(case, w_mom):
    scored = []
    for c in case["cands"]:
        base = case["final"].get(c)
        if base is None:
            continue
        scored.append((_key(c), base + w_mom * case["mom"].get(c, 0)))
    scored.sort(key=lambda t: -t[1])
    return [n for n, _ in scored[:SEATS]]


def hits(pred, winners):
    return sum(1 for p in pred if any(p in w or w in p for w in winners))


def main():
    s = requests.Session(); s.headers.update(sh.UA)
    cases = []
    for e in ESTADOS:
        c = build_case(e, s)
        if c:
            cases.append(c)
            print(f"  {e:20} {c['npolls']:2} pesquisas | momentum={'sim' if c['has_mom'] else 'não'} | eleitos={c['winners']}")
    mom_cases = [c for c in cases if c["has_mom"]]
    total = sum(SEATS for _ in cases)
    total_mom = sum(SEATS for _ in mom_cases)
    print(f"\nAmostra OOS: {len(cases)} estados ({total} vagas); com série p/ momentum: {len(mom_cases)} ({total_mom} vagas)\n")
    print("Acurácia (top-2 = eleitos por votos):")
    for wm in (0.0, 0.5, 1.0, 1.5, 2.0):
        all_h = sum(hits(predict(c, wm), c["winners"]) for c in cases)
        mom_h = sum(hits(predict(c, wm), c["winners"]) for c in mom_cases)
        tag = "  (pesquisa pura)" if wm == 0 else ""
        print(f"  peso_momentum {wm:>3}: todos {all_h}/{total} | só c/ série {mom_h}/{total_mom}{tag}")


if __name__ == "__main__":
    main()
