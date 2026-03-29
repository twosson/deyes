"""Migration: Add ERP Lite procurement and inventory schema.

Revision ID: 007_erp_lite_procurement
Revises: 006_demand_discovery_metadata
Create Date: 2026-03-29 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "007_erp_lite_procurement"
down_revision: Union[str, None] = "006_demand_discovery_metadata"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return inspector.has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _has_index(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    # Create product_masters table
    if not _has_table("product_masters"):
        op.create_table(
            "product_masters",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("candidate_product_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("internal_sku", sa.String(length=50), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("category", sa.String(length=100), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["candidate_product_id"], ["candidate_products.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("internal_sku"),
        )
        op.create_index("idx_product_masters_internal_sku", "product_masters", ["internal_sku"])
        op.create_index("idx_product_masters_candidate_product_id", "product_masters", ["candidate_product_id"])

    # Create product_variants table
    if not _has_table("product_variants"):
        op.create_table(
            "product_variants",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("master_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("variant_sku", sa.String(length=50), nullable=False),
            sa.Column("attributes", sa.JSON(), nullable=True),
            sa.Column("inventory_mode", sa.String(length=50), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["master_id"], ["product_masters.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_product_variants_master_id", "product_variants", ["master_id"])
        op.create_index(
            "uq_variant_sku",
            "product_variants",
            ["master_id", "variant_sku"],
            unique=True,
        )

    # Create suppliers table
    if not _has_table("suppliers"):
        op.create_table(
            "suppliers",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("alibaba_id", sa.String(length=100), nullable=True),
            sa.Column("contact_email", sa.String(length=255), nullable=True),
            sa.Column("contact_phone", sa.String(length=20), nullable=True),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
        )
        op.create_index("idx_suppliers_name", "suppliers", ["name"])
        op.create_index("idx_suppliers_alibaba_id", "suppliers", ["alibaba_id"])

    # Create supplier_offers table
    if not _has_table("supplier_offers"):
        op.create_table(
            "supplier_offers",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("unit_price", sa.DECIMAL(precision=10, scale=2), nullable=False),
            sa.Column("currency", sa.String(length=3), nullable=False),
            sa.Column("moq", sa.Integer(), nullable=False),
            sa.Column("lead_time_days", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
            sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_supplier_offers_supplier_id", "supplier_offers", ["supplier_id"])
        op.create_index("idx_supplier_offers_variant_id", "supplier_offers", ["variant_id"])
        op.create_index(
            "uq_supplier_offer",
            "supplier_offers",
            ["supplier_id", "variant_id"],
            unique=True,
        )

    # Create purchase_orders table
    if not _has_table("purchase_orders"):
        op.create_table(
            "purchase_orders",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("po_number", sa.String(length=50), nullable=False),
            sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("order_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expected_delivery_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column("actual_delivery_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column("total_amount", sa.DECIMAL(precision=12, scale=2), nullable=True),
            sa.Column("currency", sa.String(length=3), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("po_number"),
        )
        op.create_index("idx_purchase_orders_po_number", "purchase_orders", ["po_number"])
        op.create_index("idx_purchase_orders_supplier_id", "purchase_orders", ["supplier_id"])

    # Create purchase_order_items table
    if not _has_table("purchase_order_items"):
        op.create_table(
            "purchase_order_items",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("purchase_order_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("unit_price", sa.DECIMAL(precision=10, scale=2), nullable=False),
            sa.Column("line_total", sa.DECIMAL(precision=12, scale=2), nullable=False),
            sa.ForeignKeyConstraint(["purchase_order_id"], ["purchase_orders.id"]),
            sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_purchase_order_items_purchase_order_id", "purchase_order_items", ["purchase_order_id"])
        op.create_index("idx_purchase_order_items_variant_id", "purchase_order_items", ["variant_id"])

    # Create inbound_shipments table
    if not _has_table("inbound_shipments"):
        op.create_table(
            "inbound_shipments",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("purchase_order_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("tracking_number", sa.String(length=100), nullable=True),
            sa.Column("shipment_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expected_arrival_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column("actual_arrival_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["purchase_order_id"], ["purchase_orders.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_inbound_shipments_purchase_order_id", "inbound_shipments", ["purchase_order_id"])
        op.create_index("idx_inbound_shipments_tracking_number", "inbound_shipments", ["tracking_number"])

    # Create inventory_levels table
    if not _has_table("inventory_levels"):
        op.create_table(
            "inventory_levels",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("available_quantity", sa.Integer(), nullable=False),
            sa.Column("reserved_quantity", sa.Integer(), nullable=False),
            sa.Column("damaged_quantity", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("variant_id"),
        )
        op.create_index("idx_inventory_levels_variant_id", "inventory_levels", ["variant_id"])

    # Create inventory_movements table
    if not _has_table("inventory_movements"):
        op.create_table(
            "inventory_movements",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("inbound_shipment_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("movement_type", sa.String(length=50), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("reference_id", sa.String(length=100), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"]),
            sa.ForeignKeyConstraint(["inbound_shipment_id"], ["inbound_shipments.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_inventory_movements_variant_id", "inventory_movements", ["variant_id"])
        op.create_index("idx_inventory_movements_inbound_shipment_id", "inventory_movements", ["inbound_shipment_id"])

    # Add compatibility columns to content_assets
    if _has_table("content_assets") and not _has_column("content_assets", "product_variant_id"):
        op.add_column(
            "content_assets",
            sa.Column("product_variant_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.create_foreign_key(
            "fk_content_assets_product_variant_id",
            "content_assets",
            "product_variants",
            ["product_variant_id"],
            ["id"],
        )
        op.create_index("idx_content_assets_product_variant_id", "content_assets", ["product_variant_id"])

    # Add compatibility columns to platform_listings
    if _has_table("platform_listings"):
        if not _has_column("platform_listings", "product_variant_id"):
            op.add_column(
                "platform_listings",
                sa.Column("product_variant_id", postgresql.UUID(as_uuid=True), nullable=True),
            )
            op.create_foreign_key(
                "fk_platform_listings_product_variant_id",
                "platform_listings",
                "product_variants",
                ["product_variant_id"],
                ["id"],
            )
            op.create_index("idx_platform_listings_product_variant_id", "platform_listings", ["product_variant_id"])

        if not _has_column("platform_listings", "inventory_mode"):
            op.add_column(
                "platform_listings",
                sa.Column("inventory_mode", sa.String(length=50), nullable=True),
            )
            op.create_index("idx_platform_listings_inventory_mode", "platform_listings", ["inventory_mode"])


def downgrade() -> None:
    # Remove compatibility columns in reverse order
    if _has_table("platform_listings"):
        if _has_index("platform_listings", "idx_platform_listings_inventory_mode"):
            op.drop_index("idx_platform_listings_inventory_mode", table_name="platform_listings")
        if _has_column("platform_listings", "inventory_mode"):
            op.drop_column("platform_listings", "inventory_mode")

        if _has_index("platform_listings", "idx_platform_listings_product_variant_id"):
            op.drop_index("idx_platform_listings_product_variant_id", table_name="platform_listings")
        if _has_column("platform_listings", "product_variant_id"):
            op.drop_constraint("fk_platform_listings_product_variant_id", "platform_listings", type_="foreignkey")
            op.drop_column("platform_listings", "product_variant_id")

    if _has_table("content_assets"):
        if _has_index("content_assets", "idx_content_assets_product_variant_id"):
            op.drop_index("idx_content_assets_product_variant_id", table_name="content_assets")
        if _has_column("content_assets", "product_variant_id"):
            op.drop_constraint("fk_content_assets_product_variant_id", "content_assets", type_="foreignkey")
            op.drop_column("content_assets", "product_variant_id")

    # Drop tables in reverse order
    if _has_table("inventory_movements"):
        op.drop_table("inventory_movements")
    if _has_table("inventory_levels"):
        op.drop_table("inventory_levels")
    if _has_table("inbound_shipments"):
        op.drop_table("inbound_shipments")
    if _has_table("purchase_order_items"):
        op.drop_table("purchase_order_items")
    if _has_table("purchase_orders"):
        op.drop_table("purchase_orders")
    if _has_table("supplier_offers"):
        op.drop_table("supplier_offers")
    if _has_table("suppliers"):
        op.drop_table("suppliers")
    if _has_table("product_variants"):
        op.drop_table("product_variants")
    if _has_table("product_masters"):
        op.drop_table("product_masters")
