"""Poll catalog, comparable aggregates, and provenance shared by collection/build.

Research observations are immutable inputs distinct from candidate scores. Each
aggregate uses one candidate set/turn/vote format; missing candidates are not zeros.
"""
from __future__ import annotations

from collections import defaultdict
import datetime as dt
import hashlib
import json
import random

from pipeline.sources.base import option_kind
from pipeline.sources.planopolitico import canonical

VERSION = "pesquisas-2"
WINDOW = 30
HALFLIFE = 14
STALE_DAYS = 14


def field_date(p):
    return dt.date.fromisoformat(p["field_end"])


def available(p, as_of):
    if not p.get("eligible"):
        return False
    try:
        return field_date(p) <= as_of and (not p.get("published_at") or dt.date.fromisoformat(p["published_at"]) <= as_of)
    except (ValueError, TypeError):
        return False


def compatible_key(p):
    return p["scenario"], p["scenario_key"], p["vote_format"]


def select_series(polls, as_of):
    eligible = [p for p in polls if available(p, as_of)]
    if not eligible:
        return [], []
    newest = max(eligible, key=lambda p: (p["field_end"], p.get("published_at") or "", p["id"]))
    series = [p for p in eligible if compatible_key(p) == compatible_key(newest)]
    # The latest available window remains visible when stale, clearly dated.
    anchor = max(field_date(p) for p in series)
    window = [p for p in series if (anchor - field_date(p)).days <= WINDOW]
    return series, window


def poll_weights(polls):
    """Exponential recency; each institute's total weight is its freshest poll.

    Frequent publication cannot multiply an institute's influence. Sample sizes
    remain visible metadata; they are not a substitute for design effects.
    """
    if not polls:
        return []
    anchor = max(field_date(p) for p in polls)
    raw = [0.5 ** ((anchor - field_date(p)).days / HALFLIFE) for p in polls]
    by_house = defaultdict(list)
    for i, p in enumerate(polls):
        by_house[p["pollster"]].append(i)
    weights = [0.0] * len(polls)
    for ids in by_house.values():
        total = sum(raw[i] for i in ids)
        for i in ids:
            weights[i] = raw[i] / total * max(raw[j] for j in ids)
    total = sum(weights)
    return [v / total for v in weights]


def mean_shares(polls, weights, field="valid_shares"):
    names = sorted({n for p in polls for n in p[field]})
    return {n: sum(w * p[field][n] for p, w in zip(polls, weights) if isinstance(p[field].get(n), (int, float))) /
            sum(w for p, w in zip(polls, weights) if isinstance(p[field].get(n), (int, float)))
            for n in names if any(isinstance(p[field].get(n), (int, float)) for p in polls)}


def summarize(polls, bootstrap=False):
    if not polls:
        return {"shares": {}, "raw_shares": {}, "intervals": {}, "weights": []}
    weights = poll_weights(polls)
    mean = mean_shares(polls, weights)
    intervals = {}
    houses = sorted({p["pollster"] for p in polls})
    if bootstrap and len(houses) >= 3:
        groups = [[p for p in polls if p["pollster"] == h] for h in houses]
        rng = random.Random(2026)
        draws = defaultdict(list)
        # Cluster bootstrap keeps dependent observations from each institute together.
        for _ in range(200):
            sampled, sampled_w = [], []
            for index in rng.choices(range(len(groups)), k=len(groups)):
                group = groups[index]
                ids = [polls.index(p) for p in group]
                sampled.extend(group)
                sampled_w.extend(weights[i] for i in ids)
            for n, v in mean_shares(sampled, sampled_w).items():
                draws[n].append(v)
        for n, values in draws.items():
            values.sort()
            intervals[n] = [round(values[int(.05 * (len(values) - 1))], 1),
                            round(values[int(.95 * (len(values) - 1))], 1)]
    return {"shares": {n: round(v, 1) for n, v in mean.items()},
            "raw_shares": {n: round(v, 1) for n, v in mean_shares(polls, weights, "shares").items()},
            "intervals": intervals, "weights": weights}


def matched_trend(series, as_of, days):
    """Compare weighted means with a fixed panel of institutes at both dates.

    Constant house offsets cancel; an institute entering the window alone cannot
    create a trend. A minimum of two shared institutes and new observations is
    required. This is descriptive, not a calibrated estimate of voter movement.
    """
    previous_date = as_of - dt.timedelta(days=days)
    current = [p for p in series if available(p, as_of) and 0 <= (as_of - field_date(p)).days <= WINDOW]
    previous = [p for p in series if available(p, previous_date) and 0 <= (previous_date - field_date(p)).days <= WINDOW]
    houses = sorted({p["pollster"] for p in current} & {p["pollster"] for p in previous})
    changes = defaultdict(list)
    for house in houses:
        now = [p for p in current if p["pollster"] == house]
        old = [p for p in previous if p["pollster"] == house]
        if {p["id"] for p in now} == {p["id"] for p in old}:
            continue
        a, b = summarize(now)["shares"], summarize(old)["shares"]
        for name in sorted(a.keys() & b.keys()):
            changes[name].append(a[name] - b[name])
    return {n: {"delta": round(sum(values) / len(values), 1), "institutes": len(values)}
            for n, values in changes.items() if len(values) >= 2}


