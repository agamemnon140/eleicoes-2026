"""Testes do modelo de índice.

Inclui casos-ouro derivados manualmente do preview e, se presente,
carrega o conjunto completo de fixtures extraído do preview (test de regressão).
"""
import json
import pathlib

import pytest

from pipeline import model

FIXTURES = pathlib.Path(__file__).parent / "fixtures_preview.json"

NORMAL_W = {"governo": 0.35, "presidente": 0.30, "senado": 0.25, "apoio": 0.10}
LATE_W = {"governo": 0.40, "presidente": 0.35, "senado": 0.15, "apoio": 0.10}


def test_s_poll_saturates_and_applies_reliability():
    assert model.s_poll(60, 1.0) == 100.0          # 60% satura em 100
    assert model.s_poll(120, 1.0) == 100.0          # acima de 60% também satura
    assert model.s_poll(70.3, 0.65) == 65.0         # proxy 2022 -> teto 0,65*100
    assert model.s_poll(None, 1.0) == 0.0


def test_apoio_levels():
    assert model.s_apoio("explícito") == 100.0
    assert model.s_apoio("chapa/aliança") == 90.0
    assert model.s_apoio("inferido") == 45.0
    assert model.s_apoio("não verificado") == 0.0


def test_golden_marcio_bittar_ac():
    r = model.score_senate(
        gov_pct=35.2, gov_reliability=0.78,
        pres_pct=70.3, pres_reliability=0.65,
        sen_norm=100.0, endorsement="explícito", weights=NORMAL_W,
    )
    assert r["components"] == {"governo": 16.0, "presidente": 19.5, "senado": 25.0, "apoio": 10.0}
    assert r["score"] == 70.5


def test_golden_cid_gomes_ce_late_switch():
    r = model.score_senate(
        gov_pct=33, gov_reliability=1.0,
        pres_pct=55, pres_reliability=1.0,
        sen_norm=100.0, endorsement="chapa/aliança", weights=LATE_W,
    )
    assert r["components"] == {"governo": 22.0, "presidente": 32.1, "senado": 15.0, "apoio": 9.0}
    assert r["score"] == 78.1


def test_golden_eduardo_braga_am_proxy():
    r = model.score_senate(
        gov_pct=27, gov_reliability=0.78,
        pres_pct=51.1, pres_reliability=0.65,
        sen_norm=100.0, endorsement="inferido", weights=NORMAL_W,
    )
    assert r["components"] == {"governo": 12.3, "presidente": 16.6, "senado": 25.0, "apoio": 4.5}
    assert r["score"] == 58.4


@pytest.mark.skipif(not FIXTURES.exists(), reason="fixtures_preview.json ainda não extraído")
def test_reproduces_all_preview_senate_records():
    records = json.loads(FIXTURES.read_text(encoding="utf-8"))
    checked = 0
    for rec in records:
        if not rec.get("modelWeights") or rec.get("modelScore") is None:
            continue
        if not rec.get("modelComponents"):
            continue
        r = model.score_senate(
            gov_pct=rec["modelGovPct"], gov_reliability=rec["modelGovReliability"],
            pres_pct=rec["modelPresPct"], pres_reliability=rec["modelPresReliability"],
            sen_norm=rec["modelSenNorm"], endorsement=rec["modelEndorsement"],
            weights=rec["modelWeights"],
        )
        assert r["score"] == pytest.approx(rec["modelScore"], abs=0.15), rec.get("candidato")
        for k, v in rec["modelComponents"].items():
            assert r["components"][k] == pytest.approx(v, abs=0.15), (rec.get("candidato"), k)
        checked += 1
    assert checked >= 80, f"esperava dezenas de registros, validei {checked}"
