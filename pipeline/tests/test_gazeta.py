"""Teste offline do coletor da Gazeta do Povo (fixture Ceará)."""
import pathlib

import yaml

from pipeline.sources import base, gazeta as gz

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIX = pathlib.Path(__file__).parent / "fixtures" / "gazeta_ce.html"
ROSTER = yaml.safe_load((ROOT / "reference" / "roster.yaml").read_text(encoding="utf-8"))
URL = "https://www.gazetadopovo.com.br/eleicoes/2026/pesquisa-eleitoral-2026/genial-quaest-governador-senado-ceara-julho-2026/"


def test_parse_ce_pega_estimulada_nao_espontanea():
    recs = gz.parse_html("CE", ROSTER["states"]["CE"], FIX.read_text(encoding="utf-8"), URL)
    gov = {r.name: r.pct for r in recs if r.cargo == "Governo"}
    # a página tem espontânea (Ciro 15%) ANTES da estimulada (Ciro 43%) — deve pegar a estimulada
    assert gov["Ciro Gomes"] == 43.0
    assert gov["Elmano de Freitas"] == 33.0
    sen = {r.name: r.pct for r in recs if r.cargo == "Senado"}
    assert sen["Cid Gomes"] == 23.0 and "Capitão Wagner" in sen
    # data vinda do meta article:published_time
    assert all(r.date for r in recs)


def test_match_candidate_por_partido_e_nome():
    rs = ROSTER["states"]["CE"]
    hit = base.match_candidate("Ciro Gomes", "PSDB", rs)
    assert hit and hit[0]["name"] == "Ciro Gomes" and hit[1] == "Governo"
    # partido errado não casa
    assert base.match_candidate("Ciro Gomes", "PT", rs) is None
