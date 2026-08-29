"""The MentisQ guided-exchange core.

`post_message` is the whole contract: check the student's usage against the
caps, and if they are under, call the provider once, persist the user and
assistant turns with the provider's usage (prompt tokens on the user turn,
completion tokens + USD cost on the assistant turn — so `SUM(cost_usd)` counts
each exchange once), and hand back the reply. On a provider timeout / outage /
bad response the student gets a fixed fallback, both turns are stored `failed`,
and the exchange is metered against nothing.

Time is read only through the injected `Clock`. The provider is reached only
through the injected `MentisQLLMClient`. Nothing here touches HTTP.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.clock import Clock
from app.mentisq.llm_client import LLMError, MentisQLLMClient
from app.mentisq.prompt import PromptContext, build_prompt
from app.mentisq.settings import MentisQSettings
from app.models import (
    MENTISQ_MODE_GUIDED,
    MENTISQ_ROLE_ASSISTANT,
    MENTISQ_ROLE_USER,
    MENTISQ_STATUS_FAILED,
    MENTISQ_STATUS_OK,
    MentisQMessage,
    MentisQSession,
    User,
)

# Shown verbatim when the provider does not complete a turn.
FALLBACK_MESSAGE = (
    "MentisQ can't reach the tutor right now. Your message wasn't counted — "
    "please try again in a little while."
)
# Shown (verbatim) when a cap is hit; no provider call is made.
LIMIT_REACHED_DAILY = (
    "You've reached today's MentisQ message limit. It resets tomorrow."
)
LIMIT_REACHED_MONTHLY = (
    "You've reached your MentisQ usage limit for this month."
)
LIMIT_REACHED_GLOBAL = (
    "MentisQ is temporarily unavailable while we manage demand. "
    "Please try again later."
)

# The reply's `status`: the two persisted message statuses, plus the transient
# "a cap blocked this, nothing was stored" case.
STATUS_LIMIT_REACHED = "limit_reached"


@dataclass(frozen=True)
class MentisQReply:
    # `None` only when a cap blocked the message before any session was created.
    session: MentisQSession | None
    reply_text: str
    status: str  # MENTISQ_STATUS_OK | MENTISQ_STATUS_FAILED | STATUS_LIMIT_REACHED


def _day_start(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


class MentisQService:
    def __init__(
        self,
        db: Session,
        clock: Clock,
        llm: MentisQLLMClient,
        settings: MentisQSettings,
    ) -> None:
        self.db = db
        self.clock = clock
        self.llm = llm
        self.settings = settings

    # -- usage read-back --------------------------------------------------

    def _messages_today(self, user_id: int, now: datetime) -> int:
        return self.db.scalar(
            select(func.count())
            .select_from(MentisQMessage)
            .join(MentisQSession)
            .where(
                MentisQSession.user_id == user_id,
                MentisQMessage.role == MENTISQ_ROLE_USER,
                MentisQMessage.status == MENTISQ_STATUS_OK,
                MentisQMessage.created_at >= _day_start(now),
            )
        )

    def _student_spend_this_month(self, user_id: int, now: datetime) -> float:
        return self.db.scalar(
            select(func.coalesce(func.sum(MentisQMessage.cost_usd), 0.0))
            .select_from(MentisQMessage)
            .join(MentisQSession)
            .where(
                MentisQSession.user_id == user_id,
                MentisQMessage.created_at >= _month_start(now),
            )
        )

    def _global_spend_this_month(self, now: datetime) -> float:
        return self.db.scalar(
            select(func.coalesce(func.sum(MentisQMessage.cost_usd), 0.0))
            .where(MentisQMessage.created_at >= _month_start(now))
        )

    def _cap_hit(self, user_id: int, now: datetime) -> str | None:
        """The fixed message for the first cap the student is over, or `None`."""
        if self._messages_today(user_id, now) >= self.settings.daily_message_cap:
            return LIMIT_REACHED_DAILY
        if (
            self._student_spend_this_month(user_id, now)
            >= self.settings.per_student_monthly_cap_usd
        ):
            return LIMIT_REACHED_MONTHLY
        global_cap = self.settings.global_monthly_cap_usd
        if (
            global_cap is not None
            and self._global_spend_this_month(now) >= global_cap
        ):
            return LIMIT_REACHED_GLOBAL
        return None

    # -- the exchange -------------------------------------------------------

    def post_message(
        self,
        *,
        user: User,
        content: str,
        context: PromptContext | None = None,
        context_topic_id: int | None = None,
        context_question_id: int | None = None,
    ) -> MentisQReply:
        now = self.clock.now()

        capped = self._cap_hit(user.id, now)
        if capped is not None:
            # Nothing is written and the provider is not called.
            return MentisQReply(None, capped, STATUS_LIMIT_REACHED)

        session = MentisQSession(
            user_id=user.id,
            context_topic_id=context_topic_id,
            context_question_id=context_question_id,
            mode=MENTISQ_MODE_GUIDED,
            created_at=now,
        )
        self.db.add(session)
        self.db.flush()

        prompt = build_prompt(content, context)
        try:
            completion = self.llm.complete(
                prompt=prompt, model=self.settings.model_name
            )
        except LLMError:
            self._persist_pair(
                session,
                now,
                content=content,
                reply=FALLBACK_MESSAGE,
                status=MENTISQ_STATUS_FAILED,
            )
            return MentisQReply(session, FALLBACK_MESSAGE, MENTISQ_STATUS_FAILED)

        self._persist_pair(
            session,
            now,
            content=content,
            reply=completion.text,
            status=MENTISQ_STATUS_OK,
            prompt_tokens=completion.prompt_tokens,
            completion_tokens=completion.completion_tokens,
            cost_usd=completion.cost_usd,
        )
        return MentisQReply(session, completion.text, MENTISQ_STATUS_OK)

    def _persist_pair(
        self,
        session: MentisQSession,
        now: datetime,
        *,
        content: str,
        reply: str,
        status: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        # Prompt tokens are the student's turn; completion tokens and the USD
        # cost are the tutor's turn. Splitting it this way keeps every row's
        # usage real while `SUM(cost_usd)` still counts each exchange once.
        self.db.add(
            MentisQMessage(
                session_id=session.id,
                role=MENTISQ_ROLE_USER,
                content=content,
                status=status,
                prompt_tokens=prompt_tokens,
                created_at=now,
            )
        )
        self.db.add(
            MentisQMessage(
                session_id=session.id,
                role=MENTISQ_ROLE_ASSISTANT,
                content=reply,
                status=status,
                completion_tokens=completion_tokens,
                cost_usd=cost_usd,
                created_at=now,
            )
        )
        self.db.commit()
