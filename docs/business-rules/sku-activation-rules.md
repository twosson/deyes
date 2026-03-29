# SKU 激活规则

> 定义 SKU 和 Listing 在不同库存模式下的激活条件、状态流转与业务逻辑
>
> 版本: v1.0
> 创建时间: 2026-03-29
> 数据来源: `backend/app/services/listing_activation_service.py`, `backend/app/core/enums.py`

---

## 📋 核心概念

### 库存模式

#### PRE_ORDER（预售模式）
- **定义**: 先上架后采购，订单驱动履约
- **激活条件**: 有供应商报价即可
- **适用平台**: Temu, AliExpress, TikTok Shop, Shopee, Mercado Libre

#### STOCK_FIRST（备货模式）
- **定义**: 先采购后上架，库存驱动销售
- **激活条件**: 库存 ≥ 平台最低阈值
- **适用平台**: Amazon, Ozon, Walmart, Wildberries, Rakuten, Allegro, eBay

### SKU 生命周期状态

```python
# 代码位置: backend/app/core/enums.py:131-135

class ProductMasterStatus(str, Enum):
    DRAFT = "draft"        # 草稿
    ACTIVE = "active"      # 激活
    ARCHIVED = "archived"  # 归档

class ProductVariantStatus(str, Enum):
    DRAFT = "draft"        # 草稿
    ACTIVE = "active"      # 激活
    ARCHIVED = "archived"  # 归档
```

### Listing 状态流转

```python
# 代码位置: backend/app/core/enums.py:83-98

class PlatformListingStatus(str, Enum):
    DRAFT = "draft"                              # 草稿
    PENDING_APPROVAL = "pending_approval"        # 待审批
    APPROVED = "approved"                        # 已审批
    PENDING = "pending"                          # 待上架
    PUBLISHING = "publishing"                    # 上架中
    ACTIVE = "active"                            # 已上架（激活）
    PAUSED = "paused"                            # 已暂停
    OUT_OF_STOCK = "out_of_stock"                # 缺货
    REJECTED = "rejected"                        # 被拒绝
    DELISTED = "delisted"                        # 已下架
    FALLBACK_QUEUED = "fallback_queued"          # RPA fallback queued
    FALLBACK_RUNNING = "fallback_running"        # RPA fallback running
    MANUAL_INTERVENTION_REQUIRED = "manual_intervention_required"  # 需人工介入
```

---

## 🎯 SKU 激活规则详解

### PRE_ORDER 模式激活条件

```python
# 代码位置: backend/app/services/listing_activation_service.py:126-130

if inventory_mode == InventoryMode.PRE_ORDER:
    eligible = has_supplier_offer
    reason = None if eligible else "no_supplier_offer"
    min_inventory_required = 0
```

**必要条件**:
| 条件 | 要求 | 检查逻辑 |
|------|------|---------|
| 有供应商报价 | ✅ 必须 | `SupplierOffer.variant_id == variant.id` |
| 供应商状态 | ACTIVE | `Supplier.status == SupplierStatus.ACTIVE` |
| 库存数量 | 不要求 | 允许 0 库存 |

**可选条件**:
| 条件 | 建议 | 说明 |
|------|------|------|
| 现货库存 | 可选 | 有则优先发货 |
| 供应商响应时间 | ≤ 7 天 | 影响履约速度 |
| 供应商履约率 | ≥ 95% | 影响订单完成率 |

**失败原因**:
| reason | 说明 | 解决方案 |
|--------|------|---------|
| `no_supplier_offer` | 无供应商报价 | 添加供应商报价 |
| `no_variant_linkage` | Listing 未关联 SKU | 关联 ProductVariant |
| `variant_not_found` | SKU 不存在 | 创建 SKU |
| `unknown_inventory_mode` | 库存模式未设置 | 设置 inventory_mode |

### STOCK_FIRST 模式激活条件

```python
# 代码位置: backend/app/services/listing_activation_service.py:132-136

if inventory_mode == InventoryMode.STOCK_FIRST:
    min_inventory_required = PLATFORM_INVENTORY_THRESHOLDS.get(listing.platform, 10)
    eligible = available_quantity >= min_inventory_required
    reason = None if eligible else f"insufficient_inventory"
```

**必要条件**:
| 条件 | 要求 | 检查逻辑 |
|------|------|---------|
| 可用库存 | ≥ 平台阈值 | `InventoryLevel.available_quantity >= threshold` |
| 库存状态 | AVAILABLE | 非预留、非冻结 |
| 仓库位置 | 符合平台要求 | 部分平台要求本地仓 |

