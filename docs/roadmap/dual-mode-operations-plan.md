# 双模式经营架构实施计划

> 基于深度业务分析与自研 ERP Lite 内核设计
>
> 版本: v1.0
> 创建时间: 2026-03-29
> 状态: 待实施

---

## 📋 文档目标

本文档是对 Stage 3-6 规划的**业务场景具体化**，明确回答：

1. **什么时候商品进入商品库？** → 通过选品阈值后立即转 SKU
2. **什么时候生成主图/详情图？** → SKU 建立后生成基础素材，发布前派生平台素材
3. **如何支持 Temu 先上架后采购 vs 传统先采购后上架？** → 统一 SKU 内核，分支在 listing 激活条件
4. **如何支持多平台/多语言/多尺寸素材？** → 三层素材体系（基础 → 平台派生 → 本地化）

---

## 🎯 核心结论

### 1. 商品进入商品库的最佳时机

**不是采购后，不是上架后，而是：**

```
CandidateProduct 通过阈值
    ↓
立即转化为 ProductMaster / ProductVariant (SKU)
    ↓
从"发现态"进入"经营态"
```

**原因**：
- SKU 是长期经营实体，可跨平台复用
- 采购、库存、订单、利润都围绕 SKU 展开
- 不同平台可共享同一 SKU 的主数据

**当前缺口**：
- `PlatformListing` 直接挂 `candidate_product_id`（`backend/app/db/models.py:381-384`）
- 缺少 `ProductMaster / ProductVariant` 模型

---

### 2. 主图/详情图的最佳生成时机

**不是等订单，不是等采购，而是分两层：**

#### Layer 1：SKU 建立后立即生成基础通用素材
- 无文字主图
- 无文字详情图基础版
- 高分辨率母版
- 风格标签（minimalist / cute / luxury）

#### Layer 2：具体平台发布前派生发布素材
- Temu US 主图：800x800，可有英语卖点角标
- Amazon US 主图：1000x1000，无文字
- Temu JP 主图：800x800，日语标注
- Amazon DE 详情图：德语尺寸规范版

**原因**：
- 基础素材可跨平台复用
- 避免每个平台/语言都从头生成
- 只有视觉差异大时才重新生成

**当前状态**：
- `ContentAsset` 模型已有 `style_tags/platform_tags/region_tags/variant_group`（`backend/app/db/models.py:320-324`）
- `ContentAssetManagerAgent` 已实现但未接入主流程（`backend/app/agents/content_asset_manager.py:23-158`）
- `DirectorWorkflow` 不包含图像生成步骤（`backend/app/agents/director_workflow.py:49-115`）

---

### 3. 两种经营模式的统一支持

#### 模式 A：Temu 类 `pre_order`（先上架/先出单，再采购履约）

```
SKU 建立
  → 生成基础素材/文案
  → 创建 PlatformListing (inventory_mode="pre_order")
  → 直接激活上架 (min_inventory_to_activate=0)
  → 订单进入
  → 创建 InventoryReservation
  → 触发 PurchaseOrder
  → 到货/履约
  → 利润结算
```

**特点**：
- 上架不依赖现货
- 订单驱动采购
- 重点是 reservation、履约、供应商响应

#### 模式 B：传统 `stock_first`（先采购入库，再上架销售）

```
SKU 建立
  → 生成基础素材/文案
  → 创建 PurchaseOrder
  → 入库
  → available_inventory 达标
  → 创建/激活 PlatformListing (inventory_mode="stock_first")
  → 订单进入
  → 扣减库存/履约
  → 利润结算
```

**特点**：
- 上架依赖库存
- 采购驱动销售
- 重点是库存阈值、补货、周转

#### 关键原则

**两种模式共享同一套 SKU / Supplier / Inventory / Order / Profit 内核，只在"Listing 激活条件"与"订单后是否触发采购"上分支。**

**分支点不在选品阶段，而在 listing activation gate。**

---

### 4. 多变体素材管理最优方案

#### 三层素材体系

**Layer 1：基础通用素材**
- 按 SKU 生成，和具体平台解绑
- 无文字主图、无文字详情图基础版
- 高分辨率母版
- 风格标签（minimalist / cute / luxury）
- 作为所有平台派生的 source-of-truth

**Layer 2：发布派生素材**
- 按平台、地区、语言派生
- Temu US 主图：800x800，可有英语卖点角标
- Amazon US 主图：1000x1000，无文字
- Temu JP 主图：800x800，日语标注
- 这层才是最终挂到 `PlatformListing` 上的素材

