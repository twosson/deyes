# 平台经营模式矩阵

> 定义各平台的库存模式、激活阈值、佣金率等核心经营参数
>
> 版本: v1.0
> 创建时间: 2026-03-29
> 数据来源: `backend/app/services/listing_activation_service.py`, `backend/app/agents/platform_publisher.py`

---

## 📋 核心概念

### 两种库存模式

#### PRE_ORDER（预售模式）
- **适用平台**: Temu, AliExpress, TikTok Shop
- **核心特点**: 先上架后采购，订单驱动履约
- **激活条件**: 需要供应商报价，允许 0 库存上架
- **典型场景**: 快速测款、轻资产运营、供应链响应快

#### STOCK_FIRST（备货模式）
- **适用平台**: Amazon, Ozon, Walmart, Wildberries
- **核心特点**: 先采购后上架，库存驱动销售
- **激活条件**: 需要达到最低库存阈值才能激活
- **典型场景**: 稳定供应链、高周转品类、平台要求现货

---

## 📊 平台经营模式矩阵

| 平台 | 推荐模式 | 最低库存阈值 | 佣金率 | 币种 | 备注 |
|------|---------|-------------|--------|------|------|
| **Temu** | `PRE_ORDER` | 0 (预售) / 10 (备货) | 8% | USD | 支持双模式，预售为主 |
| **Amazon** | `STOCK_FIRST` | 50 | 15% | USD/EUR/GBP | 严格要求现货，FBA 优先 |
| **AliExpress** | `PRE_ORDER` | 0 (预售) / 20 (备货) | - | USD | 支持双模式，预售为主 |
| **Ozon** | `STOCK_FIRST` | 30 | 10% | RUB | 俄罗斯本地仓优先 |
| **Wildberries** | `STOCK_FIRST` | 25 | - | RUB | 俄罗斯本地仓必须 |
| **Shopee** | `PRE_ORDER` | 0 (预售) / 15 (备货) | 6% | 多币种 | 东南亚市场，预售为主 |
| **Mercado Libre** | `PRE_ORDER` | 0 (预售) / 20 (备货) | - | 多币种 | 拉美市场，支持双模式 |
| **TikTok Shop** | `PRE_ORDER` | 0 (预售) / 10 (备货) | 5% | USD | 直播电商，预售为主 |
| **eBay** | `STOCK_FIRST` | 5 | - | USD | 灵活库存要求 |
| **Walmart** | `STOCK_FIRST` | 40 | - | USD | 严格现货要求 |
| **Rakuten** | `STOCK_FIRST` | 20 | - | JPY | 日本市场，现货为主 |
| **Allegro** | `STOCK_FIRST` | 15 | - | PLN | 波兰市场，现货为主 |

**数据来源**:
- 最低库存阈值: `backend/app/services/listing_activation_service.py:20-33`
- 佣金率: `backend/app/agents/platform_publisher.py:54-61`

---

## 🔄 双模式支持平台

部分平台支持同一 SKU 同时运营两种模式：

### Temu
- **预售模式**: 0 库存即可上架，订单后触发采购
- **备货模式**: 需 10 件库存，直接发货

### AliExpress
- **预售模式**: 0 库存即可上架，标注预售期
- **备货模式**: 需 20 件库存，海外仓发货

### Shopee
- **预售模式**: 0 库存即可上架，7-15 天发货
- **备货模式**: 需 15 件库存，本地仓发货

---

## 🎯 激活规则详解

### PRE_ORDER 模式激活条件

```python
# 代码位置: backend/app/services/listing_activation_service.py:126-130

if inventory_mode == InventoryMode.PRE_ORDER:
    eligible = has_supplier_offer
    reason = None if eligible else "no_supplier_offer"
    min_inventory_required = 0
```

**必要条件**:
1. ✅ 有供应商报价（`SupplierOffer` 记录存在）
2. ✅ 供应商状态为 `ACTIVE`
3. ✅ 供应商响应时间 ≤ 平台要求

**可选条件**:
- 库存数量（允许为 0）
- 现货库存（不要求）

### STOCK_FIRST 模式激活条件

```python
# 代码位置: backend/app/services/listing_activation_service.py:132-136

if inventory_mode == InventoryMode.STOCK_FIRST:
    min_inventory_required = PLATFORM_INVENTORY_THRESHOLDS.get(listing.platform, 10)
    eligible = available_quantity >= min_inventory_required
    reason = None if eligible else f"insufficient_inventory"
```

