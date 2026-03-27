-- Recommendation Feedback
-- Migration: 002_recommendation_feedback
-- Created: 2026-03-27

-- ============================================================================
-- 创建 recommendation_feedback 表
-- ============================================================================

CREATE TABLE recommendation_feedback (
    id UUID PRIMARY KEY,
    candidate_product_id UUID NOT NULL REFERENCES candidate_products(id) ON DELETE CASCADE,
    action VARCHAR(20) NOT NULL,
    comment TEXT,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- 索引
CREATE INDEX idx_recommendation_feedback_candidate_product_id ON recommendation_feedback(candidate_product_id);
CREATE INDEX idx_recommendation_feedback_action ON recommendation_feedback(action);
CREATE INDEX idx_recommendation_feedback_created_at ON recommendation_feedback(created_at);

-- 注释
COMMENT ON TABLE recommendation_feedback IS '用户对推荐的反馈';
COMMENT ON COLUMN recommendation_feedback.action IS '反馈动作: accepted, rejected, deferred';
COMMENT ON COLUMN recommendation_feedback.comment IS '用户评论';
COMMENT ON COLUMN recommendation_feedback.metadata IS '额外元数据（如推荐分数、推荐等级等）';
