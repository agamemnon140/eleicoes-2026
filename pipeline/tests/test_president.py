"""Teste offline do agregador presidencial (fixture Genial/Quaest)."""
import pathlib

from pipeline import president as pr

FIX = pathlib.Path(__file__).parent / "fixtures" / "gazeta_pres.html"
URL = "https://www.gazetadopovo.com.br/eleicoes/2026/pesquisa-eleitoral-2026/genial-quaest-presidente-agosto-2026/"


def test_parse_presidencial():
    p = pr.parse_poll(FIX.read_text(encoding="utf-8"), URL)
    fr = {name: pct for name, _party, pct in p["first_round"]}
    # cenário estimulado 1º turno (não a espontânea, onde Lula tinha 25%)
    assert fr["Lula"] == 39.0 and fr["Flávio Bolsonaro"] == 30.0
    # 2º turno Lula x Flávio
    ro = {name: pct for name, _party, pct in p["runoff"]}
    assert ro["Lula"] == 44.0 and ro["Flávio Bolsonaro"] == 39.0
    assert p["pollster"].startswith("Genial")


def test_aggregate_filtra_ruido():
    p = pr.parse_poll(FIX.read_text(encoding="utf-8"), URL)
    agg = pr.aggregate([p, p, p])   # 3 cópias -> n=3 para todos
    names = [c["name"] for c in agg["first_round"]]
    assert names[0] == "Lula" and "Flávio Bolsonaro" in names
    assert agg["runoff"]["Lula"] == 44.0
    # bloco atribuído por nome
    assert agg["first_round"][0]["bloc"] == "Lula"
