"""Pure "study this next" selection — no database, no clock, no I/O.

The dashboard router loads the caller's cached Topic mastery
(`PerformanceSnapshot`, `dimension = topic`) and the published syllabus, hands
both here as plain maps, and renders the result.

Selection (ticket 02):

- a Topic is **weak** if it has a snapshot with ``mastery < threshold``; a Topic
  with no snapshot is never recommended (the student hasn't touched it);
- a prerequisite is **satisfied** if it has no snapshot (untouched) or its
  mastery is ``>= threshold``;
- a weak Topic whose every prerequisite is satisfied is recommended as-is
  (``reason = "practice"``);
- a weak Topic blocked by a prerequisite that scores *lower than the Topic
  itself* is replaced by "revise <that prerequisite>"
  (``reason = "revise_prerequisite"``, ``for_topic_id`` naming the Topic it
  unblocks); the weakest such prerequisite wins;
- a weak Topic blocked only by prerequisites that are weak but *not* lower than
  it is dropped — the student is stuck on something the data can't rank;
- results are de-duplicated by Topic: a direct ``practice`` pick beats a
  substitution for the same Topic, and when one weak prerequisite blocks
  several Topics its single "revise" entry names the weakest (then earliest)
  Topic it unblocks — a deterministic choice, never "whichever came first";
- what survives is ordered by mastery ascending then syllabus order, and
  capped at ``limit``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

REASON_PRACTICE = "practice"
REASON_REVISE_PREREQUISITE = "revise_prerequisite"


@dataclass(frozen=True)
class TopicNode:
    """One Topic in the published syllabus. ``order`` is its position in
    syllabus order (lower sorts first); ``prerequisite_ids`` is already
    filtered to Topics the student can see."""

    topic_id: int
    order: int
    prerequisite_ids: tuple[int, ...]


@dataclass(frozen=True)
class Recommendation:
    topic_id: int
    reason: str
    # The mastery this pick is sorted and rendered by — the recommended Topic's
    # own mastery (the prerequisite's, for a substitution).
    mastery: float
    # Set only for ``reason == REASON_REVISE_PREREQUISITE``: the weak Topic the
    # revision unblocks.
    for_topic_id: int | None


def recommend(
    *,
    masteries: Mapping[int, float],
    topics: Mapping[int, TopicNode],
    threshold: float,
    limit: int,
) -> list[Recommendation]:
    def satisfied(topic_id: int) -> bool:
        mastery = masteries.get(topic_id)
        return mastery is None or mastery >= threshold

    def more_urgent(a: Recommendation, b: Recommendation) -> Recommendation:
        """Which of two picks for the same Topic to keep. A direct ``practice``
        pick always beats a substitution; between two substitutions, the one
        unblocking the weaker — then earlier — Topic wins. Deterministic, so a
        prerequisite blocking several weak Topics never resolves arbitrarily."""
        if a.reason != b.reason:
            return a if a.reason == REASON_PRACTICE else b
        if a.reason == REASON_PRACTICE:
            return a  # identical direct picks — keep the first seen
        a_for, b_for = a.for_topic_id, b.for_topic_id
        assert a_for is not None and b_for is not None
        a_key = (masteries[a_for], topics[a_for].order)
        b_key = (masteries[b_for], topics[b_for].order)
        return a if a_key <= b_key else b

    picks: list[Recommendation] = []
    for topic_id, node in topics.items():
        if satisfied(topic_id):
            continue  # untouched or already solid — nothing to recommend
        mastery = masteries[topic_id]

        blockers = [
            pid
            for pid in node.prerequisite_ids
            if pid in topics and not satisfied(pid)
        ]
        if not blockers:
            picks.append(
                Recommendation(topic_id, REASON_PRACTICE, mastery, None)
            )
            continue

        lower = [pid for pid in blockers if masteries[pid] < mastery]
        if not lower:
            continue  # stuck on a prerequisite the data can't rank below it

        sub = min(
            lower, key=lambda pid: (masteries[pid], topics[pid].order)
        )
        picks.append(
            Recommendation(
                sub, REASON_REVISE_PREREQUISITE, masteries[sub], topic_id
            )
        )

    best: dict[int, Recommendation] = {}
    for rec in picks:
        current = best.get(rec.topic_id)
        best[rec.topic_id] = (
            rec if current is None else more_urgent(current, rec)
        )

    ordered = sorted(
        best.values(),
        key=lambda r: (r.mastery, topics[r.topic_id].order),
    )
    return ordered[:limit]
