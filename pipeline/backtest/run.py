"""Backtest de sanidade: nos casos documentados de erro/acerto de pesquisa (2018/2022),
o modelo ponderado por chapa recupera os vencedores melhor que a pesquisa pura? E como
a acurácia varia com o teto do peso do Senado?

Uso: py -m pipeline.backtest.run
"""
from __future__ import annotations

import pathlib

import yaml

from pipeline import model, schedule

HERE = pathlib.Path(__file__).parent
RACES = yaml.safe_load((HERE / "races.yaml").read_text(encoding="utf-8"))["races"]


def _sen_norm(cands):
    leader = max((c["poll_pct"] for c in cands), default=0) or 1
    return {c["name"]: c["poll_pct"] / leader * 100 for c in cands}


def predict_model(race, k, cap):
    w = schedule.senate_weights(0, may_change_pct=race.get("may_change"), k=k, cap=cap)
    weights = {"governo": w.gov, "presidente": w.pres, "senado": w.sen, "apoio": w.apoio}
    sn = _sen_norm(race["senate"])
    scored = []
    for c in race["senate"]:
        r = model.score_senate(
            gov_pct=race["gov"].get(c["bloc"]), gov_reliability=1.0,
            pres_pct=race["pres"].get(c["bloc"]), pres_reliability=1.0,
            sen_norm=sn[c["name"]], endorsement=c.get("endorsement", "inferido"),
            weights=weights,
        )
        scored.append((c["name"], r["score"]))
    scored.sort(key=lambda t: -t[1])
    return [n for n, _ in scored[: race["seats"]]]


def predict_raw(race):
    ordered = sorted(race["senate"], key=lambda c: -c["poll_pct"])
    return [c["name"] for c in ordered[: race["seats"]]]


def hits(pred, winners):
    return len(set(pred) & set(winners))


def main():
    total = sum(len(r["winners"]) for r in RACES)
    base = sum(hits(predict_raw(r), r["winners"]) for r in RACES)
    print(f"Amostra: {len(RACES)} corridas, {total} vagas.  (casos documentados — amostra enviesada)\n")
    print(f"Baseline (pesquisa pura, top-N): {base}/{total} vencedores acertados\n")
    print("Modelo ponderado por chapa — acertos por teto do Senado:")
    print(f"  {'teto':>6} | " + " | ".join(f"k={k}" for k in (2.5, 2.75, 3.0)))
    for cap in (0.40, 0.45, 0.50, 0.55, 0.60, 0.80, 1.00):
        row = []
        for k in (2.5, 2.75, 3.0):
            h = sum(hits(predict_model(r, k, cap), r["winners"]) for r in RACES)
            row.append(f"{h:>3}/{total}")
        print(f"  {cap:>6.2f} | " + " | ".join(row))
    print("\nPor corrida (k=2.75, teto=0.50):")
    for r in RACES:
        pm = predict_model(r, 2.75, 0.50)
        pr = predict_raw(r)
        print(f"  {r['id']:8} real={r['winners']}\n"
              f"           modelo={pm} ({hits(pm, r['winners'])}/{len(r['winners'])}) | "
              f"pesquisa={pr} ({hits(pr, r['winners'])}/{len(r['winners'])})")


if __name__ == "__main__":
    main()
