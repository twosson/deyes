-- ============================================================================
-- Migration: 003_auto_action_engine
-- Description: Add auto action engine support to platform_listings
-- Date: 2026-03-27
-- ============================================================================

-- Add new columns to platform_listings
ALTER TABLE platform_listings
ADD COLUMN IF NOT EXISTS approval_required BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS approval_reason TEXT,
ADD COLUMN IF NOT EXISTS auto_action_metadata JSONB,
ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP WITH TIME ZONE,
ADD COLUMN IF NOT EXISTS approved_by VARCHAR(100),
ADD COLUMN IF NOT EXISTS rejected_at TIMESTAMP WITH TIME ZONE,
ADD COLUMN IF NOT EXISTS rejected_by VARCHAR(100),
ADD COLUMN IF NOT EXISTS rejection_reason TEXT,
ADD COLUMN IF NOT EXISTS last_auto_action_at TIMESTAMP WITH TIME ZONE;

-- Add index for approval queries
CREATE INDEX IF NOT EXISTS idx_platform_listings_approval_required
ON platform_listings(approval_required)
WHERE approval_required = TRUE;

-- Add index for status queries
CREATE INDEX IF NOT EXISTS idx_platform_listings_status_approval
ON platform_listings(status, approval_required);

-- Update status enum to include new states
-- Note: PostgreSQL doesn't support ALTER TYPE ADD VALUE in transaction
-- This needs to be run separately or with COMMIT before ALTER TYPE

-- Create price_history table
CREATE TABLE IF NOT EXISTS price_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    listing_id UUID NOT NULL REFERENCES platform_listings(id) ON DELETE CASCADE,
    old_price DECIMAL(10, 2) NOT NULL,
    new_price DECIMAL(10, 2) NOT NULL,
    reason VARCHAR(100) NOT NULL,
    changed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Add index for price history queries
CREATE INDEX IF NOT EXISTS idx_price_history_listing_id
ON price_history(listing_id);

CREATE INDEX IF NOT EXISTS idx_price_history_changed_at
ON price_history(changed_at DESC);

-- Add comments
COMMENT ON COLUMN platform_listings.approval_required IS 'Whether this listing requires human approval before publishing';
COMMENT ON COLUMN platform_listings.approval_reason IS 'Reason why approval is required (e.g., high_price, low_margin, first_time)';
COMMENT ON COLUMN platform_listings.auto_action_metadata IS 'Metadata for auto actions (recommendation_score, risk_score, etc.)';
COMMENT ON COLUMN platform_listings.approved_at IS 'Timestamp when listing was approved';
COMMENT ON COLUMN platform_listings.approved_by IS 'User who approved the listing';
COMMENT ON COLUMN platform_listings.rejected_at IS 'Timestamp when listing was rejected';
COMMENT ON COLUMN platform_listings.rejected_by IS 'User who rejected the listing';
COMMENT ON COLUMN platform_listings.rejection_reason IS 'Reason for rejection';
COMMENT ON COLUMN platform_listings.last_auto_action_at IS 'Timestamp of last auto action (reprice, pause, asset switch)';

COMMENT ON TABLE price_history IS 'History of price changes for platform listings';
COMMENT ON COLUMN price_history.listing_id IS 'Reference to platform listing';
COMMENT ON COLUMN price_history.old_price IS 'Previous price';
COMMENT ON COLUMN price_history.new_price IS 'New price after change';
COMMENT ON COLUMN price_history.reason IS 'Reason for price change (e.g., low_roi, high_roi)';
COMMENT ON COLUMN price_history.changed_at IS 'Timestamp when price was changed';
