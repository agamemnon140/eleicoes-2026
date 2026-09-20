"""Daily primary collection from Plano Político; legacy scrapers remain opt-in."""
from __future__ import annotations

import datetime as dt
import json
import pathlib

import requests
import yaml

from pipeline import research, roster_sync
from pipeline.sources import planopolitico as pp

ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "research" / "catalog.json"


def load_catalog():
    return json.loads(CATALOG.read_text(encoding="utf-8")) if CATALOG.exists() else {"polls": [], "sources": {}}


def run(date_str, cache_dir=None):
    from pipeline.collect import latest_snapshot, recompute_derived
    as_of = dt.date.fromisoformat(date_str)
    catalog = load_catalog()
    before = {p["id"]: research.digest(p) for p in catalog["polls"]}
    first_import = "changes" not in catalog
    session = requests.Session()
    session.headers.update({"User-Agent": "eleicoes-2026/2 (+https://github.com/agamemnon140/eleicoes-2026)"})
    successes = 0
    for section, cargo in pp.PAGES.items():
        try:
            if cache_dir:
                filename = "plano.html" if section == "presidente" else section + ".html"
                data = pp.extract((pathlib.Path(cache_dir) / filename).read_text(encoding="utf-8-sig"))
                rows, updated = pp.parse_page(data, section), data["generated_at"]
            else:
                rows, updated = pp.fetch(session, section)
            old = {p["id"]: p for p in catalog["polls"] if p["cargo"] == cargo}
            for p in rows:
                old.pop(p["id"], None)
            # Retain disappeared records for audit, excluding withdrawn observations.
            archived = [{**p, "eligible": False, "withdrawn": True,
                         "issues": ["Não consta na versão atual da fonte"]} for p in old.values()]
            catalog["polls"] = [p for p in catalog["polls"] if p["cargo"] != cargo] + rows + archived
            catalog["sources"][section] = {"status": "ok", "checked_at": date_str,
                                          "updated_at": updated, "count": len(rows), "url": pp.ROOT_URL + section + "/"}
            successes += 1
            print(f"Plano Político / {section}: {len(rows)} cenários; {sum(not p['eligible'] for p in rows)} com inconsistências.")
        except (requests.RequestException, ValueError, KeyError, TypeError, OSError) as exc:
            previous = catalog["sources"].get(section, {})
            catalog["sources"][section] = {**previous, "status": "error", "checked_at": date_str, "error": str(exc)[:240]}
            print(f"Plano Político / {section}: falha; mantendo último catálogo válido ({exc}).")
    if not catalog["polls"]:
        raise RuntimeError("Nenhuma pesquisa disponível: snapshot anterior preservado")
    catalog.update(version=research.VERSION, checked_at=date_str)
    catalog["polls"].sort(key=lambda p: p["id"])
    after = {p["id"]: research.digest(p) for p in catalog["polls"]}
    if before != after or first_import:
        catalog["changes"] = {"date": date_str,
            "added": len(after) if first_import else len(after.keys() - before.keys()),
            "revised": sum(before[k] != after[k] for k in before.keys() & after.keys()),
            "methodology": research.VERSION if first_import else None,
            "note": "Importação de pesquisas históricas; crescimento da base não significa pesquisas divulgadas hoje." if first_import else "Novos registros e revisões da fonte, separados de mudanças de metodologia."}
    CATALOG.parent.mkdir(parents=True, exist_ok=True)
    CATALOG.write_text(json.dumps(catalog, ensure_ascii=False, indent=1), encoding="utf-8")
    roster = yaml.safe_load((ROOT / "reference" / "roster.yaml").read_text(encoding="utf-8"))
    snap = latest_snapshot()
    roster_sync.sync(snap["records"], roster)
    research.apply_catalog(snap["records"], catalog["polls"], as_of)
    recompute_derived(snap["records"])
    # The new comparable poll series has a different base than legacy snapshots.
    # Do not call a source/base transition a late campaign movement.
    for r in snap["records"]:
        if r.get("research_managed"):
            r["mom"] = 0.0
    pres = research.presidential(catalog["polls"], as_of)
    if pres["polls"]:
        snap["president"] = pres
    # Keep state observations in total-vote units expected by the existing lean.
    states = {}
    for p in catalog["polls"]:
        if p["cargo"] != "Presidente" or p["uf"] == "BR" or not research.available(p, as_of):
            continue
        from pipeline.president import _bloc
        shares = {_bloc(n): v for n, v in p["shares"].items() if _bloc(n) != "Indefinido" and isinstance(v, (int, float))}
        states.setdefault(p["uf"], []).append({"pollster": p["pollster"], "date": p["date"], "url": p["url"],
            "first_round": shares if p["scenario"] == "1º turno" else None,
            "runoff": shares if p["scenario"] == "2º turno" else None})
    snap["president_states"] = states or snap.get("president_states", {})
    snap.update(date=date_str, source="Plano Político (pesquisas individuais; fontes originais preservadas)",
                polls_date=max((p["field_end"] for p in catalog["polls"] if research.available(p, as_of)), default=snap.get("date")),
                research_version=research.VERSION, research_digest=research.digest(catalog["polls"]))
    old_path = ROOT / "data" / "polls" / f"{date_str}.json"
    old_path.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Catálogo salvo: {len(catalog['polls'])} cenários; {successes}/3 fontes consultadas.")
