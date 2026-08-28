"""Coleta pesquisas das fontes e mescla no snapshot mais recente.

Fluxo: parte do último snapshot (mantém entradas do modelo), sincroniza as candidaturas
com reference/roster.yaml (roster_sync), busca pesquisas frescas (Wikipedia/Gazeta),
aplica guardrails (validate), recomputa sen_norm por estado e propaga o pct do governador
para o tailwind do Senado. Escreve data/polls/<data>.json.

Roda TODO DIA: quando nada muda de verdade, não grava snapshot novo (ver `changed`),
para o histórico não virar 50 cópias idênticas.

Uso: py -m pipeline.collect [YYYY-MM-DD] [--force]
"""
from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import re
from collections import defaultdict

import requests
import yaml

from pipeline import president, roster_sync, validate
from pipeline.sources import base
from pipeline.sources import gazeta as gz
from pipeline.sources import wikipedia as wk

norm_name = roster_sync.norm    # comparação de nomes sem acento/caixa

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


from pipeline.model import MA_HALFLIFE_DAYS, MA_WINDOW_DAYS, fill_pct_valid   # noqa: E402  (parâmetros do modelo)


def _recency_weight(age_days: float) -> float:
    """Peso exponencial decrescente com a idade da pesquisa (mais recente pesa mais)."""
    return 0.5 ** (max(0.0, age_days) / MA_HALFLIFE_DAYS)


def collect_fresh(roster: dict) -> dict:
    """Wikipedia + Gazeta -> média móvel (poll-of-polls) por candidato E CENÁRIO.

    A chave inclui o cenário: 1º e 2º turno são perguntas diferentes e não podem cair na
    mesma média. E a média é feita sobre `pct_valid` (% dos válidos), não sobre o %
    publicado: institutos publicam em bases diferentes (uns sobre o total de entrevistados,
    com indeciso dentro; outros já sobre válidos) e somar as duas mistura escalas.
    """
    estados = {uf: st["estado"] for uf, st in roster["states"].items()}
    obs: dict = defaultdict(list)   # (uf,cargo,nome,cenário) -> lista de PollRecord

    def add(recs):
        for r in recs:
            obs[(r.uf, r.cargo, r.name, r.scenario)].append(r)

    # 1) Wikipedia (última linha por candidato)
    ws = requests.Session(); ws.headers.update(wk.UA)
    wiki_states = set()
    for uf in sorted(roster["states"]):
        recs = wk.collect_state(estados[uf], uf, roster["states"][uf], ws)
        add(recs)
        if recs:
            wiki_states.add(uf)
    print(f"  Wikipedia: {len(wiki_states)} estados")

    # 2) Gazeta (várias matérias por estado, paginando o índice)
    gsx = requests.Session(); gsx.headers.update(gz.UA)
    gz_states = set()
    for uf, urls in gz.discover(gsx, estados, per_uf=3).items():
        for url in urls:
            recs = gz.collect_url(uf, roster["states"][uf], url, gsx)
            add(recs)
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
        # % publicado em escala POR VOTO: pesquisa de Senado com 2 votos por pessoa (soma
        # ~200%) entra pela metade, para não somar 30% (2 votos) com 15% (normalizado) do
        # mesmo candidato. Os válidos já são comparáveis (fatia das menções válidas).
        avg = round(sum(w * r.pct / (r.votos or 1) for w, r in zip(weights, window)) / wsum, 1)
        # média dos válidos só entre as pesquisas em que deu para converter
        vw = [(w, r) for w, r in zip(weights, window) if r.pct_valid is not None]
        avg_valid = (round(sum(w * r.pct_valid for w, r in vw) / sum(w for w, _ in vw), 1)
                     if vw else None)
        label = f"média móvel de {len(window)} pesquisas" if len(window) > 1 else newest.pollster
        if len(window) > 1:
            n_avg += 1
        fresh[key] = {
            "pct": avg, "pct_valid": avg_valid, "date": newest.date, "pollster": label,
            "scenario": newest.scenario,
            "opponents": list(newest.opponents),
            "sources": [{"pollster": r.pollster, "date": r.date, "pct": r.pct,
                         "pct_valid": r.pct_valid, "base": r.base, "sum_cands": r.sum_cands,
                         "undecided": r.undecided, "scenario": r.scenario, "votos": r.votos,
                         "source": r.source, "url": r.url, "weight": round(w / wsum, 3)}
                        for w, r in zip(weights, window)],
        }

    covered = wiki_states | gz_states
    print(f"Cobertura total: {len(covered)}/27 estados; {n_avg} candidatos com média móvel (>1 pesquisa).")
    return fresh


def apply_fresh(records: list[dict], fresh: dict) -> tuple[int, int, int]:
    updated = flagged = skipped_old = 0
    for r in records:
        fr = fresh.get((r["uf"], r["cargo"], r["name"], base.FIRST_ROUND))
        if not r.get("active"):
            continue
        # cenários de 2º turno viram um mapa adversário -> % dos válidos
        r["runoff"] = {}
        for (uf, cargo, name, cen), f2 in fresh.items():
            if cen != base.RUNOFF or (uf, cargo, name) != (r["uf"], r["cargo"], r["name"]):
                continue
            rival = next((o for o in f2["opponents"] if norm_name(o) != norm_name(name)), None)
            if rival and f2["pct_valid"] is not None:
                r["runoff"][rival] = {"pct_valid": f2["pct_valid"], "pct": f2["pct"],
                                      "date": f2["date"], "polls": f2["sources"]}
        if not fr:
            continue
        base_rec = parse_recency(r.get("campo"))
        if base_rec > (0, 0, 0) and parse_recency(fr["date"]) < base_rec:
            skipped_old += 1          # coleta mais antiga que a atual — não rebaixa
            continue
        ok, reason = validate.check(r.get("pct"), fr["pct"])
        if ok:
            r["pct"] = fr["pct"]
            r["pct_valid"] = fr["pct_valid"]
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


