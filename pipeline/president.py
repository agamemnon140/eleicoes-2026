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
    """Instituto da pesquisa presidencial, no mesmo nome canônico das estaduais.

    Sem isso o `.title()` do slug gera "Cnt Mda" e "Genial Quaest" enquanto as estaduais
    dizem "CNT/MDA" e "Quaest" — o mesmo instituto com dois nomes no registro.
    """
    canon = gz.pollster_from(url)
    if canon != "instituto não identificado":
        return canon
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
    return {"pollster": pollster_from_url(url), "date": date, "url": url,
            "first_round": first, "runoff": runoff}


def state_scoped(url: str, estados: dict) -> bool:
    """Matéria presidencial recortada POR ESTADO (ex.: …-presidente-agosto-26-sp-mg-rj-pe-df).

    Esses números medem UM eleitorado estadual: entrar no poll-of-polls nacional
    contamina a média — a lista de SP entraria como se fosse o Brasil, e com o maior
    peso por ser a mais recente. O slug denuncia: siglas de UF ou nome de estado.
    """
    slug = "-" + strip_accents(url.rstrip("/").split("/")[-1]).lower() + "-"
    if any(f"-{gz.uf_slug(nome)}-" in slug for nome in (estados or {}).values()):
        return True
    toks = set(slug.strip("-").split("-"))
    return any(uf.lower() in toks for uf in (estados or {}))


_RUNOFF_HDR = ("segundo turno", "2o turno", "2 turno")


def _uf_from_ctx(ctx: str, estados: dict) -> str | None:
    """UF do cabeçalho da lista ('São Paulo - Pesquisa estimulada'). ctx já vem normalizado."""
    for uf, nome in estados.items():
        if ctx.startswith(strip_accents(nome).lower()):
            return uf
    return None


def parse_state_poll(html: str, url: str, estados: dict) -> dict:
    """Matéria multi-estado -> {uf: {pollster, date, url, first_round, runoff}}.

    `first_round`/`runoff` são {bloco: %} — só os 4 blocos presidenciais entram, porque é
    isso que o pres_lean acompanha. Estado pode vir só com 2º turno (RJ/PE/DF na Datafolha
    de ago/26); quem consome decide o que fazer com cada cenário — aqui não se mistura.
    """
    date = gz.published_date(html, url)
    pollster = pollster_from_url(url)
    out: dict = {}
    for ctx, items in _lists(html):
        uf = _uf_from_ctx(ctx, estados)
        if not uf or not items:
            continue
        by_bloc: dict = {}
        for name, _party, pct in items:
            b = _bloc(name)
            if b != "Indefinido" and b not in by_bloc:
                by_bloc[b] = pct
        if not by_bloc:
            continue
        e = out.setdefault(uf, {"pollster": pollster, "date": date, "url": url,
                                "first_round": None, "runoff": None})
        if any(k in ctx for k in _RUNOFF_HDR):
            if e["runoff"] is None and "Lula" in by_bloc and "Flávio" in by_bloc:
                e["runoff"] = {"Lula": by_bloc["Lula"], "Flávio": by_bloc["Flávio"]}
        elif "estimulad" in ctx and "espontan" not in ctx:
            if e["first_round"] is None:
                e["first_round"] = by_bloc
    return {uf: e for uf, e in out.items() if e["first_round"] or e["runoff"]}


HALFLIFE_DAYS = 14   # meia-vida do peso por recência no agregado presidencial


def _pord(d: str | None) -> int:
    y, m, dd = _recency(d)
    return y * 365 + m * 30 + dd


def aggregate(polls: list[dict], window: int = 6) -> dict:
    polls = [p for p in polls if p["first_round"]]
    polls.sort(key=lambda p: _recency(p["date"]), reverse=True)
    win = polls[:window]
    if not win:
        return {}
    top = max((_pord(p["date"]) for p in win), default=0)

    def wof(p: dict) -> float:
        return 0.5 ** (max(0, top - _pord(p["date"])) / HALFLIFE_DAYS)

    # 1º turno: média PONDERADA POR RECÊNCIA por candidato
    fr, frw, cnt, party = defaultdict(float), defaultdict(float), defaultdict(int), {}
    for p in win:
        w = wof(p)
        for name, pty, pct in p["first_round"]:
            fr[name] += w * pct
            frw[name] += w
            cnt[name] += 1
            party.setdefault(name, pty)
    min_n = max(2, len(win) // 2)   # candidato precisa aparecer em ao menos metade das pesquisas
    first = sorted(
        [{"name": n, "party": party[n], "bloc": _bloc(n),
          "avg": round(fr[n] / frw[n], 1), "n": cnt[n]}
         for n in fr if cnt[n] >= min_n],
        key=lambda c: -c["avg"])[:8]
    # 2º turno Lula x Flávio (ponderado)
    ro, row = defaultdict(float), defaultdict(float)
    for p in win:
        w = wof(p)
        for name, _pty, pct in p["runoff"]:
            b = _bloc(name)
            if b in ("Lula", "Flávio"):
                ro[b] += w * pct
                row[b] += w
    runoff = {b: round(ro[b] / row[b], 1) for b in ro if row[b]}
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
    wsum = sum(wof(p) for p in win) or 1.0
    used = [{"pollster": p["pollster"], "date": p["date"], "url": p.get("url", ""),
             "weight": round(wof(p) / wsum, 3),
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


def collect_all(session: requests.Session, estados: dict | None = None) -> tuple[dict, list]:
    """Agregado nacional + leituras presidenciais POR ESTADO.

    Retorna (nacional, estaduais); estaduais é uma lista de dicts com "uf" — matérias
    recortadas por estado saem do poll-of-polls nacional e entram aqui.
    """
    polls, states = [], []
    for url in discover_pres(session):
        try:
            html = session.get(url, timeout=30).text
        except requests.RequestException:
            continue
        if estados and state_scoped(url, estados):
            for uf, e in parse_state_poll(html, url, estados).items():
                states.append({"uf": uf, **e})
            continue
        p = parse_poll(html, url)
        if p["first_round"]:
            polls.append(p)
    return aggregate(polls), states


def collect(session: requests.Session) -> dict:
    return collect_all(session)[0]
