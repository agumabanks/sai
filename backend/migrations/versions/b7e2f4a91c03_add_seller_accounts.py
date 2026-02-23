"""add_seller_accounts

Revision ID: b7e2f4a91c03
Revises: a3f8c2e71d04
Create Date: 2026-02-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b7e2f4a91c03'
down_revision: Union[str, Sequence[str], None] = 'a3f8c2e71d04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('seller_accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('seller_uuid', sa.String(length=36), nullable=False),
        sa.Column('soko_user_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('shop_name', sa.String(length=255), nullable=True),
        sa.Column('phone', sa.String(length=20), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('whatsjet_vendor_uid', sa.String(length=100), nullable=True),
        sa.Column('api_key', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='active', nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_seller_accounts_id', 'seller_accounts', ['id'])
    op.create_index('ix_seller_accounts_seller_uuid', 'seller_accounts', ['seller_uuid'], unique=True)
    op.create_index('idx_seller_accounts_phone', 'seller_accounts', ['phone'])
    op.create_index('idx_seller_accounts_email', 'seller_accounts', ['email'])
    op.create_index('ix_seller_accounts_api_key', 'seller_accounts', ['api_key'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_seller_accounts_api_key', table_name='seller_accounts')
    op.drop_index('idx_seller_accounts_email', table_name='seller_accounts')
    op.drop_index('idx_seller_accounts_phone', table_name='seller_accounts')
    op.drop_index('ix_seller_accounts_seller_uuid', table_name='seller_accounts')
    op.drop_index('ix_seller_accounts_id', table_name='seller_accounts')
    op.drop_table('seller_accounts')
