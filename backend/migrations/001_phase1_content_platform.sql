-- Phase 1 最小中台: 内容资产管理 & 平台发布
-- Migration: 001_phase1_content_platform
-- Created: 2026-03-22

-- ============================================================================
-- 1. 扩展 candidate_products 表
-- ============================================================================

ALTER TABLE candidate_products
ADD COLUMN internal_sku VARCHAR(50) UNIQUE,
ADD COLUMN lifecycle_status VARCHAR(50) DEFAULT 'draft';

CREATE INDEX idx_candidate_products_internal_sku ON candidate_products(internal_sku);
CREATE INDEX idx_candidate_products_lifecycle_status ON candidate_products(lifecycle_status);

-- ============================================================================
-- 2. 创建 content_assets 表
-- ============================================================================

CREATE TABLE content_assets (
    id UUID PRIMARY KEY,
    candidate_product_id UUID NOT NULL REFERENCES candidate_products(id) ON DELETE CASCADE,

    -- 资产类型
    asset_type VARCHAR(50) NOT NULL,

    -- 标签系统
    style_tags TEXT[],
    platform_tags TEXT[],
    region_tags TEXT[],

    -- 文件信息
    file_url TEXT NOT NULL,
    file_size INTEGER,
    dimensions VARCHAR(20),
    format VARCHAR(10),

    -- 质量评分
    ai_quality_score DECIMAL(3,1),
    human_approved BOOLEAN DEFAULT FALSE,
    approval_notes TEXT,

    -- 使用统计
    usage_count INTEGER DEFAULT 0,
    conversion_rate DECIMAL(5,4),

    -- 版本控制
    version INTEGER DEFAULT 1,
    parent_asset_id UUID REFERENCES content_assets(id) ON DELETE SET NULL,

    -- 生成参数
    generation_params JSONB,

    -- 时间戳
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_content_assets_candidate_product_id ON content_assets(candidate_product_id);
CREATE INDEX idx_content_assets_asset_type ON content_assets(asset_type);
CREATE INDEX idx_content_assets_parent_asset_id ON content_assets(parent_asset_id);

-- ============================================================================
-- 3. 创建 platform_listings 表
-- ============================================================================

CREATE TABLE platform_listings (
    id UUID PRIMARY KEY,
    candidate_product_id UUID NOT NULL REFERENCES candidate_products(id) ON DELETE CASCADE,

    -- 平台信息
    platform VARCHAR(50) NOT NULL,
    region VARCHAR(10) NOT NULL,

    -- 平台商品ID
    platform_listing_id VARCHAR(100),
    platform_url TEXT,

    -- 价格和库存
    price DECIMAL(10,2) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    inventory INTEGER DEFAULT 0,

    -- 状态
    status VARCHAR(50) NOT NULL DEFAULT 'pending',

    -- 平台特定数据
    platform_data JSONB,

    -- 同步信息
    last_synced_at TIMESTAMP WITH TIME ZONE,
    sync_error TEXT,

    -- 销售数据
    total_sales INTEGER DEFAULT 0,
    total_revenue DECIMAL(12,2),

    -- 时间戳
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_platform_listings_candidate_product_id ON platform_listings(candidate_product_id);
CREATE INDEX idx_platform_listings_platform ON platform_listings(platform);
CREATE INDEX idx_platform_listings_region ON platform_listings(region);
CREATE INDEX idx_platform_listings_platform_listing_id ON platform_listings(platform_listing_id);
CREATE INDEX idx_platform_listings_status ON platform_listings(status);

-- ============================================================================
-- 4. 创建 listing_asset_associations 表 (多对多关联)
-- ============================================================================

CREATE TABLE listing_asset_associations (
    listing_id UUID NOT NULL REFERENCES platform_listings(id) ON DELETE CASCADE,
    asset_id UUID NOT NULL REFERENCES content_assets(id) ON DELETE CASCADE,
    display_order INTEGER DEFAULT 0,
    is_main BOOLEAN DEFAULT FALSE,

    PRIMARY KEY (listing_id, asset_id)
);

CREATE INDEX idx_listing_asset_associations_listing_id ON listing_asset_associations(listing_id);
CREATE INDEX idx_listing_asset_associations_asset_id ON listing_asset_associations(asset_id);

-- ============================================================================
-- 5. 创建 inventory_sync_logs 表
-- ============================================================================

CREATE TABLE inventory_sync_logs (
    id UUID PRIMARY KEY,
    listing_id UUID NOT NULL REFERENCES platform_listings(id) ON DELETE CASCADE,

    old_inventory INTEGER NOT NULL,
    new_inventory INTEGER NOT NULL,

    sync_status VARCHAR(20) NOT NULL,
    error_message TEXT,

    synced_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX idx_inventory_sync_logs_listing_id ON inventory_sync_logs(listing_id);
CREATE INDEX idx_inventory_sync_logs_synced_at ON inventory_sync_logs(synced_at);

-- ============================================================================
-- 6. 创建 price_history 表
-- ============================================================================

CREATE TABLE price_history (
    id UUID PRIMARY KEY,
    listing_id UUID NOT NULL REFERENCES platform_listings(id) ON DELETE CASCADE,

    old_price DECIMAL(10,2) NOT NULL,
    new_price DECIMAL(10,2) NOT NULL,

    reason VARCHAR(200),
    changed_by VARCHAR(100),

    changed_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX idx_price_history_listing_id ON price_history(listing_id);
CREATE INDEX idx_price_history_changed_at ON price_history(changed_at);

-- ============================================================================
-- 7. 创建触发器：自动更新 updated_at
-- ============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_content_assets_updated_at BEFORE UPDATE ON content_assets
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_platform_listings_updated_at BEFORE UPDATE ON platform_listings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- 完成
-- ============================================================================

COMMENT ON TABLE content_assets IS 'Phase 1: 内容资产库（图片、视频等）';
COMMENT ON TABLE platform_listings IS 'Phase 1: 平台商品映射';
COMMENT ON TABLE listing_asset_associations IS 'Phase 1: 商品与资产的多对多关联';
COMMENT ON TABLE inventory_sync_logs IS 'Phase 1: 库存同步日志';
COMMENT ON TABLE price_history IS 'Phase 1: 价格变更历史';
