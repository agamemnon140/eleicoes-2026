"""Regra de dois turnos do governador — o índice do 1º turno sozinho não decide."""
from pipeline import model


def c(name, pct_valid=None, score=0.0, runoff=None):
    return {"name": name, "pct_valid": pct_valid, "score": score,
            "runoff": {k: {"pct_valid": v} for k, v in (runoff or {}).items()}}


def test_maioria_dos_validos_encerra_no_primeiro_turno():
    r = model.governor_race([c("A", 54.0, score=80), c("B", 30.0, score=60), c("C", 16.0)])
    assert r["turno"] == 1 and r["winner"] == "A"
    assert r["finalistas"] == []


def test_abaixo_de_50_vai_a_segundo_turno():
    r = model.governor_race([c("A", 45.0, score=80), c("B", 35.0, score=60), c("C", 20.0)])
    assert r["turno"] == 2 and r["finalistas"] == ["A", "B"]


def test_pesquisa_de_segundo_turno_pode_virar_o_resultado():
    """O caso que motiva a regra: quem lidera o 1º turno perde o duelo."""
    r = model.governor_race([
        c("A", 40.0, score=90, runoff={"B": 48.0}),
        c("B", 36.0, score=50, runoff={"A": 52.0}),
        c("C", 24.0),
    ])
    assert r["turno"] == 2 and r["winner"] == "B"          # e não "A", o líder do 1º turno
    assert r["decidido_por"] == "pesquisa de 2º turno"
    assert r["margem"] == 4.0


def test_sem_pesquisa_do_duelo_cai_no_indice():
    r = model.governor_race([c("A", 40.0, score=90), c("B", 36.0, score=50), c("C", 24.0)])
    assert r["turno"] == 2 and r["winner"] == "A"
    assert "índice" in r["decidido_por"]


def test_pesquisa_de_duelo_de_outro_par_e_ignorada():
    """Duelo A x C não pode decidir um 2º turno entre A e B."""
    r = model.governor_race([
        c("A", 40.0, score=50, runoff={"C": 60.0}),
        c("B", 36.0, score=90, runoff={"C": 30.0}),
        c("C", 24.0),
    ])
    assert r["finalistas"] == ["A", "B"]
    assert "índice" in r["decidido_por"] and r["winner"] == "B"


def test_grafia_diferente_no_nome_do_adversario_ainda_casa():
    """O nome vem como o instituto escreveu: 'Daniel Santos' tem de casar com 'Dr. Daniel Santos'."""
    r = model.governor_race([
        c("Hana Ghassan", 39.9, score=66, runoff={"Daniel Santos": 49.5}),
        c("Dr. Daniel Santos", 35.6, score=59, runoff={"Hana Ghassan": 50.5}),
    ])
    assert r["winner"] == "Dr. Daniel Santos" and r["decidido_por"] == "pesquisa de 2º turno"


def test_um_lado_do_duelo_basta():
    """Só um dos dois teve o cenário parseado — em válidos, o outro é o complemento de 100."""
    r = model.governor_race([
        c("A", 40.0, score=90, runoff={"B": 47.0}),
        c("B", 36.0, score=50),
        c("C", 24.0),
    ])
    assert r["winner"] == "B" and r["duelo"] == {"A": 47.0, "B": 53.0}


def test_sem_pesquisa_comparavel_usa_indice_e_nao_quebra():
    r = model.governor_race([c("A", None, score=70), c("B", None, score=40)])
    assert r["winner"] == "A" and r["turno"] is None
    assert model.governor_race([])["winner"] is None
