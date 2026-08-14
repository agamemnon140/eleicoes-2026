"""Reconcilia o snapshot de pesquisas com o roster — quem está de fato na disputa.

`reference/roster.yaml` é a FONTE ÚNICA de candidaturas: quem concorre, a qual cargo,
por qual partido, em qual bloco. Os snapshots em `data/polls/` guardam só o que foi
COLETADO (percentuais, instituto, campo). Antes de aplicar pesquisas frescas, este
módulo faz o snapshot obedecer ao roster:

  * candidato no roster e não no snapshot  -> registro novo (sem pesquisa ainda)
  * candidato no snapshot e não no roster  -> `active: false` (some da estimativa,
                                              mas o histórico de pesquisas fica)
  * em ambos                               -> partido/bloco/apoio/active vêm do roster
  * troca de cargo (governo -> senado)     -> cai dos dois lados acima, sem caso especial

Assim, atualizar uma candidatura às vésperas do prazo do TSE é editar UM arquivo YAML.

Uso:
  py -m pipeline.roster_sync            # aplica ao último snapshot e grava o de hoje
  py -m pipeline.roster_sync --dry-run  # só relata o que mudaria
"""
from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import unicodedata

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]

# roster.states[UF].<chave> -> cargo usado nos registros
OFFICES = {"governor": "Governo", "senate": "Senado"}

# campos que o roster manda (identidade e situação da candidatura)
ROSTER_FIELDS = ("party", "bloc", "endorsement", "apoio", "apoio_verificado", "active")
# campos opcionais: só sobrescrevem quando presentes no YAML
ROSTER_OPTIONAL = ("gov_ticket", "status", "status_tipo", "situacao")

OUT_STATUS = "Fora do roster: candidatura não confirmada"


