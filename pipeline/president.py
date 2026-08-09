"""Agregador nacional presidencial (poll-of-polls) a partir das pesquisas da Gazeta.

Cada matéria "<instituto>-presidente-<mês>-2026" traz listas <li>Lula (PT): 39%</li> no
cenário estimulado de 1º turno e cenários de 2º turno (Lula x Flávio etc.). Fazemos a média
das pesquisas mais recentes (poll-of-polls) e uma tendência simples.
"""
from __future__ import annotations

import re
from collections import defaultdict

import requests

from pipeline.sources import gazeta as gz
from pipeline.sources.base import strip_accents

BLOC_BY_NAME = (("lula", "Lula"), ("flavio", "Flávio"), ("caiado", "Caiado"), ("zema", "Zema"))


def _bloc(name: str) -> str:
    n = strip_accents(name).lower()
    for key, bloc in BLOC_BY_NAME:
        if key in n:
            return bloc
    return "Indefinido"


def _recency(d: str | None) -> tuple[int, int, int]:
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", d or "")
    if m:
        return (int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = re.match(r"(\d{1,2})/(\d{4})", d or "")
    return (int(m.group(2)), int(m.group(1)), 0) if m else (0, 0, 0)


def discover_pres(session: requests.Session, max_pages: int = 2, limit: int = 8) -> list[str]:
    from bs4 import BeautifulSoup
    urls, seen = [], set()
    for page in range(1, max_pages + 1):
        u = gz.INDEX if page == 1 else f"{gz.INDEX}{page}/"
        try:
            r = session.get(u, timeout=30)
        except requests.RequestException:
            break
        if r.status_code != 200:
            break
        for a in BeautifulSoup(r.text, "lxml").select('a[href*="pesquisa-eleitoral-2026/"]'):
            href = a.get("href") or ""
            if "#" in href or "presidente" not in href:
                continue
            slug = href.rstrip("/").split("/")[-1]
            if slug in seen or slug.startswith("o-que-dizem"):
                continue
            seen.add(slug)
            urls.append(href if href.startswith("http") else gz.BASE + href)
        if len(urls) >= limit:
            break
    return urls[:limit]


def _lists(html: str):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    uls, out = [], []
    for li in soup.select('li[class*="postListItem"]'):
        ul = li.find_parent(["ul", "ol"])
        if ul is not None and ul not in uls:
            uls.append(ul)
    for ul in uls:
        prev = ul.find_previous(["p", "h2", "h3", "h4", "strong", "b"])
        ctx = strip_accents(prev.get_text(" ", strip=True)).lower() if prev else ""
        items = []
        for li in ul.select('li[class*="postListItem"]'):
            m = gz.LI_RE.match(li.get_text(" ", strip=True))
            if m:
                pct = gz._pct(m.group(3))
                if pct is not None:
                    items.append((m.group(1).strip(), m.group(2).strip(), pct))
        out.append((ctx, items))
    return out


def pollster_from_url(url: str) -> str:
    slug = url.rstrip("/").split("/")[-1]
    return slug.split("-presidente")[0].replace("-", " ").title()


def parse_poll(html: str, url: str) -> dict:
    date = gz.published_date(html, url)
    first, runoff = [], []
    for ctx, items in _lists(html):
        if not first and "estimulad" in ctx and "espontan" not in ctx and " x " not in ctx:
            first = items
        if not runoff and "lula x flavio" in ctx:
            runoff = items
    return {"pollster": pollster_from_url(url), "date": date, "first_round": first, "runoff": runoff}


def aggregate(polls: list[dict], window: int = 6) -> dict:
    polls = [p for p in polls if p["first_round"]]
    polls.sort(key=lambda p: _recency(p["date"]), reverse=True)
    win = polls[:window]
    if not win:
        return {}
    # 1º turno: média por candidato
    fr, party = defaultdict(list), {}
    for p in win:
        for name, pty, pct in p["first_round"]:
            fr[name].append(pct)
            party.setdefault(name, pty)
    min_n = max(2, len(win) // 2)   # candidato precisa aparecer em ao menos metade das pesquisas
    first = sorted(
        [{"name": n, "party": party[n], "bloc": _bloc(n),
          "avg": round(sum(v) / len(v), 1), "n": len(v)}
         for n, v in fr.items() if len(v) >= min_n],
        key=lambda c: -c["avg"])[:8]
    # 2º turno Lula x Flávio
    ro = defaultdict(list)
    for p in win:
        for name, _pty, pct in p["runoff"]:
            b = _bloc(name)
            if b in ("Lula", "Flávio"):
                ro[b].append(pct)
    runoff = {b: round(sum(v) / len(v), 1) for b, v in ro.items() if v}
    # tendência (mais antigo -> mais novo na janela) para Lula e Flávio no 1º turno
    trend = {}
    for b in ("Lula", "Flávio"):
        series = []
        for p in reversed(win):
            for name, _pty, pct in p["first_round"]:
                if _bloc(name) == b:
                    series.append(pct)
        if len(series) >= 2:
            trend[b] = round(series[-1] - series[0], 1)
    used = [{"pollster": p["pollster"], "date": p["date"],
             "Lula": next((v for n, _q, v in p["first_round"] if _bloc(n) == "Lula"), None),
             "Flávio": next((v for n, _q, v in p["first_round"] if _bloc(n) == "Flávio"), None)}
            for p in win]
    return {
        "polls": len(win),
        "institutos": [p["pollster"] for p in win],
        "latest_date": win[0]["date"],
        "first_round": first,
        "runoff": runoff,
        "trend": trend,
        "used": used,
    }


def collect(session: requests.Session) -> dict:
    polls = []
    for url in discover_pres(session):
        try:
            html = session.get(url, timeout=30).text
        except requests.RequestException:
            continue
        p = parse_poll(html, url)
        if p["first_round"]:
            polls.append(p)
    return aggregate(polls)
