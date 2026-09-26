"""normalise snapshot_run status values and restrict them"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

_STATUS_VALUES = ("running", "succeeded", "no_new_data", "failed")


def upgrade() -> None:
    # Rows stored with enum member names ("SUCCEEDED") instead of values
    # ("succeeded") cannot be loaded by the model, which maps values only.
    op.execute("UPDATE snapshot_run SET status = lower(status) WHERE status <> lower(status)")
    allowed = ", ".join(f"'{value}'" for value in _STATUS_VALUES)
    op.create_check_constraint("ck_snapshot_run_status", "snapshot_run", f"status IN ({allowed})")


def downgrade() -> None:
    # The lowercasing is not reverted: lowercase values are the only form the
    # model has ever been able to read.
    op.drop_constraint("ck_snapshot_run_status", "snapshot_run", type_="check")
