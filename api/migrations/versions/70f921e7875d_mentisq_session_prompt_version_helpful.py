"""mentisq_sessions: prompt_version + helpful

Revision ID: 70f921e7875d
Revises: cd4ce2b430cd
Create Date: 2026-08-29 23:10:00.000000

Multi-turn MentisQ. `prompt_version` records which `guided_v*` template a session
ran under; the `server_default` backfills rows that predate the bump to
`guided_v1` and is a harmless backstop thereafter — the app always writes the
value explicitly (`GUIDED_PROMPT_VERSION`) on new sessions. `helpful` is the
student's optional 👍/👎 on the whole conversation (nullable = not rated).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '70f921e7875d'
down_revision: Union[str, None] = 'cd4ce2b430cd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('mentisq_sessions', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'prompt_version',
                sa.String(),
                nullable=False,
                server_default='guided_v1',
            )
        )
        batch_op.add_column(
            sa.Column('helpful', sa.Boolean(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table('mentisq_sessions', schema=None) as batch_op:
        batch_op.drop_column('helpful')
        batch_op.drop_column('prompt_version')
