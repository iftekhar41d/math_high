"""initial baseline

Revision ID: a830b32f3f44
Revises: 
Create Date: 2026-08-28 21:52:30.470399

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a830b32f3f44'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Baseline revision. The walking skeleton has no domain tables yet — running
    # this against a fresh database just establishes `alembic_version` as the
    # schema anchor. Phase 1 domain tables (User, YearLevel, Subject, ...) are
    # added by later tickets' migrations that chain off this one.
    pass


def downgrade() -> None:
    pass