def norm(name: str) -> str:
    """Chave de comparação de nomes: sem acento, sem caixa, sem espaço extra."""
    s = unicodedata.normalize("NFKD", str(name or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).casefold().strip()


def key(uf: str, cargo: str, name: str) -> tuple:
    return (uf, cargo, norm(name))


def roster_index(roster: dict) -> dict:
    """{(uf, cargo, nome_normalizado): spec} a partir de reference/roster.yaml.

    Nomes duplicados (típico de edição manual na véspera: "Angelo"/"Ângelo") param o
    pipeline — senão a última entrada vence em silêncio e pode reverter um dado bom.
    """
    idx, dupes = {}, []
    for uf, st in (roster.get("states") or {}).items():
        for office, cargo in OFFICES.items():
            for c in ((st.get(office) or {}).get("candidates") or []):
                k = key(uf, cargo, c["name"])
                if k in idx:
                    dupes.append(f"{uf} {cargo}: {idx[k]['name']!r} == {c['name']!r}")
                idx[k] = {**c, "uf": uf, "cargo": cargo}
    if dupes:
        raise SystemExit("roster.yaml tem candidatos duplicados:\n  " + "\n  ".join(dupes))
    return idx


def new_record(spec: dict) -> dict:
    """Registro zerado para uma candidatura que ainda não tem pesquisa coletada."""
    r = {
        "uf": spec["uf"], "cargo": spec["cargo"], "name": spec["name"],
        "party": spec.get("party"), "bloc": spec.get("bloc", "Indefinido"),
        "endorsement": spec.get("endorsement", "não verificado"),
        "apoio": spec.get("apoio", "Não verificado"),
        "apoio_verificado": bool(spec.get("apoio_verificado", False)),
        "pct": None, "pctDisplay": "N/D", "sen_norm": 0.0,
        "gov_ticket": spec.get("gov_ticket"), "gov_pct": None,
        "gov_reliability": 0.78, "pres_pct": None, "pres_reliability": 0.65,
        "pres_basis": None, "may_change": None,
        "instituto": "N/D", "campo": "N/D", "cenario": None, "indecisao": None,
        "situacao": "Sem percentual comparável", "fonte": "roster",
        "status": spec.get("status", "Candidatura do roster; sem pesquisa coletada"),
        "status_tipo": spec.get("status_tipo", "info"),
        "active": bool(spec.get("active", True)),
        "estimated_preview": False, "certainty_preview": None,
        "source": "roster", "stale": False, "mom": 0.0,
    }
    return r


def _info(r: dict) -> tuple:
    """Quanto de informação um registro carrega (para escolher entre duplicatas)."""
    return (r.get("pct") is not None, len(r.get("polls") or []), bool(r.get("active")))


def dedupe(records: list[dict], report: dict | None = None) -> list[dict]:
    """Funde registros do mesmo candidato ("Angelo"/"Ângelo") mantendo o mais informativo.

    Duplicata não é inofensiva: o fantasma sem pesquisa ainda pontua pelo apoio e pode
    entrar no top-2 do estado.
    """
    best: dict = {}
    for r in records:
        k = key(r["uf"], r["cargo"], r["name"])
        if k not in best or _info(r) > _info(best[k]):
            if k in best and report is not None:
                report.setdefault("deduped", []).append(f"{r['uf']} {r['cargo']}: {best[k]['name']!r}")
            best[k] = r
        elif report is not None:
            report.setdefault("deduped", []).append(f"{r['uf']} {r['cargo']}: {r['name']!r}")
    kept = list(best.values())
    return kept


def sync(records: list[dict], roster: dict) -> dict:
    """Aplica o roster aos registros (in place). Devolve um relatório do que mudou.

    `records` é modificado no lugar (inclusive removendo duplicatas), então continua
    válido para quem já segurava a lista.
    """
    idx = roster_index(roster)
    seen = set()
    left: set = set()    # (uf, nome) que saíram de algum cargo
    joined: dict = {}    # (uf, nome) -> cargo em que entraram
    report = {"added": [], "deactivated": [], "changed": [], "moved_office": []}

    records[:] = dedupe(records, report)

    for r in records:
        k = key(r["uf"], r["cargo"], r["name"])
        spec = idx.get(k)
        if spec is None:
            if r.get("active"):
                r["active"] = False
                r["status"] = OUT_STATUS
                r["status_tipo"] = "alerta"
                report["deactivated"].append(f"{r['uf']} {r['cargo']}: {r['name']}")
                left.add((r["uf"], norm(r["name"])))
            continue
        seen.add(k)
        diffs = []
        if r["name"] != spec["name"]:      # grafia canônica é a do roster
            diffs.append(f"name: {r['name']!r} -> {spec['name']!r}")
            r["name"] = spec["name"]
        for f in ROSTER_FIELDS:
            if f in spec and r.get(f) != spec[f]:
                diffs.append(f"{f}: {r.get(f)!r} -> {spec[f]!r}")
                r[f] = spec[f]
        for f in ROSTER_OPTIONAL:
            if f in spec and r.get(f) != spec[f]:
                diffs.append(f"{f}: {r.get(f)!r} -> {spec[f]!r}")
                r[f] = spec[f]
        if diffs:
            report["changed"].append(f"{r['uf']} {r['cargo']} {r['name']} — " + "; ".join(diffs))

    for k, spec in idx.items():
        if k in seen:
            continue
        records.append(new_record(spec))
        report["added"].append(f"{spec['uf']} {spec['cargo']}: {spec['name']} ({spec.get('party')})")
        joined[(spec["uf"], norm(spec["name"]))] = (spec["cargo"], spec["name"])

    # troca de cargo: mesmo nome saiu de um cargo e entrou no outro
    for (uf, n), (cargo, display) in joined.items():
        if (uf, n) in left:
            report["moved_office"].append(f"{uf}: {display} passou a disputar {cargo}")

    prune_tickets(records, report)
    return report


def prune_tickets(records: list[dict], report: dict | None = None) -> int:
    """Limpa `gov_ticket` que aponta para governador que saiu da disputa.

    Sem isso, um senador continuaria herdando o vento de chapa de um candidato a
    governador que nem está mais concorrendo.
    """
    live = {(r["uf"], norm(r["name"])) for r in records
            if r["cargo"] == "Governo" and r.get("active")}
    n = 0
    for r in records:
        t = r.get("gov_ticket")
        if r["cargo"] == "Senado" and t and (r["uf"], norm(t)) not in live:
            r["gov_ticket"] = None
            r["gov_pct"] = None
            n += 1
            if report is not None:
                report.setdefault("tickets_cleared", []).append(f"{r['uf']} {r['name']} (chapa de {t})")
    return n


def print_report(rep: dict) -> None:
    labels = (("+ novos", "added"), ("- desativados", "deactivated"), ("~ atualizados", "changed"),
              ("→ trocaram de cargo", "moved_office"), ("⚑ chapa limpa", "tickets_cleared"),
              ("= duplicatas fundidas", "deduped"))
    for label, k in labels:
        items = rep.get(k) or []
        if items:
            print(f"  {label}: {len(items)}")
            for it in items:
                print(f"      {it}")
    if not any(rep.get(k) for _, k in labels):
        print("  roster e snapshot já estavam sincronizados.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Sincroniza o snapshot com reference/roster.yaml")
    ap.add_argument("date", nargs="?", default=datetime.date.today().isoformat())
    ap.add_argument("--dry-run", action="store_true", help="só relata, não grava")
    args = ap.parse_args()

    from pipeline import collect  # import tardio: evita exigir `requests` no dry-run

    roster = yaml.safe_load((ROOT / "reference" / "roster.yaml").read_text(encoding="utf-8"))
    snap = collect.latest_snapshot()
    records = snap["records"]
    before = collect.fingerprint(records, snap.get("president"))

    print("Sincronizando snapshot com o roster…")
    print_report(sync(records, roster))

    if args.dry_run:
        print("(dry-run: nada gravado)")
        return
    if collect.fingerprint(records, snap.get("president")) == before:
        print("  nenhuma mudança de candidatura — nenhum snapshot novo.")
        return

    collect.recompute_derived(records)
    snap["date"] = args.date
    out = ROOT / "data" / "polls" / f"{args.date}.json"
    out.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  -> data/polls/{args.date}.json")


if __name__ == "__main__":
    main()
