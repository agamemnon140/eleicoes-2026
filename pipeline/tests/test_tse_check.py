"""Diff roster x TSE — sem rede: alimenta o diff com candidaturas sintéticas."""
from pipeline import tse_check as tc


def roster():
    return {"states": {"AL": {
        "estado": "Alagoas",
        "governor": {"candidates": [
            {"name": "Renan Filho", "party": "MDB", "active": True},
            {"name": "JHC", "party": "PSDB", "active": False},   # saiu: não deve cobrar registro
        ]},
        "senate": {"seats": 2, "candidates": [
            {"name": "Arthur Lira", "party": "PP", "active": True},
        ]}}}}


def cand(uf, cargo, urna, nome, partido):
    return {"uf": uf, "cargo": cargo, "urna": urna, "nome": nome,
            "partido": partido, "situacao": "APTO"}


KNOWN = {"mdb", "pp", "republicanos"}


def test_casa_nome_de_urna_com_nome_do_roster():
    cands = [cand("AL", "Governo", "RENAN FILHO", "RENAN CALHEIROS FILHO", "MDB"),
             cand("AL", "Senado", "ARTHUR LIRA", "ARTHUR CESAR PEREIRA DE LIRA", "PP")]
    d = tc.diff(cands, roster(), KNOWN, todos=True)
    assert d["novos"] == [] and d["ausentes"] == []


def test_registro_novo_aparece_como_divergencia():
    cands = [cand("AL", "Senado", "DAVI DAVINO FILHO", "DAVI DAVINO FILHO", "REPUBLICANOS"),
             cand("AL", "Governo", "RENAN FILHO", "RENAN CALHEIROS FILHO", "MDB"),
             cand("AL", "Senado", "ARTHUR LIRA", "ARTHUR C P DE LIRA", "PP")]
    d = tc.diff(cands, roster(), KNOWN, todos=True)
    assert [n["urna"] for n in d["novos"]] == ["DAVI DAVINO FILHO"]


def test_candidato_do_roster_sem_registro_e_cobrado():
    d = tc.diff([], roster(), KNOWN, todos=True)
    nomes = {a["name"] for a in d["ausentes"]}
    assert nomes == {"Renan Filho", "Arthur Lira"}, "inativo não deve ser cobrado"


def test_partido_fora_de_parties_yaml_so_aparece_com_todos():
    cands = [cand("AL", "Senado", "ALEXANDRE FLEMING", "ALEXANDRE FLEMING", "UP")]
    assert tc.diff(cands, roster(), KNOWN, todos=False)["novos"] == []
    assert len(tc.diff(cands, roster(), KNOWN, todos=True)["novos"]) == 1


def test_particulas_nao_casam_sozinhas():
    # "Filho"/"Junior" não podem casar dois candidatos diferentes
    assert not (tc.toks("Renan Filho") & tc.toks("Davi Davino Filho"))
