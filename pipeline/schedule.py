"""Cronograma de pesos que varia com o tempo até a eleição.

Evidência (Jennings & Wlezien 2018; Erikson & Wlezien): o erro das pesquisas cai
numa curva CÔNCAVA — devagar no início, acelerando nas últimas 6-8 semanas. Logo,
o peso da pesquisa do próprio pleito cresce ~p**k, e os sinais estruturais decaem.

Governador: peso presidencial (lean) cai de 0,20 -> 0,03 (teto 0,25).
Senado:     peso da pesquisa própria cresce 0,15 -> 0,50 (teto rígido 0,55),
            modulado para baixo por volatilidade ("pode mudar o voto").

Todos os números são calibráveis por backtest 2018/2022 (ver pipeline/backtest).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# --- constantes de calibração -------------------------------------------------
ELECTION_DATE = date(2026, 10, 4)   # 1º turno
D0 = 270                            # dias; início da corrida (~9 meses)
K = 2.75                            # expoente da curva côncava

# Governador
GOV_PRES_START = 0.20               # peso presidencial no início
GOV_PRES_END = 0.03                 # peso presidencial no dia
GOV_PRES_CAP = 0.25                 # teto rígido

# Senado
SEN_POLL_MIN = 0.15                 # peso da pesquisa do Senado no início
SEN_POLL_CAP = 0.50                 # teto default no fim
SEN_POLL_HARD_MAX = 0.55            # teto rígido (só 1 vaga + líder estável)
SEN_POLL_ABS_FLOOR = 0.05           # nunca zera
SEN_APOIO = 0.10                    # peso do apoio/chapa (constante)
SEN_GOV_SHARE = 0.35 / 0.65         # repartição do restante entre gov e pres
SEN_PRES_SHARE = 0.30 / 0.65        # (ratio 0,35:0,30 do preview)


# Momentum: só nos últimos dias, peso pequeno (bônus em pontos = peso × Δp.p. da pesquisa)
MOM_WINDOW = 14     # dias antes da eleição em que o momentum passa a valer
MOM_MAX = 1.0       # peso máximo no dia (backtest: pequeno; 3,0 seria overfit)


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def momentum_weight(days_to_election: float) -> float:
    """0 fora da janela final; sobe linear até MOM_MAX no dia da eleição."""
    if days_to_election >= MOM_WINDOW:
        return 0.0
    return MOM_MAX * (MOM_WINDOW - max(0.0, days_to_election)) / MOM_WINDOW


def days_until(as_of: date, election: date = ELECTION_DATE) -> int:
    return (election - as_of).days


def progress(days_to_election: float, d0: int = D0) -> float:
    """0 no início da corrida -> 1 no dia da eleição."""
    return clamp((d0 - days_to_election) / d0, 0.0, 1.0)


def ramp(days_to_election: float, k: float = K, d0: int = D0) -> float:
    """Curva côncava p**k (acelera no fim)."""
    return progress(days_to_election, d0) ** k


# --- governador ---------------------------------------------------------------
@dataclass(frozen=True)
class GovWeights:
    gov: float
    pres: float


def governor_weights(days_to_election: float, k: float = K) -> GovWeights:
    r = ramp(days_to_election, k)
    w_pres = clamp(
        GOV_PRES_END + (GOV_PRES_START - GOV_PRES_END) * (1 - r),
        GOV_PRES_END,
        GOV_PRES_CAP,
    )
    return GovWeights(gov=1.0 - w_pres, pres=w_pres)


# --- senado -------------------------------------------------------------------
def volatility_factor(may_change_pct: float | None) -> float:
    """Reduz o peso da pesquisa de Senado quando muitos podem mudar o voto.
    <=30% -> 1,0 ; 70%+ -> ~0,65 (puxa para perto do piso)."""
    if may_change_pct is None:
        return 1.0
    return 1.0 - 0.35 * clamp((may_change_pct - 30.0) / 40.0, 0.0, 1.0)


@dataclass(frozen=True)
class SenateWeights:
    gov: float
    pres: float
    sen: float
    apoio: float


def senate_weights(
    days_to_election: float,
    may_change_pct: float | None = None,
    single_seat_stable: bool = False,
    k: float = K,
    cap: float = SEN_POLL_CAP,
) -> SenateWeights:
    r = ramp(days_to_election, k)
    w_sen = (SEN_POLL_MIN + (cap - SEN_POLL_MIN) * r) * volatility_factor(may_change_pct)
    if single_seat_stable:
        w_sen *= 1.10  # permite chegar ao teto rígido em corrida de 1 vaga estável
    hi = SEN_POLL_HARD_MAX if single_seat_stable else cap
    w_sen = clamp(w_sen, SEN_POLL_ABS_FLOOR, hi)
    rem = 1.0 - SEN_APOIO - w_sen
    return SenateWeights(
        gov=rem * SEN_GOV_SHARE,
        pres=rem * SEN_PRES_SHARE,
        sen=w_sen,
        apoio=SEN_APOIO,
    )
