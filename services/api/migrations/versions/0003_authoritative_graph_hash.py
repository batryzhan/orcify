"""Track authoritative graph hash separately from reducer replay hash."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0003_authoritative_graph_hash"
down_revision: str | None = "0002_snapshots_approvals"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("current_graph_hash", sa.String(length=64), nullable=True))
    op.execute(
        """UPDATE projects SET current_graph_hash = COALESCE(
            (SELECT snapshot_hash FROM project_snapshots
             WHERE project_snapshots.tenant_id = projects.tenant_id
               AND project_snapshots.project_id = projects.project_id
               AND project_snapshots.snapshot_kind = 'graph'
             ORDER BY revision DESC LIMIT 1),
            current_snapshot_hash
        )"""
    )
    with op.batch_alter_table("projects") as batch_op:
        batch_op.alter_column("current_graph_hash", nullable=False)


def downgrade() -> None:
    op.drop_column("projects", "current_graph_hash")
