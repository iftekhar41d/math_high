"""question_attempts.part_results

Revision ID: 5ea211d064d9
Revises: 2b9c1ec8795f
Create Date: 2026-08-30 00:04:46.972583

The `multi_part` question type (Phase 2b ticket 08) grades each sub-question on
its own. `part_results` stores the ordered per-part correctness vector
(`[true, false, ...]`) on the attempt; `is_correct` is its `all(...)`. Nullable
— every other question type and solution-only marker rows leave it null.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5ea211d064d9'
down_revision: Union[str, None] = '2b9c1ec8795f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('question_attempts', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('part_results', sa.JSON(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table('question_attempts', schema=None) as batch_op:
        batch_op.drop_column('part_results')