def aggregate(polls, as_of, history=True):
    series, window = select_series(polls, as_of)
    result = summarize(window, bootstrap=True)
    result.update({"polls": len(window), "institutes": sorted({p["pollster"] for p in window}),
                   "latest_field": max((p["field_end"] for p in window), default=None),
                   "used_ids": [p["id"] for p in window],
                   "scenario_key": window[0]["scenario_key"] if window else None,
                   "vote_format": window[0]["vote_format"] if window else None,
                   "trends": {str(days): matched_trend(series, as_of, days) for days in (7, 14)},
                   "history": []})
    if history and series:
        for offset in range(60, -1, -3):
            day = as_of - dt.timedelta(days=offset)
            rows = [p for p in series if available(p, day) and 0 <= (day - field_date(p)).days <= WINDOW]
            if rows:
                point = summarize(rows, bootstrap=True)
                result["history"].append({"date": day.isoformat(), "shares": point["shares"], "intervals": point["intervals"]})
    result["age_days"] = (as_of - dt.date.fromisoformat(result["latest_field"])).days if result["latest_field"] else None
    result["stale"] = result["age_days"] is None or result["age_days"] > STALE_DAYS
    return result


def match_name(name, candidates):
    """Exact normalized name, then a unique token subset; never first-token wins."""
    key = canonical(name)
    exact = [c for c in candidates if canonical(c["name"]) == key]
    if len(exact) == 1:
        return exact[0]
    tokens = set(key.split()) - {"de", "da", "do", "dos", "das", "dr", "dra", "professor", "professora"}
    matched = [c for c in candidates if tokens and tokens <= set(canonical(c["name"]).split())]
    return matched[0] if len(matched) == 1 else None


def observation(p, name, weight):
    return {**{k: p.get(k) for k in ("id", "registro", "pollster", "date", "field_start", "field_end",
            "published_at", "sample_size", "method", "source", "source_url", "url", "base", "scenario",
            "scenario_key", "vote_format", "sum_cands", "undecided")},
            "pct": p["shares"].get(name), "pct_valid": p["valid_shares"].get(name), "votos": 1,
            "weight": round(weight, 5)}


def apply_catalog(records, polls, as_of):
    """Replace only races covered by the new source; retain flagged legacy fallback."""
    for uf, cargo in sorted({(r["uf"], r["cargo"]) for r in records}):
        race = [r for r in records if (r["uf"], r["cargo"]) == (uf, cargo) and r.get("active")]
        rows = [p for p in polls if (p["uf"], p["cargo"]) == (uf, cargo)]
        first = [p for p in rows if p["scenario"] == "1º turno"]
        _, selected = select_series(first, as_of)
        if not selected:
            for r in race:
                r["research_fallback"] = True
            continue
        agg = summarize(selected)
        for r in race:
            # A new scenario must not retain an old percentage for an omitted name.
            r.update(pct=None, pct_valid=None, pct_valid_estimado=False, pctDisplay="Não medido neste cenário",
                     polls=[], runoff={}, sen_norm=0.0, research_managed=True, research_fallback=False, stale=False)
        for name, value in agg["shares"].items():
            r = match_name(name, race) if option_kind(name) == "candidato" else None
            if not r:
                continue
            r.update(pct=agg["raw_shares"].get(name), pct_valid=value,
                     pctDisplay=f'{agg["raw_shares"].get(name, value):.1f}%'.replace(".", ","),
                     instituto=f"média de {len(selected)} pesquisas", campo=max(p["date"] for p in selected if p["field_end"] == max(x["field_end"] for x in selected)),
                     source="Plano Político", fonte=selected[0]["source_url"],
                     polls=[observation(p, name, w) for p, w in zip(selected, agg["weights"]) if name in p["valid_shares"]])
        for signature in sorted({p["scenario_key"] for p in rows if p["scenario"] == "2º turno"}):
            duel = [p for p in rows if p["scenario"] == "2º turno" and p["scenario_key"] == signature]
            _, selected_duel = select_series(duel, as_of)
            da = summarize(selected_duel)
            names = [n for n in da["shares"] if option_kind(n) == "candidato"]
            if len(names) != 2:
                continue
            for name in names:
                r = match_name(name, race)
                rival = match_name(next(n for n in names if n != name), race)
                if r and rival:
                    r["runoff"][rival["name"]] = {"pct_valid": da["shares"][name],
                        "date": max(p["field_end"] for p in selected_duel),
                        "polls": [observation(p, name, w) for p, w in zip(selected_duel, da["weights"])]}


