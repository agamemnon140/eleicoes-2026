"""Modelo de índice: funções de score S_* (0-100) e composição ponderada.

Fórmula derivada e validada contra os registros do preview (ver tests/):
  S_poll = reliability * min(100, pct / 0,6)   # governador e presidente (satura em 60%)
  S_sen  = senNorm                              # pesquisa do Senado normalizada (líder=100)
  S_apoio = {explícito:100, chapa/aliança:90, inferido:45, não verificado:0}
  score  = Σ pesoᵢ * Sᵢ

O índice serve para ORDENAR candidatos; não é probabilidade calibrada de vitória.
"""
from __future__ import annotations

PCT_NORM = 0.6  # 60% satura o componente em 100

APOIO_SCORE = {
    "explícito": 100.0,
    "chapa/aliança": 90.0,
    "inferido": 45.0,
    "não verificado": 0.0,
}


def s_poll(pct: float | None, reliability: float) -> float:
    """Score 0-100 de governador ou presidente a partir do % e da confiabilidade."""
    if pct is None:
        return 0.0
    return reliability * min(100.0, pct / PCT_NORM)


def s_apoio(endorsement: str | None) -> float:
    return APOIO_SCORE.get(endorsement or "", 0.0)


def _round1(x: float) -> float:
    return round(x, 1)


def score_senate(
    *,
    gov_pct: float | None,
    gov_reliability: float,
    pres_pct: float | None,
    pres_reliability: float,
    sen_norm: float,
    endorsement: str | None,
    weights: dict,
) -> dict:
    """Índice de um candidato ao Senado. `weights` tem chaves governo/presidente/senado/apoio.

    Reproduz exatamente os `modelComponents`/`modelScore` do preview quando alimentado
    com os pesos e entradas embutidos em cada registro.
    """
    gs = s_poll(gov_pct, gov_reliability)
    ps = s_poll(pres_pct, pres_reliability)
    aps = s_apoio(endorsement)
    comps = {
        "governo": weights["governo"] * gs,
        "presidente": weights["presidente"] * ps,
        "senado": weights["senado"] * sen_norm,
        "apoio": weights["apoio"] * aps,
    }
    return {
        "components": {k: _round1(v) for k, v in comps.items()},
        "score": _round1(sum(comps.values())),
        "scores": {"governo": gs, "presidente": ps, "senado": sen_norm, "apoio": aps},
    }


def score_governor(
    *,
    gov_pct: float | None,
    gov_reliability: float,
    pres_pct: float | None,
    pres_reliability: float,
    w_gov: float,
    w_pres: float,
) -> dict:
    """Índice de um candidato a governador: pesquisa do governador + lean presidencial.

    O apoio/chapa é fundido no lean presidencial (colineares) para evitar dupla contagem.
    """
    gs = s_poll(gov_pct, gov_reliability)
    ps = s_poll(pres_pct, pres_reliability)
    comps = {"governo": w_gov * gs, "presidente": w_pres * ps}
    return {
        "components": {k: _round1(v) for k, v in comps.items()},
        "score": _round1(sum(comps.values())),
        "scores": {"governo": gs, "presidente": ps},
    }
