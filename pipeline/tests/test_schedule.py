"""Testes do cronograma de pesos (sem dados externos)."""
import math

from pipeline import schedule as sc


def approx(a, b, tol=1e-6):
    return math.isclose(a, b, abs_tol=tol)


def test_progress_and_ramp_bounds():
    assert approx(sc.progress(sc.D0), 0.0)          # início da corrida
    assert approx(sc.progress(0), 1.0)              # dia da eleição
    assert approx(sc.progress(-10), 1.0)            # após a eleição fica saturado
    assert approx(sc.ramp(sc.D0), 0.0)
    assert approx(sc.ramp(0), 1.0)


def test_governor_weights_bounds_and_decay():
    start = sc.governor_weights(sc.D0)
    end = sc.governor_weights(0)
    assert approx(start.pres, 0.20)                 # 0,20 no início
    assert approx(end.pres, 0.03)                   # ~0,03 no dia
    assert start.pres <= sc.GOV_PRES_CAP + 1e-9     # nunca acima do teto
    # governador sempre domina e soma 1
    for w in (start, end):
        assert w.gov > w.pres
        assert approx(w.gov + w.pres, 1.0)
    # peso presidencial decresce à medida que a eleição se aproxima
    assert sc.governor_weights(200).pres > sc.governor_weights(30).pres


def test_senate_weights_grow_and_sum_to_one():
    start = sc.senate_weights(sc.D0)
    end = sc.senate_weights(0)
    assert approx(start.sen, sc.SEN_POLL_MIN)       # 0,15 no início
    assert approx(end.sen, sc.SEN_POLL_CAP)         # 0,50 no fim (default)
    assert end.sen <= sc.SEN_POLL_HARD_MAX + 1e-9   # nunca acima de 0,55
    for w in (start, end):
        assert approx(w.gov + w.pres + w.sen + w.apoio, 1.0)
        assert approx(w.apoio, sc.SEN_APOIO)
    # cresce monotonicamente com a proximidade
    assert sc.senate_weights(30).sen > sc.senate_weights(200).sen


def test_senate_volatility_pulls_weight_down():
    calm = sc.senate_weights(0, may_change_pct=10)
    volatile = sc.senate_weights(0, may_change_pct=70)
    assert volatile.sen < calm.sen                  # 2 vagas emboladas -> peso menor
    assert volatile.sen >= 0.30                      # mas não abaixo de ~0,30 no fim


def test_senate_single_seat_stable_reaches_hard_max():
    w = sc.senate_weights(0, may_change_pct=10, single_seat_stable=True)
    assert approx(w.sen, sc.SEN_POLL_HARD_MAX)      # 0,55 em corrida de 1 vaga estável