**Layer 3：本地化内容层**
- 图片里的文字、卖点、标题、描述
- 不和图片文件强耦合
- 新增 `LocalizationContent` 表
- 新增 `PlatformContentRule` 表

#### 素材最优原则

1. **主图优先"无文字母版"**
   - Amazon 主图普遍要求无文字
   - 同一视觉更容易跨平台复用
   - 语言变化时不必重新生成整个画面

2. **详情图允许"模板 + 标注派生"**
   - 详情图常需要语言化卖点
   - 最好是"基础图层 + 本地化标注层"组合输出
   - 避免每种语言都从零生成视觉

3. **平台差异优先做"派生"而非"重生成"**
   - 如果只是尺寸不同、裁切不同、是否允许文字不同
   - 优先做 resize / crop / overlay / template render
   - 而不是重新跑完整的 ComfyUI 生成

4. **只有这些情况才重新生成视觉**
   - 不同地区审美明显不同
   - 平台合规要求导致画面结构要变
   - 需要完全不同场景图��格
   - A/B 测试要换风格方向

---

## 🏗️ 自研 ERP Lite 内核边界

不接 Odoo，系统内部要自己承担这些模块：

### 1. 商品中心
- `ProductMaster`
- `ProductVariant / SKU`

### 2. 供应商中心
- `Supplier`
- `SupplierOffer`

### 3. 采购中心
- `PurchaseOrder`
- `PurchaseOrderLine`
- `InboundShipment`

### 4. 库存中心
- `Warehouse`
- `InventoryBalance`
- `InventoryMovement`
- `InventoryReservation`

### 5. 订单中心
- `PlatformOrder`
- `PlatformOrderLine`
- `FulfillmentRecord`

### 6. 售后中心
- `RefundCase`
- `ReturnCase`
- `AfterSaleIssue`

### 7. 利润中心
- `SettlementEntry`
- `AdCostAllocation`
- `ProfitLedger`

### 8. 平台发布中心
- `PlatformListing`
- `UnifiedListingService`
- `PlatformRegistry`
- `PlatformPolicy / PlatformContentRule`

### 9. 内容与本地化中心
- `ContentAsset`（扩展）
- `LocalizationContent`
- `PlatformContentRule`

### 10. 自动经营控制平面
- `SkuLifecycleState`
- `LifecycleRule`
- `ActionRule`
- `ActionExecutionLog`

---

## 📅 开发计划

### Phase 0：业务规则矩阵定义（1-2 天）

#### 目标
把平台模式和素材规则先抽象清楚，避免后面反复返工。

#### 要产出

**1. 平台经营模式矩阵**

| 平台 | 模式 | min_inventory_to_activate | auto_reserve_on_order | auto_replenish_threshold |
|------|------|--------------------------|----------------------|-------------------------|
| Temu | pre_order | 0 | true | 10 |
| Amazon | stock_first | 50 | true | 20 |
| Ozon | stock_first | 30 | true | 15 |
| AliExpress | pre_order | 0 | true | 10 |

**2. 平台内容规则矩阵**

| 平台 | 主图尺寸 | 详情图尺寸 | 详情图数量 | 主图允许文字 | 详情图允许文字 |
|------|---------|-----------|-----------|------------|--------------|
| Temu | 800x800 | 800x1200 | 8 | true | true |
| Amazon | 1000x1000 | 1000x1000 | 7 | false | true |
| Ozon | 1200x1200 | 1200x1200 | 15 | true | true |

**3. SKU 激活规则**

```python
# pre_order 模式
if sku.inventory_mode == "pre_order":
    can_activate = (
        has_base_assets and
        has_localization_content and
        has_supplier_offer
    )

# stock_first 模式
if sku.inventory_mode == "stock_first":
    can_activate = (
        has_base_assets and
        has_localization_content and
        available_inventory >= min_inventory_to_activate
    )
```

#### 验收标准
- [ ] 平台模式矩阵文档完成
- [ ] 平台内容规则矩阵文档完成
- [ ] SKU 激活规则文档完成

---

### Phase 1：ERP Lite 核心 Schema（80-116h）

#### 目标
建立真正的经营事实层。

#### 要做

**1. 商品主数据（15-20h）**
- 新增 `ProductMaster` 模型
- 新增 `ProductVariant` 模型
- 实现 `ProductMasterService.create_from_candidate()`
- 实现 SKU 生命周期基础字段

**2. 供应商主数据（19-27h）**
- 新增 `Supplier` 模型
- 新增 `SupplierOffer` 模型
- 实现 `SupplierMasterService.resolve_supplier_entity()`
- 实现供应商归一化逻辑

