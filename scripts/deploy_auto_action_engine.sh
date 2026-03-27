#!/bin/bash
# AutoActionEngine 快速部署脚本
# 用法: ./scripts/deploy_auto_action_engine.sh

set -e  # 遇到错误立即退出

echo "=========================================="
echo "AutoActionEngine 部署脚本"
echo "=========================================="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查是否在项目根目录
if [ ! -f "docker-compose.yaml" ]; then
    echo -e "${RED}错误: 请在项目根目录执行此脚本${NC}"
    exit 1
fi

# 步骤 1: 检查基础服务
echo -e "${YELLOW}[1/7] 检查基础服务状态...${NC}"
if ! docker compose ps | grep -q "deyes-postgres.*Up"; then
    echo -e "${RED}错误: PostgreSQL 未运行,请先执行 'docker compose up -d postgres'${NC}"
    exit 1
fi
if ! docker compose ps | grep -q "deyes-backend.*Up"; then
    echo -e "${RED}错误: Backend 未运行,请先执行 'docker compose up -d backend'${NC}"
    exit 1
fi
echo -e "${GREEN}✓ 基础服务运行正常${NC}"
echo ""

# 步骤 2: 备份现有配置
echo -e "${YELLOW}[2/7] 备份现有配置...${NC}"
if [ -f "backend/.env" ]; then
    BACKUP_FILE="backend/.env.backup.$(date +%Y%m%d_%H%M%S)"
    cp backend/.env "$BACKUP_FILE"
    echo -e "${GREEN}✓ 已备份到 $BACKUP_FILE${NC}"
else
    echo -e "${YELLOW}⚠ backend/.env 不存在,跳过备份${NC}"
fi
echo ""

# 步骤 3: 添加 AutoActionEngine 配置
echo -e "${YELLOW}[3/7] 添加 AutoActionEngine 配置...${NC}"
if grep -q "ENABLE_AUTO_ACTIONS" backend/.env 2>/dev/null; then
    echo -e "${YELLOW}⚠ AutoActionEngine 配置已存在,跳过${NC}"
else
    cat >> backend/.env <<'EOF'

# Auto Action Engine (2026-03-27)
ENABLE_AUTO_ACTIONS=true

# Auto Publish Rules
AUTO_PUBLISH_REQUIRE_APPROVAL_FIRST_TIME=true
AUTO_PUBLISH_REQUIRE_APPROVAL_HIGH_RISK=true
AUTO_PUBLISH_REQUIRE_APPROVAL_PRICE_ABOVE=100.0
AUTO_PUBLISH_REQUIRE_APPROVAL_MARGIN_BELOW=0.25
AUTO_PUBLISH_AUTO_EXECUTE_SCORE_ABOVE=75.0
AUTO_PUBLISH_AUTO_EXECUTE_RISK_BELOW=30
AUTO_PUBLISH_AUTO_EXECUTE_MARGIN_ABOVE=0.35

# Auto Reprice Rules
AUTO_REPRICE_ENABLE=true
AUTO_REPRICE_TARGET_ROI=0.30
AUTO_REPRICE_LOW_ROI_THRESHOLD=0.24
AUTO_REPRICE_HIGH_ROI_THRESHOLD=0.36
AUTO_REPRICE_DECREASE_PERCENTAGE=0.08
AUTO_REPRICE_INCREASE_PERCENTAGE=0.04
AUTO_REPRICE_MAX_CHANGE_PERCENTAGE=0.10
AUTO_REPRICE_LOOKBACK_DAYS=7

# Auto Pause Rules
AUTO_PAUSE_ENABLE=true
AUTO_PAUSE_ROI_THRESHOLD=0.10
AUTO_PAUSE_LOOKBACK_DAYS=7
AUTO_PAUSE_MIN_DATA_POINTS=7