from pipeline.model import model_pct   # noqa: E402  (qual base entra na conta é do modelo)


def recompute_derived(records: list[dict]) -> None:
    fill_pct_valid(records)
    # sen_norm por estado (líder = 100) — sobre a base comparável, não sobre o % publicado
    by_uf = defaultdict(list)
    for r in records:
        if r["cargo"] == "Senado" and r.get("active") and isinstance(model_pct(r), (int, float)):
            by_uf[r["uf"]].append(r)
    for rs in by_uf.values():
        leader = max((model_pct(x) for x in rs), default=0) or 1
        for x in rs:
            x["sen_norm"] = round(model_pct(x) / leader * 100, 6)
    # propaga o % do governador para o tailwind do Senado (chapa)
    gov_pct = {(r["uf"], r["name"]): model_pct(r) for r in records
               if r["cargo"] == "Governo" and isinstance(model_pct(r), (int, float))}
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


# campos que definem se um snapshot é DIFERENTE do anterior (o resto é derivado ou ruído)
MATERIAL_FIELDS = ("uf", "cargo", "name", "party", "bloc", "endorsement", "apoio",
                   "apoio_verificado", "active", "pct", "campo", "instituto",
                   "gov_ticket", "status", "stale")


def fingerprint(records: list[dict], pres: dict | None, pres_states: dict | None = None) -> str:
    """Assinatura do conteúdo coletado, insensível à ordem e aos campos derivados."""
    recs = sorted(({k: r.get(k) for k in MATERIAL_FIELDS} for r in records),
                  key=lambda d: (d["uf"], d["cargo"], str(d["name"])))
    return json.dumps({"records": recs, "president": pres, "president_states": pres_states},
                      ensure_ascii=False, sort_keys=True)


def merge_president_states(prev: dict | None, novas: list) -> dict:
    """Acumula leituras presidenciais por estado; (instituto, data) identifica cada uma.

    Coleta vazia não apaga o histórico (mesma regra do agregado nacional): a série
    acumulada é o que dá peso crescente às pesquisas estaduais no blend do build.
    """
    out = {uf: list(ps) for uf, ps in (prev or {}).items()}
    for e in novas:
        entry = {k: v for k, v in e.items() if k != "uf"}
        lst = out.setdefault(e["uf"], [])
        for i, old in enumerate(lst):
            if (old.get("pollster"), old.get("date")) == (entry["pollster"], entry["date"]):
                lst[i] = entry
                break
        else:
            lst.append(entry)
    return out


def main():
    ap = argparse.ArgumentParser(description="Coleta pesquisas e grava um snapshot")
    ap.add_argument("date", nargs="?", default=datetime.date.today().isoformat())
    ap.add_argument("--force", action="store_true",
                    help="grava o snapshot mesmo sem mudança material")
    args = ap.parse_args()
    date_str = args.date

    roster = yaml.safe_load((ROOT / "reference" / "roster.yaml").read_text(encoding="utf-8"))
    estados = {uf: st["estado"] for uf, st in roster["states"].items()}
    snap = latest_snapshot()
    records = snap["records"]
    before = fingerprint(records, snap.get("president"), snap.get("president_states"))

    print("Sincronizando candidaturas com o roster…")
    roster_sync.print_report(roster_sync.sync(records, roster))

    print("Coletando pesquisas (Wikipedia)…")
    fresh = collect_fresh(roster)
    updated, flagged, skipped_old = apply_fresh(records, fresh)
    recompute_derived(records)
    mom_n = compute_momentum(records, date_str)

    print("Agregando pesquisas presidenciais (poll-of-polls)…")
    psx = requests.Session(); psx.headers.update(gz.UA)
    pres_raw_new, pres_states_new = president.collect_all(psx, estados)
    # o agregado sai do HISTÓRICO mesclado, não só do que o índice mostrou hoje
    pres_polls = president.merge_polls(snap.get("president_polls"), pres_raw_new)
    pres_agg = president.aggregate(pres_polls)
    if pres_raw_new:
        print(f"  presidencial: {len(pres_raw_new)} lidas hoje, {len(pres_polls)} no histórico")
    if pres_agg:
        print(f"  presidencial: {pres_agg['polls']} pesquisas, "
              f"Lula {pres_agg['first_round'][0]['avg']}% x "
              f"{pres_agg['first_round'][1]['avg']}% {pres_agg['first_round'][1]['name']}")
    elif snap.get("president"):
        # numa rodada diária, uma falha do agregador não pode apagar o último bom
        pres_agg = snap["president"]
        print("  presidencial: coleta vazia — mantendo o agregado anterior.")
    pres_states = merge_president_states(snap.get("president_states"), pres_states_new)
    if pres_states_new:
        print(f"  presidencial por estado: {len(pres_states_new)} leituras "
              f"({', '.join(sorted({e['uf'] for e in pres_states_new}))})")

    print(f"OK: {updated} atualizadas, {skipped_old} ignoradas por serem mais antigas, "
          f"{flagged} descartadas pelos guardrails.")

    if fingerprint(records, pres_agg, pres_states) == before and not args.force:
        print("Nada mudou desde o último snapshot — nenhum arquivo novo (use --force para gravar).")
        return

    out = {"date": date_str, "source": "wikipedia + gazeta + base",
           "records": records, "president": pres_agg, "president_polls": pres_polls,
           "president_states": pres_states}
    (ROOT / "data" / "polls" / f"{date_str}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  -> data/polls/{date_str}.json")


if __name__ == "__main__":
    main()
