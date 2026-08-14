"""Testes offline do coletor: parser da Wikipedia (fixture) + trava de recência."""
import pathlib

import yaml

from pipeline import collect
from pipeline.sources import base
from pipeline.sources import wikipedia as wk

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = pathlib.Path(__file__).parent / "fixtures" / "wiki_sp.html"
ROSTER = yaml.safe_load((ROOT / "reference" / "roster.yaml").read_text(encoding="utf-8"))


def test_parse_sp_from_fixture():
    recs = wk.parse_state(FIX.read_text(encoding="utf-8"), "SP", ROSTER["states"]["SP"])
    gov = {r.name: r.pct for r in recs if r.cargo == "Governo" and r.scenario == base.FIRST_ROUND}
    assert gov["Tarcísio de Freitas"] == 52.9          # Vox Brasil, 29–31 Jul (mais recente)
    assert gov["Fernando Haddad"] == 34.3
    sen = {r.name for r in recs if r.cargo == "Senado"}
    assert "Guilherme Derrite" in sen and "Marina Silva" in sen
    # classificação correta: os nomes de governo não vazam para o senado e vice-versa
    assert "Tarcísio de Freitas" not in sen


def test_segundo_turno_nao_entra_na_media_do_primeiro():
    """A página da SP tabula 1º e 2º turno; misturar os dois inflaria o líder."""
    recs = wk.parse_state(FIX.read_text(encoding="utf-8"), "SP", ROSTER["states"]["SP"])
    ro = [r for r in recs if r.cargo == "Governo" and r.scenario == base.RUNOFF]
    assert ro, "a fixture tem tabela de 2º turno — ela precisa ser reconhecida"
    tarcisio = {r.scenario: r.pct for r in recs if r.name == "Tarcísio de Freitas"}
    assert tarcisio[base.FIRST_ROUND] != tarcisio[base.RUNOFF]


def test_pct_valid_normaliza_base():
    """45% de totais com 10% de indeciso vira 50% de válidos."""
    r = base.PollRecord("SP", "Governo", "X", "PT", 45.0, "Inst", "01/08/2026", "teste",
                        base=base.BASE_TOTAL, sum_cands=90.0, undecided=10.0)
    assert r.pct_valid == 50.0
    # quem já publica em válidos passa direto
    v = base.PollRecord("SP", "Governo", "X", "PT", 45.0, "Inst", "01/08/2026", "teste",
                        base=base.BASE_VALID, sum_cands=100.0, undecided=0.0)
    assert v.pct_valid == 45.0


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
