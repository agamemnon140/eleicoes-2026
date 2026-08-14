"""Teste offline do coletor da Gazeta do Povo (fixture Ceará)."""
import pathlib

import yaml

from pipeline.sources import base, gazeta as gz

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = pathlib.Path(__file__).parent / "fixtures" / "gazeta_ce.html"
ROSTER = yaml.safe_load((ROOT / "reference" / "roster.yaml").read_text(encoding="utf-8"))
URL = "https://www.gazetadopovo.com.br/eleicoes/2026/pesquisa-eleitoral-2026/genial-quaest-governador-senado-ceara-julho-2026/"


def _fr(recs, cargo):
    return {r.name: r.pct for r in recs if r.cargo == cargo and r.scenario == base.FIRST_ROUND}


def test_parse_ce_pega_estimulada_nao_espontanea():
    recs = gz.parse_html("CE", ROSTER["states"]["CE"], FIX.read_text(encoding="utf-8"), URL)
    gov = _fr(recs, "Governo")
    # a página tem espontânea (Ciro 15%) ANTES da estimulada (Ciro 43%) — deve pegar a estimulada
    assert gov["Ciro Gomes"] == 43.0
    assert gov["Elmano de Freitas"] == 33.0
    sen = _fr(recs, "Senado")
    assert sen["Cid Gomes"] == 23.0 and "Capitão Wagner" in sen
    # data vinda do meta article:published_time
    assert all(r.date for r in recs)


def test_instituto_e_o_da_pesquisa_nao_o_do_portal():
    """A Gazeta é veículo; creditar tudo a ela fundiria Quaest e Datafolha na mesma série."""
    assert gz.pollster_from(URL) == "Quaest"
    assert gz.pollster_from(".../datafolha-governador-ceara-agosto-2026/") == "Datafolha"
    assert gz.pollster_from(".../parana-pesquisas-governador-senador-alagoas-julho-2026/") \
        == "Paraná Pesquisas"
    assert gz.pollster_from(".../eal-time-big-data-governador-acre-julho-2026/") \
        == "Real Time Big Data"          # slug com typo do próprio portal
    assert gz.pollster_from(".../materia-qualquer-sem-instituto/") == "instituto não identificado"


def test_separa_turno_e_calcula_base():
    recs = gz.parse_html("CE", ROSTER["states"]["CE"], FIX.read_text(encoding="utf-8"), URL)
    ciro = {r.scenario: r for r in recs if r.name == "Ciro Gomes"}
    assert base.RUNOFF in ciro, "a simulação de 2º turno tem que ser reconhecida"
    r1 = ciro[base.FIRST_ROUND]
    assert r1.base == base.BASE_TOTAL and r1.sum_cands and r1.sum_cands < 100
    assert r1.pct_valid > r1.pct, "em base de totais, o % dos válidos é maior"


def test_match_candidate_por_partido_e_nome():
    rs = ROSTER["states"]["CE"]
    hit = base.match_candidate("Ciro Gomes", "PSDB", rs)
    assert hit and hit[0]["name"] == "Ciro Gomes" and hit[1] == "Governo"
    # partido errado não casa
    assert base.match_candidate("Ciro Gomes", "PT", rs) is None
