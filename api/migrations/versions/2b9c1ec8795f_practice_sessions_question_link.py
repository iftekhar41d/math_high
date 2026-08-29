"""practice sessions + question link

Revision ID: 2b9c1ec8795f
Revises: 70f921e7875d
Create Date: 2026-08-29 23:33:30.093916

Persists practice runs. `practice_sessions` holds one row per run — its `mode`
(`topic` now; `mixed` / `timed` in later Phase 2b tickets), its polymorphic
`scope_type` / `scope_id`, the frozen `question_count`, optional
`time_limit_seconds`, `started_at`, and the nullable `submitted_at` / `score`
used only by the whole-set modes. `practice_session_questions` freezes the
ordered Question set at creation (`position` is 0-based).
`question_attempts.practice_session_id` is a nullable FK: an attempt made
outside any run stays standalone.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2b9c1ec8795f'
down_revision: Union[str, None] = '70f921e7875d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'practice_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('mode', sa.String(), nullable=False),
        sa.Column('scope_type', sa.String(), nullable=False),
        sa.Column('scope_id', sa.Integer(), nullable=False),
        sa.Column('question_count', sa.Integer(), nullable=False),
        sa.Column('time_limit_seconds', sa.Integer(), nullable=True),
        sa.Column(
            'started_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('score', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('practice_sessions', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_practice_sessions_user_id'),
            ['user_id'],
            unique=False,
        )

    op.create_table(
        'practice_session_questions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('question_id', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['question_id'], ['questions.id'], ),
        sa.ForeignKeyConstraint(['session_id'], ['practice_sessions.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table(
        'practice_session_questions', schema=None
    ) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_practice_session_questions_question_id'),
            ['question_id'],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f('ix_practice_session_questions_session_id'),
            ['session_id'],
            unique=False,
        )

    with op.batch_alter_table('question_attempts', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('practice_session_id', sa.Integer(), nullable=True)
        )
        batch_op.create_index(
            batch_op.f('ix_question_attempts_practice_session_id'),
            ['practice_session_id'],
            unique=False,
        )
        batch_op.create_foreign_key(
            'fk_question_attempts_practice_session_id',
            'practice_sessions',
            ['practice_session_id'],
            ['id'],
        )


def downgrade() -> None:
    with op.batch_alter_table('question_attempts', schema=None) as batch_op:
        batch_op.drop_constraint(
            'fk_question_attempts_practice_session_id', type_='foreignkey'
        )
        batch_op.drop_index(
            batch_op.f('ix_question_attempts_practice_session_id')
        )
        batch_op.drop_column('practice_session_id')

    with op.batch_alter_table(
        'practice_session_questions', schema=None
    ) as batch_op:
        batch_op.drop_index(
            batch_op.f('ix_practice_session_questions_session_id')
        )
        batch_op.drop_index(
            batch_op.f('ix_practice_session_questions_question_id')
        )
    op.drop_table('practice_session_questions')

    with op.batch_alter_table('practice_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_practice_sessions_user_id'))
    op.drop_table('practice_sessions')
