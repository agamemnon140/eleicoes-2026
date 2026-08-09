"""Testes offline do coletor: parser da Wikipedia (fixture) + trava de recência."""
import pathlib

import yaml

from pipeline import collect
from pipeline.sources import wikipedia as wk

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = pathlib.Path(__file__).parent / "fixtures" / "wiki_sp.html"
ROSTER = yaml.safe_load((ROOT / "reference" / "roster.yaml").read_text(encoding="utf-8"))


def test_parse_sp_from_fixture():
    recs = wk.parse_state(FIX.read_text(encoding="utf-8"), "SP", ROSTER["states"]["SP"])
    gov = {r.name: r.pct for r in recs if r.cargo == "Governo"}
    assert gov["Tarcísio de Freitas"] == 52.9          # Vox Brasil, 29–31 Jul (mais recente)
    assert gov["Fernando Haddad"] == 34.3
    sen = {r.name for r in recs if r.cargo == "Senado"}
    assert "Guilherme Derrite" in sen and "Marina Silva" in sen
    # classificação correta: os nomes de governo não vazam para o senado e vice-versa
    assert "Tarcísio de Freitas" not in sen


def test_parse_recency():
    pr = collect.parse_recency
    assert pr("publicado 03/08/2026") == (2026, 8, 3)
    assert pr("29–31 Jul") == (2026, 7, 31)          # sem ano -> assume 2026
    assert pr("13-17 Aug 2025") == (2025, 8, 17)
    assert pr("18–23/07/2026") == (2026, 7, 23)
    assert pr("1-3 Jul 2026") == (2026, 7, 3)
    assert pr("29–31 Jul") > pr("13-17 Apr")          # Julho é mais recente que Abril
    assert pr("") == (0, 0, 0)


def test_recency_gate_blocks_older():
    # base mais nova (Julho) não deve ser rebaixada por coleta mais antiga (Abril)
    base = collect.parse_recency("23–27/07/2026")
    older = collect.parse_recency("23–27 Apr")
    assert older < base
