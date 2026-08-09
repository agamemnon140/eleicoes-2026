"""Guardrails: decide se um valor coletado pode substituir o último bom.

Se reprovar, o coletor mantém o valor anterior e marca o registro como possivelmente
desatualizado (stale) — o site nunca publica lixo óbvio de um parser quebrado.
"""
from __future__ import annotations

MAX_JUMP = 30.0   # p.p. — queda/subida maior que isso de uma semana pra outra é suspeita


def check(old: float | None, new: float | None) -> tuple[bool, str]:
    """Retorna (ok, motivo). Se não ok, não aplique o novo valor."""
    if new is None:
        return False, "sem valor"
    if new < 0 or new > 100:
        return False, "fora de 0–100"
    if old is not None and abs(new - old) > MAX_JUMP:
        return False, f"salto de {abs(new - old):.0f} p.p."
    return True, ""
