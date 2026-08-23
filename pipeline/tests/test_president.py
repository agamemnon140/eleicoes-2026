"""Teste offline do agregador presidencial (fixture Genial/Quaest)."""
import pathlib

import yaml

from pipeline import president as pr

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = pathlib.Path(__file__).parent / "fixtures" / "gazeta_pres.html"
FIX_ESTADOS = pathlib.Path(__file__).parent / "fixtures" / "gazeta_pres_estados.html"
URL = "https://www.gazetadopovo.com.br/eleicoes/2026/pesquisa-eleitoral-2026/genial-quaest-presidente-agosto-2026/"
URL_ESTADOS = "https://www.gazetadopovo.com.br/eleicoes/2026/pesquisa-eleitoral-2026/datafolha-presidente-agosto-26-sp-mg-rj-pe-df/"
ROSTER = yaml.safe_load((ROOT / "reference" / "roster.yaml").read_text(encoding="utf-8"))
ESTADOS = {uf: st["estado"] for uf, st in ROSTER["states"].items()}


def test_parse_presidencial():
    p = pr.parse_poll(FIX.read_text(encoding="utf-8"), URL)
    fr = {name: pct for name, _party, pct in p["first_round"]}
    # cenário estimulado 1º turno (não a espontânea, onde Lula tinha 25%)
    assert fr["Lula"] == 39.0 and fr["Flávio Bolsonaro"] == 30.0
    # 2º turno Lula x Flávio
    ro = {name: pct for name, _party, pct in p["runoff"]}
    assert ro["Lula"] == 44.0 and ro["Flávio Bolsonaro"] == 39.0
    # nome canônico: "genial-quaest" e "quaest" são o MESMO instituto e têm de virar
    # uma série só, aqui e nas estaduais
    assert p["pollster"] == "Quaest"


def test_materia_estadual_fica_fora_do_agregado_nacional():
    """Regressão: a Datafolha por estado de 22/08 entrou no poll-of-polls NACIONAL
    como se fosse pesquisa nacional — a lista de SP (Flávio 35 x Lula 34), com o
    maior peso do agregado por ser a mais recente."""
    assert pr.state_scoped(URL_ESTADOS, ESTADOS)
    assert not pr.state_scoped(URL, ESTADOS)
    assert not pr.state_scoped(".../datafolha-presidente-agosto-2026/", ESTADOS)
    # nome de estado por extenso no slug também denuncia
    assert pr.state_scoped(".../datafolha-presidente-sao-paulo-agosto-2026/", ESTADOS)


def test_parse_state_poll_separa_estados_e_cenarios():
    d = pr.parse_state_poll(FIX_ESTADOS.read_text(encoding="utf-8"), URL_ESTADOS, ESTADOS)
    assert set(d) == {"SP", "MG", "RJ", "PE", "DF"}
    # SP e MG têm estimulada + 2º turno; só os 4 blocos entram (Marçal/Renan ficam fora)
    assert d["SP"]["first_round"] == {"Lula": 34.0, "Flávio": 35.0, "Zema": 3.0, "Caiado": 3.0}
    assert d["SP"]["runoff"] == {"Lula": 42.0, "Flávio": 47.0}
    assert d["MG"]["first_round"]["Zema"] == 8.0
    # RJ/PE/DF só têm 2º turno — first_round tem de ficar vazio, não inventado
    assert d["RJ"]["first_round"] is None
    assert d["RJ"]["runoff"] == {"Lula": 40.0, "Flávio": 49.0}
    assert d["PE"]["runoff"] == {"Lula": 62.0, "Flávio": 29.0}
    assert d["DF"]["runoff"] == {"Lula": 39.0, "Flávio": 51.0}
    assert all(e["pollster"] == "Datafolha" and e["date"] for e in d.values())


def test_aggregate_filtra_ruido():
    p = pr.parse_poll(FIX.read_text(encoding="utf-8"), URL)
    agg = pr.aggregate([p, p, p])   # 3 cópias -> n=3 para todos
    names = [c["name"] for c in agg["first_round"]]
    assert names[0] == "Lula" and "Flávio Bolsonaro" in names
    assert agg["runoff"]["Lula"] == 44.0
    # bloco atribuído por nome
    assert agg["first_round"][0]["bloc"] == "Lula"
