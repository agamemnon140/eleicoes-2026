"""Raspa a série temporal de pesquisas ao Senado de 2018 da Wikipedia PT (para backtest OOS).

Páginas "Eleições estaduais em <Estado> em 2018" têm, sob "Para senador", uma tabela com
cabeçalho Data | Instituto | Margem | <Sobrenome (Partido)>... e várias linhas ao longo do
tempo. Extraímos a série (data ordenável + % por candidato) para testar momentum sem hindsight.
"""
from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

from pipeline.sources.base import strip_accents

UA = {"User-Agent": "eleicoes-2026-bot/0.1 (github.com/agamemnon140/eleicoes-2026)"}
PT_MONTHS = {"janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
             "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
             "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6, "jul": 7, "ago": 8,
             "set": 9, "out": 10, "nov": 11, "dez": 12}
HEADER_NONCAND = ("data", "instituto", "margem", "contratante", "ref", "lider", "líder",
                  "não sabe", "nao sabe", "brancos", "nulos", "outros", "vantagem")


def fetch_state(estado: str, year: int, session: requests.Session) -> str | None:
    for title in (f"Eleições estaduais em {estado} em {year}",
                  f"Eleições estaduais no {estado} em {year}"):
        try:
            r = session.get(f"https://pt.wikipedia.org/wiki/{title}", timeout=30)
        except requests.RequestException:
            continue
        if r.status_code == 200 and "wikitable" in r.text:
            return r.text
    return None


def date_key(s: str) -> tuple[int, int]:
    """(mês, dia) do fim do período. (0,0) se não parsear."""
    s = strip_accents(s).lower()
    mon = None
    for name, num in PT_MONTHS.items():
        if re.search(rf"\b{name}", s):
            mon = num
            break
    days = re.findall(r"\d{1,2}", s.split(str(mon))[0] if mon and str(mon) in s else s)
    day = int(days[-1]) if days else 0
    # formato dd/mm
    m = re.search(r"(\d{1,2})[/.](\d{1,2})", s)
    if m and mon is None:
        return (int(m.group(2)), int(m.group(1)))
    return (mon or 0, day)


def table_to_grid(table) -> list[list[str]]:
    """Expande a tabela num grid resolvendo rowspan/colspan (células alinhadas)."""
    rows = table.find_all("tr")
    occ: dict = {}
    for r, tr in enumerate(rows):
        c = 0
        for cell in tr.find_all(["th", "td"]):
            while (r, c) in occ:
                c += 1
            txt = cell.get_text(" ", strip=True)
            cs = int(cell.get("colspan", 1) or 1)
            rsp = int(cell.get("rowspan", 1) or 1)
            for dc in range(cs):
                for dr in range(rsp):
                    occ[(r + dr, c + dc)] = txt
            c += cs
    if not occ:
        return []
    maxc = max(cc for _r, cc in occ) + 1
    return [[occ.get((r, c), "") for c in range(maxc)] for r in range(len(rows))]


def _resolve_cand_cols(grid: list[list[str]]) -> dict:
    """Colunas de candidato = 'Sobrenome (Partido)' no header de 1 ou 2 linhas."""
    cols = {}
    ncol = max(len(grid[0]), len(grid[1]) if len(grid) > 1 else 0)
    for c in range(ncol):
        for hrow in (1, 0) if len(grid) > 1 else (0,):
            label = grid[hrow][c] if c < len(grid[hrow]) else ""
            ll = strip_accents(label).lower().strip()
            if not ll or "candidato" in ll or any(k in ll for k in HEADER_NONCAND):
                continue
            m = re.match(r"(.+?)\s*\(([^)]+)\)", label)
            if m:
                cols[c] = (m.group(1).strip(), m.group(2).strip())
                break
    return cols


