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


def test_pct_tolera_separador_orfao():
    # regressão: "Fernando Haddad (PT):,27%" (typo da Gazeta na Datafolha SP de 21/08)
    # virava 0,27% — e os 45% do Tarcísio viravam 77% dos válidos
    assert gz._pct(",27") == 27.0
    assert gz._pct("48,9") == 48.9
    assert gz._pct("27") == 27.0
    assert gz._pct("27.") == 27.0


def test_typo_da_fonte_nao_derruba_candidato():
    html = """
    <p>Tarcísio lidera intenções de voto na simulação de primeiro turno</p>
    <ul>
     <li class="postListItem">Tarcísio de Freitas (Republicanos): 45%</li>
     <li class="postListItem">Fernando Haddad (PT):,27%</li>
     <li class="postListItem">Em branco/nulo/nenhum: 11%</li>
    </ul>"""
    recs = gz.parse_html("SP", ROSTER["states"]["SP"], html,
                         ".../datafolha-governador-sao-paulo-agosto-2026/")
    por_nome = {r.name: r for r in recs}
    assert por_nome["Fernando Haddad"].pct == 27.0
    # com o Haddad no denominador certo, os válidos do líder voltam ao chão
    assert por_nome["Tarcísio de Freitas"].pct_valid == round(45 / 72 * 100, 2)


def test_senado_2_votos_por_pessoa_e_classificado():
    """Senado: soma ~200% = % de entrevistados que citam (2 votos); soma ~100% = normalizado.
    Sem separar, a média soma 30% de um formato com 15% do outro para o mesmo candidato."""
    assert base.votos_por_pessoa(142.1, 15.6) == 2      # Paraná Pesquisas SP 19/08
    assert base.votos_por_pessoa(53.0, 45.0) == 1       # Datafolha MG 21/08
    assert base.votos_por_pessoa(128.0, 22.2) == 2      # Paraná RJ: soma sozinha já passa de 100
    assert base.votos_por_pessoa(95.0, 0.0) == 1        # governador, sem branco listado
    sen = ROSTER["states"]["SP"]["senate"]["candidates"][:3]
    lis = "".join(f'<li class="postListItem">{c["name"]} ({c["party"]}): {p}%</li>'
                  for c, p in zip(sen, (61, 58, 40)))
    html = f"<p>Senado - estimulada</p><ul>{lis}<li class='postListItem'>Indecisos: 20%</li></ul>"
    recs = gz.parse_html("SP", ROSTER["states"]["SP"], html, ".../x-senador-sao-paulo-agosto-2026/")
    assert recs and all(r.votos == 2 for r in recs)
    # a fatia dos válidos independe do formato: 61 / (61+58+40)
    assert recs[0].pct_valid == round(61 / 159 * 100, 2)


def test_match_candidate_por_partido_e_nome():
    rs = ROSTER["states"]["CE"]
    hit = base.match_candidate("Ciro Gomes", "PSDB", rs)
    assert hit and hit[0]["name"] == "Ciro Gomes" and hit[1] == "Governo"
    # partido errado não casa
    assert base.match_candidate("Ciro Gomes", "PT", rs) is None
