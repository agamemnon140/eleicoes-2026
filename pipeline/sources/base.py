"""Tipos comuns das fontes de coleta."""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass


FIRST_ROUND = "1º turno"
RUNOFF = "2º turno"

BASE_TOTAL = "totais"    # % sobre todos os entrevistados (inclui branco/nulo/indeciso)
BASE_VALID = "válidos"   # % sobre os votos válidos (só candidatos)


@dataclass
class PollRecord:
    uf: str
    cargo: str          # "Governo" | "Senado"
    name: str           # nome casado com o roster
    party: str
    pct: float          # como publicado
    pollster: str
    date: str
    source: str         # ex.: "wikipedia"
    url: str = ""       # link para a fonte da pesquisa
    # --- contexto do cenário, para não somar alhos com bugalhos ---
    scenario: str = FIRST_ROUND   # FIRST_ROUND | RUNOFF
    base: str = BASE_TOTAL        # base em que o instituto publicou
    sum_cands: float | None = None  # soma dos % de TODOS os candidatos do cenário
    undecided: float | None = None  # branco/nulo/indeciso (fora dos válidos)
    opponents: tuple = ()           # no 2º turno, quem estava no cenário

    @property
    def pct_valid(self) -> float | None:
        """% sobre votos válidos — a base comparável entre institutos.

        Institutos publicam em bases diferentes (uns sobre o total de entrevistados, com
        indeciso dentro; outros já sobre válidos). Comparar sem converter mistura escalas:
        45% de totais com 30% de indeciso é ~64% de válidos.
        """
        if self.pct is None:
            return None
        if self.base == BASE_VALID:
            return round(self.pct, 2)
        if not self.sum_cands or self.sum_cands <= 0:
            return None
        return round(self.pct / self.sum_cands * 100, 2)


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


# linhas que NÃO são voto válido (saem do denominador dos válidos) — pt e en (Wikipedia)
_BLANK = ("nulo", "branco", "nao sabe", "nao respondeu", "nao opinou", "nao definiu",
          "ninguem", "nenhum", "indeciso", "nao vota", "nao iria",
          "undec", "undicided", "none", "blank", "null", "abstention", "would not vote")
# linhas que SÃO voto válido, mas de candidatos que não acompanhamos
_OTHER = ("outros", "outras respostas", "demais", "demais candidatos", "other")


def option_kind(label: str) -> str:
    """'branco' (fora dos válidos), 'outros' (válido, candidato menor) ou 'candidato'."""
    s = strip_accents(label or "").lower().strip()
    if any(k in s for k in _BLANK):
        return "branco"
    if any(s.startswith(k) for k in _OTHER):
        return "outros"
    return "candidato"


# instituto -> nome canônico. Vale para TODAS as fontes: "Genial/Quaest" (Wikipedia),
# "genial-quaest" (slug da Gazeta) e "quaest" são o mesmo instituto e têm de virar uma
# série só — senão a média móvel trata o mesmo instituto como dois.
POLLSTERS = {
    "atlasintel": "AtlasIntel", "atlas intel": "AtlasIntel",
    "real time big data": "Real Time Big Data", "eal time big data": "Real Time Big Data",
    "realtimebigdata": "Real Time Big Data",
    "parana pesquisas": "Paraná Pesquisas", "paranapesquisas": "Paraná Pesquisas",
    "futura inteligencia": "Futura Inteligência",
    "datafolha": "Datafolha", "genial quaest": "Quaest", "quaest": "Quaest",
    "ipec": "Ipec", "ipespe": "Ipespe", "cnt mda": "CNT/MDA", "mda": "CNT/MDA", "cnt": "CNT/MDA",
    "irg": "IRG", "neokemp": "NeoKemp", "ideia": "Ideia", "poderdata": "PoderData",
    "gerp": "Gerp", "nexus": "Nexus", "brasmarket": "Brasmarket", "verita": "Veritá",
    "opiniao": "Opinião", "ranking": "Ranking Pesquisas", "offerwise": "Offerwise",
    "ativa": "Ativa Pesquisas", "vox": "Vox Populi",
}
_POLLSTER_KEYS = sorted(POLLSTERS, key=len, reverse=True)   # casa o mais específico antes


def canon_pollster(texto: str) -> str | None:
    """Nome canônico do instituto a partir de texto livre ou slug. None se não reconhecer."""
    s = strip_accents(texto or "").lower().replace("-", " ").replace("/", " ")
    s = " ".join(s.split())
    for k in _POLLSTER_KEYS:
        if k in s:
            return POLLSTERS[k]
    return None


def norm_party(p: str) -> str:
    p = strip_accents(p or "").upper().strip()
    return {
        "SD": "SOLIDARIEDADE",
        "UNIAO": "UNIAO", "UNIAO BRASIL": "UNIAO",
        "PROGRESSISTAS": "PP",
    }.get(p, p)


def match_candidate(name: str, party: str | None, roster_state: dict, only_cargo: str | None = None):
    """Casa (nome, partido) com um candidato do roster. -> (cand, cargo) ou None.

    `only_cargo` restringe a busca. Sem ele, quem disputa os dois cargos no mesmo estado
    (caso do João Roma na BA) casa sempre com o primeiro da ordem — e um número da lista
    do Senado acaba virando pesquisa de governador.
    """
    name_toks = [strip_accents(t).lower().strip(".") for t in name.split() if len(strip_accents(t)) > 2]
    if not name_toks:
        return None
    npu = norm_party(party) if party else None
    for office_key, cargo in (("governor", "Governo"), ("senate", "Senado")):
        if only_cargo and cargo != only_cargo:
            continue
        for c in roster_state.get(office_key, {}).get("candidates", []):
            if npu and norm_party(c["party"]) != npu:
                continue
            cname = strip_accents(c["name"]).lower()
            if any(t in cname for t in name_toks):
                return c, cargo
    return None
