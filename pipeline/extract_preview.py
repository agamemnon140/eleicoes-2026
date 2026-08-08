"""Extrai DATA e S do preview.html e gera os artefatos de bootstrap.

Saídas:
  pipeline/tests/fixtures_preview.json  registros do Senado (teste de regressão do modelo)
  reference/roster.yaml                 camada editorial: candidatos·partido·bloco·apoio,
                                        holdovers, totais nacionais, lean presidencial, certezas
  data/polls/<data>.json                snapshot de pesquisas (entradas do modelo por candidato)

Uso:
  py pipeline/extract_preview.py [caminho/para/source_preview.html] [YYYY-MM-DD]
Padrão do caminho: reference/source_preview.html
"""
from __future__ import annotations

import datetime
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_preview(path: pathlib.Path):
    html = path.read_text(encoding="utf-8")
    m = re.search(r"const\s+DATA\s*=\s*(\[.*?\])\s*,\s*S\s*=\s*(\{.*?\})\s*;\s*let\s+cargo",
                  html, re.DOTALL)
    if not m:
        raise SystemExit("Não encontrei 'const DATA=[...],S={...}; let cargo' no HTML.")
    return json.loads(m.group(1)), json.loads(m.group(2))


def bloc_of(rec: dict) -> str:
    return rec.get("modelBloc") or rec.get("bloco") or "Indefinido"


def build_roster(data, S) -> dict:
    """Camada editorial (estável): quem concorre, partido, bloco, apoio, + referências."""
    states: dict = {}
    for r in data:
        uf = r["uf"]
        st = states.setdefault(uf, {"estado": r["estado"],
                                    "governor": {"candidates": []},
                                    "senate": {"seats": 2, "candidates": []}})
        cand = {
            "name": r["candidato"],
            "party": r["partido"],
            "bloc": bloc_of(r),
            "endorsement": r.get("modelEndorsement", "não verificado"),
            "apoio": r.get("apoio", ""),
            "apoio_verificado": bool(r.get("apoioVerificado")),
            "active": bool(r.get("ativo", True)),
        }
        key = "governor" if r["cargo"] == "Governo" else "senate"
        st[key]["candidates"].append(cand)

    return {
        "election_date": "2026-10-04",
        "generated_from": "preview snapshot",
        "holdovers": {row["party"]: row["holdNames"]
                      for row in S["nationalRows"] if row.get("holdNames")},
        "national_seed": [{"party": row["party"], "hold": row["hold"], "gov": row["gov"]}
                          for row in S["nationalRows"]],
        "pres_lean": S["pres"],
        "gov_confidence": S["govConf"],
        "sen_confidence": S["senConf"],
        "gov_estimate": S["govEst"],
        "sen_estimate": S["senEst"],
        "late_switch": S.get("lateSwitch", {}),
        "states": states,
    }


def build_polls_snapshot(data, date_str: str) -> dict:
    """Snapshot de pesquisas: entradas por candidato para o build.py recomputar."""
    records = []
    for r in data:
        records.append({
            "uf": r["uf"], "cargo": r["cargo"], "name": r["candidato"], "party": r["partido"],
            "bloc": bloc_of(r), "endorsement": r.get("modelEndorsement", "não verificado"),
            "apoio": r.get("apoio", ""), "apoio_verificado": bool(r.get("apoioVerificado")),
            "pct": r.get("pct"), "pctDisplay": r.get("pctDisplay"),
            "sen_norm": r.get("modelSenNorm"),
            "gov_ticket": r.get("modelGov"), "gov_pct": r.get("modelGovPct"),
            "gov_reliability": r.get("modelGovReliability"),
            "pres_pct": r.get("modelPresPct"), "pres_reliability": r.get("modelPresReliability"),
            "pres_basis": r.get("modelPresBasis"),
            "may_change": r.get("mudancaTardiaPct"),
            "instituto": r.get("instituto"), "campo": r.get("campo"), "cenario": r.get("cenario"),
            "indecisao": r.get("indecisao"), "situacao": r.get("situacao"),
            "fonte": r.get("fonte"), "status": r.get("status"), "status_tipo": r.get("statusTipo"),
            "active": bool(r.get("ativo", True)),
            "estimated_preview": bool(r.get("estimadoEleito")),
            "certainty_preview": r.get("estimativaCerteza", ""),
        })
    return {"date": date_str, "source": "preview snapshot", "records": records}


def dump_yaml(obj, path: pathlib.Path):
    import yaml  # PyYAML
    path.write_text(yaml.safe_dump(obj, allow_unicode=True, sort_keys=False, width=100),
                    encoding="utf-8")


def main():
    src = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reference" / "source_preview.html"
    date_str = sys.argv[2] if len(sys.argv) > 2 else datetime.date.today().isoformat()
    if not src.exists():
        raise SystemExit(f"Arquivo não encontrado: {src}\nSalve o preview.html ali e rode de novo.")

    data, S = load_preview(src)
    senate = [r for r in data if r["cargo"] == "Senado"]

    (ROOT / "pipeline" / "tests" / "fixtures_preview.json").write_text(
        json.dumps(senate, ensure_ascii=False, indent=1), encoding="utf-8")

    dump_yaml(build_roster(data, S), ROOT / "reference" / "roster.yaml")

    polls_dir = ROOT / "data" / "polls"
    polls_dir.mkdir(parents=True, exist_ok=True)
    (polls_dir / f"{date_str}.json").write_text(
        json.dumps(build_polls_snapshot(data, date_str), ensure_ascii=False, indent=1),
        encoding="utf-8")

    print(f"OK: {len(data)} registros ({len(senate)} ao Senado).")
    print(f"  -> pipeline/tests/fixtures_preview.json")
    print(f"  -> reference/roster.yaml")
    print(f"  -> data/polls/{date_str}.json")


if __name__ == "__main__":
    main()
