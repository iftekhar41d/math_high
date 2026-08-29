"""`/practice/...` — starting a Topic practice session, submitting answers, and
requesting a worked solution.

Reached in the browser under `/api/practice/...` (the proxy strips `/api`).

Grading is entirely server-side (`app/practice/grading.py`); the correct answer
never reaches the browser. Every endpoint requires a verified caller. Students
can only practise `published` Topics; a `ContentAdmin` may also practise drafts
(for preview). Each submission writes a `QuestionAttempt`.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.auth.dependencies import require_verified_user
from app.clock import Clock, get_clock
from app.content_access import topic_is_published
from app.database import get_db
from app.models import (
    PRACTICE_MODE_MIXED,
    PRACTICE_MODE_TIMED,
    PRACTICE_MODE_TOPIC,
    PRACTICE_SCOPE_TOPIC,
    PRACTICE_SCOPE_UNIT,
    PRACTICE_SCOPE_YEAR_LEVEL,
    QUESTION_MULTI_PART,
    SNAPSHOT_DIMENSION_SKILL_TAG,
    PerformanceSnapshot,
    PracticeSession,
    PracticeSessionQuestion,
    Question,
    QuestionAttempt,
    Subject,
    Topic,
    Unit,
    User,
    YearLevel,
    is_content_admin,
)
from app.practice.grading import grade_parts, is_correct
from app.practice.mixed import (
    DEFAULT_MIXED_QUESTION_COUNT,
    Candidate,
    select_mixed_questions,
)
from app.practice.payload import public_question
from app.practice.settings import (
    default_question_seconds,
    solution_reveal_after_attempts,
)
from app.practice.timed import Countdown, proportion_correct, total_time_limit
from app.schemas import (
    MixedSessionOut,
    PracticeSessionOut,
    SessionReviewOut,
    SessionReviewQuestionOut,
    SolutionResponse,
    StartMixedPracticeRequest,
    StartPracticeRequest,
    StartTimedQuizRequest,
    SubmitAnswerRequest,
    SubmitAnswerResponse,
    TimedAnswerOut,
    TimedSessionOut,
    TopicRef,
    UnitRef,
)

router = APIRouter(prefix="/practice", tags=["practice"])


def _not_found(what: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=f"No such {what}."
    )


def _visible_to(user: User, topic: Topic) -> bool:
    """A student practises only published Topics; a ContentAdmin also drafts."""
    return is_content_admin(user) or topic_is_published(topic)


def _visible_topic_or_404(db: Session, slug: str, user: User) -> Topic:
    topic = db.scalar(select(Topic).where(Topic.slug == slug))
    if topic is None or not _visible_to(user, topic):
        raise _not_found("topic")
    return topic


def _practisable_question_or_404(
    db: Session, question_id: int, user: User
) -> Question:
    question = db.get(Question, question_id)
    if question is None or not _visible_to(user, question.topic):
        raise _not_found("question")
    return question


def _active_session_id(
    db: Session, user: User, question_id: int
) -> int | None:
    """The `PracticeSession` a bare submit / show-solution on this Question
    belongs to: the caller's most recent still-open run that froze it (`topic`
    runs never set `submitted_at`, so a run stays linkable until a later ticket
    gives it an explicit close). If several open runs froze the question the
    newest (`id` desc) wins. `None` when they never started one — the attempt
    is then standalone.
    """
    return db.scalar(
        select(PracticeSession.id)
        .join(
            PracticeSessionQuestion,
            PracticeSessionQuestion.session_id == PracticeSession.id,
        )
        .where(
            PracticeSession.user_id == user.id,
            PracticeSession.submitted_at.is_(None),
            PracticeSessionQuestion.question_id == question_id,
        )
        .order_by(PracticeSession.id.desc())
    )


# How long past its own time limit a still-open `timed` run keeps withholding
# correctness / worked solutions from a bare submit or show-solution. Past this
# the run is treated as abandoned so ordinary topic practice on the same
# questions is no longer affected (ticket 04's "recency window" ask). A run
# observed via `GET /practice/sessions/{id}` is closed for real before then.
_TIMED_ABANDON_GRACE = timedelta(minutes=15)


def _open_timed_session_for(
    db: Session, user: User, question_id: int, now: datetime
) -> PracticeSession | None:
    """The caller's newest not-yet-submitted `timed` run that froze this
    question — the state in which its correctness and worked solution are
    withheld. Independent of `_active_session_id`, so a topic run started in
    another tab can't out-rank the quiz. `None` once the run is submitted or
    more than `_TIMED_ABANDON_GRACE` past its limit.
    """
    session = db.scalar(
        select(PracticeSession)
        .join(
            PracticeSessionQuestion,
            PracticeSessionQuestion.session_id == PracticeSession.id,
        )
        .where(
            PracticeSession.user_id == user.id,
            PracticeSession.mode == PRACTICE_MODE_TIMED,
            PracticeSession.submitted_at.is_(None),
            PracticeSessionQuestion.question_id == question_id,
        )
        .order_by(PracticeSession.id.desc())
    )
    if session is None:
        return None
    abandoned_at = (
        session.started_at
        + timedelta(seconds=session.time_limit_seconds or 0)
        + _TIMED_ABANDON_GRACE
    )
    return None if now > abandoned_at else session


@router.post("/sessions", response_model=PracticeSessionOut)
def start_session(
    body: StartPracticeRequest,
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    user: User = Depends(require_verified_user),
) -> PracticeSessionOut:
    topic = _visible_topic_or_404(db, body.topic_slug, user)
    # `Question` has no `order` column (per the ticket schema); id order is
    # seed order, i.e. the order questions appear in the manifest.
    questions = list(
        db.scalars(
            select(Question)
            .where(Question.topic_id == topic.id)
            .order_by(Question.id)
        )
    )
    # Persist the run and freeze its ordered question set. The response is
    # unchanged from Phase 1 — the session is server-side bookkeeping the
    # submit / show-solution endpoints link their attempts to.
    db.add(
        PracticeSession(
            user_id=user.id,
            mode=PRACTICE_MODE_TOPIC,
            scope_type=PRACTICE_SCOPE_TOPIC,
            scope_id=topic.id,
            question_count=len(questions),
            started_at=clock.now(),
            questions=[
                PracticeSessionQuestion(question_id=q.id, position=i)
                for i, q in enumerate(questions)
            ],
        )
    )
    db.commit()
    return PracticeSessionOut(
        topic=TopicRef.model_validate(topic),
        questions=[public_question(q) for q in questions],
    )


# -- mixed practice mode --------------------------------------------------
#
# A `mixed` `PracticeSession` samples its frozen set across a Unit or Year level
# at creation, weighted toward the SkillTags where the caller's cached
# `PerformanceSnapshot` mastery is lowest. "No mastery data yet" is judged
# **per scope**: a student with snapshots elsewhere but none for any SkillTag in
# *this* scope still gets the even round-robin coverage (spec story 15 — "new to
# a Unit"). The weighting is fixed at this one call — no within-session
# adaptation. Feedback is *not* withheld: `submit_answer` / `show-solution`
# behave exactly as for `topic` practice (a mixed run is not a `timed` run, so
# `_open_timed_session_for` never matches it, and `_active_session_id` links
# each attempt to the open mixed run that froze the question).


def _resolve_mixed_scope(
    db: Session, scope_type: str, scope_id: int, user: User
) -> tuple[list[Question], str]:
    """The scope entity's practisable Questions (SkillTags + Topic publish state
    eager-loaded) and a display label, in one place. 404 if the entity is gone.
    """
    if scope_type == PRACTICE_SCOPE_UNIT:
        scope = db.get(Unit, scope_id)
        label = scope.title if scope is not None else None
    else:  # PRACTICE_SCOPE_YEAR_LEVEL
        scope = db.get(YearLevel, scope_id)
        label = scope.name if scope is not None else None
    if scope is None:
        raise _not_found(scope_type.replace("_", " "))

    query = (
        select(Question)
        .join(Topic, Topic.id == Question.topic_id)
        .options(
            selectinload(Question.skill_tags),
            selectinload(Question.topic).selectinload(Topic.lecture_content),
        )
    )
    if scope_type == PRACTICE_SCOPE_UNIT:
        query = query.where(Topic.unit_id == scope_id).order_by(
            Topic.order, Question.id
        )
    else:
        query = (
            query.join(Unit, Unit.id == Topic.unit_id)
            .join(Subject, Subject.id == Unit.subject_id)
            .where(Subject.year_level_id == scope_id)
            .order_by(Unit.order, Topic.order, Question.id)
        )
    questions = [
        q
        for q in db.scalars(query).unique().all()
        if _visible_to(user, q.topic)
    ]
    return questions, label


@router.post("/mixed-sessions", response_model=MixedSessionOut)
def start_mixed_session(
    body: StartMixedPracticeRequest,
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    user: User = Depends(require_verified_user),
) -> MixedSessionOut:
    candidates_q, label = _resolve_mixed_scope(
        db, body.scope_type, body.scope_id, user
    )
    if not candidates_q:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This scope has no practice questions yet.",
        )

    # Only this scope's SkillTags decide weighted-vs-cold-start, so a student
    # with history in other Units still gets even coverage here.
    scope_tag_ids = {t.id for q in candidates_q for t in q.skill_tags}
    mastery = {
        row.dimension_id: row.mastery
        for row in db.scalars(
            select(PerformanceSnapshot).where(
                PerformanceSnapshot.user_id == user.id,
                PerformanceSnapshot.dimension == SNAPSHOT_DIMENSION_SKILL_TAG,
                PerformanceSnapshot.dimension_id.in_(scope_tag_ids),
            )
        )
    }

    count = body.question_count or DEFAULT_MIXED_QUESTION_COUNT
    chosen_ids = select_mixed_questions(
        [
            Candidate(
                question_id=q.id,
                difficulty=q.difficulty,
                skill_tag_ids=tuple(t.id for t in q.skill_tags),
            )
            for q in candidates_q
        ],
        skill_mastery=mastery,
        question_count=count,
        rng=random.Random(),
    )
    by_id = {q.id: q for q in candidates_q}
    chosen = [by_id[qid] for qid in chosen_ids]

    session = PracticeSession(
        user_id=user.id,
        mode=PRACTICE_MODE_MIXED,
        scope_type=body.scope_type,
        scope_id=body.scope_id,
        question_count=len(chosen),
        started_at=clock.now(),
        questions=[
            PracticeSessionQuestion(question_id=q.id, position=i)
            for i, q in enumerate(chosen)
        ],
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return MixedSessionOut(
        session_id=session.id,
        mode=session.mode,
        scope_type=session.scope_type,
        scope_label=label,
        questions=[public_question(q) for q in chosen],
    )


@router.post(
    "/questions/{question_id}/submit", response_model=SubmitAnswerResponse
)
def submit_answer(
    question_id: int,
    body: SubmitAnswerRequest,
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    user: User = Depends(require_verified_user),
) -> SubmitAnswerResponse:
    question = _practisable_question_or_404(db, question_id, user)
    correct = is_correct(question.type, question.answer_schema, body.answer)
    # `multi_part` additionally records the per-part correctness vector
    # (`is_correct` above already reduced it to the single "all parts" bool).
    part_results: list[bool] | None = (
        grade_parts(question.answer_schema, body.answer)
        if question.type == QUESTION_MULTI_PART
        else None
    )

    graded_so_far = db.scalar(
        select(func.count())
        .select_from(QuestionAttempt)
        .where(
            QuestionAttempt.user_id == user.id,
            QuestionAttempt.question_id == question.id,
            QuestionAttempt.attempt_no > 0,
        )
    )
    attempt_no = graded_so_far + 1

    # A submit made inside an open `timed` quiz is graded and persisted as
    # usual, but the response withholds correctness and the worked solution
    # until the whole set is submitted for review. An answer that arrives after
    # the quiz's limit is flagged, never rejected.
    timed_open = _open_timed_session_for(db, user, question.id, clock.now())
    # A running timed quiz owns every submit of a question it froze, ahead of
    # any topic run; otherwise fall back to the usual most-recent-open rule.
    session_id = (
        timed_open.id
        if timed_open is not None
        else _active_session_id(db, user, question.id)
    )
    after_limit = timed_open is not None and Countdown(
        timed_open.time_limit_seconds or 0, timed_open.started_at
    ).is_after_limit(clock.now())

    db.add(
        QuestionAttempt(
            user_id=user.id,
            question_id=question.id,
            practice_session_id=session_id,
            submitted_answer=body.answer,
            is_correct=correct,
            part_results=part_results,
            time_taken=body.time_taken,
            attempt_no=attempt_no,
            after_time_limit=after_limit if timed_open is not None else None,
            created_at=clock.now(),
        )
    )
    db.commit()

    if timed_open is not None:
        return SubmitAnswerResponse(
            is_correct=None,
            attempt_no=attempt_no,
            worked_solution=None,
            after_time_limit=after_limit,
        )

    reveal_after = solution_reveal_after_attempts(db)
    return SubmitAnswerResponse(
        is_correct=correct,
        attempt_no=attempt_no,
        worked_solution=(
            question.worked_solution
            if attempt_no >= reveal_after
            else None
        ),
    )


@router.post(
    "/questions/{question_id}/show-solution", response_model=SolutionResponse
)
def show_solution(
    question_id: int,
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    user: User = Depends(require_verified_user),
) -> SolutionResponse:
    # This is the explicit "show me the solution" request — it always returns
    # it. Only the automatic reveal in `submit` is gated by the
    # `solution_reveal_after_attempts` Setting.
    question = _practisable_question_or_404(db, question_id, user)

    # ...except inside an open timed quiz, where no solution is available until
    # the whole set is submitted for review.
    if _open_timed_session_for(db, user, question.id, clock.now()) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Worked solutions are hidden until the timed quiz is submitted.",
        )

    latest = db.scalar(
        select(QuestionAttempt)
        .where(
            QuestionAttempt.user_id == user.id,
            QuestionAttempt.question_id == question.id,
        )
        .order_by(QuestionAttempt.id.desc())
    )
    if latest is None:
        # No submission yet — record a marker row so the view is still counted.
        db.add(
            QuestionAttempt(
                user_id=user.id,
                question_id=question.id,
                practice_session_id=_active_session_id(db, user, question.id),
                attempt_no=0,
                solution_viewed=True,
                created_at=clock.now(),
            )
        )
    else:
        latest.solution_viewed = True
    db.commit()

    return SolutionResponse(worked_solution=question.worked_solution)


# -- timed quiz mode --------------------------------------------------------
#
# A `timed` `PracticeSession` freezes every visible question in a Unit, sets a
# `time_limit_seconds` from the questions' estimated times, and stamps
# `started_at` from the `Clock`. Expiry is server-authoritative: the countdown
# and the late-answer flag are both derived from `started_at` + the `Clock`,
# never trusted from the client. Feedback is withheld (see `submit_answer`)
# until the whole set is submitted; then `score` / `submitted_at` are set and
# the review carries per-question correctness and worked solutions. Each start
# is a fresh session — retakes are unlimited.


def _session_or_404(
    db: Session, user: User, session_id: int
) -> PracticeSession:
    session = db.get(PracticeSession, session_id)
    if session is None or session.user_id != user.id:
        raise _not_found("practice session")
    return session


def _timed_session_or_404(
    db: Session, user: User, session_id: int
) -> PracticeSession:
    session = _session_or_404(db, user, session_id)
    if session.mode != PRACTICE_MODE_TIMED:
        raise _not_found("timed quiz")
    return session


def _unit_questions(db: Session, unit: Unit, user: User) -> list[Question]:
    """Every question in the Unit the caller may practise, in topic order then
    question (seed) order."""
    rows = db.scalars(
        select(Question)
        .join(Topic, Topic.id == Question.topic_id)
        .where(Topic.unit_id == unit.id)
        .order_by(Topic.order, Question.id)
    )
    return [q for q in rows if _visible_to(user, q.topic)]


def _frozen_questions(
    db: Session, session: PracticeSession
) -> list[Question]:
    """The session's frozen question set, in `position` order."""
    return list(
        db.scalars(
            select(Question)
            .join(
                PracticeSessionQuestion,
                PracticeSessionQuestion.question_id == Question.id,
            )
            .where(PracticeSessionQuestion.session_id == session.id)
            .order_by(PracticeSessionQuestion.position)
        )
    )


