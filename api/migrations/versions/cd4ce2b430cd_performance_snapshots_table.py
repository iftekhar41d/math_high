"""performance_snapshots table

Revision ID: cd4ce2b430cd
Revises: 31df1b0725a5
Create Date: 2026-08-29 21:53:30.181347

Adds the cached mastery table that `python -m app.analytics.recompute` writes:
one row per (user, dimension, dimension_id) where `dimension` is `topic` or
`skill_tag`, carrying a recency-weighted `mastery`, a bucketed `trend`, the
contributing `sample_size`, and the `computed_at` stamp of the run that
produced it. `dimension_id` is polymorphic (a `topics.id` or a `skill_tags.id`)
so it is not a foreign key; the unique constraint keeps the row set to one per
student per dimension value.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cd4ce2b430cd'
down_revision: Union[str, None] = '31df1b0725a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'performance_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('dimension', sa.String(), nullable=False),
        sa.Column('dimension_id', sa.Integer(), nullable=False),
        sa.Column('mastery', sa.Float(), nullable=False),
        sa.Column('trend', sa.String(), nullable=False),
        sa.Column('sample_size', sa.Integer(), nullable=False),
        sa.Column('computed_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'user_id', 'dimension', 'dimension_id',
            name='uq_performance_snapshots_user_dimension',
        ),
    )
    with op.batch_alter_table('performance_snapshots', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_performance_snapshots_user_id'),
            ['user_id'],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table('performance_snapshots', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_performance_snapshots_user_id'))

    op.drop_table('performance_snapshots')
