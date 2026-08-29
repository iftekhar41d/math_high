"""timed quiz: question estimated time + attempt late flag

Revision ID: 837888981cfc
Revises: 5ea211d064d9
Create Date: 2026-08-30 00:27:26.389844

Ticket 06 (timed quiz mode). `questions.estimated_time_seconds` (nullable) is
the author's per-question time estimate; a `timed` `PracticeSession`'s
`time_limit_seconds` is the sum across its frozen set, gaps filled with the
`practice.default_question_seconds` Setting. `question_attempts.after_time_limit`
(nullable) flags an answer that arrived after a timed quiz's limit elapsed —
stored, not rejected; null for every attempt outside a timed quiz. Both are
plain nullable column adds, batch mode, up/down/up round-trip verified.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '837888981cfc'
down_revision: Union[str, None] = '5ea211d064d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('question_attempts', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('after_time_limit', sa.Boolean(), nullable=True)
        )

    with op.batch_alter_table('questions', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('estimated_time_seconds', sa.Integer(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table('questions', schema=None) as batch_op:
        batch_op.drop_column('estimated_time_seconds')

    with op.batch_alter_table('question_attempts', schema=None) as batch_op:
        batch_op.drop_column('after_time_limit')
