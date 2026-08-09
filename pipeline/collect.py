"""Coleta pesquisas das fontes e mescla no snapshot mais recente.

Fluxo: parte do último snapshot (mantém bloco/apoio/entradas), busca pesquisas frescas
(Wikipedia), aplica guardrails (validate), recomputa sen_norm por estado e propaga o pct
do governador para o tailwind do Senado. Escreve data/polls/<data>.json.

Uso: py -m pipeline.collect [YYYY-MM-DD]
"""
from __future__ import annotations

import datetime
import json
import pathlib
import re
import sys
from collections import defaultdict

import requests
import yaml

from pipeline import president, validate
from pipeline.sources import gazeta as gz
from pipeline.sources import wikipedia as wk

ROOT = pathlib.Path(__file__).resolve().parents[1]


def fmt_pct(p: float) -> str:
    return (f"{p:.1f}%").replace(".", ",")


_MONTHS = {"jan": 1, "fev": 2, "feb": 2, "mar": 3, "abr": 4, "apr": 4, "mai": 5, "may": 5,
           "jun": 6, "jul": 7, "ago": 8, "aug": 8, "set": 9, "sep": 9, "out": 10, "oct": 10,
           "nov": 11, "dez": 12, "dec": 12}


def parse_recency(s: str | None) -> tuple[int, int, int]:
    """Extrai (ano, mês, dia) do FIM do período, tolerando dd/mm/yyyy e '29–31 Jul 2026'.
    (0,0,0) quando não dá pra parsear."""
    if not s:
        return (0, 0, 0)
    dmy = re.findall(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if dmy:
        d, mo, y = dmy[-1]
        return (int(y), int(mo), int(d))
    ym = re.search(r"(20\d{2})", s)
    year = int(ym.group(1)) if ym else 2026
    mon = next((v for k, v in _MONTHS.items() if re.search(rf"\b{k}", s.lower())), None)
    if mon is None:
        return (0, 0, 0)
    head = s.split(str(year))[0] if str(year) in s else s
    days = re.findall(r"\d{1,2}", head)
    return (year, mon, int(days[-1]) if days else 0)


def latest_snapshot() -> dict:
    files = sorted((ROOT / "data" / "polls").glob("*.json"))
    if not files:
        raise SystemExit("Nenhum snapshot base em data/polls/. Rode o extract_preview.py.")
    return json.loads(files[-1].read_text(encoding="utf-8"))


def _ord(rec: tuple) -> int:
    return rec[0] * 365 + rec[1] * 30 + rec[2]


MA_WINDOW_DAYS = 30    # janela da média móvel (poll-of-polls) para governador/senado
MA_HALFLIFE_DAYS = 14  # meia-vida do peso por recência: pesquisa 14 dias mais velha pesa metade


def _recency_weight(age_days: float) -> float:
    """Peso exponencial decrescente com a idade da pesquisa (mais recente pesa mais)."""
    return 0.5 ** (max(0.0, age_days) / MA_HALFLIFE_DAYS)


def collect_fresh(roster: dict) -> dict:
    """Wikipedia + Gazeta -> média móvel (poll-of-polls) por candidato numa janela recente."""
    estados = {uf: st["estado"] for uf, st in roster["states"].items()}
    obs: dict = defaultdict(list)   # (uf,cargo,nome) -> lista de PollRecord (observações)

    # 1) Wikipedia (última linha por candidato)
    ws = requests.Session(); ws.headers.update(wk.UA)
    wiki_states = set()
    for uf in sorted(roster["states"]):
        recs = wk.collect_state(estados[uf], uf, roster["states"][uf], ws)
        for r in recs:
            obs[(r.uf, r.cargo, r.name)].append(r)
        if recs:
            wiki_states.add(uf)
    print(f"  Wikipedia: {len(wiki_states)} estados")

    # 2) Gazeta (várias matérias por estado, paginando o índice)
    gsx = requests.Session(); gsx.headers.update(gz.UA)
    gz_states = set()
    for uf, urls in gz.discover(gsx, estados, per_uf=3).items():
        for url in urls:
            recs = gz.collect_url(uf, roster["states"][uf], url, gsx)
            for r in recs:
                obs[(r.uf, r.cargo, r.name)].append(r)
            if recs:
                gz_states.add(uf)
    print(f"  Gazeta: {len(gz_states)} estados")

    # média móvel PONDERADA POR RECÊNCIA das pesquisas dentro de MA_WINDOW_DAYS da mais recente
    fresh: dict = {}
    n_avg = 0
    for key, lst in obs.items():
        lst.sort(key=lambda r: parse_recency(r.date), reverse=True)
        newest = lst[0]
        top = _ord(parse_recency(newest.date))
        window = [r for r in lst if isinstance(r.pct, (int, float))
                  and top - _ord(parse_recency(r.date)) <= MA_WINDOW_DAYS]
        if not window:
            window = [newest]
        weights = [_recency_weight(top - _ord(parse_recency(r.date))) for r in window]
        wsum = sum(weights) or 1.0
        avg = round(sum(w * r.pct for w, r in zip(weights, window)) / wsum, 1)
        label = f"média móvel de {len(window)} pesquisas" if len(window) > 1 else newest.pollster
        if len(window) > 1:
            n_avg += 1
        fresh[key] = {
            "pct": avg, "date": newest.date, "pollster": label,
            "sources": [{"pollster": r.pollster, "date": r.date, "pct": r.pct, "source": r.source,
                         "weight": round(w / wsum, 3)}
                        for w, r in zip(weights, window)],
        }

    covered = wiki_states | gz_states
    print(f"Cobertura total: {len(covered)}/27 estados; {n_avg} candidatos com média móvel (>1 pesquisa).")
    return fresh


def apply_fresh(records: list[dict], fresh: dict) -> tuple[int, int]:
    updated = flagged = skipped_old = 0
    for r in records:
        fr = fresh.get((r["uf"], r["cargo"], r["name"]))
        if not fr or not r.get("active"):
            continue
        base_rec = parse_recency(r.get("campo"))
        if base_rec > (0, 0, 0) and parse_recency(fr["date"]) < base_rec:
            skipped_old += 1          # coleta mais antiga que a atual — não rebaixa
            continue
        ok, reason = validate.check(r.get("pct"), fr["pct"])
        if ok:
            r["pct"] = fr["pct"]
            r["pctDisplay"] = fmt_pct(fr["pct"])
            r["instituto"] = fr["pollster"]
            r["campo"] = fr["date"]
            r["source"] = "média"
            r["polls"] = fr["sources"]     # pesquisas que compõem a média (transparência)
            r["stale"] = False
            updated += 1
        else:
            r["stale"] = True
            print(f"  guardrail: {r['uf']} {r['name']} descartado ({reason})")
            flagged += 1
    return updated, flagged, skipped_old


def recompute_derived(records: list[dict]) -> None:
    # sen_norm por estado (líder = 100)
    by_uf = defaultdict(list)
    for r in records:
        if r["cargo"] == "Senado" and r.get("active") and isinstance(r.get("pct"), (int, float)):
            by_uf[r["uf"]].append(r)
    for rs in by_uf.values():
        leader = max((x["pct"] for x in rs), default=0) or 1
        for x in rs:
            x["sen_norm"] = round(x["pct"] / leader * 100, 6)
    # propaga pct do governador para o tailwind do Senado (chapa)
    gov_pct = {(r["uf"], r["name"]): r["pct"] for r in records
               if r["cargo"] == "Governo" and isinstance(r.get("pct"), (int, float))}
    for r in records:
        if r["cargo"] == "Senado" and r.get("gov_ticket"):
            gp = gov_pct.get((r["uf"], r["gov_ticket"]))
            if gp is not None:
                r["gov_pct"] = gp


def compute_momentum(records: list[dict], date_str: str) -> int:
    """Δ p.p. da pesquisa vs. um snapshot de ~3 semanas atrás (para o termo de momentum)."""
    for r in records:
        r["mom"] = 0.0
    cur = datetime.date.fromisoformat(date_str)
    best, best_diff = None, 999
    for f in (ROOT / "data" / "polls").glob("*.json"):
        try:
            age = (cur - datetime.date.fromisoformat(f.stem)).days
        except ValueError:
            continue
        if 14 <= age <= 42 and abs(age - 21) < best_diff:
            best, best_diff = f, abs(age - 21)
    if not best:
        return 0
    prev = {(x["uf"], x["cargo"], x["name"]): x.get("pct")
            for x in json.loads(best.read_text(encoding="utf-8")).get("records", [])}
    n = 0
    for r in records:
        p0 = prev.get((r["uf"], r["cargo"], r["name"]))
        if isinstance(p0, (int, float)) and isinstance(r.get("pct"), (int, float)):
            r["mom"] = round(r["pct"] - p0, 1)
            n += 1
    return n


def main():
    date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    roster = yaml.safe_load((ROOT / "reference" / "roster.yaml").read_text(encoding="utf-8"))
    snap = latest_snapshot()
    records = snap["records"]

    print("Coletando pesquisas (Wikipedia)…")
    fresh = collect_fresh(roster)
    updated, flagged, skipped_old = apply_fresh(records, fresh)
    recompute_derived(records)
    mom_n = compute_momentum(records, date_str)

    print("Agregando pesquisas presidenciais (poll-of-polls)…")
    psx = requests.Session(); psx.headers.update(gz.UA)
    pres_agg = president.collect(psx)
    if pres_agg:
        print(f"  presidencial: {pres_agg['polls']} pesquisas, "
              f"Lula {pres_agg['first_round'][0]['avg']}% x "
              f"{pres_agg['first_round'][1]['avg']}% {pres_agg['first_round'][1]['name']}")

    out = {"date": date_str, "source": "wikipedia + gazeta + base",
           "records": records, "president": pres_agg}
    (ROOT / "data" / "polls" / f"{date_str}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK: {updated} atualizadas, {skipped_old} ignoradas por serem mais antigas, "
          f"{flagged} descartadas pelos guardrails.")
    print(f"  -> data/polls/{date_str}.json")


if __name__ == "__main__":
    main()