# Auto Asset Switch Rules
AUTO_ASSET_SWITCH_ENABLE=true
AUTO_ASSET_SWITCH_CTR_THRESHOLD=0.80
AUTO_ASSET_SWITCH_LOOKBACK_DAYS=7

# Platform API Configuration
TEMU_USE_MOCK=true
EOF
    echo -e "${GREEN}✓ 配置已添加到 backend/.env${NC}"
fi
echo ""

# 步骤 4: 执行数据库迁移
echo -e "${YELLOW}[4/7] 执行数据库迁移...${NC}"
if [ ! -f "backend/migrations/003_auto_action_engine.sql" ]; then
    echo -e "${RED}错误: 迁移文件不存在: backend/migrations/003_auto_action_engine.sql${NC}"
    exit 1
fi

# 复制迁移文件到容器
docker cp backend/migrations/003_auto_action_engine.sql deyes-postgres:/tmp/

# 执行迁移
if docker compose exec -T postgres psql -U deyes -d deyes -f /tmp/003_auto_action_engine.sql > /dev/null 2>&1; then
    echo -e "${GREEN}✓ 数据库迁移成功${NC}"
else
    echo -e "${YELLOW}⚠ 迁移可能已执行过,继续...${NC}"
fi
echo ""

# 步骤 5: 验证数据库结构
echo -e "${YELLOW}[5/7] 验证数据库结构...${NC}"
if docker compose exec -T postgres psql -U deyes -d deyes -c "\d platform_listings" | grep -q "approval_required"; then
    echo -e "${GREEN}✓ platform_listings 表结构正确${NC}"
else
    echo -e "${RED}错误: platform_listings 表缺少新字段${NC}"
    exit 1
fi

if docker compose exec -T postgres psql -U deyes -d deyes -c "\dt price_history" | grep -q "price_history"; then
    echo -e "${GREEN}✓ price_history 表已创建${NC}"
else
    echo -e "${RED}错误: price_history 表不存在${NC}"
    exit 1
fi
echo ""

# 步骤 6: 重启服务
echo -e "${YELLOW}[6/7] 重启服务...${NC}"
docker compose restart backend
echo -e "${GREEN}✓ Backend 已重启${NC}"

docker compose restart worker
echo -e "${GREEN}✓ Worker 已重启${NC}"

docker compose restart beat
echo -e "${GREEN}✓ Beat 已重启${NC}"

# 等待服务启动
echo -e "${YELLOW}等待服务启动 (10秒)...${NC}"
sleep 10
echo ""

# 步骤 7: 验证部署
echo -e "${YELLOW}[7/7] 验证部署...${NC}"

# 检查 API 健康
if curl -s http://127.0.0.1:8000/api/v1/health | grep -q "ok"; then
    echo -e "${GREEN}✓ API 健康检查通过${NC}"
else
    echo -e "${RED}错误: API 健康检查失败${NC}"
    exit 1
fi

# 检查 AutoActionEngine 端点
if curl -s http://127.0.0.1:8000/docs | grep -q "auto-actions"; then
    echo -e "${GREEN}✓ AutoActionEngine 端点已注册${NC}"
else
    echo -e "${YELLOW}⚠ 无法确认 AutoActionEngine 端点,请手动检查 http://127.0.0.1:8000/docs${NC}"
fi

echo ""
echo "=========================================="
echo -e "${GREEN}部署完成!${NC}"
echo "=========================================="
echo ""
echo "下一步:"
echo "1. 访问 API 文档: http://<server-ip>:8000/docs"
echo "2. 查看使用指南: docs/services/auto-action-engine.md"
echo "3. 查看部署文档: docs/deployment/auto-action-engine-deployment.md"
echo ""
echo "测试命令:"
echo "  curl http://127.0.0.1:8000/api/v1/auto-actions/pending-approval"
echo ""
echo "查看日志:"
echo "  docker compose logs -f backend | grep -i auto_action"
echo "  docker compose logs -f worker"
echo "  docker compose logs -f beat"
echo ""
