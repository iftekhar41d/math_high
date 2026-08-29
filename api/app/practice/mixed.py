"""Question selection for `mixed` practice mode — pure, deterministic given its
`rng`, no DB / clock / network (in the mould of `grading.py` and `timed.py`).

`select_mixed_questions(...)` takes the scope's candidate Questions, the
student's cached per-SkillTag mastery, a target size, and a seeded
`random.Random`, and returns the ordered ids of the frozen set. The weighting is
fixed at this one call — there is no within-session adaptation (spec §"Mixed
selection").

Two regimes:

- **Weighted** (``skill_mastery`` is non-empty). The caller passes only the
  scope's SkillTags, so this means the student has data for at least one skill
  *in this scope*. Each SkillTag carries weight ``1 - mastery`` (floored so a
  mastered skill is never fully excluded); a SkillTag with no snapshot is
  neutral. A Question's weight is the mean of its tags' weights (an untagged
  Question falls back to the mean weight applied across the candidate set's
  tags). The set is drawn without replacement, weighted, via Efraimidis–Spirakis
  — so low-mastery skills are over-represented but the draw is still stochastic.
- **Cold start** (``skill_mastery`` empty — no in-scope mastery data): even
  SkillTag coverage — round-robin across the SkillTags, each tag's Questions
  taken difficulty-ascending — then any untagged Questions to fill the gap.

Either way the returned set is ordered difficulty-ascending (then by id), so the
run opens gently.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from app.models import DIFFICULTY_EASY, DIFFICULTY_HARD, DIFFICULTY_MEDIUM

# The default target size of a mixed run (spec "Locked default values":
# Mixed practice `question_count`: 10). A named constant, not a `Setting` —
# tune against pilot data later.
DEFAULT_MIXED_QUESTION_COUNT = 10

# A fully-mastered SkillTag still contributes this much to the draw, so a mixed
# run never collapses into a single-skill drill.
_MIN_SKILL_WEIGHT = 0.05
# Weight for a SkillTag the student has no snapshot for yet — neither favoured
# nor starved relative to the ones they do.
_NEUTRAL_SKILL_WEIGHT = 0.5

_DIFFICULTY_RANK = {DIFFICULTY_EASY: 0, DIFFICULTY_MEDIUM: 1, DIFFICULTY_HARD: 2}


@dataclass(frozen=True)
class Candidate:
    """One Question eligible for a mixed run: its id, its difficulty, and the
    ids of the SkillTags it carries (container-level for a `multi_part`)."""

    question_id: int
    difficulty: str
    skill_tag_ids: tuple[int, ...]


def _difficulty_key(c: Candidate) -> tuple[int, int]:
    return (_DIFFICULTY_RANK.get(c.difficulty, len(_DIFFICULTY_RANK)), c.question_id)


def _skill_weight(mastery: float) -> float:
    return max(_MIN_SKILL_WEIGHT, 1.0 - mastery)


def _candidate_weight(
    c: Candidate, tag_weights: dict[int, float], fallback: float
) -> float:
    ws = [tag_weights.get(t, _NEUTRAL_SKILL_WEIGHT) for t in c.skill_tag_ids]
    if not ws:
        return fallback
    return sum(ws) / len(ws)


def _weighted_sample(
    candidates: list[Candidate],
    weights: list[float],
    k: int,
    rng: random.Random,
) -> list[Candidate]:
    """Efraimidis–Spirakis A-Res: key each item ``u ** (1 / w)`` for a fresh
    uniform ``u``, keep the k largest keys. A weighted sample without
    replacement, deterministic for a seeded `rng`."""
    keyed: list[tuple[float, int, Candidate]] = []
    for i, (c, w) in enumerate(zip(candidates, weights)):
        key = rng.random() ** (1.0 / max(w, 1e-9))
        keyed.append((key, i, c))
    keyed.sort(key=lambda t: (t[0], -t[1]), reverse=True)
    return [c for _, _, c in keyed[:k]]


def _cold_start(candidates: list[Candidate], k: int) -> list[int]:
    by_tag: dict[int, list[Candidate]] = {}
    for c in candidates:
        for t in c.skill_tag_ids:
            by_tag.setdefault(t, []).append(c)
    for lst in by_tag.values():
        lst.sort(key=_difficulty_key)

    chosen: dict[int, Candidate] = {}
    tag_order = sorted(by_tag)
    cursors = {t: 0 for t in tag_order}
    progressed = True
    while len(chosen) < k and progressed:
        progressed = False
        for t in tag_order:
            if len(chosen) >= k:
                break
            lst = by_tag[t]
            i = cursors[t]
            while i < len(lst) and lst[i].question_id in chosen:
                i += 1
            if i < len(lst):
                chosen[lst[i].question_id] = lst[i]
                cursors[t] = i + 1
                progressed = True
            else:
                cursors[t] = i

    if len(chosen) < k:
        untagged = sorted(
            (
                c
                for c in candidates
                if not c.skill_tag_ids and c.question_id not in chosen
            ),
            key=_difficulty_key,
        )
        for c in untagged:
            if len(chosen) >= k:
                break
            chosen[c.question_id] = c

    return [c.question_id for c in sorted(chosen.values(), key=_difficulty_key)]


def select_mixed_questions(
    candidates: list[Candidate],
    *,
    skill_mastery: dict[int, float],
    question_count: int,
    rng: random.Random,
) -> list[int]:
    """The ordered ids of the questions to freeze into a mixed run.

    `skill_mastery` maps `skill_tags.id` → cached mastery (0–1); an empty map is
    the cold-start signal. `question_count` is the target size; fewer eligible
    candidates yields a smaller set. `rng` seeds the weighted draw.
    """
    k = max(0, question_count)
    if k == 0 or not candidates:
        return []
    if k >= len(candidates):
        return [c.question_id for c in sorted(candidates, key=_difficulty_key)]

    if not skill_mastery:
        return _cold_start(candidates, k)

    tag_weights = {t: _skill_weight(m) for t, m in skill_mastery.items()}
    # The fallback for an untagged question is the mean of the weights actually
    # applied across the candidate set's SkillTags — including the neutral
    # weight the unseen ones get — so it matches what a tagged question would
    # draw, not just the mean over tags that happen to have a snapshot.
    applied = [
        tag_weights.get(t, _NEUTRAL_SKILL_WEIGHT)
        for t in {tag for c in candidates for tag in c.skill_tag_ids}
    ]
    fallback = sum(applied) / len(applied) if applied else _NEUTRAL_SKILL_WEIGHT
    weights = [_candidate_weight(c, tag_weights, fallback) for c in candidates]
    picked = _weighted_sample(candidates, weights, k, rng)
    picked.sort(key=_difficulty_key)
    return [c.question_id for c in picked]
