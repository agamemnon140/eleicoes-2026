"""Regression tests for source ingestion, comparability and panel-based trends."""
import datetime as dt
import json
from pathlib import Path

import pytest

from pipeline import research
from pipeline.sources import planopolitico as pp

TODAY = dt.date(2026, 9, 20)
FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "planopolitico.json").read_text(encoding="utf-8"))


def poll(house="A", day="2026-09-18", values=None, registro=None, uf="BR", turn="1º turno"):
    return pp.normalize({"registro": registro or f"{house}-{day}", "instituto": house,
        "dt_inicio": day, "dt_fim": day, "dt_divulgacao": day, "n": 2000,
        "shares": values or {"Lula": 40., "Flávio Bolsonaro": 40., "Outros": 10., "Indecisos": 10.}},
        uf, "Presidente", turn, pp.ROOT_URL)


def test_public_fixture_keeps_metadata_and_scope():
    html = '<script type="application/json" id="agg-data">' + json.dumps(FIXTURE) + '</script>'
    rows = pp.parse_page(pp.extract(html), "presidente")
    assert {r["uf"] for r in rows} >= {"BR", "PR"}
    p = next(r for r in rows if r["registro"] == "BR-04029/2026" and r["scenario"] == "1º turno")
    assert p["sample_size"] == 2002
    assert p["field_start"] == "2026-09-15" and p["field_end"] == "2026-09-17"
    assert p["method"] == "Presencial" and p["url"].startswith("https://")
    assert p["valid_shares"]["Lula"] == pytest.approx(39 / 92 * 100, abs=.001)
    assert p["source"] == "Plano Político" and p["base"] == "totais"


def test_senate_inconsistent_sum_quarantined_without_inventing_normalization():
    rows = pp.parse_page(FIXTURE, "senado")
    sp = next(p for p in rows if p["uf"] == "SP")
    al = next(p for p in rows if p["uf"] == "AL")
    assert not sp["eligible"] and not sp["valid_shares"] and sp["shares"]
    assert al["eligible"] and al["valid_shares"]
    name = next(iter(al["valid_shares"]))
    assert al["valid_shares"][name] == pytest.approx(al["shares"][name], abs=.001)


def test_id_deduplicates_registration_across_urls_but_preserves_turn_and_scenario():
    p = poll(registro="BR-001/2026")
    q = poll(registro="BR-001/2026")
    q["url"] = "https://different.example/"
    assert p["id"] == q["id"]
    assert p["id"] != poll(registro="BR-001/2026", turn="2º turno")["id"]
    assert p["id"] != poll(registro="BR-001/2026", values={"Lula":40,"Caiado":40})["id"]


def test_houses_with_constant_offsets_do_not_create_ten_point_trend():
    rows = [poll("A", day, {"Lula":40,"Flávio Bolsonaro":30,"Outros":20,"Indecisos":10})
            for day in ("2026-09-01","2026-09-18")]
    rows += [poll("B", day, {"Lula":30,"Flávio Bolsonaro":40,"Outros":20,"Indecisos":10})
             for day in ("2026-09-02","2026-09-19")]
    # Another institute entering late with a different level must not affect trend.
    rows += [poll("C","2026-09-20", {"Lula":20,"Flávio Bolsonaro":50,"Outros":20,"Indecisos":10})]
    trend = research.matched_trend(rows, TODAY, 14)
    assert trend["Flávio Bolsonaro"] == {"delta": 0., "institutes": 2}
    assert research.matched_trend(rows[:2], TODAY, 14) == {}


def test_fixed_window_excludes_old_future_and_different_candidates():
    rows = [poll("A","2026-08-01"),poll("B","2026-09-01"),poll("C","2026-09-19"),poll("D","2026-09-21")]
    rows.append(poll("E","2026-09-18",{"Lula":40,"Caiado":40,"Indecisos":20}))
    series, selected = research.select_series(rows, TODAY)
    assert {p["pollster"] for p in selected} == {"B","C"}
    assert all(p["field_end"] <= TODAY.isoformat() for p in series)


