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

from pipeline import validate
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


def collect_fresh(roster: dict) -> dict:
    """Roda Wikipedia + Gazeta e funde por recência (mantém a pesquisa mais nova por candidato)."""
    estados = {uf: st["estado"] for uf, st in roster["states"].items()}
    fresh: dict = {}

    def keep_newer(r):
        k = (r.uf, r.cargo, r.name)
        if k not in fresh or parse_recency(r.date) >= parse_recency(fresh[k].date):
            fresh[k] = r

    # 1) Wikipedia (agregador estruturado)
    ws = requests.Session(); ws.headers.update(wk.UA)
    wiki_states = set()
    for uf in sorted(roster["states"]):
        recs = wk.collect_state(estados[uf], uf, roster["states"][uf], ws)
        for r in recs:
            keep_newer(r)
        if recs:
            wiki_states.add(uf)
    print(f"  Wikipedia: {len(wiki_states)} estados ({', '.join(sorted(wiki_states))})")

    # 2) Gazeta do Povo (portais, cobre o que a Wikipedia não tabula), paginando o índice
    gsx = requests.Session(); gsx.headers.update(gz.UA)
    gz_states = set()
    for uf, urls in gz.discover(gsx, estados).items():
        for url in urls:
            recs = gz.collect_url(uf, roster["states"][uf], url, gsx)
            for r in recs:
                keep_newer(r)
            if recs:
                gz_states.add(uf)
    print(f"  Gazeta: {len(gz_states)} estados ({', '.join(sorted(gz_states))})")

    covered = wiki_states | gz_states
    print(f"Cobertura total: {len(covered)}/27 estados.")
    return fresh


def apply_fresh(records: list[dict], fresh: dict) -> tuple[int, int]:
    updated = flagged = skipped_old = 0
    for r in records:
        fr = fresh.get((r["uf"], r["cargo"], r["name"]))
        if not fr or not r.get("active"):
            continue
        base_rec = parse_recency(r.get("campo"))
        if base_rec > (0, 0, 0) and parse_recency(fr.date) < base_rec:
            skipped_old += 1          # pesquisa da Wikipedia é mais antiga que a atual — não rebaixa
            continue
        ok, reason = validate.check(r.get("pct"), fr.pct)
        if ok:
            r["pct"] = fr.pct
            r["pctDisplay"] = fmt_pct(fr.pct)
            r["instituto"] = fr.pollster
            r["campo"] = fr.date
            r["source"] = "wikipedia"
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


def main():
    date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    roster = yaml.safe_load((ROOT / "reference" / "roster.yaml").read_text(encoding="utf-8"))
    snap = latest_snapshot()
    records = snap["records"]

    print("Coletando pesquisas (Wikipedia)…")
    fresh = collect_fresh(roster)
    updated, flagged, skipped_old = apply_fresh(records, fresh)
    recompute_derived(records)

    out = {"date": date_str, "source": "wikipedia + base", "records": records}
    (ROOT / "data" / "polls" / f"{date_str}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK: {updated} atualizadas, {skipped_old} ignoradas por serem mais antigas, "
          f"{flagged} descartadas pelos guardrails.")
    print(f"  -> data/polls/{date_str}.json")


if __name__ == "__main__":
    main()