**3. 采购履约（17-25h）**
- 新增 `PurchaseOrder` 模型
- 新增 `PurchaseOrderLine` 模型
- 新增 `InboundShipment` 模型
- 实现 `ProcurementService` 基础框架

### 4. 库存事实层（16-23h）
- 新增 `Warehouse` 模型
- 新增 `InventoryLevel` 模型
- 新增 `InventoryMovement` 模型
- 新增 `InventoryReservation` 模型
- 实现 `InventoryAllocator` 服务

**5. 调整现有关系（13-21h）**
- `PlatformListing` 增加 `product_variant_id` 字段
- `PlatformListing` 增加 `inventory_mode` 字段
- `ContentAsset` 增加 `product_variant_id` 字段
- 实现 Candidate → SKU 转化服务
- 更新 `DirectorWorkflow` 接入 SKU 转化

#### 验收标准
- [ ] 一个 Candidate 可稳定转 ProductMaster / SKU
- [ ] 一个 SKU 可绑定主供应商
- [ ] 一个 SKU 可有库存事实
- [ ] 一个 SKU 可区分 `pre_order` / `stock_first`
- [ ] migration 可成功执行
- [ ] 核心测试通过

#### 参考文档
- `docs/roadmap/stage3-implementation-tasks.md`
- `docs/roadmap/stage3-development-backlog.md`

---

### Phase 2：素材与本地化体系（24-36h）

#### 目标
让素材真正可服务多平台、多语言、多尺寸。

#### 要做

**1. 扩展 ContentAsset 模型（4-6h）**
- 新增 `language_tags` 字段
- 新增 `spec` 字段（结构化尺寸规格）
- 新增 `compliance_tags` 字段
- 新增 `usage_scope` 字段
- 更新 migration

**2. 新增本地化内容模型（8-12h）**
- 新增 `LocalizationContent` 模型
- 实现 `LocalizationService`
- 实现本地化内容生成逻辑
- 实现本地化内容查询接口

**3. 新增平台内容规则（6-8h）**
- 新增 `PlatformContentRule` 模型
- 实现 `PlatformAssetAdapter`
- 实现平台变体生成逻辑

**4. 接入内容生成主流程（6-10h）**
- 在 `DirectorWorkflow` 里增加 `ContentAssetManagerAgent` 步骤
- 实现 SKU 创建后自动生成基础素材
- 实现 Listing 发布前自动选择匹配素材
- 实现素材回退机制（通用素材 fallback）

#### 验收标准
- [ ] 一个 SKU 可维护素材矩阵
- [ ] 一个 Listing 可自动选择匹配的素材组合
- [ ] 同一视觉可复用到多个平台/语言版本
- [ ] 素材生成接入主流程
- [ ] 测试通过

#### 参考文档
- `docs/roadmap/stage5-implementation-tasks.md` (D1-D3)

---

### Phase 3：双模式发布编排（18-26h）

#### 目标
让同一个 SKU 可以在不同平台按不同模式经营。

#### 要做

**1. 新增统一发布服务（10-14h）**
- 新增 `PlatformRegistry`
- 新增 `UnifiedListingService`
- 实现平台适配器注册与解析
- 实现统一 listing 创建/更新/同步接口

**2. 发布前判定逻辑（8-12h）**
- 实现 `pre_order` 激活条件判定
- 实现 `stock_first` 激活条件判定
- 实现 listing 状态机
- 实现库存不足时自动暂停逻辑

#### 验收标准
- [ ] 同一 SKU 可同时有 Temu `pre_order` listing 和 Amazon `stock_first` listing
- [ ] 两个 listing 共用商品主数据，但激活规则不同
- [ ] `pre_order` listing 可 0 库存激活
- [ ] `stock_first` listing 需库存达标才激活
- [ ] 测试通过

#### 参考文档
- `docs/roadmap/stage5-implementation-tasks.md` (A1-A4)

---

### Phase 4：订单/履约/库存联动（22-32h）

#### 目标
真正跑通两种模式。

#### 要做

**1. 新增订单中心（15-20h）**
- 新增 `PlatformOrder` 模型
- 新增 `PlatformOrderLine` 模型
- 新增 `FulfillmentRecord` 模型
- 实现 `OrderIngestionService`

**2. 接库存联动（7-12h）**
- 实现下单后 reservation
- 实现发货后 outbound movement
- 实现取消/退款后释放 reservation
- 实现 `pre_order` 订单触发采购建议
- 实现 `stock_first` 订单直接消耗库存

