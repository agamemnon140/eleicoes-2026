"""Read the public JSON embedded in Plano Político's aggregator pages.

Only individual `recent_polls` are imported, never model projections/trajectories.
The published representation is retained: Senate shares are already normalized by
the provider and must not be described as original percentages from the institute.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re

from pipeline.sources.base import canon_pollster, option_kind, strip_accents

ROOT_URL = "https://planopolitico.com.br/agregador/"
PAGES = {"presidente": "Presidente", "governadores": "Governo", "senado": "Senado"}


def extract(html: str) -> dict:
    m = re.search(r'<script\b(?=[^>]*\bid=[\"\']agg-data[\"\'])[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise ValueError("Bloco público agg-data não encontrado")
    data = json.loads(m[1])
    if not isinstance(data, dict) or not data.get("generated_at"):
        raise ValueError("Estrutura agg-data inválida")
    return data


def canonical(name: str) -> str:
    name = " ".join(strip_accents(name).lower().split())
    return {"zema": "romeu zema", "escritor augusto cury": "augusto cury",
            "flavio": "flavio bolsonaro"}.get(name, name)


def normalize(raw: dict, uf: str, cargo: str, turn: str, page: str) -> dict:
    shares = raw.get("shares") or {}
    if not isinstance(shares, dict) or not shares:
        raise ValueError("Pesquisa sem shares")
    issues = []
    numeric = {k: v for k, v in shares.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
    if any(v is not None and (not isinstance(v, (int, float)) or isinstance(v, bool)) for v in shares.values()):
        issues.append("Percentual com tipo inválido")
    if any(not math.isfinite(v) or v < 0 or v > 100 for v in numeric.values()):
        issues.append("Percentual fora de 0–100")
    candidates = {k: v for k, v in numeric.items() if option_kind(k) != "branco"}
    total = sum(candidates.values())
    senate = cargo == "Senado"
    # Public Senate shares claim to be valid votes; a contradictory total is
    # quarantined, not silently renormalized. Null = not measured, never zero.
    if senate and not 98 <= total <= 102:
        issues.append("Soma dos votos válidos incompatível com 100%")
    if not senate and (sum(numeric.values()) > 102 or total <= 0):
        issues.append("Soma incompatível com percentual dos entrevistados")
    try:
        date = dt.date.fromisoformat(raw.get("dt_fim", ""))
    except (ValueError, TypeError):
        date = None
        issues.append("Fim do campo ausente ou inválido")
    names = sorted(canonical(k) for k in candidates if option_kind(k) == "candidato")
    signature = "|".join(names)
    identity = [raw.get("registro") or raw.get("url") or raw.get("instituto"), uf,
                cargo, turn, signature, raw.get("dt_fim") if not raw.get("registro") else None]
    pid = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()[:20]
    return {
        "id": pid, "uf": uf, "cargo": cargo, "scenario": turn,
        "scenario_key": signature, "registro": raw.get("registro"),
        "pollster": canon_pollster(raw.get("instituto")) or raw.get("instituto") or "Não informado",
        "field_start": raw.get("dt_inicio"), "field_end": raw.get("dt_fim"),
        "published_at": raw.get("dt_divulgacao"), "sample_size": raw.get("n"),
        "method": raw.get("method"), "url": raw.get("url") or "",
        "source": "Plano Político", "source_url": page,
        "base": "válidos" if senate else "totais",
        "vote_format": "voto único normalizado pelo Plano Político" if senate else "voto único",
        "shares": shares, "sum_cands": total,
        "undecided": raw.get("indecisos", sum(v for k, v in numeric.items() if option_kind(k) == "branco")),
        "valid_shares": {k: round(v if senate else v / total * 100, 4)
                         for k, v in candidates.items()} if total > 0 and not issues else {},
        "eligible": not issues, "issues": issues,
        "date": date.strftime("%d/%m/%Y") if date else "",
    }


def parse_page(data: dict, section: str) -> list[dict]:
    page = ROOT_URL + section + "/"
    cargo = PAGES[section]
    bundles = []
    if section == "presidente":
        bundles.append((None, data["presidente_t1"]["recent_polls"]))
    else:
        key = "governador" if section == "governadores" else "senado"
        bundles.extend((uf, st["recent_polls"]) for uf, st in data[key]["states"].items())
    polls = {}
    for uf, bundle in bundles:
        for turn, rows in bundle.items():
            if turn not in ("t1", "t2"):
                continue
            for raw in rows:
                scope = uf or raw.get("scope")
                if not scope:
                    raise ValueError("Pesquisa sem abrangência")
                p = normalize(raw, scope, cargo, "1º turno" if turn == "t1" else "2º turno", page)
                polls[p["id"]] = p
    if not polls:
        raise ValueError("Página sem pesquisas individuais reconhecidas")
    return list(polls.values())


def fetch(session, section: str) -> tuple[list[dict], str]:
    response = session.get(ROOT_URL + section + "/", timeout=45)
    response.raise_for_status()
    data = extract(response.content.decode("utf-8"))
    return parse_page(data, section), data["generated_at"]
