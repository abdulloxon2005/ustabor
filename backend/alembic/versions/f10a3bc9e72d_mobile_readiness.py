"""Mobile readiness: dispatch, location, device tokens, admin settings and chat moderation.

Revision ID: f10a3bc9e72d
Revises: d33b7979a340
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f10a3bc9e72d"
down_revision: Union[str, None] = "d33b7979a340"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("master_profiles") as batch_op:
        batch_op.add_column(sa.Column("location_sharing_enabled", sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.add_column(sa.Column("location_updated_at", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("orders") as batch_op:
        batch_op.add_column(sa.Column("dispatch_radius_km", sa.Integer(), server_default="0", nullable=False))
    with op.batch_alter_table("order_messages") as batch_op:
        batch_op.add_column(sa.Column("is_hidden", sa.Boolean(), server_default=sa.false(), nullable=False))

    op.create_table(
        "device_tokens",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(length=512), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )
    op.create_index("ix_device_tokens_user_id", "device_tokens", ["user_id"])

    op.create_table(
        "platform_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("commission_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("commission_rate", sa.Integer(), server_default="10", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "chat_reports",
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("reported_by", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="open", nullable=False),
        sa.Column("admin_note", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["order_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reported_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_reports_order_id", "chat_reports", ["order_id"])
    op.create_index("ix_chat_reports_message_id", "chat_reports", ["message_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_reports_message_id", table_name="chat_reports")
    op.drop_index("ix_chat_reports_order_id", table_name="chat_reports")
    op.drop_table("chat_reports")
    op.drop_table("platform_settings")
    op.drop_index("ix_device_tokens_user_id", table_name="device_tokens")
    op.drop_table("device_tokens")
    with op.batch_alter_table("order_messages") as batch_op:
        batch_op.drop_column("is_hidden")
    with op.batch_alter_table("orders") as batch_op:
        batch_op.drop_column("dispatch_radius_km")
    with op.batch_alter_table("master_profiles") as batch_op:
        batch_op.drop_column("location_updated_at")
        batch_op.drop_column("location_sharing_enabled")
