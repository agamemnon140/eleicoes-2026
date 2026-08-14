"""Confere o roster contra os registros oficiais de candidatura do TSE.

Fonte: dados abertos do TSE (`consulta_cand_2026.zip`, ~3 MB), regerado todo dia. É a
única fonte autoritativa de quem de fato pediu registro — imprensa e Wikipedia atrasam
e divergem, ainda mais na semana do prazo (**15/08/2026, 19h**).

NÃO aplica nada: o roster é curado (só candidaturas competitivas entram no modelo, senão
o índice enche de nome com 0 pesquisa). Este módulo só RELATA divergências para revisão:

  A) registrado no TSE e fora do roster  -> candidatura nova, avaliar se é competitiva
  B) no roster e sem registro no TSE     -> antes do prazo é provável atraso;
                                            DEPOIS do prazo é candidatura que não existe

Uso:
  py -m pipeline.tse_check              # relatório no terminal
  py -m pipeline.tse_check --json out.json
  py -m pipeline.tse_check --todos      # inclui partidos fora de reference/parties.yaml
"""
from __future__ import annotations

import argparse
import csv
import datetime
import io
import json
import pathlib
import re
import unicodedata
import zipfile

import requests
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
URL = "https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_2026.zip"
UA = {"User-Agent": "eleicoes-2026-bot/0.1 (github.com/agamemnon140/eleicoes-2026)"}
PRAZO_REGISTRO = datetime.date(2026, 8, 15)
CARGOS = {"GOVERNADOR": "Governo", "SENADOR": "Senado"}

# partículas que não identificam ninguém sozinhas
STOP = {"jr", "junior", "filho", "neto", "sobrinho", "de", "da", "do", "dos", "das",
        "dr", "dra", "prof", "professor", "professora"}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).casefold().strip()


def toks(name: str) -> set:
    """Tokens identificadores de um nome (casa 'JHC' x 'Joao Henrique Caldas' não — de propósito:
    nome de urna e nome civil são comparados juntos pelo chamador)."""
    return {t for t in re.split(r"[^\w]+", norm(name)) if len(t) > 2 and t not in STOP}


def download(cache: pathlib.Path | None = None) -> bytes:
    if cache and cache.exists():
        return cache.read_bytes()
    r = requests.get(URL, headers=UA, timeout=180)
    r.raise_for_status()
    if cache:
        cache.write_bytes(r.content)
    return r.content


def parse(blob: bytes) -> tuple[list[dict], str]:
    """Candidaturas a governador/senador, deduplicadas por SQ_CANDIDATO."""
    z = zipfile.ZipFile(io.BytesIO(blob))
    seen, out, gerado = set(), [], ""
    for n in z.namelist():
        if not n.lower().endswith(".csv"):
            continue
        for r in csv.DictReader(io.StringIO(z.read(n).decode("latin-1")), delimiter=";"):
            gerado = gerado or f"{r.get('DT_GERACAO')} {r.get('HH_GERACAO')}"
            cargo = CARGOS.get((r.get("DS_CARGO") or "").upper())
            sq = r.get("SQ_CANDIDATO")
            if not cargo or sq in seen:
                continue
            seen.add(sq)
            out.append({"uf": r.get("SG_UF"), "cargo": cargo,
                        "urna": r.get("NM_URNA_CANDIDATO"), "nome": r.get("NM_CANDIDATO"),
                        "partido": r.get("SG_PARTIDO"),
                        "situacao": r.get("DS_SITUACAO_CANDIDATURA")})
    return out, gerado


def diff(cands: list[dict], roster: dict, known_parties: set, todos: bool) -> dict:
    by_key: dict = {}
    for c in cands:
        by_key.setdefault((c["uf"], c["cargo"]), []).append(c)

    novos, ausentes = [], []
    for uf in sorted(roster["states"]):
        st = roster["states"][uf]
        for office, cargo in (("governor", "Governo"), ("senate", "Senado")):
            ros = [c for c in (st.get(office) or {}).get("candidates", [])
                   if c.get("active", True)]
            tse = by_key.get((uf, cargo), [])
            for t in tse:
                tt = toks(t["urna"]) | toks(t["nome"])
                if any(tt & toks(c["name"]) for c in ros):
                    continue
                conhecido = norm(t["partido"]) in known_parties
                if conhecido or todos:
                    novos.append({**t, "partido_conhecido": conhecido})
            for c in ros:
                ct = toks(c["name"])
                if not any(ct & (toks(t["urna"]) | toks(t["nome"])) for t in tse):
                    ausentes.append({"uf": uf, "cargo": cargo, "name": c["name"],
                                     "partido": c.get("party")})
    return {"novos": novos, "ausentes": ausentes,
            "cobertura": {f"{uf}/{cargo}": len(v) for (uf, cargo), v in sorted(by_key.items())}}


def main() -> None:
    ap = argparse.ArgumentParser(description="Confere o roster contra o registro do TSE")
    ap.add_argument("--json", dest="out", help="grava o relatório em JSON")
    ap.add_argument("--todos", action="store_true",
                    help="inclui candidaturas de partidos fora de reference/parties.yaml")
    ap.add_argument("--cache", help="arquivo para cachear o zip do TSE")
    args = ap.parse_args()

    roster = yaml.safe_load((ROOT / "reference" / "roster.yaml").read_text(encoding="utf-8"))
    parties = yaml.safe_load((ROOT / "reference" / "parties.yaml").read_text(encoding="utf-8"))
    known = {norm(p) for p in (parties.get("parties") or {})} | \
            {norm(p) for p in (parties.get("party_field") or {})}

    blob = download(pathlib.Path(args.cache) if args.cache else None)
    cands, gerado = parse(blob)
    rep = diff(cands, roster, known, args.todos)
    rep["gerado_tse"] = gerado
    rep["total_tse"] = len(cands)

    hoje = datetime.date.today()
    faltam = (PRAZO_REGISTRO - hoje).days
    print(f"TSE gerado em {gerado} — {len(cands)} candidaturas majoritárias registradas.")
    print(f"Prazo de registro: 15/08/2026 19h ({'faltam %d dia(s)' % faltam if faltam >= 0 else 'ENCERRADO'}).")

    print(f"\nA) registrado no TSE e FORA do roster ({len(rep['novos'])})"
          + ("" if args.todos else " — só partidos conhecidos; use --todos para ver o resto"))
    for t in rep["novos"]:
        print(f"   {t['uf']} {t['cargo']:8s} {t['urna']:34s} {t['partido']}")

    print(f"\nB) no roster e SEM registro no TSE ({len(rep['ausentes'])})")
    if faltam >= 0:
        print("   (antes do prazo isto é, quase sempre, registro ainda não protocolado)")
    for a in rep["ausentes"]:
        print(f"   {a['uf']} {a['cargo']:8s} {a['name']:34s} {a['partido']}")

    if args.out:
        pathlib.Path(args.out).write_text(json.dumps(rep, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
        print(f"\n-> {args.out}")


if __name__ == "__main__":
    main()