**必要条件**:
1. ✅ 可用库存 ≥ 平台最低阈值
2. ✅ 库存状态为 `AVAILABLE`（非预留、非冻结）
3. ✅ 仓库位置符合平台要求

**可选条件**:
- 供应商报价（建议有，但非必须）
- 补货计划（建议有，避免断货）

---

## 💰 佣金率与定价策略

### 平台佣金率

| 平台 | 佣金率 | 备注 |
|------|--------|------|
| Temu | 8% | 低佣金，高流量 |
| Amazon | 15% | 高佣金，品牌溢价 |
| Ozon | 10% | 俄罗斯主流平台 |
| Shopee | 6% | 东南亚低佣金 |
| TikTok Shop | 5% | 直播电商，最低佣金 |

### 定价策略矩阵

| 策略 | 加价倍数 | 最低毛利率 | 适用场景 |
|------|---------|-----------|---------|
| **Standard** | 2.5x | 25% | 常规品类 |
| **Aggressive** | 2.0x | 20% | 竞争激烈品类 |
| **Premium** | 3.0x | 30% | 高端品类 |

**代码位置**: `backend/app/agents/platform_publisher.py:38-52`

---

## 🌍 地区与币种映射

| 地区代码 | 币种 | 主要平台 |
|---------|------|---------|
| `us` | USD | Temu, Amazon, eBay, Walmart |
| `uk` | GBP | Amazon UK |
| `de` | EUR | Amazon DE |
| `fr` | EUR | Amazon FR |
| `es` | EUR | Amazon ES |
| `it` | EUR | Amazon IT |
| `au` | AUD | Amazon AU |
| `ca` | CAD | Amazon CA |
| `ru` | RUB | Ozon, Wildberries |
| `jp` | JPY | Rakuten, Amazon JP |

**代码位置**: `backend/app/agents/platform_publisher.py:63-75`

---

## 📈 库存阈值设计原则

### 为什么不同平台阈值不同？

1. **平台政策要求**
   - Amazon: 严格要求现货，FBA 需 50+ 件
   - Temu: 允许预售，0 库存即可

2. **物流时效要求**
   - 本地仓平台（Ozon, Wildberries）: 需 25-30 件
   - 跨境平台（AliExpress, Shopee）: 可 0-20 件

3. **竞争环境**
   - 高竞争平台（Amazon）: 高库存保证不断货
   - 新兴平台（TikTok Shop）: 低库存快速测款

4. **资金周转**
   - 预售模式: 0 库存，资金占用低
   - 备货模式: 高库存，资金占用高

---

## 🔧 实现细节

### 数据库字段

```sql
-- ProductVariant 表
inventory_mode VARCHAR(20) NOT NULL  -- 'pre_order' | 'stock_first'

-- PlatformListing 表
inventory_mode VARCHAR(20)  -- 继承自 variant，可覆盖
min_inventory_to_activate INT  -- 平台特定阈值
```

### 服务接口

```python
# ListingActivationService
async def check_activation_eligibility(
    db: AsyncSession,
    listing_id: UUID,
) -> ActivationEligibility:
    """检查 listing 是否满足激活条件"""

# ActivationEligibility 返回结构
@dataclass
class ActivationEligibility:
    eligible: bool
    reason: Optional[str]
    inventory_mode: Optional[InventoryMode]
    available_quantity: int
    min_inventory_required: int
    has_supplier_offer: bool
```

**代码位置**: `backend/app/services/listing_activation_service.py:36-151`

---

## 🎯 使用建议

### 选择 PRE_ORDER 模式的场景
- ✅ 新品测款，不确定销量
- ✅ 供应链响应快（3-7 天）
- ✅ 资金有限，不想压货
- ✅ 平台允许预售（Temu, AliExpress）

### 选择 STOCK_FIRST 模式的场景
- ✅ 爆款复制，销量可预测
- ✅ 平台要求现货（Amazon, Walmart）
- ✅ 追求快速发货（1-2 天）
- ✅ 有稳定供应链和仓储能力

### 双模式并行策略
- Temu 用 PRE_ORDER 测款
- 验证后 Amazon 用 STOCK_FIRST 放量
- 同一 SKU，不同平台不同模式

---

## 📚 相关文档

- [SKU 激活规则](./sku-activation-rules.md)
- [平台内容规则矩阵](./platform-content-rules.md)
- [双模式经营架构实施计划](../roadmap/dual-mode-operations-plan.md)
- [ListingActivationService 实现](../../backend/app/services/listing_activation_service.py)

---

**最后更新**: 2026-03-29
**维护者**: Deyes 研发团队
**数据状态**: 生产环境实际配置
