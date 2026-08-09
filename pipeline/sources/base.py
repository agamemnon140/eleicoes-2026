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
