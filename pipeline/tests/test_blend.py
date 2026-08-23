"""Blend das pesquisas presidenciais por estado no pres_lean (build.blend_state_pres)."""
import datetime

from pipeline.build import blend_state_pres

AS_OF = datetime.date(2026, 8, 23)


def _poll(**kw):
    base = {"pollster": "Datafolha", "date": "23/08/2026", "url": "",
            "first_round": None, "runoff": None}
    base.update(kw)
    return base


def test_uma_pesquisa_fresca_entra_com_um_terco():
    lean = {"Lula": 30, "Flávio": 34, "basis": "Quaest 23-27/07"}
    out = blend_state_pres(lean, [_poll(first_round={"Lula": 34.0, "Flávio": 35.0})], AS_OF)
    assert out["Lula"] == 31.3 and out["Flávio"] == 34.3
    assert "Datafolha estadual (w=0.33)" in out["basis"]
    assert lean["Lula"] == 30, "o prior não pode ser mutado"


def test_so_segundo_turno_atualiza_a_razao_e_preserva_a_soma():
    # RJ na Datafolha de ago/26: sem estimulada, só o duelo Lula x Flávio.
    # Cenários diferentes não se misturam: o duelo move a razão, não o nível.
    lean = {"Lula": 30, "Flávio": 32, "basis": "Quaest 21-25/07"}
    out = blend_state_pres(lean, [_poll(runoff={"Lula": 40.0, "Flávio": 49.0})], AS_OF)
    assert out["Lula"] == 29.3 and out["Flávio"] == 32.7
    assert out["Lula"] + out["Flávio"] == lean["Lula"] + lean["Flávio"]


def test_pesquisa_fora_da_janela_nao_conta():
    lean = {"Lula": 30, "Flávio": 34, "basis": "proxy 2022"}
    out = blend_state_pres(
        lean, [_poll(date="01/06/2026", first_round={"Lula": 50.0, "Flávio": 20.0})], AS_OF)
    assert out == lean


def test_sem_pesquisas_devolve_o_prior():
    lean = {"Lula": 30, "Flávio": 34, "basis": "proxy 2022"}
    assert blend_state_pres(lean, [], AS_OF) is lean


def test_guardrail_barra_salto_absurdo():
    # mesmo com 1/3 de peso, um valor de parser quebrado não pode entrar
    lean = {"Lula": 5, "Flávio": 34, "basis": "proxy 2022"}
    out = blend_state_pres(lean, [_poll(first_round={"Lula": 99.0, "Flávio": 35.0})], AS_OF)
    assert out["Lula"] == 5, "salto de +31 p.p. no blend tem de ser barrado"
    assert out["Flávio"] == 34.3