#### 验收标准
- [ ] pre_order 平台订单可触发补货链路
- [ ] stock_first 平台订单可直接消耗库存
- [ ] 库存事实层始终闭环一致
- [ ] 订单导入幂等
- [ ] 测试通过

#### 参考文档
- `docs/roadmap/stage4-implementation-tasks.md` (A1-A4)

---

### Phase 5：真实利润与售后层（23-33h）

#### 目标
把系统从"理论利润"升级为"真实净利"。

#### 要做

**1. 新增售后中心（10-14h）**
- 新增 `RefundCase` 模型
- 新增 `ReturnCase` 模型
- 新增 `AfterSaleIssue` 模型
- 实现 `RefundAnalysisService`

**2. 新增利润台账（13-19h）**
- 新增 `SettlementEntry` 模型
- 新增 `AdCostAllocation` 模型
- 新增 `ProfitLedger` 模型
- 实现 `ProfitLedgerService`
- 实现真实利润口径计算

#### 验收标准
- [ ] 每个 SKU / listing / order line 都可追踪真实净利
- [ ] 退款、售后、广告费能进入真实经营反馈
- [ ] 利润计算公式正确
- [ ] 测试通过

#### 参考文档
- `docs/roadmap/stage4-implementation-tasks.md` (B1-C3)

---

### Phase 6：生命周期与自动经营控制平面（20-30h）

#### 目标
让系统自动做经营动作，人只处理例外。

#### 要做

**1. 生命周期引擎（9-13h）**
- 新增 `SkuLifecycleState` 模型
- 新增 `LifecycleRule` 模型
- 新增 `LifecycleTransitionLog` 模型
- 实现 `LifecycleEngineService`

**2. 自动动作引擎（11-17h）**
- 新增 `ActionRule` 模型
- 新增 `ActionExecutionLog` 模型
- 实现 `ActionEngineService`
- 实现动作类型：repricing / replenish / swap_content / delist / retire

#### 验收标准
- [ ] 系统可按模式自动做不同经营动作
- [ ] 每个动作可追踪、可解释、可回滚
- [ ] `pre_order` 更关注履约风险、供应商 lead time
- [ ] `stock_first` 更关注库存周转、滞销风险
- [ ] 测试通过

#### 参考文档
- `docs/roadmap/stage6-implementation-tasks.md`

---

## 🎯 推荐的第一批开发包

如果要立即开工，建议按以下顺序：

### Batch 1：最小可用双模式闭环（80-116h）
- `ProductMaster / ProductVariant`
- `Supplier / SupplierOffer`
- `Warehouse / InventoryLevel / InventoryReservation`
- `PurchaseOrder / InboundShipment`
- `PlatformListing` 关联 `product_variant_id` + `inventory_mode`

### Batch 2：素材与本地化（24-36h）
- 扩展 `ContentAsset`
- `LocalizationContent`
- `PlatformContentRule`
- `ContentAssetManagerAgent` 接入主流程
- Listing 发布时自动选素材

### Batch 3：订单与库存联动（22-32h）
- `PlatformOrder / PlatformOrderLine`
- `FulfillmentRecord`
- `OrderIngestionService`
- pre_order 订单触发采购
- stock_first 订单消耗库存

### Batch 4：真实利润（23-33h）
- `RefundCase`
- `SettlementEntry`
- `ProfitLedger`

### Batch 5：自动经营（20-30h）
- `SkuLifecycleState`
- `ActionRule`
- `ActionExecutionLog`

---

## 📊 总工作量估算

| Phase | 工作量 | 优先级 |
|-------|--------|--------|
| Phase 0 | 1-2 天 | P0 |
| Phase 1 | 80-116h | P0 |
| Phase 2 | 24-36h | P0 |
| Phase 3 | 18-26h | P0 |
| Phase 4 | 22-32h | P0 |
| Phase 5 | 23-33h | P1 |
| Phase 6 | 20-30h | P1 |
| **总计** | **187-275h** | **约 5-7 人月** |

---

## 🔗 相关文档

- [Stage 3 实施任务清单](stage3-implementation-tasks.md)
- [Stage 3 开发 Backlog](stage3-development-backlog.md)
- [Stage 4 实施任务清单](stage4-implementation-tasks.md)
- [Stage 4 开发 Backlog](stage4-development-backlog.md)
- [Stage 5 实施任务清单](stage5-implementation-tasks.md)
- [Stage 6 实施任务清单](stage6-implementation-tasks.md)
- [研发路线图 2026](engineering-roadmap-2026.md)
- [核心业务流程](../workflows/core-business-flows.md)

---

**最后更新**: 2026-03-29
**文档状态**: 待实施
**维护者**: Deyes 研发团队
