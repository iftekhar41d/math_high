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
  *not* joined into a chain; that is too ambiguous to trust as an identity
  claim.
- A *simplification chain* is checked only when it has 3+ members, or was
  extended by a leading-``=`` continuation line. A step is called ``INVALID``
  only when the two sides are non-equivalent under *every* domain `app.cas`
  offers, so an identity that holds only for, say, positive ``x``
  (``sqrt(x^2) = x``) is passed over in silence, not flagged.
- A run of 2+ *consecutive* single-line ``L = R`` lines (no leading ``=``) is an
  *equation chain* — the student solving an equation. For each adjacent pair the
  difference test asks `app.cas` whether ``L₁ − R₁`` is equivalent to
  ``L₂ − R₂``: equivalent → the same quantity was added to both sides (or the
  equation rearranged), a sound step → ``VALID``; anything else → **silent**. An
  equation chain never emits ``INVALID``: a non-equivalent difference can be a
  legal ``×``/``÷`` of both sides (``2x = 6`` → ``x = 3``) just as easily as an
  error, and `app.cas` compares expressions, not equations, so it can't tell
  them apart. A lone ``L = R`` line with no equation line after it injects
  nothing.
- Known gap: multiplicative equation steps and additive *errors* in an equation
  chain are still unverified — the difference test is VALID-or-silent by design.
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
class _Equation:
    """One single-line ``left = right`` the student wrote while solving."""

    left: str
    right: str


@dataclass
class _EquationRun:
    """Consecutive `_Equation` lines — the student solving one equation."""

    equations: list[_Equation] = field(default_factory=list)


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


def _is_lone_equation(chain: _Chain) -> bool:
    """A single-line ``L = R`` — exactly two mathy members, no continuation.
    On its own it is a conditional equation being solved; a run of them is an
    `_EquationRun`."""
    return (
        len(chain.members) == 2
        and not chain.continued
        and all(_is_mathy(member) for member in chain.members)
    )


def _flush_run(run: list[_Chain], items: list[_Chain | _EquationRun]) -> None:
    """Move `run` (consecutive lone ``L = R`` lines) onto `items`: as one
    `_EquationRun` when it is 2+ long, otherwise the lone chain unchanged. `run`
    is emptied."""
    if len(run) >= 2:
        items.append(
            _EquationRun([_Equation(c.members[0], c.members[1]) for c in run])
        )
    else:
        items.extend(run)
    run.clear()


def _partition(chains: list[_Chain]) -> list[_Chain | _EquationRun]:
    """Fold each maximal run of 2+ consecutive lone ``L = R`` lines into an
    `_EquationRun`; everything else (simplification chains, and a lone equation
    with nothing after it) passes through untouched, in order."""
    items: list[_Chain | _EquationRun] = []
    run: list[_Chain] = []
    for chain in chains:
        if _is_lone_equation(chain):
            run.append(chain)
            continue
        _flush_run(run, items)
        items.append(chain)
    _flush_run(run, items)
    return items


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


def _equation_step_provably_sound(
    prev: _Equation, cur: _Equation, variables: list[str]
) -> bool:
    """The difference test: `True` when moving from equation `prev` to `cur`
    leaves ``left − right`` unchanged (the same quantity added to both sides, or
    a pure rearrangement) — a provably sound step. `False` = stay silent: either
    side unreadable, or the difference changed (a legal ``×``/``÷`` step or an
    error — `app.cas` compares expressions, not equations, and can't tell which,
    so an equation chain never reports `INVALID`)."""
    a = f"({prev.left}) - ({prev.right})"
    b = f"({cur.left}) - ({cur.right})"
    return bool(check_equivalence(a, b, variables=variables, domain="real"))


def _equation_run_verdicts(
    run: _EquationRun, step: int, out: list[_Verdict]
) -> int:
    """Append a `VALID` verdict for each provably-sound adjacent pair; an
    unprovable step stays silent (an equation chain never emits `INVALID`).
    Returns the running step count, advanced past this run."""
    variables = _free_variables(
        [side for eq in run.equations for side in (eq.left, eq.right)]
    )
    for prev, cur in zip(run.equations, run.equations[1:]):
        step += 1
        if len(out) >= _MAX_STEPS:
            break
        if _equation_step_provably_sound(prev, cur, variables):
            out.append(_Verdict(step, True, ""))
    return step


def _chain_verdicts(chain: _Chain, step: int, out: list[_Verdict]) -> int:
    """Append a `VALID` / `INVALID` verdict for each decidable adjacent pair of a
    simplification chain; an unreadable or restricted-domain pair stays silent.
    Returns the running step count, advanced past this chain."""
    variables = _free_variables(chain.members)
    for prev, cur in zip(chain.members, chain.members[1:]):
        step += 1
        if len(out) >= _MAX_STEPS:
            break
        outcome = _compare(prev, cur, variables)
        if outcome is None:
            continue
        out.append(
            _Verdict(step, True, "")
            if outcome
            else _Verdict(step, False, f'"{prev}" is not equivalent to "{cur}"')
        )
    return step


def _verdicts(items: list[_Chain | _EquationRun]) -> list[_Verdict]:
    out: list[_Verdict] = []
    step = 1  # the running relation count across the whole turn's working
    for item in items:
        if len(out) >= _MAX_STEPS:
            break
        if isinstance(item, _EquationRun):
            step = _equation_run_verdicts(item, step, out)
        elif _checkable(item):
            step = _chain_verdicts(item, step, out)
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
    verdicts = _verdicts(_partition(_extract_chains(text)))
    if not verdicts:
        return None
    lines = [_HEADER]
    for verdict in verdicts:
        if verdict.valid:
            lines.append(f"- step {verdict.step}: VALID")
        else:
            lines.append(f"- step {verdict.step}: INVALID — {verdict.detail}")
    return "\n".join(lines)
