# Stage 4 回归验证 Checklist

## 核心验证命令

```bash
cd backend

# Stage 4 专项测试
pytest tests/test_phase4_order_fulfillment.py -v
pytest tests/test_refund_analysis_service.py -v
pytest tests/test_profit_ledger_service.py -v
pytest tests/test_operating_metrics_service.py -v
pytest tests/test_feedback_aggregator.py::test_feedback_aggregator_consumes_real_profit -v
pytest tests/test_feedback_aggregator.py::test_feedback_aggregator_fallback_to_theoretical_profit -v

# Stage 1-3 核心回归
pytest tests/test_phase1_mvp.py -v
pytest tests/test_dual_mode_phase3_integration.py -v
```

## 验收标准

### A. 订单导入与库存联动
- [ ] 订单导入幂等（重复导入同一订单不产生重复）
- [ ] SKU/listing 映射正确
- [ ] pre_order 订单创建 reservation
- [ ] stock_first 订单直接扣减库存

### B. 退款分析服务
- [ ] 退款案件可创建并关联订单/SKU
- [ ] 退款率可按 SKU/listing 聚合
- [ ] 退款原因可汇总分布
- [ ] 退款案件可联动利润台账

### C. 利润台账服务
- [ ] 订单行可生成利润台账
- [ ] 退款可调整利润台账
- [ ] 广告成本可分摊
- [ ] SKU/listing/supplier 利润快照可查询
- [ ] 平台维度利润快照可查询

### D. 经营快照服务
- [ ] SKU 经营快照可查询（利润+退款+表现）
- [ ] Listing 经营快照可查询（利润+退款+表现）
- [ ] Supplier 经营快照可查询（利润）

### E. 反馈闭环升级
- [ ] FeedbackAggregator 优先消费真实损益事实
- [ ] 真实数据不足时自动 fallback 到理论利润
- [ ] Stage 1-3 核心回归不受影响

## 测试覆盖矩阵

| 服务 | 单元测试 | 集成测试 | 回归测试 |
|------|---------|---------|---------|
| OrderIngestionService | ✅ | ✅ | ✅ |
| RefundAnalysisService | ✅ | ✅ | ✅ |
| ProfitLedgerService | ✅ | ✅ | ✅ |
| OperatingMetricsService | ✅ | ✅ | ✅ |
| FeedbackAggregator | ✅ | ✅ | ✅ |

## 核心验证场景

### 场景 1: 订单导入幂等
```python
# 重复导入同一订单
order1 = await service.ingest_order(db, platform, region, "ORDER-001", payload)
order2 = await service.ingest_order(db, platform, region, "ORDER-001", payload)
assert order1.id == order2.id  # 应返回同一订单
```

### 场景 2: SKU/listing 映射
```python
# 订单行应正确映射到 listing 和 variant
order = await service.ingest_order(db, platform, region, "ORDER-002", payload)
line = order.lines[0]
assert line.platform_listing_id == listing.id
assert line.product_variant_id == variant.id
```

### 场景 3: pre_order 订单创建 reservation
```python
# pre_order 模式订单应创建库存预留
order, actions = await service.ingest_order_with_inventory(db, platform, region, "ORDER-003", payload)
assert len(actions["reservations_created"]) == 1
assert len(actions["outbound_movements"]) == 0
```

### 场景 4: stock_first 订单直接扣减库存
```python
# stock_first 模式订单应直接扣减库存
order, actions = await service.ingest_order_with_inventory(db, platform, region, "ORDER-004", payload)
assert len(actions["reservations_created"]) == 0
assert len(actions["outbound_movements"]) == 1
```

### 场景 5: 退款案件联动利润台账
```python
# 退款案件应自动���新利润台账
refund_case = await refund_service.create_refund_case(db, order_id, amount, ...)
updated_ledger = await refund_service.link_refund_to_profit_ledger(db, refund_case.id)
assert updated_ledger.refund_loss == amount
```

### 场景 6: 广告成本分摊
```python
# 广告成本应按比例分摊到利润台账
updated_ledgers = await profit_service.allocate_ad_cost(db, listing_id, ad_cost, date)
assert sum(ledger.ad_cost for ledger in updated_ledgers) == ad_cost
```

### 场景 7: SKU/listing/supplier 利润快照
```python
# 应可查询多维度利润快照
sku_snapshot = await profit_service.get_profit_snapshot(db, variant_id=variant_id)
listing_snapshot = await profit_service.get_listing_profitability(db, listing_id)
supplier_snapshot = await profit_service.get_supplier_profitability(db, supplier_id)
assert sku_snapshot["entry_count"] > 0
```

