"""O roster manda: candidatura que entra, sai, troca de cargo ou está duplicada."""
import pathlib

import pytest
import yaml

from pipeline import roster_sync as rs

ROOT = pathlib.Path(__file__).resolve().parents[2]


def rec(uf, cargo, name, **kw):
    base = {"uf": uf, "cargo": cargo, "name": name, "party": "X", "bloc": "Indefinido",
            "endorsement": "não verificado", "apoio": "Não verificado",
            "apoio_verificado": False, "active": True, "pct": None, "gov_ticket": None}
    base.update(kw)
    return base


def roster(gov=(), sen=()):
    return {"states": {"AL": {"estado": "Alagoas",
                              "governor": {"candidates": list(gov)},
                              "senate": {"seats": 2, "candidates": list(sen)}}}}


def test_candidato_fora_do_roster_fica_inativo():
    records = [rec("AL", "Governo", "Fulano", pct=30.0)]
    rs.sync(records, roster(gov=[]))
    assert records[0]["active"] is False
    assert records[0]["status"] == rs.OUT_STATUS
    assert records[0]["pct"] == 30.0, "histórico de pesquisa não pode sumir"


def test_candidato_novo_do_roster_entra_sem_pesquisa():
    records = []
    rep = rs.sync(records, roster(sen=[{"name": "JHC", "party": "PSDB", "bloc": "Indefinido"}]))
    assert len(records) == 1 and records[0]["cargo"] == "Senado"
    assert records[0]["pct"] is None and records[0]["active"] is True
    assert rep["added"]


def test_troca_de_cargo_e_relatada_e_limpa_a_chapa():
    records = [rec("AL", "Governo", "JHC", pct=45.9),
               rec("AL", "Senado", "Maria", gov_ticket="JHC", gov_pct=45.9)]
    rep = rs.sync(records, roster(sen=[{"name": "JHC", "party": "PSDB"},
                                       {"name": "Maria", "party": "PSDB"}]))
    assert any("JHC" in m for m in rep["moved_office"])
    maria = next(r for r in records if r["name"] == "Maria")
    assert maria["gov_ticket"] is None and maria["gov_pct"] is None


def test_roster_sobrescreve_partido_e_apoio():
    records = [rec("AL", "Senado", "Lira", party="PP", endorsement="não verificado")]
    rs.sync(records, roster(sen=[{"name": "Lira", "party": "PP", "bloc": "Flávio",
                                  "endorsement": "explícito", "apoio_verificado": True}]))
    assert records[0]["endorsement"] == "explícito"
    assert records[0]["bloc"] == "Flávio"


def test_duplicata_por_acento_e_fundida_mantendo_a_com_pesquisa():
    records = [rec("BA", "Senado", "Angelo Coronel", pct=18.0),
               rec("BA", "Senado", "Ângelo Coronel", pct=None)]
    rep = {}
    kept = rs.dedupe(records, rep)
    assert len(kept) == 1 and kept[0]["pct"] == 18.0
    assert rep["deduped"]


def test_roster_com_nome_duplicado_para_o_pipeline():
    with pytest.raises(SystemExit):
        rs.roster_index(roster(sen=[{"name": "Angelo Coronel"}, {"name": "Ângelo Coronel"}]))


def test_roster_de_producao_nao_tem_duplicatas():
    r = yaml.safe_load((ROOT / "reference" / "roster.yaml").read_text(encoding="utf-8"))
    idx = rs.roster_index(r)          # levanta SystemExit se houver duplicata
    assert len(idx) > 200


def test_producao_sincronizada_com_o_snapshot():
    """O snapshot publicado tem que refletir o roster — senão o site mostra candidatura velha."""
    from pipeline import collect
    r = yaml.safe_load((ROOT / "reference" / "roster.yaml").read_text(encoding="utf-8"))
    snap = collect.latest_snapshot()
    before = collect.fingerprint(snap["records"], snap.get("president"))
    rs.sync(snap["records"], r)
    assert collect.fingerprint(snap["records"], snap.get("president")) == before, \
        "rode `py -m pipeline.roster_sync` para aplicar as mudanças do roster"