def parse_senate_polls(html: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    for t in soup.select("table.wikitable"):
        header0 = " ".join(strip_accents(c.get_text(" ", strip=True)).lower()
                           for c in (t.find("tr").find_all(["th", "td"]) if t.find("tr") else []))
        if "instituto" not in header0 and "data" not in header0 and "divulgacao" not in header0:
            continue
        heading = t.find_previous(["h2", "h3", "h4"])
        if "senad" not in (strip_accents(heading.get_text(" ", strip=True)).lower() if heading else ""):
            continue
        grid = table_to_grid(t)
        if len(grid) < 3:
            continue
        cols = _resolve_cand_cols(grid)
        if len(cols) < 2:
            continue
        series = []
        for row in grid:
            dk = date_key(row[0])
            if dk == (0, 0):
                continue
            pcts = {}
            for c, (name, _party) in cols.items():
                if c < len(row):
                    v = row[c].replace("%", "").replace(",", ".").replace("–", "").replace("—", "").strip()
                    try:
                        pcts[name] = float(v)
                    except ValueError:
                        pass
            if len(pcts) >= 2:
                series.append({"date": row[0], "key": dk, "pcts": pcts})
        if series:
            return {"candidates": {n: p for n, p in cols.values()}, "series": series}
    return None


def parse_senate_results(html: str, seats: int):
    """Top-N eleitos (por votos) na tabela de RESULTADO do Senado. Retorna nomes completos."""
    soup = BeautifulSoup(html, "lxml")
    best, best_rows = None, 0
    for t in soup.select("table.wikitable"):
        grid = table_to_grid(t)
        if len(grid) < 2:
            continue
        header = [strip_accents(h).lower() for h in grid[0]]
        hjoined = " ".join(header)
        heading = t.find_previous(["h2", "h3", "h4"])
        htx = strip_accents(heading.get_text(" ", strip=True)).lower() if heading else ""
        is_sen = ("senad" in htx or "senador" in hjoined)
        if not is_sen or "instituto" in hjoined:
            continue
        if any(x in htx + " " + hjoined for x in ("governad", "deputad", "presiden")):
            continue
        vcol = next((i for i, h in enumerate(header)
                     if ("votos" in h or "votacao" in h) and "%" not in h and "porcent" not in h), None)
        ncol = next((i for i, h in enumerate(header)
                     if any(k in h for k in ("candidato", "senador", "nome"))), None)
        if vcol is None or ncol is None:
            continue
        rows = []
        for row in grid[1:]:
            if vcol >= len(row) or ncol >= len(row):
                continue
            vd = re.sub(r"[^\d]", "", row[vcol])
            name = re.sub(r"\[.*?\]", "", row[ncol]).strip()
            nl = strip_accents(name).lower()
            if len(vd) < 4 or not name or nl.startswith(("tota", "branco", "nulo", "absten")):
                continue
            rows.append((name, int(vd)))
        if len(rows) > best_rows:
            best, best_rows = rows, len(rows)
    if not best or best_rows < seats:
        return None
    best.sort(key=lambda r: -r[1])
    return [n for n, _ in best[:seats]]


if __name__ == "__main__":
    import sys
    estados = ["São Paulo", "Minas Gerais", "Rio Grande do Sul", "Bahia", "Paraná",
               "Rio de Janeiro", "Pernambuco", "Ceará", "Goiás", "Santa Catarina",
               "Pará", "Maranhão", "Espírito Santo", "Amazonas", "Mato Grosso"]
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2018
    s = requests.Session(); s.headers.update(UA)
    ok = 0
    for e in estados:
        html = fetch_state(e, year, s)
        res = parse_senate_polls(html) if html else None
        if res:
            ok += 1
            last = sorted(res["series"], key=lambda r: r["key"])[-1]
            print(f"{e:18} {len(res['series']):2} pesquisas | cands={list(res['candidates'])[:5]} | "
                  f"última {last['date']}: {dict(list(last['pcts'].items())[:4])}")
        else:
            print(f"{e:18} — sem tabela de pesquisa de Senado")
    print(f"\nCobertura: {ok}/{len(estados)} estados")
