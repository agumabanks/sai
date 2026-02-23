"""add_watchdog_alert_state

Revision ID: a3f8c2e71d04
Revises: 910bd1947b60
Create Date: 2026-02-15 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a3f8c2e71d04'
down_revision: Union[str, Sequence[str], None] = '910bd1947b60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create watchdog_alert_state table
    op.create_table('watchdog_alert_state',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fingerprint', sa.String(length=32), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('metric', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='open'),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('latest_message', sa.Text(), nullable=False),
        sa.Column('latest_value', sa.String(length=200), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acknowledged_by', sa.String(length=100), nullable=True),
        sa.Column('notification_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('last_notified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_notify_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('backoff_tier', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('occurrence_count', sa.Integer(), nullable=True, server_default='1'),
        sa.Column('heal_attempts', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('heal_successes', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('last_heal_action', sa.String(length=200), nullable=True),
        sa.Column('last_heal_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_watchdog_alert_state_id'), 'watchdog_alert_state', ['id'], unique=False)
    op.create_index(op.f('ix_watchdog_alert_state_fingerprint'), 'watchdog_alert_state', ['fingerprint'], unique=True)
    op.create_index('idx_alert_state_status', 'watchdog_alert_state', ['status'], unique=False)
    op.create_index('idx_alert_state_last_seen', 'watchdog_alert_state', ['last_seen_at'], unique=False)

    # Add fingerprint column to existing alerts table
    op.add_column('alerts', sa.Column('fingerprint', sa.String(length=32), nullable=True))
    op.create_index('idx_alerts_fingerprint', 'alerts', ['fingerprint'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_alerts_fingerprint', table_name='alerts')
    op.drop_column('alerts', 'fingerprint')
    op.drop_index('idx_alert_state_last_seen', table_name='watchdog_alert_state')
    op.drop_index('idx_alert_state_status', table_name='watchdog_alert_state')
    op.drop_index(op.f('ix_watchdog_alert_state_fingerprint'), table_name='watchdog_alert_state')
    op.drop_index(op.f('ix_watchdog_alert_state_id'), table_name='watchdog_alert_state')
    op.drop_table('watchdog_alert_state')
