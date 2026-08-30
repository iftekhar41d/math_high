"""animations table + animation_topics m2m

Revision ID: f9eb9224e28e
Revises: 837888981cfc
Create Date: 2026-08-30 10:22:07.326952

Phase 2 ticket 10. `animations` makes a rendered explainer video first-class
content: `slug` (the natural key the ContentAdmin upload screen upserts by),
`title` / `description`, `video_key` + nullable `transcript_key` (keys into the
`MediaStorage` seam, served by nginx's `/media/` path), nullable
`duration_seconds`, and `status` (`draft` / `published`, mirroring
`LectureContent` — a student sees `published` only). `animation_topics` is the
many-to-many with `Topic` ("one or more Topics" per `CONTEXT.md`), both FKs
`ON DELETE CASCADE`. Two plain `create_table`s, batch mode for the slug index;
up/down/up round-trip verified.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f9eb9224e28e'
down_revision: Union[str, None] = '837888981cfc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'animations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('slug', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column(
            'description', sa.Text(), server_default='', nullable=False
        ),
        sa.Column('video_key', sa.String(), nullable=False),
        sa.Column('transcript_key', sa.String(), nullable=True),
        sa.Column('duration_seconds', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('animations', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_animations_slug'), ['slug'], unique=True
        )

    op.create_table(
        'animation_topics',
        sa.Column('animation_id', sa.Integer(), nullable=False),
        sa.Column('topic_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ['animation_id'], ['animations.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['topic_id'], ['topics.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('animation_id', 'topic_id'),
    )


def downgrade() -> None:
    op.drop_table('animation_topics')
    with op.batch_alter_table('animations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_animations_slug'))

    op.drop_table('animations')
