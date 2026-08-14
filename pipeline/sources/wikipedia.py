"""Coletor da Wikipedia (inglês): tabelas de pesquisa por estado.

As páginas "2026_<Estado>_gubernatorial_election" trazem tabelas <table class="wikitable">
com cabeçalho "Pollster firm | Polling period | <Candidato Partido> | ... | Others | Undec. |
Margin | Sample | Lead | Link". A 1ª linha de dados é a pesquisa mais recente.

A tabela é classificada em Governo/Senado casando seus candidatos contra o roster (robusto
a variações de título de seção). Retorna o percentual mais recente por candidato casado.
"""
from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

from pipeline.sources.base import (BASE_TOTAL, BASE_VALID, FIRST_ROUND, RUNOFF, PollRecord,
                                   norm_party, option_kind, strip_accents)

UA = {"User-Agent": "eleicoes-2026-bot/0.1 (github.com/agamemnon140/eleicoes-2026)"}
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
KNOWN_PARTIES = {norm_party(p) for p in (
    "PT PL PSD MDB PP Republicanos União PSB PDT Rede Novo PSOL Podemos Avante PSDB "
    "Solidariedade PSC DC PRD PCB PSTU UP Cidadania Democrata Missão PV PCdoB Agir SD".split())}


def page_titles(estado: str) -> list[str]:
    e = estado.replace(" ", "_")
    return [f"2026_{e}_gubernatorial_election", f"2026_{e}_general_election"]


def fetch_html(estado: str, session: requests.Session) -> tuple[str, str] | tuple[None, None]:
    for title in page_titles(estado):
        url = f"https://en.wikipedia.org/wiki/{title}"
        try:
            r = session.get(url, timeout=30)
        except requests.RequestException:
            continue
        if r.status_code == 200 and "wikitable" in r.text:
            return r.text, url
    return None, None


def _is_num(s: str) -> bool:
    try:
        float(s.replace(",", "").replace(".", ""))
        return True
    except ValueError:
        return False


def _pct(s: str) -> float | None:
    s = s.replace(",", ".").replace("%", "").replace("–", "").replace("—", "").strip()
    if not s or "N/a" in s or s in {".", "-"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _match_header(cell: str, roster_state: dict):
    """Casa um cabeçalho 'Sobrenome Partido' com um candidato do roster. -> (cand, cargo)."""
    toks = cell.split()
    if not toks:
        return None
    party_tok = norm_party(toks[-1])
    has_party = party_tok in KNOWN_PARTIES
    name_toks = [strip_accents(t).lower().strip(".")
                 for t in (toks[:-1] if has_party else toks) if len(strip_accents(t)) > 2]
    if not name_toks:
        return None
    for office_key, cargo in (("governor", "Governo"), ("senate", "Senado")):
        for c in roster_state.get(office_key, {}).get("candidates", []):
            if has_party and norm_party(c["party"]) != party_tok:
                continue
            cname = strip_accents(c["name"]).lower()
            if any(t in cname for t in name_toks):
                return c, cargo
    return None


def _latest_row(rows, hlen: int):
    for tr in rows[1:]:
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
        if len(cells) != hlen:
            continue
        pollster, date = cells[0], cells[1]
        if not pollster or _is_num(pollster) or "ithdr" in pollster or "esist" in pollster:
            continue
        if not any(m in date for m in MONTHS):
            continue
        return cells
    return None


def collect_state(estado: str, uf: str, roster_state: dict, session: requests.Session) -> list[PollRecord]:
    html, url = fetch_html(estado, session)
    if not html:
        return []
    return parse_state(html, uf, roster_state, url or "")


_META_HDR = ("margin", "sample", "lead", "link", "ref", "source", "date", "pollster",
             "turnout", "method")
_RUNOFF_HDR = ("second round", "runoff", "run-off", "2nd round")


def _table_scenario(t) -> str:
    """1º ou 2º turno, pelo título de seção acima da tabela."""
    h = t.find_previous(["h2", "h3", "h4"])
    for _ in range(3):
        if h is None:
            break
        txt = strip_accents(h.get_text(" ", strip=True)).lower()
        if any(k in txt for k in _RUNOFF_HDR):
            return RUNOFF
        if "first round" in txt or "opinion polling" in txt:
            return FIRST_ROUND
        h = h.find_previous(["h2", "h3", "h4"])
    return FIRST_ROUND


def _hdr_kind(idx: int, h: str) -> str:
    """'meta', 'branco', 'outros' ou 'candidato' para uma coluna do cabeçalho."""
    s = strip_accents(h or "").lower().strip()
    if idx < 2 or any(k in s for k in _META_HDR):
        return "meta"
    return option_kind(h)


def parse_state(html: str, uf: str, roster_state: dict, url: str = "") -> list[PollRecord]:
    soup = BeautifulSoup(html, "lxml")
    records: list[PollRecord] = []
    seen: set = set()   # (cargo, name, cenário) — pega da tabela mais recente (1ª ocorrência)
    for t in soup.select("table.wikitable"):
        rows = t.find_all("tr")
        if not rows:
            continue
        header = [c.get_text(" ", strip=True) for c in rows[0].find_all(["th", "td"])]
        if not any("Pollster" in h or "Date(s) conducted" in h for h in header):
            continue
        cols, tally, kinds = {}, {}, {}
        for idx, h in enumerate(header):
            kinds[idx] = _hdr_kind(idx, h)
            if idx < 2:
                continue
            m = _match_header(h, roster_state)
            if m:
                cols[idx] = m
                tally[m[1]] = tally.get(m[1], 0) + 1
        if not cols:
            continue
        cargo_tbl = max(tally, key=tally.get)
        row = _latest_row(rows, len(header))
        if not row:
            continue

        # base da tabela: soma dos candidatos (+ "Others") x indecisos/brancos
        soma_cands = undecided = 0.0
        for idx, kind in kinds.items():
            if kind == "meta" or idx >= len(row):
                continue
            v = _pct(row[idx])
            if v is None:
                continue
            if kind == "branco":
                undecided += v
            else:
                soma_cands += v
        base = BASE_VALID if (undecided < 0.5 and abs(soma_cands - 100) < 2.5) else BASE_TOTAL
        cenario = _table_scenario(t)
        adversarios = tuple(c["name"] for _, (c, cargo) in cols.items() if cargo == cargo_tbl)

        for idx, (cand, cargo) in cols.items():
            if cargo != cargo_tbl:
                continue
            key = (cargo, cand["name"], cenario)
            if key in seen:
                continue
            pct = _pct(row[idx]) if idx < len(row) else None
            if pct is None:
                continue
            seen.add(key)
            records.append(PollRecord(
                uf, cargo, cand["name"], cand["party"], pct,
                _clean(row[0]), _clean(row[1]), "wikipedia", url,
                scenario=cenario, base=base, sum_cands=round(soma_cands, 1),
                undecided=round(undecided, 1),
                opponents=adversarios if cenario == RUNOFF else ()))
    return records


def _clean(s: str) -> str:
    return re.sub(r"\[.*?\]", "", s).strip()