**平台库存阈值**:
| 平台 | 最低库存 | 说明 |
|------|---------|------|
| Temu | 10 | 备货模式阈值 |
| Amazon | 50 | FBA 要求 |
| AliExpress | 20 | 海外仓建议 |
| Ozon | 30 | 俄罗斯本地仓 |
| Wildberries | 25 | 俄罗斯本地仓 |
| Shopee | 15 | 东南亚海外仓 |
| Mercado Libre | 20 | 拉美海外仓 |
| TikTok Shop | 10 | 备货模式阈值 |
| eBay | 5 | 灵活要求 |
| Walmart | 40 | 严格现货 |
| Rakuten | 20 | 日本本地仓 |
| Allegro | 15 | 波兰本地仓 |

**代码位置**: `backend/app/services/listing_activation_service.py:20-33`

**失败原因**:
| reason | 说明 | 解决方案 |
|--------|------|---------|
| `insufficient_inventory` | 库存不足 | 补货至阈值以上 |
| `no_variant_linkage` | Listing 未关联 SKU | 关联 ProductVariant |
| `variant_not_found` | SKU 不存在 | 创建 SKU |
| `unknown_inventory_mode` | 库存模式未设置 | 设置 inventory_mode |

---

## 📊 激活流程图

### PRE_ORDER 模式激活流程

```
                    ┌─────────────────┐
                    │ SKU 创建        │
                    │ inventory_mode  │
                    │ = PRE_ORDER     │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ 有供应商报价？   │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              │              ▼
         ┌─────────┐         │         ┌─────────┐
         │   是    │         │         │   否    │
         └────┬────┘         │         └────┬────┘
              │              │              │
              ▼              │              ▼
    ┌─────────────────┐      │      ┌─────────────────┐
    │ ✅ 可激活       │      │      │ ❌ 无法激活     │
    │ min_inventory   │      │      │ reason:         │
    │ = 0            │      │      │ no_supplier_    │
    │                 │      │      │ offer           │
    └────────┬────────┘      │      └─────────────────┘
             │               │
             ▼               │
    ┌─────────────────┐      │
    │ 创建 Listing    │      │
    │ status=ACTIVE   │      │
    └─────────────────┘      │
                             │
```

### STOCK_FIRST 模式激活流程

```
                    ┌─────────────────┐
                    │ SKU 创建        │
                    │ inventory_mode  │
                    │ = STOCK_FIRST   │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ 查询可用库存     │
                    │ available_      │
                    │ quantity        │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ 库存 ≥ 平台阈值？│
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              │              ▼
         ┌─────────┐         │         ┌─────────┐
         │   是    │         │         │   否    │
         └────┬────┘         │         └────┬────┘
              │              │              │
              ▼              │              ▼
    ┌─────────────────┐      │      ┌─────────────────┐
    │ ✅ 可激活       │      │      │ ❌ 无法激活     │
    │ status=ACTIVE   │      │      │ reason:         │
    └────────┬────────┘      │      │ insufficient_   │
             │               │      │ inventory       │
             ▼               │      │ (need N, have M)│
    ┌─────────────────┐      │      └─────────────────┘
    │ 创建 Listing    │      │
    │ status=ACTIVE   │      │
    └─────────────────┘      │
                             │
```

---

## 🔄 Listing 状态流转

### 正常流转路径

```
DRAFT → PENDING_APPROVAL → APPROVED → PENDING → PUBLISHING → ACTIVE
                                                      │
                                                      ▼
                         PAUSED ←── ACTIVE ──→ OUT_OF_STOCK
                           │                      │
                           ▼                      ▼
                         DELISTED              DELISTED
```

### 状态说明

| 状态 | 触发条件 | 可执行操作 |
|------|---------|-----------|
| `DRAFT` | 创建 Listing | 编辑、提交审批 |
| `PENDING_APPROVAL` | 提交审批 | 等待审批结果 |
| `APPROVED` | 审批通过 | 准备上架 |
| `PENDING` | 准备上架 | 检查激活条件 |
| `PUBLISHING` | 调用平台 API | 等待上架结果 |
| `ACTIVE` | 上架成功 | 正常销售、暂停、下架 |
| `PAUSED` | 手动暂停或库存预警 | 恢复上架、下架 |
| `OUT_OF_STOCK` | 库存归零 | 补货、下架 |
| `REJECTED` | 平台拒绝 | 修改、重新提交 |
| `DELISTED` | 下架 | 重新上架、归档 |

### 状态转换触发器

| 触发器 | 当前状态 | 目标状态 | 条件 |
|--------|---------|---------|------|
| `submit_for_approval` | DRAFT | PENDING_APPROVAL | 内容完整 |
| `approve` | PENDING_APPROVAL | APPROVED | 审批通过 |
| `reject` | PENDING_APPROVAL | REJECTED | 审批拒绝 |
| `check_activation` | APPROVED/PENDING | ACTIVE/PENDING | 激活条件检查 |
| `publish` | PENDING | PUBLISHING | 开始上架 |
| `publish_success` | PUBLISHING | ACTIVE | 上架成功 |
| `publish_fail` | PUBLISHING | REJECTED | 上架失败 |
| `pause` | ACTIVE | PAUSED | 手动暂停 |
| `resume` | PAUSED | ACTIVE | 恢复上架 |
| `out_of_stock` | ACTIVE | OUT_OF_STOCK | 库存归零 |
| `restock` | OUT_OF_STOCK | ACTIVE | 库存恢复 |
| `delist` | ANY | DELISTED | 下架 |

