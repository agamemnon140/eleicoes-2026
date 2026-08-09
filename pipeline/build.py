"""Constrói os JSONs que o site lê, a partir do roster + do snapshot de pesquisas mais recente.

Recomputa governador e senado com o modelo (model.py) e os pesos que variam no tempo
(schedule.py), na data do snapshot. Emite:
  data/forecast.json   estados (gov + senado) + consolidado nacional + metadados
  data/parties.json    cores/rótulos de blocos e partidos (de reference/parties.yaml)
  data/president.json   agregado nacional (stub até o president.py/agregador)

Uso: py -m pipeline.build   (ou  .venv/Scripts/python.exe -m pipeline.build)
"""
from __future__ import annotations

import datetime
import json
import pathlib

import yaml

from pipeline import model, schedule

ROOT = pathlib.Path(__file__).resolve().parents[1]
WEB_DATA = ROOT / "docs" / "data"         # JSONs publicados (servidos pelo site via GitHub Pages)
BLOCS = ("Lula", "Flávio", "Caiado", "Zema")


def latest_polls() -> dict:
    files = sorted((ROOT / "data" / "polls").glob("*.json"))
    if not files:
        raise SystemExit("Nenhum snapshot em data/polls/. Rode o extract_preview.py ou os scrapers.")
    return json.loads(files[-1].read_text(encoding="utf-8"))


def pres_reliability(basis: str | None) -> float:
    return 0.65 if (basis and "proxy" in basis.lower()) else 1.0


def state_may_change(sen_records: list[dict]) -> float | None:
    for r in sen_records:
        if r.get("may_change") is not None:
            return r["may_change"]
    return None


def score_state(uf, gov_recs, sen_recs, pres_lean, days, gov_conf, sen_conf):
    lean = pres_lean.get(uf, {})
    basis = lean.get("basis")

    # --- governador: pesquisa própria (confiab. 1.0) + lean presidencial do bloco ---
    gw = schedule.governor_weights(days)
    govs = []
    for r in gov_recs:
        pres_pct = lean.get(r["bloc"]) if r["bloc"] in BLOCS else None
        res = model.score_governor(
            gov_pct=r.get("pct"), gov_reliability=1.0,
            pres_pct=pres_pct, pres_reliability=pres_reliability(basis),
            w_gov=gw.gov, w_pres=gw.pres,
        )
        govs.append({**_public(r), "score": res["score"], "components": res["components"],
                     "model": {
                         "scores": res["scores"],
                         "weights": {"governo": round(gw.gov, 3), "presidente": round(gw.pres, 3)},
                         "inputs": {"gov_pct": r.get("pct"), "gov_reliability": 1.0,
                                    "pres_pct": pres_pct, "pres_reliability": pres_reliability(basis),
                                    "pres_bloc": r["bloc"], "pres_basis": basis}}})
    govs.sort(key=lambda c: c["score"], reverse=True)

    gov_estimate = next((c for c in govs if c["active"]), None)
    for c in govs:
        c["estimated"] = c is gov_estimate

    # --- senado: chapa (gov + pres com confiab. do preview) + pesquisa do Senado + apoio ---
    mc = state_may_change(sen_recs)
    sw = schedule.senate_weights(days, may_change_pct=mc)
    weights = {"governo": sw.gov, "presidente": sw.pres, "senado": sw.sen, "apoio": sw.apoio}
    sens = []
    for r in sen_recs:
        res = model.score_senate(
            gov_pct=r.get("gov_pct"), gov_reliability=r.get("gov_reliability") or 0.78,
            pres_pct=r.get("pres_pct"), pres_reliability=r.get("pres_reliability") or 0.65,
            sen_norm=r.get("sen_norm") or 0.0, endorsement=r.get("endorsement"),
            weights=weights,
        )
        sens.append({**_public(r), "score": res["score"], "components": res["components"],
                     "model": {
                         "scores": res["scores"],
                         "weights": weights,
                         "inputs": {"gov_pct": r.get("gov_pct"), "gov_reliability": r.get("gov_reliability") or 0.78,
                                    "pres_pct": r.get("pres_pct"), "pres_reliability": r.get("pres_reliability") or 0.65,
                                    "pres_bloc": r["bloc"], "pres_basis": basis,
                                    "sen_norm": r.get("sen_norm"), "gov_ticket": r.get("gov_ticket"),
                                    "endorsement": r.get("endorsement")}}})
    sens.sort(key=lambda c: c["score"], reverse=True)

    sen_estimate = [c for c in sens if c["active"]][:2]
    est_ids = {id(c) for c in sen_estimate}
    for c in sens:
        c["estimated"] = id(c) in est_ids

    return {
        "uf": uf,
        "estado": gov_recs[0]["_estado"] if gov_recs else (sen_recs[0]["_estado"] if sen_recs else uf),
        "governor": {
            "bloc": gov_estimate["bloc"] if gov_estimate else "Indefinido",
            "certainty": gov_conf.get(uf, ""),
            "stale": False,
            "estimate": _mini(gov_estimate),
            "weights": {"gov": round(gw.gov, 3), "pres": round(gw.pres, 3)},
            "candidates": govs,
        },
        "senate": {
            "seats": 2,
            "bloc": sen_estimate[0]["bloc"] if sen_estimate else "Indefinido",
            "blocs": [c["bloc"] for c in sen_estimate],
            "certainty": sen_conf.get(uf, ""),
            "stale": False,
            "may_change": mc,
            "weights": {k: round(v, 3) for k, v in weights.items()},
            "estimate": [_mini(c) for c in sen_estimate],
            "candidates": sens,
        },
    }


