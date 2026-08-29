"""CAS — server-side symbolic equivalence, the pure counterpart to `grading`.

`app.cas.check_equivalence(expr_a, expr_b, *, variables=..., domain=...)`
decides whether two expression *strings* denote the same function, never by
string comparison. It is deterministic, does no I/O, and never raises on bad
input — an unparseable side yields a `parse_error` result, a well-formed but
different side a `not_equivalent` one.

Downstream: the `symbolic` question grader and the MentisQ step-check both call
`check_equivalence` and branch on `EquivalenceResult`.
"""

from app.cas.equivalence import (
    EquivalenceOutcome,
    EquivalenceResult,
    check_equivalence,
    expression_parses,
)

__all__ = [
    "EquivalenceOutcome",
    "EquivalenceResult",
    "check_equivalence",
    "expression_parses",
]