def test_repeated_institute_does_not_dominate_and_more_than_six_polls_allowed():
    rows = [poll("A", registro=f"A-{i}") for i in range(10)] + [poll("B")]
    weights = research.poll_weights(rows)
    assert sum(weights[:10]) == pytest.approx(.5)
    assert weights[-1] == pytest.approx(.5)
    assert research.aggregate(rows, TODAY, history=False)["polls"] == 11


def test_single_institute_has_no_bootstrap_interval():
    assert research.summarize([poll()], bootstrap=True)["intervals"] == {}
    a=research.summarize([poll("A"),poll("B"),poll("C")], bootstrap=True)
    assert a["intervals"]["Lula"][0] <= a["shares"]["Lula"] <= a["intervals"]["Lula"][1]


def test_presidential_state_poll_never_enters_national_and_runoff_is_separate():
    rows=[poll("A"),poll("B",uf="SP",values={"Lula":70,"Flávio Bolsonaro":20}),
          poll("C",turn="2º turno",values={"Lula":40,"Flávio Bolsonaro":50,"Indecisos":10})]
    a=research.presidential(rows,TODAY)
    assert a["polls"] == 1 and a["runoff_poll_count"] == 1
    assert a["runoff"]["Lula"] == 44.4
    assert a["first_round"][0]["avg"] < 50


def test_missing_roster_candidate_clears_old_measurement_and_reports_unmapped():
    from pipeline.model import fill_pct_valid
    p=poll(values={"Lula":30,"Flávio Bolsonaro":40,"Outros":20,"Indecisos":10},uf="SP")
    p["cargo"]="Governo"
    records=[{"name":"Lula","uf":"SP","cargo":"Governo","active":True,"pct":99},
             {"name":"Ausente","uf":"SP","cargo":"Governo","active":True,"pct":40,"pct_valid":80}]
    research.apply_catalog(records,[p],TODAY)
    fill_pct_valid(records)
    assert records[0]["pct_valid"] == 33.3
    assert records[1]["pct"] is None and records[1]["pct_valid"] is None
    health=research.race_health(records,[p],TODAY)
    assert health["missing_candidates"] == ["Ausente"]
    assert health["unmapped_candidates"] == ["Flávio Bolsonaro"]
    assert research.match_name("Silva",[{"name":"Ana Silva"},{"name":"João Silva"}]) is None


def test_age_uses_field_date_and_stale_data_stays_visible():
    p=poll(day="2026-08-01")
    p["published_at"]="2026-09-19"
    a=research.aggregate([p],TODAY,history=False)
    assert a["age_days"] == 50 and a["stale"] and a["polls"] == 1
    assert research.aggregate([],TODAY)["stale"]


def test_failed_collection_keeps_catalog_and_records_error(tmp_path,monkeypatch):
    import requests
    from pipeline import research_collect as rc
    from pipeline import collect
    catalog_path=tmp_path/'data/research/catalog.json'
    catalog_path.parent.mkdir(parents=True)
    p=poll()
    catalog_path.write_text(json.dumps({"polls":[p],"sources":{}}),encoding='utf-8')
    (tmp_path/'reference').mkdir()
    (tmp_path/'reference/roster.yaml').write_text('states: {}',encoding='utf-8')
    (tmp_path/'data/polls').mkdir()
    monkeypatch.setattr(rc,'ROOT',tmp_path)
    monkeypatch.setattr(rc,'CATALOG',catalog_path)
    monkeypatch.setattr(collect,'latest_snapshot',lambda:{"records":[]})
    def fail(*args): raise requests.ConnectionError('offline')
    monkeypatch.setattr(pp,'fetch',fail)
    rc.run(TODAY.isoformat())
    saved=json.loads(catalog_path.read_text(encoding='utf-8'))
    assert saved['polls']==[p]
    assert all(s['status']=='error' for s in saved['sources'].values())