def presidential(polls, as_of):
    from pipeline.president import _bloc
    first = [p for p in polls if p["cargo"] == "Presidente" and p["uf"] == "BR" and p["scenario"] == "1º turno"]
    agg = aggregate(first, as_of)
    by_id = {p["id"]: p for p in first}
    selected = [by_id[i] for i in agg["used_ids"]]
    parties = {"Lula": "PT", "Flávio": "PL", "Zema": "Novo", "Caiado": "PSD"}
    entries = [{"name": n, "party": parties.get(_bloc(n), ""), "bloc": _bloc(n), "avg": v,
                "raw_avg": agg["raw_shares"].get(n), "interval": agg["intervals"].get(n), "n": agg["polls"]}
               for n, v in agg["shares"].items() if option_kind(n) != "branco"]
    entries.sort(key=lambda c: -c["avg"])
    runoff_rows = [p for p in polls if p["cargo"] == "Presidente" and p["uf"] == "BR" and p["scenario"] == "2º turno"
                   and p["scenario_key"] == "flavio bolsonaro|lula"]
    runoff = aggregate(runoff_rows, as_of, history=False)
    return {"polls": agg["polls"], "institutos": agg["institutes"], "latest_date": agg["latest_field"],
            "base": "válidos", "first_round": entries,
            "runoff": {_bloc(n): v for n, v in runoff["shares"].items() if _bloc(n) != "Indefinido"},
            "runoff_poll_count": runoff["polls"], "trend": {}, "research": agg,
            "used": [{**observation(p, "Lula", w), "Lula": p["valid_shares"].get("Lula"),
                      "Flávio": p["valid_shares"].get("Flávio Bolsonaro")}
                     for p, w in zip(selected, agg["weights"])]}


def race_health(records, polls, as_of):
    agg = aggregate([p for p in polls if p["scenario"] == "1º turno"], as_of, history=False)
    active = [r for r in records if r.get("active")]
    missing = [r["name"] for r in active if r.get("pct_valid") is None]
    unmapped = [n for n in agg["shares"] if option_kind(n) == "candidato" and not match_name(n, active)]
    return {**{k: agg[k] for k in ("polls", "institutes", "latest_field", "age_days", "stale", "vote_format")},
            "missing_candidates": missing, "unmapped_candidates": unmapped,
            "excluded": sum(not p["eligible"] for p in polls),
            "fallback": not agg["polls"],
            "estimated_base": any(r.get("pct_valid_estimado") for r in active)}


def digest(polls):
    return hashlib.sha256(json.dumps(polls, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def export(catalog, states, as_of):
    polls = catalog["polls"]
    races, used = {}, set()
    for uf, st in states.items():
        for office, cargo in (("governor", "Governo"), ("senate", "Senado")):
            rows = [p for p in polls if p["uf"] == uf and p["cargo"] == cargo]
            agg = aggregate([p for p in rows if p["scenario"] == "1º turno"], as_of)
            used.update(agg["used_ids"])
            health = race_health(st[office]["candidates"], rows, as_of)
            health["has_runoff"] = st[office].get("race", {}).get("decidido_por") == "pesquisa de 2º turno"
            finalistas = st[office].get("race", {}).get("finalistas", [])
            dates = [p.get("field_end") for c in st[office]["candidates"] if c["name"] in finalistas
                     for rival, info in (c.get("runoff") or {}).items() if rival in finalistas
                     for p in info.get("polls", []) if p.get("field_end")]
            health["runoff_latest_field"] = max(dates, default=None)
            st[office]["research"] = health
            st[office]["stale"] = health["stale"]
            races[f"{uf}:{cargo}"] = agg
    pres = presidential(polls, as_of)
    used.update(pres["research"]["used_ids"])
    return {"version": VERSION, "generated_at": as_of.isoformat(), "sources": catalog["sources"],
            "changes": catalog.get("changes", {}),
            "method": {"window_days": WINDOW, "halflife_days": HALFLIFE, "stale_days": STALE_DAYS,
                       "interval": "Faixa de 90% por reamostragem de institutos (200 réplicas). Mede dispersão do agregado, não previsão eleitoral. Disponível com 3 ou mais institutos."},
            "counts": {"scenarios": len(polls), "registrations": len({p["registro"] for p in polls if p.get("registro")}),
                       "excluded": sum(not p["eligible"] for p in polls), "used": len(used)},
            "races": races,
            "polls": [{**p, "in_aggregate": p["id"] in used} for p in polls]}
