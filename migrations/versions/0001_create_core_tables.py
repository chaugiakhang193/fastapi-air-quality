"""create core tables"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

_SEED_LOCATIONS = [
    {
        "code": "hanoi",
        "name": "Hà Nội",
        "latitude": 21.0245,
        "longitude": 105.84117,
        "timezone": "Asia/Ho_Chi_Minh",
    },
    {
        "code": "hcmc",
        "name": "Thành phố Hồ Chí Minh",
        "latitude": 10.82302,
        "longitude": 106.62965,
        "timezone": "Asia/Ho_Chi_Minh",
    },
    {
        "code": "danang",
        "name": "Đà Nẵng",
        "latitude": 16.06778,
        "longitude": 108.22083,
        "timezone": "Asia/Ho_Chi_Minh",
    },
    {
        "code": "dienbienphu",
        "name": "Điện Biên Phủ",
        "latitude": 21.38602,
        "longitude": 103.02301,
        "timezone": "Asia/Ho_Chi_Minh",
    },
    {
        "code": "dalat",
        "name": "Đà Lạt",
        "latitude": 11.94646,
        "longitude": 108.44193,
        "timezone": "Asia/Ho_Chi_Minh",
    },
]


def upgrade() -> None:
    location = op.create_table(
        "location",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
    )
    op.bulk_insert(location, _SEED_LOCATIONS)

    op.create_table(
        "model_run",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("model", sa.String(32), nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("check_count", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("model", "run_at", name="uq_model_run_model_run_at"),
    )

    op.create_table(
        "snapshot",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("model_run_id", sa.Integer(), sa.ForeignKey("model_run.id"), nullable=False),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("location.id"), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.UniqueConstraint("model_run_id", "location_id", name="uq_snapshot_model_run_location"),
    )

    op.create_table(
        "air_reading",
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("location.id"), primary_key=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("pm2_5", sa.Float(), nullable=True),
        sa.Column("pm10", sa.Float(), nullable=True),
        sa.Column("us_aqi", sa.Integer(), nullable=True),
        sa.Column("european_aqi", sa.Integer(), nullable=True),
        sa.Column("model_run_id", sa.Integer(), sa.ForeignKey("model_run.id"), nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "snapshot_run",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("model_run_id", sa.Integer(), sa.ForeignKey("model_run.id"), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_detail", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("snapshot_run")
    op.drop_table("air_reading")
    op.drop_table("snapshot")
    op.drop_table("model_run")
    op.drop_table("location")
