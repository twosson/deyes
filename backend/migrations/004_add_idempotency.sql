-- ============================================================================
-- Migration: 004_add_idempotency
-- Description: Add idempotency key support to platform_listings
-- Date: 2026-03-27
-- ============================================================================

ALTER TABLE platform_listings
ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(255);

CREATE INDEX IF NOT EXISTS idx_platform_listings_idempotency_key
ON platform_listings(idempotency_key);

COMMENT ON COLUMN platform_listings.idempotency_key IS 'Idempotency key for preventing duplicate auto actions';
