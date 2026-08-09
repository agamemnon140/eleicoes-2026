"""Coletor da Gazeta do Povo: páginas de pesquisa por estado (governador + senado).

O índice /eleicoes/2026/pesquisa-eleitoral-2026/ lista as matérias por estado; cada matéria
traz listas <li class="...postListItem">Nome (Partido): 48,9%</li> com os percentuais.
Cobre os estados que a Wikipedia não tabula (BA, CE, RJ etc.).
"""
from __future__ import annotations

import re

import requests

from pipeline.sources.base import PollRecord, match_candidate, strip_accents

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
BASE = "https://www.gazetadopovo.com.br"
INDEX = BASE + "/eleicoes/2026/pesquisa-eleitoral-2026/"
LI_RE = re.compile(r"^\s*(.+?)\s*\(([^)]+)\)\s*:\s*([\d.,]+)\s*%")
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
            "segundo turno", "2o turno", "2 turno")               # 2º turno
_SKIP = tuple(strip_accents(k) for k in SKIP_CTX)


def collect_url(uf: str, roster_state: dict, url: str, session: requests.Session) -> list[PollRecord]:
    try:
        r = session.get(url, timeout=30)
    except requests.RequestException:
        return []
    return parse_html(uf, roster_state, r.text, url)


def parse_html(uf: str, roster_state: dict, html: str, url: str) -> list[PollRecord]:
    from bs4 import BeautifulSoup
    date = published_date(html, url)
    soup = BeautifulSoup(html, "lxml")
    # agrupa por lista (ul), na ordem do documento; pula espontânea/2º turno pelo contexto
    uls = []
    for li in soup.select('li[class*="postListItem"]'):
        ul = li.find_parent(["ul", "ol"])
        if ul is not None and ul not in uls:
            uls.append(ul)
    records, seen = [], set()
    for ul in uls:
        prev = ul.find_previous(["p", "h2", "h3", "h4", "strong", "b"])
        ctx = strip_accents(prev.get_text(" ", strip=True)).lower() if prev else ""
        if any(k in ctx for k in _SKIP):
            continue
        for li in ul.select('li[class*="postListItem"]'):
            m = LI_RE.match(li.get_text(" ", strip=True))
            if not m:
                continue
            pct = _pct(m.group(3))
            if pct is None:
                continue
            hit = match_candidate(m.group(1), m.group(2), roster_state)
            if not hit:
                continue
            cand, cargo = hit
            key = (cargo, cand["name"])
            if key in seen:                # 1º cenário estimulado por candidato
                continue
            seen.add(key)
            records.append(PollRecord(uf, cargo, cand["name"], cand["party"], pct,
                                       "Gazeta do Povo", date, "gazeta"))
    return records
