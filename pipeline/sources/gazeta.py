"""Coletor da Gazeta do Povo: páginas de pesquisa por estado (governador + senado).

O índice /eleicoes/2026/pesquisa-eleitoral-2026/ lista as matérias por estado; cada matéria
traz listas <li class="...postListItem">Nome (Partido): 48,9%</li> com os percentuais.
Cobre os estados que a Wikipedia não tabula (BA, CE, RJ etc.).
"""
from __future__ import annotations

import re

import requests

from pipeline.sources.base import (BASE_TOTAL, BASE_VALID, FIRST_ROUND, RUNOFF, PollRecord,
                                   canon_pollster, match_candidate, option_kind, strip_accents)

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
BASE = "https://www.gazetadopovo.com.br"
INDEX = BASE + "/eleicoes/2026/pesquisa-eleitoral-2026/"
LI_RE = re.compile(r"^\s*(.+?)\s*\(([^)]+)\)\s*:\s*([\d.,]+)\s*%")
PLAIN_RE = re.compile(r"^\s*([^:]{2,60}?)\s*:\s*([\d.,]+)\s*%")   # "Nulo/Branco: 7%"
_MONTHS_PT = {"janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
              "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}


def uf_slug(estado: str) -> str:
    return strip_accents(estado).lower().replace(" ", "-")


def discover(session: requests.Session, estados: dict, max_pages: int = 6, per_uf: int = 2) -> dict:
    """Pagina o índice e retorna {uf: [urls]} das matérias (novas primeiro).
    per_uf limita as páginas por estado (pega, ex., governador-only + senador-only)."""
    from bs4 import BeautifulSoup
    slugs = {uf: uf_slug(nome) for uf, nome in estados.items()}
    found: dict = {}
    seen_slugs: set = set()
    for page in range(1, max_pages + 1):
        url = INDEX if page == 1 else f"{INDEX}{page}/"
        try:
            r = session.get(url, timeout=30)
        except requests.RequestException:
            break
        if r.status_code != 200:
            break
        soup = BeautifulSoup(r.text, "lxml")
        new_this_page = 0
        for a in soup.select('a[href*="pesquisa-eleitoral-2026/"]'):
            href = a.get("href") or ""
            if "#" in href or "presidente" in href:
                continue
            if not any(k in href for k in ("governador", "senador", "senado")):
                continue
            slug = href.rstrip("/").split("/")[-1]
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            new_this_page += 1
            matched = [(uf, s) for uf, s in slugs.items() if f"-{s}-" in href]
            if not matched:
                continue
            uf = max(matched, key=lambda t: len(t[1]))[0]
            full = href if href.startswith("http") else BASE + href
            lst = found.setdefault(uf, [])
            if full not in lst and len(lst) < per_uf:
                lst.append(full)
        if new_this_page == 0:
            break
    return found


def _pct(s: str) -> float | None:
    # separador órfão colado no número é typo da fonte ("Haddad (PT):,27%" = 27, não 0,27)
    s = s.strip(",.")
    try:
        return float(s.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def published_date(html: str, url: str) -> str:
    m = re.search(r'article:published_time"\s+content="(\d{4})-(\d{2})-(\d{2})', html)
    if m:
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    m = re.search(r"-(" + "|".join(_MONTHS_PT) + r")-(\d{4})", strip_accents(url).lower())
    if m:
        return f"{_MONTHS_PT[m.group(1)]:02d}/{m.group(2)}"  # mm/yyyy (fallback)
    return ""


SKIP_CTX = ("espontan", "nao definiu", "nao sabe", "nao soube",   # pesquisa espontânea
            "nao votaria", "rejei")                               # rejeição (soma >100)
_SKIP = tuple(strip_accents(k) for k in SKIP_CTX)

# contexto que indica simulação de 2º turno: "segundo turno" ou o padrão "Fulano X Beltrano"
_RUNOFF_CTX = ("segundo turno", "2o turno", "2 turno", "2º turno")
_VS = re.compile(r"\s+[xX×]\s+")

def pollster_from(url: str, html: str = "") -> str:
    """Instituto que fez a pesquisa — NÃO o portal que publicou.

    A Gazeta é veículo, não instituto: creditar tudo a "Gazeta do Povo" apaga a diferença
    entre Datafolha e Paraná Pesquisas e faz a média móvel tratar as duas como a mesma série.
    O slug da matéria começa pelo instituto; o texto é o plano B.
    """
    slug = url.rstrip("/").split("/")[-1]
    # só a parte antes do cargo: evita casar "para" (Pará) e afins no resto do slug
    cabeca = re.split(r"-(governador|senador|senado|presidente)-", slug)[0]
    return canon_pollster(cabeca) or canon_pollster(html[:20000]) or "instituto não identificado"


def collect_url(uf: str, roster_state: dict, url: str, session: requests.Session) -> list[PollRecord]:
    try:
        r = session.get(url, timeout=30)
    except requests.RequestException:
        return []
    return parse_html(uf, roster_state, r.text, url)


def _scenario(ctx_raw: str, ctx: str, n_cands: int) -> str:
    if any(k in ctx for k in (strip_accents(x) for x in _RUNOFF_CTX)):
        return RUNOFF
    # "Fulano X Beltrano" com só dois nomes na lista = simulação de 2º turno
    if n_cands == 2 and _VS.search(ctx_raw):
        return RUNOFF
    return FIRST_ROUND


def parse_html(uf: str, roster_state: dict, html: str, url: str) -> list[PollRecord]:
    from bs4 import BeautifulSoup
    date = published_date(html, url)
    pollster = pollster_from(url, html)
    soup = BeautifulSoup(html, "lxml")
    # agrupa por lista (ul), na ordem do documento; pula espontânea/rejeição pelo contexto
    uls = []
    for li in soup.select('li[class*="postListItem"]'):
        ul = li.find_parent(["ul", "ol"])
        if ul is not None and ul not in uls:
            uls.append(ul)
    records, seen = [], set()
    for ul in uls:
        prev = ul.find_previous(["p", "h2", "h3", "h4", "strong", "b"])
        ctx_raw = prev.get_text(" ", strip=True) if prev else ""
        ctx = strip_accents(ctx_raw).lower()
        if any(k in ctx for k in _SKIP):
            continue

        # 1ª passada: lê a lista inteira para saber a base (válidos x totais) do cenário
        itens, soma_cands, brancos = [], 0.0, 0.0
        for li in ul.select('li[class*="postListItem"]'):
            txt = li.get_text(" ", strip=True)
            m = LI_RE.match(txt)
            if m:
                rotulo, partido, pct = m.group(1), m.group(2), _pct(m.group(3))
            else:
                # "Nulo/Branco: 7%" e "Outros: 2%" vêm sem partido entre parênteses
                m2 = PLAIN_RE.match(txt)
                if not m2:
                    continue
                rotulo, partido, pct = m2.group(1), None, _pct(m2.group(2))
            if pct is None:
                continue
            kind = option_kind(rotulo)
            if kind == "branco":
                brancos += pct
            else:
                soma_cands += pct          # inclui "Outros" (é voto válido)
                if kind == "candidato":
                    itens.append((rotulo, partido, pct))
        if not itens:
            continue
        nomes = [i[0] for i in itens]
        cenario = _scenario(ctx_raw, ctx, len(nomes))
        # sem branco/indeciso e somando ~100 -> o instituto já publicou em válidos
        base = BASE_VALID if (brancos < 0.5 and abs(soma_cands - 100) < 2.5) else BASE_TOTAL

        # a lista inteira é de UM cargo: decide pela maioria dos casamentos e prende nele
        tally: dict = {}
        for nome, partido, _ in itens:
            hit = match_candidate(nome, partido, roster_state)
            if hit:
                tally[hit[1]] = tally.get(hit[1], 0) + 1
        if not tally:
            continue
        cargo_ul = max(tally, key=tally.get)

        for nome, partido, pct in itens:
            hit = match_candidate(nome, partido, roster_state, only_cargo=cargo_ul)
            if not hit:
                continue
            cand, cargo = hit
            key = (cargo, cand["name"], cenario)
            if key in seen:                # 1º cenário estimulado de cada tipo
                continue
            seen.add(key)
            records.append(PollRecord(
                uf, cargo, cand["name"], cand["party"], pct, pollster, date, "gazeta", url,
                scenario=cenario, base=base, sum_cands=round(soma_cands, 1),
                undecided=round(brancos, 1),
                opponents=tuple(nomes) if cenario == RUNOFF else ()))
    return records