---

## 🛠️ 服务接口

### ListingActivationService

```python
# 代码位置: backend/app/services/listing_activation_service.py

@dataclass
class ActivationEligibility:
    eligible: bool                    # 是否可激活
    reason: Optional[str]             # 不可激活原因
    inventory_mode: Optional[InventoryMode]  # 库存模式
    available_quantity: int           # 可用库存
    min_inventory_required: int       # 最低库存要求
    has_supplier_offer: bool          # 是否有供应商报价

class ListingActivationService:
    async def check_activation_eligibility(
        db: AsyncSession,
        listing_id: UUID,
    ) -> ActivationEligibility:
        """检查 listing 是否满足激活条件"""

    async def activate_listing_if_eligible(
        db: AsyncSession,
        listing_id: UUID,
    ) -> tuple[bool, Optional[str]]:
        """如果满足条件则激活 listing"""
```

### 使用示例

```python
# 检查激活条件
eligibility = await activation_service.check_activation_eligibility(
    db=db_session,
    listing_id=listing_id,
)

if eligibility.eligible:
    print(f"可以激活: 库存模式={eligibility.inventory_mode}")
else:
    print(f"无法激活: 原因={eligibility.reason}")

# 尝试激活
activated, reason = await activation_service.activate_listing_if_eligible(
    db=db_session,
    listing_id=listing_id,
)
```

---

## 📐 设计原则

### 为什么 PRE_ORDER 不要求库存？

1. **业务模式差异**
   - Temu 等平台允许预售，订单后才采购
   - 减少资金压力，快速测款
   - 供应商响应时间决定履约能力

2. **风险控制**
   - 必须有供应商报价（确保供应链）
   - 供应商履约率监控
   - 订单超时自动取消

### 为什么 STOCK_FIRST 要求库存阈值？

1. **平台政策要求**
   - Amazon FBA 要求最低入库量
   - 保证发货时效（1-2 天）
   - 避免断货影响店铺评分

2. **用户体验保障**
   - 现货立即可发
   - 减少取消订单率
   - 提高店铺评分

### 为什么不同平台阈值不同？

1. **物流时效要求**
   - Amazon: 2 天发货 → 高库存
   - Temu: 7-15 天发货 → 低库存

2. **竞争环境**
   - 高竞争平台: 高库存保证不断货
   - 新兴平台: 低库存快速测款

3. **资金周转**
   - 高阈值: 资金占用大，风险高
   - 低阈值: 资金灵活，风险低

---

## 🎯 最佳实践

### PRE_ORDER 模式最佳实践

1. **供应商管理**
   - 选择响应时间 ≤ 7 天的供应商
   - 定期评估供应商履约率
   - 建立备用供应商

2. **订单管理**
   - 设置订单超时自动取消（默认 15 天）
   - 监控未发货订单
   - 及时通知买家发货进度

3. **风险控制**
   - 单 SKU 单供应商订单量限制
   - 供应商断供时自动下架
   - 负面评价监控

### STOCK_FIRST 模式最佳实践

1. **库存管理**
   - 设置安全库存预警（阈值 × 1.5）
   - 自动补货触发点（阈值 × 0.8）
   - 定期盘点校准

2. **补货策略**
   - 基于历史销量预测补货量
   - 考虑供应商交货周期
   - 旺季提前备货

3. **滞销处理**
   - 30 天无销量预警
   - 60 天无销量自动降价
   - 90 天无销量自动下架

### 双模式并行策略

1. **测款阶段**
   - Temu 用 PRE_ORDER 快速测款
   - 收集销量、评价数据
   - 低成本验证市场需求

2. **放量阶段**
   - 验证成功后转 STOCK_FIRST
   - Amazon 用备货模式放量
   - 高库存保证发货时效

3. **SKU 管理**
   - 同一 SKU 可有多平台 Listing
   - 每个 Listing 可独立设置库存模式
   - 统一 SKU 主数据，灵活库存策略

---

## 📚 相关文档

- [平台经营模式矩阵](./platform-mode-matrix.md)
- [平台内容规则矩阵](./platform-content-rules.md)
- [双模式经营架构实施计划](../roadmap/dual-mode-operations-plan.md)
- [ListingActivationService 实现](../../backend/app/services/listing_activation_service.py)
- [InventoryAllocator 实现](../../backend/app/services/inventory_allocator.py)

---

**最后更新**: 2026-03-29
**维护者**: Deyes 研发团队
**数据状态**: 生产环境实际配置
