"""add provider to agent_profiles

Revision ID: a4f3b2f5d101
Revises: 90c1f2326ced
Create Date: 2026-02-25 13:42:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a4f3b2f5d101"
down_revision = "90c1f2326ced"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("agent_profiles", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "provider",
                sa.String(length=20),
                nullable=False,
                server_default="openai",
            ),
        )
    op.execute("UPDATE agent_profiles SET provider = 'openai' WHERE provider IS NULL")


def downgrade() -> None:
    with op.batch_alter_table("agent_profiles", schema=None) as batch_op:
        batch_op.drop_column("provider")
