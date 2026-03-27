# AutoActionEngine 服务器部署 - 快速参考

> 5 分钟快速部署指南
> 最后更新: 2026-03-27

---

## 前置条件

- ✅ 服务器已部署基础服务 (按 `DEPLOYMENT.md`)
- ✅ PostgreSQL, Redis, Backend, Worker 运行正常
- ✅ 已拉取最新代码

---

## 快速部署 (5 步)

### 1. 进入项目目录

```bash
cd ~/deyes
```

### 2. 执行自动部署脚本

```bash
chmod +x scripts/deploy_auto_action_engine.sh
./scripts/deploy_auto_action_engine.sh
```

脚本会自动完成:
- ✅ 检查基础服务状态
- ✅ 备份现有配置
- ✅ 添加 AutoActionEngine 配置到 `backend/.env`
- ✅ 执行数据库迁移 (`003_auto_action_engine.sql`)
- ✅ 验证数据库结构
- ✅ 重启 backend, worker, beat
- ✅ 验证 API 端点

### 3. 验证部署

```bash
# 检查 API 健康
curl http://127.0.0.1:8000/api/v1/health

# 查看待审批列表
curl http://127.0.0.1:8000/api/v1/auto-actions/pending-approval

# 访问 Swagger 文档
# http://<server-ip>:8000/docs
```

### 4. 查看日志

```bash
# Backend 日志
docker compose logs -f backend | grep -i auto_action

# Worker 日志
docker compose logs -f worker

# Beat 日志 (定时任务)
docker compose logs -f beat
```

### 5. 测试自动上架 (可选)

**重要变更 (2026-03-27)**:
- `recommendation_score`, `risk_score`, `margin_percentage` 参数已废弃
- 服务端会从数据库重新计算这些值（source-of-truth）
- 客户端仍需传递这些字段以保持向后兼容，但值会被忽略

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auto-actions/publish \
  -H "Content-Type: application/json" \
  -d '{
    "candidate_id": "<your-candidate-id>",
    "platform": "temu",
    "region": "US",
    "price": 50.0,
    "currency": "USD",
    "recommendation_score": 80.0,
    "risk_score": 20,
    "margin_percentage": 40.0
  }'
```

**注意**: 上述三个分数字段会被服务端忽略并从数据库真实数据重新计算。

---

## 手动部署 (如果脚本失败)

### 1. 添加配置到 backend/.env

```bash
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
```

### 2. 执行数据库迁移

```bash
docker cp backend/migrations/003_auto_action_engine.sql deyes-postgres:/tmp/
docker compose exec postgres psql -U deyes -d deyes -f /tmp/003_auto_action_engine.sql
```

### 3. 重启服务

```bash
docker compose restart backend worker beat
```

---

## 配置说明

### 审批边界 (Approval Boundaries)

**重要**: 审批决策基于服务端从数据库重算的真实值（PricingAssessment, RiskAssessment, normalized_attributes），不依赖客户端传入的分数。

**自动执行 (无需审批)**:
- 推荐分数 ≥ 75
- 风险分数 < 30
- 利润率 ≥ 35%

**需要审批**:
- 首次上架新商品
- 高风险品类 (风险分数 ≥ 50)
- 高价商品 (价格 > $100)
- 低利润率 (< 25%)

### 定时任务

- **每天凌晨 2:00** - 自动调价 (`auto_reprice_all_listings`)
- **每天凌晨 3:00** - 自动暂停 (`auto_pause_all_listings`)
- **每天凌晨 4:00** - 自动换素材 (`auto_asset_switch_all_listings`)

---

## 常见问题

### Q1: 脚本执行失败

**检查基础服务**:
```bash
docker compose ps
docker compose logs backend | tail -50
```

### Q2: 数据库迁移失败

**手动执行**:
```bash
docker cp backend/migrations/003_auto_action_engine.sql deyes-postgres:/tmp/
docker compose exec postgres psql -U deyes -d deyes -f /tmp/003_auto_action_engine.sql
```

### Q3: API 端点不存在

**确认路由已注册**:
```bash
grep "routes_auto_actions" backend/app/main.py
docker compose restart backend
```

### Q4: 配置未生效

**确认 .env 文件位置**:
```bash
ls -la backend/.env
grep "ENABLE_AUTO_ACTIONS" backend/.env
docker compose restart backend worker
```

---

## 下一步

1. **查看完整文档**: `docs/deployment/auto-action-engine-deployment.md`
2. **查看使用指南**: `docs/services/auto-action-engine.md`
3. **调整审批边界**: 根据实际运营情况修改 `backend/.env`
4. **启用真实 API**: 设置 `TEMU_USE_MOCK=false` 并配置 API 凭证

---

## 相关文档

- [完整部署指南](auto-action-engine-deployment.md) - 详细部署步骤、故障排查
- [使用指南](../services/auto-action-engine.md) - API 使用示例、配置说明
- [统一部署指南](../../DEPLOYMENT.md) - 基础服务部署
- [项目状态报告](../PROJECT_STATUS.md) - 战略转向说明

---

**最后更新**: 2026-03-27
**状态**: 生产就绪