def _latest_attempts(
    db: Session, session: PracticeSession
) -> dict[int, QuestionAttempt]:
    """The most recent graded attempt (`attempt_no > 0`) per question in this
    session, keyed by question id."""
    latest: dict[int, QuestionAttempt] = {}
    for attempt in db.scalars(
        select(QuestionAttempt)
        .where(
            QuestionAttempt.practice_session_id == session.id,
            QuestionAttempt.attempt_no > 0,
        )
        .order_by(QuestionAttempt.id)
    ):
        latest[attempt.question_id] = attempt
    return latest


def _build_review(
    db: Session, session: PracticeSession
) -> SessionReviewOut:
    frozen = _frozen_questions(db, session)
    latest = _latest_attempts(db, session)
    return SessionReviewOut(
        session_id=session.id,
        mode=session.mode,
        score=session.score if session.score is not None else 0.0,
        question_count=session.question_count,
        submitted_at=session.submitted_at,
        questions=[
            SessionReviewQuestionOut(
                question=public_question(q),
                submitted_answer=(
                    latest[q.id].submitted_answer if q.id in latest else None
                ),
                is_correct=(
                    latest[q.id].is_correct if q.id in latest else None
                ),
                after_time_limit=bool(
                    q.id in latest and latest[q.id].after_time_limit
                ),
                worked_solution=q.worked_solution,
            )
            for q in frozen
        ],
    )


