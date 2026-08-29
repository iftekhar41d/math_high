"""`/mentisq/...` — the student's guided exchange with the AI tutor.

Reached in the browser under `/api/mentisq/...` (the proxy strips `/api`).

`POST /mentisq/messages` takes the student's message plus an optional context
anchor (a lecture Topic or a practice Question) and an optional `session_id`,
runs one guided turn in that (multi-turn) conversation, and returns the tutor's
reply. `GET /mentisq/sessions/current` hands back the general conversation the
next message would continue, so the SPA can render the running exchange.
`POST /mentisq/sessions/{id}/helpful` records the student's 👍/👎.

Caps, session selection, and provider failures are handled in
`app/mentisq/service.py`; this router only resolves the context and maps the
result onto HTTP. Every call requires a verified caller.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_verified_user
from app.clock import Clock, get_clock
from app.content_access import topic_is_published
from app.database import get_db
from app.mentisq.llm_client import MentisQLLMClient, get_llm_client
from app.mentisq.prompt import PromptContext, lecture_excerpt
from app.mentisq.service import MentisQService
from app.mentisq.settings import MentisQSettings
from app.models import (
    MENTISQ_STATUS_OK,
    MentisQSession,
    Question,
    Topic,
    User,
    is_content_admin,
)
from app.practice.grading import correct_answer_text
from app.schemas import (
    MentisQAskRequest,
    MentisQHelpfulRequest,
    MentisQReplyOut,
    MentisQSessionOut,
    MentisQTurnOut,
)

router = APIRouter(prefix="/mentisq", tags=["mentisq"])


def _visible_to(user: User, topic: Topic) -> bool:
    return is_content_admin(user) or topic_is_published(topic)


def _not_found(what: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=f"No such {what}."
    )


def _resolve_topic(db: Session, slug: str, user: User) -> Topic:
    topic = db.scalar(select(Topic).where(Topic.slug == slug))
    if topic is None or not _visible_to(user, topic):
        raise _not_found("topic")
    return topic


def _resolve_question(db: Session, question_id: int, user: User) -> Question:
    question = db.get(Question, question_id)
    if question is None or not _visible_to(user, question.topic):
        raise _not_found("question")
    return question


@router.post("/messages", response_model=MentisQReplyOut)
def post_message(
    body: MentisQAskRequest,
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    llm: MentisQLLMClient = Depends(get_llm_client),
    user: User = Depends(require_verified_user),
) -> MentisQReplyOut:
    if body.topic_slug is not None and body.question_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide a topic or a question, not both.",
        )

    topic: Topic | None = None
    question: Question | None = None
    context: PromptContext | None = None

    if body.topic_slug is not None:
        topic = _resolve_topic(db, body.topic_slug, user)
        lc = topic.lecture_content
        context = PromptContext(
            topic_title=topic.title,
            lecture_excerpt=lecture_excerpt(lc.body if lc is not None else None),
        )
    elif body.question_id is not None:
        question = _resolve_question(db, body.question_id, user)
        context = PromptContext(
            topic_title=question.topic.title,
            question_body=question.body,
            correct_answer=correct_answer_text(
                question.type, question.answer_schema
            ),
            worked_solution=question.worked_solution,
        )

    if body.session_id is not None:
        # A stale id (deleted / never existed) is fine — the service opens a
        # fresh session — but one belonging to someone else is a client bug,
        # not a context change, and must not silently start a new conversation.
        claimed = db.get(MentisQSession, body.session_id)
        if claimed is not None and claimed.user_id != user.id:
            raise _not_found("session")

    service = MentisQService(db, clock, MentisQSettings(db), llm)
    reply = service.post_message(
        user=user,
        content=body.content,
        context=context,
        context_topic_id=topic.id if topic is not None else None,
        context_question_id=question.id if question is not None else None,
        session_id=body.session_id,
        new_chat=body.new_chat,
    )
    return MentisQReplyOut(
        session_id=reply.session.id if reply.session is not None else None,
        reply=reply.reply_text,
        status=reply.status,
    )


def _session_out(db: Session, session) -> MentisQSessionOut:
    turns = [
        MentisQTurnOut(role=m.role, content=m.content)
        for m in session.messages
        if m.status == MENTISQ_STATUS_OK
    ]
    topic_slug = None
    if session.context_topic_id is not None:
        topic_slug = db.scalar(
            select(Topic.slug).where(Topic.id == session.context_topic_id)
        )
    return MentisQSessionOut(
        session_id=session.id,
        topic_slug=topic_slug,
        question_id=session.context_question_id,
        helpful=session.helpful,
        turns=turns,
    )


@router.get("/sessions/current", response_model=MentisQSessionOut | None)
def current_session(
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    user: User = Depends(require_verified_user),
) -> MentisQSessionOut | None:
    """The general (no Topic/Question) conversation the next general message
    would continue, with its non-failed turns — or `null` if there is none."""
    service = MentisQService(db, clock, MentisQSettings(db))
    session = service.latest_general_session(user)
    return _session_out(db, session) if session is not None else None


@router.post("/sessions/{session_id}/helpful", response_model=MentisQSessionOut)
def rate_session(
    session_id: int,
    body: MentisQHelpfulRequest,
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    user: User = Depends(require_verified_user),
) -> MentisQSessionOut:
    """Record the student's 👍/👎 on one of their own conversations."""
    service = MentisQService(db, clock, MentisQSettings(db))
    session = service.set_helpful(
        user=user, session_id=session_id, helpful=body.helpful
    )
    if session is None:
        raise _not_found("session")
    return _session_out(db, session)