def _public(r: dict) -> dict:
    """Campos de exibição que o front usa (sem os internos do modelo)."""
    keep = ("uf", "cargo", "name", "party", "bloc", "apoio", "apoio_verificado", "pct",
            "pctDisplay", "instituto", "campo", "cenario", "indecisao", "situacao", "fonte",
            "status", "status_tipo", "active", "gov_ticket", "may_change",
            "estimated_preview", "certainty_preview")
    return {k: r.get(k) for k in keep}


def _mini(c):
    if not c:
        return None
    return {"name": c["name"], "party": c["party"], "bloc": c["bloc"], "score": c["score"]}


def national_table(states: dict, roster: dict) -> list[dict]:
    hold = {row["party"]: row["hold"] for row in roster["national_seed"]}
    holdnames = roster.get("holdovers", {})
    newsen: dict = {}
    gov: dict = {}
    for st in states.values():
        for c in st["senate"]["estimate"]:
            newsen[c["party"]] = newsen.get(c["party"], 0) + 1
        est = st["governor"]["estimate"]
        if est:
            gov[est["party"]] = gov.get(est["party"], 0) + 1
    parties = set(hold) | set(newsen) | set(gov)
    rows = []
    for p in parties:
        h, n, g = hold.get(p, 0), newsen.get(p, 0), gov.get(p, 0)
        rows.append({"party": p, "hold": h, "newSen": n, "sen2027": h + n, "gov": g,
                     "holdNames": holdnames.get(p, [])})
    rows.sort(key=lambda r: (r["sen2027"], r["gov"]), reverse=True)
    return rows


def parties_json():
    p = yaml.safe_load((ROOT / "reference" / "parties.yaml").read_text(encoding="utf-8"))
    (WEB_DATA / "parties.json").write_text(
        json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    WEB_DATA.mkdir(parents=True, exist_ok=True)
    roster = yaml.safe_load((ROOT / "reference" / "roster.yaml").read_text(encoding="utf-8"))
    polls = latest_polls()
    date_str = polls.get("date") or datetime.date.today().isoformat()
    as_of = datetime.date.fromisoformat(date_str)
    days = schedule.days_until(as_of)

    # anexa nome do estado a cada registro e agrupa por UF/cargo
    estados = {uf: st["estado"] for uf, st in roster["states"].items()}
    by_uf: dict = {}
    for r in polls["records"]:
        r["_estado"] = estados.get(r["uf"], r["uf"])
        by_uf.setdefault(r["uf"], {"Governo": [], "Senado": []})[r["cargo"]].append(r)

    states = {}
    for uf in sorted(by_uf):
        states[uf] = score_state(
            uf, by_uf[uf]["Governo"], by_uf[uf]["Senado"], roster["pres_lean"],
            days, roster["gov_confidence"], roster["sen_confidence"],
        )

    forecast = {
        "generated_at": date_str,
        "election_date": roster.get("election_date", "2026-10-04"),
        "days_to_election": days,
        "source": polls.get("source", "snapshot"),
        "national": national_table(states, roster),
        "states": states,
    }
    (WEB_DATA / "forecast.json").write_text(
        json.dumps(forecast, ensure_ascii=False, indent=1), encoding="utf-8")

    president = {
        "generated_at": date_str,
        "available": False,
        "note": "Agregado nacional presidencial será preenchido pelo president.py (agregador).",
        "pres_lean": roster.get("pres_lean", {}),
    }
    (WEB_DATA / "president.json").write_text(
        json.dumps(president, ensure_ascii=False, indent=1), encoding="utf-8")

    parties_json()

    n_states = len(states)
    n_est_sen = sum(len(s["senate"]["estimate"]) for s in states.values())
    print(f"OK: {n_states} estados, {n_est_sen} senadores estimados, {days} dias até a eleição.")
    print("  -> docs/data/forecast.json, docs/data/president.json, docs/data/parties.json")


if __name__ == "__main__":
    main()