def _finalize_timed_session(
    db: Session, session: PracticeSession, now: datetime
) -> None:
    """Grade the whole frozen set (unanswered → incorrect), stamp `score` /
    `submitted_at`, commit. No-op if already submitted — so a manual submit
    racing the SPA's auto-submit-at-zero, or an expiry close racing either,
    all converge on the first result."""
    if session.submitted_at is not None:
        return
    frozen = _frozen_questions(db, session)
    latest = _latest_attempts(db, session)
    session.score = proportion_correct(
        [
            bool(latest[q.id].is_correct) if q.id in latest else False
            for q in frozen
        ]
    )
    session.submitted_at = now
    db.commit()


def _timed_session_out(
    db: Session,
    session: PracticeSession,
    now: datetime,
) -> TimedSessionOut:
    unit = db.get(Unit, session.scope_id)
    limit = session.time_limit_seconds or 0
    submitted = session.submitted_at is not None

    questions: list = []
    answers: list[TimedAnswerOut] = []
    review: SessionReviewOut | None = None
    if submitted:
        review = _build_review(db, session)
    else:
        frozen = _frozen_questions(db, session)
        latest = _latest_attempts(db, session)
        questions = [public_question(q) for q in frozen]
        answers = [
            TimedAnswerOut(
                question_id=qid,
                submitted_answer=attempt.submitted_answer,
                after_time_limit=bool(attempt.after_time_limit),
            )
            for qid, attempt in latest.items()
        ]

    return TimedSessionOut(
        session_id=session.id,
        mode=session.mode,
        scope_type=session.scope_type,
        unit=UnitRef.model_validate(unit),
        time_limit_seconds=limit,
        started_at=session.started_at,
        remaining_seconds=Countdown(limit, session.started_at).remaining(now),
        submitted_at=session.submitted_at,
        questions=questions,
        answers=answers,
        review=review,
    )


