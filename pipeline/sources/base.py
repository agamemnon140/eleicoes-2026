"""Tipos comuns das fontes de coleta."""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass


@dataclass
class PollRecord:
    uf: str
    cargo: str          # "Governo" | "Senado"
    name: str           # nome casado com o roster
    party: str
    pct: float
    pollster: str
    date: str
    source: str         # ex.: "wikipedia"


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def norm_party(p: str) -> str:
    p = strip_accents(p or "").upper().strip()
    return {
        "SD": "SOLIDARIEDADE",
        "UNIAO": "UNIAO", "UNIAO BRASIL": "UNIAO",
        "PROGRESSISTAS": "PP",
    }.get(p, p)


def match_candidate(name: str, party: str | None, roster_state: dict):
    """Casa (nome, partido) com um candidato do roster. -> (cand, cargo) ou None.
    Usado pelos adapters (Wikipedia, Gazeta) para atribuir o cargo e o nome canônico."""
    name_toks = [strip_accents(t).lower().strip(".") for t in name.split() if len(strip_accents(t)) > 2]
    if not name_toks:
        return None
    npu = norm_party(party) if party else None
    for office_key, cargo in (("governor", "Governo"), ("senate", "Senado")):
        for c in roster_state.get(office_key, {}).get("candidates", []):
            if npu and norm_party(c["party"]) != npu:
                continue
            cname = strip_accents(c["name"]).lower()
            if any(t in cname for t in name_toks):
                return c, cargo
    return None