### 场景 8: FeedbackAggregator 消费真实损益事实
```python
# 当真实利润数据充足时（>= 10 条），应优先使用真实数据
aggregator = FeedbackAggregator(lookback_days=90)
await aggregator.refresh(db)
prior = aggregator.get_seed_performance_prior(seed, seed_type)
# 真实利润应提升 prior 分数
```

### 场景 9: FeedbackAggregator fallback 到理论利润
```python
# 当真实利润数据不足时（< 10 条），应 fallback 到理论利润
aggregator = FeedbackAggregator(lookback_days=90)
await aggregator.refresh(db)
prior = aggregator.get_seed_performance_prior(seed, seed_type)
# 应使用 PricingAssessment 和 RiskAssessment 计算 prior
```

## 性能基准

| 操作 | 目标延迟 | 备注 |
|------|---------|------|
| 订单导入 | < 100ms | 单订单 |
| 利润台账生成 | < 50ms | 单订单行 |
| 退款率查询 | < 200ms | 单 SKU/listing |
| 利润快照查询 | < 300ms | 单 SKU/listing/supplier |
| 经营快照查询 | < 500ms | 单 SKU/listing（含多维度聚合） |

## 数据一致性检查

### 利润台账一致性
```sql
-- 利润台账净利应等于：gross_revenue - platform_fee - refund_loss - ad_cost - fulfillment_cost
SELECT
    id,
    gross_revenue,
    platform_fee,
    refund_loss,
    ad_cost,
    fulfillment_cost,
    net_profit,
    (gross_revenue - platform_fee - refund_loss - ad_cost - fulfillment_cost) AS calculated_net_profit
FROM profit_ledger
WHERE net_profit != (gross_revenue - platform_fee - refund_loss - ad_cost - fulfillment_cost);
-- 应返回 0 行
```

### 退款率一致性
```sql
-- 退款率应等于：refunded_orders / total_orders * 100
SELECT
    product_variant_id,
    COUNT(DISTINCT platform_order_id) AS total_orders,
    COUNT(DISTINCT CASE WHEN refund_amount > 0 THEN platform_order_id END) AS refunded_orders,
    ROUND(COUNT(DISTINCT CASE WHEN refund_amount > 0 THEN platform_order_id END)::NUMERIC / COUNT(DISTINCT platform_order_id) * 100, 2) AS refund_rate
FROM refund_cases
GROUP BY product_variant_id;
```

## 回归验证流程

1. **运行 Stage 4 专项测试**
   ```bash
   pytest tests/test_phase4_order_fulfillment.py -v
   pytest tests/test_refund_analysis_service.py -v
   pytest tests/test_profit_ledger_service.py -v
   pytest tests/test_operating_metrics_service.py -v
   ```

2. **运行 FeedbackAggregator 升级测试**
   ```bash
   pytest tests/test_feedback_aggregator.py::test_feedback_aggregator_consumes_real_profit -v
   pytest tests/test_feedback_aggregator.py::test_feedback_aggregator_fallback_to_theoretical_profit -v
   ```

3. **运行 Stage 1-3 核心回归**
   ```bash
   pytest tests/test_phase1_mvp.py -v
   pytest tests/test_dual_mode_phase3_integration.py -v
   ```

4. **验证数据一致性**
   - 运行上述 SQL 一致性检查
   - 确认无数据不一致

5. **性能基准测试**
   - 使用 pytest-benchmark 测试关键操作延迟
   - 确认符合性能基准

## 成功标准

- ✅ 所有 Stage 4 专项测试通过
- ✅ FeedbackAggregator 升级测试通过
- ✅ Stage 1-3 核心回归测试通过
- ✅ 数据一致性检查通过
- ✅ 性能基准符合目标

## 故障排查

### 订单导入失败
- 检查 idempotency_key 是否正确
- 检查 platform_sku 是否存在于 PlatformListing
- 检查 product_variant_id 映射是否正确

### 利润台账计算错误
- 检查 SupplierOffer 是否存在
- 检查 platform_fee 计算是否正确（默认 10%）
- 检查 net_profit 公式是否正确

### 退款率查询异常
- 检查 RefundCase 是否正确关联 PlatformOrder
- 检查 product_variant_id 或 platform_listing_id 是否正确
- 检查日期范围是否正确

### FeedbackAggregator 未消费真实数据
- 检查 ProfitLedger entry_count 是否 >= 10
- 检查 product_variant_id 是否正确关联
- 检查 lookback_days 是否覆盖数据时间范围

---

**最后更新**: 2026-03-29
**文档版本**: v1.0
**状态**: 生产就绪