@router.post("/timed-sessions", response_model=TimedSessionOut)
def start_timed_session(
    body: StartTimedQuizRequest,
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    user: User = Depends(require_verified_user),
) -> TimedSessionOut:
    unit = db.get(Unit, body.unit_id)
    if unit is None:
        raise _not_found("unit")

    questions = _unit_questions(db, unit, user)
    if not questions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This unit has no practice questions yet.",
        )

    limit = total_time_limit(
        [q.estimated_time_seconds for q in questions],
        default_question_seconds(db),
    )
    session = PracticeSession(
        user_id=user.id,
        mode=PRACTICE_MODE_TIMED,
        scope_type=PRACTICE_SCOPE_UNIT,
        scope_id=unit.id,
        question_count=len(questions),
        time_limit_seconds=limit,
        started_at=clock.now(),
        questions=[
            PracticeSessionQuestion(question_id=q.id, position=i)
            for i, q in enumerate(questions)
        ],
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _timed_session_out(db, session, clock.now())


@router.get("/sessions/{session_id}", response_model=TimedSessionOut)
def get_timed_session(
    session_id: int,
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    user: User = Depends(require_verified_user),
) -> TimedSessionOut:
    session = _timed_session_or_404(db, user, session_id)
    # Expiry is server-authoritative: observing a run whose countdown has run
    # out closes it here and now, so a review and score exist even if the SPA
    # never fired its auto-submit (the tab was closed). Late answers are still
    # accepted up to the close (see `submit_answer`). Precedent for a mutating
    # GET: `GET /content/topics/{slug}` writes a `TopicView`.
    now = clock.now()
    limit = session.time_limit_seconds or 0
    if (
        session.submitted_at is None
        and limit > 0
        and Countdown(limit, session.started_at).remaining(now) == 0
    ):
        _finalize_timed_session(db, session, now)
    return _timed_session_out(db, session, now)


@router.post(
    "/sessions/{session_id}/submit", response_model=SessionReviewOut
)
def submit_timed_session(
    session_id: int,
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    user: User = Depends(require_verified_user),
) -> SessionReviewOut:
    session = _timed_session_or_404(db, user, session_id)
    _finalize_timed_session(db, session, clock.now())
    return _build_review(db, session)
