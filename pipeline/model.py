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


MAIORIA = 50.0     # % dos votos válidos que encerra a eleição no 1º turno

# --- média móvel (poll-of-polls) ---------------------------------------------
MA_WINDOW_DAYS = 30    # janela: pesquisas até 30 dias mais velhas que a mais recente
MA_HALFLIFE_DAYS = 14  # meia-vida do peso por recência: 14 dias mais velha pesa metade


def model_pct(r: dict) -> float | None:
    """% que o modelo usa: os válidos quando dá para converter, senão o publicado.

    Fica aqui (e não no coletor) porque é decisão de modelo: qual base entra na conta.
    """
    v = r.get("pct_valid")
    return v if isinstance(v, (int, float)) else r.get("pct")


def _norm(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).casefold().strip()


def governor_race(cands: list[dict], threshold: float = MAIORIA) -> dict:
    """Decide a eleição de governador em DOIS TURNOS, como ela de fato acontece.

    `cands` são os candidatos ativos, cada um com `pct_valid` (% dos votos VÁLIDOS — é
    sobre válidos que a Constituição conta a maioria), `score` (índice, usado como
    desempate) e `runoff` ({adversário: % válidos no 2º turno}).

    Regra:
      1. líder com >= 50% dos válidos  -> eleito no 1º turno;
      2. senão, os dois primeiros vão ao 2º turno e, havendo pesquisa DAQUELE par,
         é ela que decide — não o índice do 1º turno;
      3. sem pesquisa de 2º turno, cai no índice (chapa + presidente) como desempate.

    Ordenar pelo 1º turno e declarar vencedor o primeiro é o erro clássico: quem lidera
    com 40% em campo dividido perde o 2º turno com frequência.
    """
    polled = [c for c in cands if isinstance(c.get("pct_valid"), (int, float))]
    by_score = sorted(cands, key=lambda c: c.get("score") or 0, reverse=True)
    if len(polled) < 2:
        w = by_score[0] if by_score else None
        return {"turno": None, "winner": w["name"] if w else None,
                "decidido_por": "índice (sem pesquisa comparável)", "finalistas": [], "pcts": {}}

    polled.sort(key=lambda c: c["pct_valid"], reverse=True)
    lider, vice = polled[0], polled[1]
    pcts = {c["name"]: c["pct_valid"] for c in polled}

    if lider["pct_valid"] >= threshold:
        return {"turno": 1, "winner": lider["name"], "decidido_por": "1º turno (maioria dos válidos)",
                "finalistas": [], "pcts": pcts,
                "margem": round(lider["pct_valid"] - vice["pct_valid"], 1)}

    finalistas = [lider["name"], vice["name"]]
    # pesquisa de 2º turno DESTE par (procura nos dois sentidos; grafia pode variar)
    duelo = {}
    for a, b in ((lider, vice), (vice, lider)):
        for rival, info in (a.get("runoff") or {}).items():
            if _norm(rival) in _norm(b["name"]) or _norm(b["name"]) in _norm(rival):
                duelo[a["name"]] = info.get("pct_valid")
    # num duelo em base de válidos os dois somam 100 — um lado basta para fechar a conta
    if len(duelo) == 1:
        (quem, valor), = duelo.items()
        if valor is not None:
            outro = finalistas[1] if quem == finalistas[0] else finalistas[0]
            duelo[outro] = round(100.0 - valor, 1)   # mesma precisão do porte JS

    if len(duelo) == 2 and all(v is not None for v in duelo.values()):
        vencedor = max(duelo, key=duelo.get)
        return {"turno": 2, "winner": vencedor, "decidido_por": "pesquisa de 2º turno",
                "finalistas": finalistas, "pcts": pcts, "duelo": duelo,
                "margem": round(abs(duelo[finalistas[0]] - duelo[finalistas[1]]), 1)}

    entre_finalistas = [c for c in by_score if c["name"] in finalistas]
    vencedor = entre_finalistas[0]["name"] if entre_finalistas else lider["name"]
    return {"turno": 2, "winner": vencedor, "decidido_por": "índice (sem pesquisa de 2º turno)",
            "finalistas": finalistas, "pcts": pcts,
            "margem": round(lider["pct_valid"] - vice["pct_valid"], 1)}


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
