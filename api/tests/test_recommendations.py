"""`app.analytics.recommendations.recommend` — the pure "study this next"
selection.

Driven directly with hand-built mastery maps and syllabus nodes; no database,
no recompute. The end-to-end path (seed attempts -> recompute -> `/dashboard`)
is covered in `test_dashboard_analytics.py`.
"""

from __future__ import annotations

from app.analytics.recommendations import (
    REASON_PRACTICE,
    REASON_REVISE_PREREQUISITE,
    TopicNode,
    recommend,
)

THRESHOLD = 0.6


def _nodes(*specs):
    """`specs` are `(topic_id, *prerequisite_ids)`; syllabus order is the order
    given."""
    return {
        spec[0]: TopicNode(
            topic_id=spec[0], order=i, prerequisite_ids=tuple(spec[1:])
        )
        for i, spec in enumerate(specs)
    }


def test_weak_topics_are_recommended_lowest_mastery_first():
    topics = _nodes((1,), (2,), (3,))
    masteries = {1: 0.2, 2: 0.9, 3: 0.5}

    recs = recommend(
        masteries=masteries, topics=topics, threshold=THRESHOLD, limit=3
    )

    assert [(r.topic_id, r.reason) for r in recs] == [
        (1, REASON_PRACTICE),
        (3, REASON_PRACTICE),
    ]
    assert recs[0].mastery == 0.2


def test_ties_break_on_syllabus_order():
    topics = _nodes((10,), (11,))
    masteries = {10: 0.4, 11: 0.4}

    recs = recommend(
        masteries=masteries, topics=topics, threshold=THRESHOLD, limit=5
    )

    assert [r.topic_id for r in recs] == [10, 11]


def test_limit_caps_the_list():
    topics = _nodes((1,), (2,), (3,), (4,))
    masteries = {1: 0.1, 2: 0.2, 3: 0.3, 4: 0.4}

    recs = recommend(
        masteries=masteries, topics=topics, threshold=THRESHOLD, limit=2
    )

    assert [r.topic_id for r in recs] == [1, 2]


def test_topic_with_no_snapshot_is_not_recommended():
    topics = _nodes((1,), (2,))
    masteries = {1: 0.3}  # topic 2 untouched

    recs = recommend(
        masteries=masteries, topics=topics, threshold=THRESHOLD, limit=5
    )

    assert [r.topic_id for r in recs] == [1]


def test_solid_topics_are_not_recommended():
    topics = _nodes((1,))
    masteries = {1: 0.6}  # exactly the threshold counts as solid

    recs = recommend(
        masteries=masteries, topics=topics, threshold=THRESHOLD, limit=5
    )

    assert recs == []


def test_prerequisite_with_no_data_does_not_block():
    topics = _nodes((1,), (2, 1))  # topic 2 requires topic 1
    masteries = {2: 0.3}  # prereq 1 untouched -> satisfied

    recs = recommend(
        masteries=masteries, topics=topics, threshold=THRESHOLD, limit=5
    )

    assert [(r.topic_id, r.reason) for r in recs] == [(2, REASON_PRACTICE)]


def test_solid_prerequisite_does_not_block():
    topics = _nodes((1,), (2, 1))
    masteries = {1: 0.8, 2: 0.3}

    recs = recommend(
        masteries=masteries, topics=topics, threshold=THRESHOLD, limit=5
    )

    assert [(r.topic_id, r.reason) for r in recs] == [(2, REASON_PRACTICE)]


def test_weaker_prerequisite_substitutes_for_the_topic():
    topics = _nodes((1,), (2, 1))  # topic 2 requires topic 1
    masteries = {1: 0.2, 2: 0.5}  # prereq scores lower than the topic

    recs = recommend(
        masteries=masteries, topics=topics, threshold=THRESHOLD, limit=5
    )

    # Topic 2 is blocked by a prereq scoring lower still -> revise the prereq.
    # Topic 1 is itself weak and ready -> also a direct pick. The direct pick
    # wins the de-dup, once, ordered by its own mastery.
    assert [(r.topic_id, r.reason, r.for_topic_id) for r in recs] == [
        (1, REASON_PRACTICE, None),
    ]


def test_substitution_when_the_prerequisite_is_not_itself_a_candidate():
    # Topic 1 requires topic 0; topic 0 is weak but has its own unsatisfied
    # weak prereq, so 0 is not a direct candidate — it only appears as a
    # substitution for 1.
    topics = _nodes((0, 9), (1, 0), (9,))
    masteries = {0: 0.3, 1: 0.5, 9: 0.35}

    recs = recommend(
        masteries=masteries, topics=topics, threshold=THRESHOLD, limit=5
    )

    by_topic = {r.topic_id: r for r in recs}
    # 1 is blocked by weak prereq 0 (0.3 < 0.5) -> "revise 0" stands in for 1.
    assert by_topic[0].reason == REASON_REVISE_PREREQUISITE
    assert by_topic[0].for_topic_id == 1
    assert 1 not in by_topic  # replaced by its prerequisite
    # 0 is itself blocked by prereq 9, but 9 (0.35) does not score lower than 0
    # (0.30), so 0 is never a *direct* pick — only the substitution above.
    # 9 is weak and ready -> its own direct pick.
    assert by_topic[9].reason == REASON_PRACTICE


def test_weakest_prerequisite_wins_the_substitution():
    # Topic 1 is blocked by two weak prereqs both scoring lower than it: 2 (0.4)
    # and 3 (0.1). Topic 3 has its own weak-but-not-lower prereq 6, so it is
    # never a direct pick — it can only reach the list as the substitute for 1,
    # which is what lets us observe that the *weakest* blocker won.
    topics = _nodes((1, 2, 3), (2,), (3, 6), (6,))
    masteries = {1: 0.5, 2: 0.4, 3: 0.1, 6: 0.2}

    recs = recommend(
        masteries=masteries, topics=topics, threshold=THRESHOLD, limit=5
    )

    sub = next(r for r in recs if r.for_topic_id == 1)
    assert sub.topic_id == 3  # the weakest blocking prerequisite, not 2


def test_one_low_prerequisite_blocking_two_topics_dedups_deterministically():
    # Prereq 3 (0.1) blocks both topic 1 (0.5) and topic 2 (0.4). Topic 3 is
    # not a direct candidate (its own prereq 8 is weak but not lower), so it
    # only reaches the list as a substitution. The single surviving "revise 3"
    # names the more urgent blocked Topic — 2 (0.4 < 0.5) — not whichever
    # happened to iterate first.
    topics = _nodes((1, 3), (2, 3), (3, 8), (8,))
    masteries = {1: 0.5, 2: 0.4, 3: 0.1, 8: 0.2}

    recs = recommend(
        masteries=masteries, topics=topics, threshold=THRESHOLD, limit=5
    )

    subs = [r for r in recs if r.topic_id == 3]
    assert len(subs) == 1
    assert subs[0].reason == REASON_REVISE_PREREQUISITE
    assert subs[0].for_topic_id == 2


def test_blocked_topic_with_no_lower_prerequisite_is_dropped():
    topics = _nodes((1, 2), (2,))
    masteries = {1: 0.3, 2: 0.5}  # prereq weak but higher than the topic

    recs = recommend(
        masteries=masteries, topics=topics, threshold=THRESHOLD, limit=5
    )

    # Topic 1 blocked by weak-but-not-lower prereq 2 -> dropped. Topic 2 is
    # itself weak and ready -> the only pick.
    assert [(r.topic_id, r.reason) for r in recs] == [(2, REASON_PRACTICE)]
