"""Deterministic algebra step-check for the guided exchange.

When a student pastes working, this module pulls the equality chains out of that
*one* message, asks `app.cas` whether each consecutive step preserves the
expression, and formats the verdicts as a short block for the tutor's system
prompt. It never calls the provider (so it adds no provider cost), never touches
the DB or the clock, and never raises on student input — a message with nothing
checkable yields `None`.

The block is reference material for the model, exactly like the problem context:
`MentisQService.post_message` appends it to the system message for the *next*
turn only. It is not persisted and must never be read back to the student
verbatim (the header says so, and the guided prompt already forbids quoting
reference material).

Scope is deliberately narrow, because a feature that exists to stop the tutor
misleading a student must not mislead one itself:

- Only the latest student turn is scanned; history is untouched.
- A "chain" is expressions joined by ``=`` — several on one line (``a = b = c``)
  or continued across lines by a leading ``=``. Consecutive plain lines are
  *not* joined; that is too ambiguous to trust.
- A chain is checked only when it has 3+ members, or was extended by a
  leading-``=`` continuation line. A lone ``a = b`` line is a conditional
  equation the student is *solving* (``2x + 4 = 10``), not an identity claim, and
  there is no reliable way to tell it apart from a wrong one-line simplification,
  so it is left alone. This does mean routine multi-line equation solving —
  separate ``a = b`` lines — goes unchecked; `app.cas` compares expressions, not
  equations, and a false ``INVALID`` on every equation a student writes would be
  worse than silence.
- A step is called ``INVALID`` only when the two sides are non-equivalent under
  *every* domain `app.cas` offers, so an identity that holds only for, say,
  positive ``x`` (``sqrt(x^2) = x``) is passed over in silence, not flagged.
- Any member that reads as prose (a 3+ letter run that is not a known function
  name) disqualifies its whole chain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.cas import check_equivalence

# Multi-letter names `app.cas` reads as functions — a member may contain one and
# still be an expression; any other 3+ letter run marks the member as prose.
# This is a prose screen, not a mirror of `app.cas`'s name table.
_FUNCTION_WORDS = {"sin", "cos", "tan", "exp", "log", "ln", "sqrt", "abs", "pi"}

# Names that are constants to `app.cas`, not free variables, so they must not be
# handed to it as `variables=`. `pi` is already covered by `_FUNCTION_WORDS`.
_RESERVED = _FUNCTION_WORDS | {"e"}

# A leading list/step marker on a working line: "- ", "* ", "•", "1) ", "2. ",
# "Step 3:". A bare "-" with no space is a minus sign, not a bullet, so it stays.
_LIST_PREFIX = re.compile(
    r"^\s*(?:[-*•]\s+|\d+[.)]\s+|[Ss]tep\s+\d+\s*[:.)]\s*)"
)

# An expression is letters/digits/operators only (a subset of `app.cas`'s own
# whitelist — no comma, since a member never has one). Prose like "I think" also
# passes this, which is why `_PROSE_RUN` screens words separately.
_MATHY = re.compile(r"^[A-Za-z0-9_.+\-*/^()\s]+$")
_PROSE_RUN = re.compile(r"[A-Za-z]{3,}")
_NAME = re.compile(r"[A-Za-z]+")

# Bounds so a huge paste can't turn into a huge amount of SymPy work; the check
# is "bounded to the latest turn's relations" by design.
_MAX_LINES = 40
_MAX_STEPS = 20

_HEADER = (
    "[Automated algebra check — deterministic, server-side. Reference only: do "
    "not show, quote, or read this block to the student. Use it to ground your "
    "reply; an INVALID line names the step to address.]"
)


@dataclass
class _Chain:
    """A run of expressions the student asserts are equal."""

    members: list[str] = field(default_factory=list)
    continued: bool = False  # extended by a leading-`=` line


@dataclass(frozen=True)
class _Verdict:
    step: int  # 1-based position of the second member in the working
    valid: bool
    detail: str  # "" when valid


def _clean_line(raw: str) -> str:
    line = raw.strip().strip("$").strip("`").strip()
    return _LIST_PREFIX.sub("", line, count=1).strip()


def _split_eq(text: str) -> list[str]:
    """`text` on `=`, trimmed, empty pieces dropped (so `a == b` and a trailing
    `=` behave)."""
    return [part.strip() for part in text.split("=") if part.strip()]


def _is_mathy(member: str) -> bool:
    if not member or not _MATHY.match(member):
        return False
    return all(
        run.lower() in _FUNCTION_WORDS for run in _PROSE_RUN.findall(member)
    )


def _extract_chains(text: str) -> list[_Chain]:
    chains: list[_Chain] = []
    current: _Chain | None = None
    for raw in text.splitlines()[:_MAX_LINES]:
        line = _clean_line(raw)
        if not line:
            continue
        parts = _split_eq(line)
        if not parts:
            continue
        if line.startswith("=") and current is not None:
            current.members.extend(parts)
            current.continued = True
        else:
            current = _Chain(members=list(parts), continued=line.startswith("="))
            chains.append(current)
    return chains


def _checkable(chain: _Chain) -> bool:
    if len(chain.members) < 2:
        return False
    if len(chain.members) < 3 and not chain.continued:
        return False
    return all(_is_mathy(member) for member in chain.members)


def _free_variables(members: list[str]) -> list[str]:
    names: set[str] = set()
    for member in members:
        for token in _NAME.findall(member):
            if token.lower() not in _RESERVED:
                names.add(token)
    return sorted(names)


def _compare(a: str, b: str, variables: list[str]) -> bool | None:
    """`True` = a sound step, `False` = wrong under every domain, `None` = stay
    silent — either side unreadable, or the sides match only on a restricted
    domain (which we can't assume applies here)."""
    real = check_equivalence(a, b, variables=variables, domain="real")
    if not real.parsed:
        return None
    if real.equivalent:
        return True
    for domain in ("positive", "complex"):
        if check_equivalence(a, b, variables=variables, domain=domain):
            return None
    return False


def _verdicts(chains: list[_Chain]) -> list[_Verdict]:
    out: list[_Verdict] = []
    step = 1  # the running expression count across the whole turn's working
    for chain in chains:
        variables = _free_variables(chain.members)
        for prev, cur in zip(chain.members, chain.members[1:]):
            step += 1
            outcome = _compare(prev, cur, variables)
            if outcome is None:
                continue
            out.append(
                _Verdict(step, True, "")
                if outcome
                else _Verdict(
                    step, False, f'"{prev}" is not equivalent to "{cur}"'
                )
            )
            if len(out) >= _MAX_STEPS:
                return out
    return out


def check_working(text: str) -> str | None:
    """The verdict block for `text`'s working, or `None` when nothing checkable
    parsed.

    The one entry point. Pure and total: any input either yields a block of
    `- step N: VALID` / `- step N: INVALID — …` lines under `_HEADER`, or
    `None`.
    """
    if not text or "=" not in text:
        return None
    chains = [chain for chain in _extract_chains(text) if _checkable(chain)]
    verdicts = _verdicts(chains) if chains else []
    if not verdicts:
        return None
    lines = [_HEADER]
    for verdict in verdicts:
        if verdict.valid:
            lines.append(f"- step {verdict.step}: VALID")
        else:
            lines.append(f"- step {verdict.step}: INVALID — {verdict.detail}")
    return "\n".join(lines)
