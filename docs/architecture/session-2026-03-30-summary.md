# 2026-03-30 讨论总结

**日期**: 2026-03-30
**参与**: 用户 + Claude (Opus 4.6)
**主题**: AlphaShop 整合分析 + 组合商品选品能力

---

## 讨论主题概览

本次讨论涵盖两个核心主题：

1. **AlphaShop / 外部产品整合可行性分析**
2. **组合商品（Bundle）选品能力设计**

---

# 主题一：AlphaShop 整合分析

## 1. 背景

用户提出研究 AlphaShop (alphashop.cn / 遨虾) 产品，评估是否可以整合到 Deyes 系统中，以增强：

- 供应商匹配能力
- 选品能力
- 采购执行能力（询盘、下单）

## 2. 核心结论

### 2.1 AlphaShop 定位判断

**AlphaShop 是面向用户的 AI 助手产品，不是开发者 API 平台。**

证据：
- 无公开 API 文档
- 无开发者门户
- 无 SDK / OpenAPI / webhook
- 当前处于免费公测阶段
- 主要通过 Web UI 和 Chrome 插件提供服务

### 2.2 可接入性评估结论

**Phase 0 验证结果：不建议作为核心采购执行通道接入。**

| 能力维度 | 评估结果 | 说明 |
|---------|---------|------|
| **询盘 API** | ❌ 不存在 | 无正式 API 文档 |
| **下单 API** | ❌ 不存在 | 无正式 API 文档 |
| **订单同步 API** | ❌ 不存在 | 无正式 API 文档 |
| **物流同步 API** | ❌ 不存在 | 无正式 API 文档 |
| **供应商发现 API** | ⚠️ 疑似存在 | 仅社区提到图片翻译端点，无官方文档 |
| **浏览器自动化** | ⚠️ 可行但高风险 | 稳定性差、维护成本高、合规风险 |

### 2.3 推荐替代方案

**优先接入 1688 官方开放平台，而不是 AlphaShop。**

理由：
- 1688 官方开放平台有正式 API 文档
- 支持询盘、下单、订单同步、物流查询
- 官方技术支持与 SLA 保障
- 稳定性与可维护性更好

官方入口：
- https://aop.alibaba.com/
- https://open.1688.com/

### 2.4 AlphaShop 的保留价值

虽然不适合作为核心采购通道，但可保留以下用途：

1. **人工辅助工具**
   - 运营人员使用 AlphaShop UI 做市场调研
   - 结果手动录入 Deyes

2. **可选情报源**（如果未来有正式 API）
   - 图片翻译增强
   - 供应商图搜补充
   - 市场趋势信号

3. **持续观察**
   - 关注 AlphaShop 是否推出正式 API
   - 关注是否开放开发者门户

## 3. 对 Deyes 整合方案的影响

### 3.1 原计划调整

**原计划**：
- P0: AlphaShop 采购执行层（询盘、下单、状态同步）
- P1: AlphaShop 供应商发现层
- P2: AlphaShop 需求情报增强层

**调整后**：
- **P0: 1688 官方开放平台接入**（询盘、下单、订单同步）
- **P1: Deyes 采购体系完善**（抽象层、询盘服务、PO 外部执行）
- **P2: AlphaShop 可选增强**（仅限有正式 API 的功能）

### 3.2 架构设计保留

虽然 AlphaShop 不适合优先接入，但原设计的抽象层仍然有效：

保留设计：
- `ProcurementExecutionProvider` 抽象 ✅
- `SupplierDiscoveryProvider` 抽象 ✅
- `MarketIntelProvider` 抽象 ✅
- 多通道路由机制 ✅

调整实现优先级：
- `Alibaba1688ProcurementProvider` ⬆️ 提升为 P0
- `AlphaShopProcurementProvider` ⬇️ 降级为 P2
- `ManualProcurementProvider` ✅ 保留作为 fallback

## 4. 已沉淀文档

### 4.1 AlphaShop 整合方案文档
- 路径：`docs/architecture/alphashop-integration-plan.md`
- 内容：
  - 总体整合策略
  - 抽象层设计
  - 数据模型扩展建议
  - 工程化接口与类设计
  - 分阶段实施计划

### 4.2 Phase 0 可接入性验证报告
- 路径：`docs/architecture/alphashop-phase0-verification.md`
- 内容：
  - 验证方法与发现
  - API 可用性评估
  - 替代方案对比
  - 风险评估
  - 最终结论与建议

## 5. 关键澄清

### AlphaShop vs 1688 官方开放平台

**用户提问**："你说的 1688 官方开放平台是指 AlphaShop 吗？"

**回答**：不是。

- **AlphaShop**：面向用户的 AI 助手产品（类似 SaaS 应用）
- **1688 官方开放平台**：面向开发者的 API 平台（类似 API 网关）

类比：
- AlphaShop = 现成的应用产品
- 1688 官方开放平台 = 开发者接口层

对 Deyes 的意义：
- 如果要做稳定、长期、可维护的系统集成 → 优先 1688 官方开放平台
- 如果要给运营人员提供智能辅助工具 → 可以用 AlphaShop UI

---

# 主题二：组合商品选品能力

## 1. 背景

用户提出新业务需求：

> "能不能组合商品形成新的 SKU"

进一步明确：
- 固定组合（不是动态组合）
- 希望利用 AI（Qwen3.5 或更强模型）自动发现组合选品机会

## 2. 当前 Deyes 状态

### 2.1 数据模型现状

**当前不支持组合 SKU / Bundle / Kit。**

现有模型：
- `ProductMaster`：商品主数据（`backend/app/db/models.py:722`）
- `ProductVariant`：单一 SKU 变体（`backend/app/db/models.py:748`）

关键约束：
- `ProductVariant` 只能关联一个 `ProductMaster`
- 没有 BOM（物料清单）/ Bundle / Kit / Composite 概念
- 没有"组件 SKU"与"组合 SKU"的关系表
- 采购、库存、订单都是按单一 variant 处理

### 2.2 选品流程现状

当前 `ProductSelectorAgent` 是单品导向：

流程：
1. 需求验证（关键词搜索量、竞争密度）
2. 平台抓取（Temu / 1688 / Amazon）
3. 供应商匹配
4. 优先级排序（季节性、销量、评分、竞争）
5. 推荐评分（利润、风险、供应商质量）

见：`backend/app/agents/product_selector.py:68`

问题：
- 每次只看单个商品
- 没有"商品之间的关联分析"
- 没有"组合机会发现"逻辑
- 没有"Bundle 推荐"能力

## 3. AI 组合选品能力判断

### 3.1 核心结论

**Qwen3.5-35B-A3B 完全可以做组合选品，但需要新增专门的 Agent 和业务逻辑。**

### 3.2 AI 可以做什么

#### A. 关联商品发现

**能力**：
- 输入：一个已选中的候选商品（如"手机壳"）
- 输出：高关联商品列表（如"钢化膜"、"数据线"、"充电头"）
- 推理：基于功能互补、使用场景、平台数据

#### B. 组合机会评分

**能力**：
- 输入：商品 A + 商品 B 的组合
- 输出：组合吸引力评分、定价建议、平台建议
- 推理：成本、利润、需求、竞争综合分析

#### C. 组合策略推荐

**能力**：
- 输入：品类、目标平台、目标区域
- 输出：推荐的组合类型（套装/多件装/礼盒）、数量、折扣策略

#### D. 组合内容生成

**能力**：
- 输入：组合的组件清单
- 输出：组合标题、描述、卖点、主图创意方向

### 3.3 具体实现方式

#### 方式 1：基于"经常一起购买"

数据来源：
- Amazon "Frequently bought together"
- Temu "搭配购买"
- 1688 "组合推荐"

AI 任务：
- 抓取关联数据
- 分析关联强度
- 过滤高价值组合

#### 方式 2：基于"功能互补"

AI 推理示例：
```
输入："iPhone 15 手机壳"
推理：需要屏幕保护 → 钢化膜
推理：需要充电 → 数据线、充电头
推理：需要清洁 → 清洁套装
输出：["钢化膜", "数据线", "充电头", "清洁套装"]
```

#### 方式 3：基于"场景匹配"

AI 推理示例：
```
场景："露营"
推理：该场景需要哪些商品
输出：["帐篷", "睡袋", "便携炉", "照明灯"]
```

#### 方式 4：基于"多件装策略"

AI 推理示例：
```
输入："袜子"
判断：是否适合多件装 → 是（日用消耗品）
输出：推荐 3双装、5双装
```

## 4. 推荐实现方案

### 4.1 短期方案（1-2 周）：规则版

**先不用 AI，用规则验证业务价值**：

1. 新增 `BundleOpportunity` 数据模型
2. 新增 `BundleDiscoveryService`（纯规则）
3. 支持场景：
   - 同品类多件装（单价 < $10 → 3件装/5件装）
   - 同供应商组合（降低采购成本）
   - 同类目互补（手机配件 → "壳+膜"）

### 4.2 中期方案（1-2 月）：AI 推理版

**引入 Qwen3.5 做智能推理**：

1. 新增 `BundleDiscoveryAgent`
2. 用 LLM 推理互补商品
3. 用 LLM 做组合评分
4. 用 LLM 生成组合内容

示例代码：
```python
class BundleDiscoveryAgent(BaseAgent):
    """组合商品发现 Agent"""

    async def discover_complementary_products(
        self,
        anchor_product: CandidateProduct,
    ) -> list[str]:
        """用 LLM 推理互补商品"""

        prompt = f"""
        商品：{anchor_product.title}
        类目：{anchor_product.category}

        请推理出 3-5 个与该商品功能互补、经常一起购买的商品类型。
        只返回商品类型关键词，不要解释。

        示例格式：
        - 钢化膜
        - 数据线
        - 充电头
        """

        response = await self.llm_client.generate(prompt)
        return parse_keywords(response)
```

### 4.3 长期方案（3-6 月）：数据驱动优化

**基于真实数据持续优化**：

1. 抓取平台关联数据
2. 分析历史销售数据
3. 训练组合推荐模型（可选）
4. 闭环优化

## 5. 业务价值评估

### 5.1 为什么值得做

| 价值维度 | 说明 |
|---------|------|
| **提高客单价** | Bundle 通常客单价更高 |
| **提高转化率** | 组合更有吸引力，降低决策成本 |
| **差异化竞争** | 不是所有卖家都做组合 |
| **库存周转** | 滞销品可以搭配热销品 |
| **降低采购成本** | 同供应商组合可以提高 MOQ 议价能力 |

### 5.2 实现难度

**技术难度：⭐⭐⭐ (中等)**

容易的部分：
- Qwen3.5 推理能力足够
- 可以用 prompt engineering 实现大部分逻辑
- 不需要训练新模型

需要解决的：
- 数据获取（平台关联数据）
- 组合评分模型（需要业务规则）
- 组合库存逻辑（虚拟库存计算）
- 组合定价逻辑（折扣策略）

## 6. 数据模型扩展需求

### 6.1 新增模型：`ProductBundle`

```python
class ProductBundle(Base):
    """组合商品定义"""

    id: UUID
    bundle_variant_id: UUID  # 指向组合 SKU 的 ProductVariant

    # 组合策略
    bundle_type: str  # "fixed_kit", "multipack", "gift_set"

    # 定价策略
    pricing_strategy: str  # "independent", "cost_plus", "discount"
    bundle_price: Decimal | None
    discount_percentage: Decimal | None

    # 库存策略
    inventory_strategy: str  # "independent", "virtual"
```

### 6.2 新增模型：`BundleComponent`

```python
class BundleComponent(Base):
    """组合商品的组件"""

    id: UUID
    bundle_id: UUID
    component_variant_id: UUID  # 指向组件 SKU
    quantity: int  # 该组件在组合中的数量
    is_primary: bool  # 是否为主商品
```

### 6.3 新增模型：`BundleOpportunity`

```python
class BundleOpportunity(Base):
    """AI 发现的组合机会"""

    id: UUID
    strategy_run_id: UUID

    # 组合定义
    anchor_candidate_id: UUID  # 主商品
    complementary_keywords: list[str]  # 互补商品关键词
    bundle_type: str

    # AI 评分
    opportunity_score: float  # 0-100
    confidence_score: float
    reasoning: str

    # 状态
    status: str  # "discovered", "validated", "rejected", "converted"
```

## 7. Agent 设计建议

### 7.1 新增 Agent：`BundleDiscoveryAgent`

职责：
1. 从已有候选商品中发现组合机会
2. 从平台数据中发现热门组合
3. 评估组合的商业价值
4. 生成组合商品定义

关键方法：
```python
async def discover_bundles(
    candidate_products: list[CandidateProduct],
    strategy: str = "complementary",
) -> list[BundleOpportunity]

async def evaluate_bundle_opportunity(
    bundle: BundleOpportunity,
) -> BundleEvaluationResult

async def generate_bundle_content(
    bundle: BundleOpportunity,
) -> BundleContentResult
```

### 7.2 扩展现有流程

建议在 `DirectorWorkflow` 中增加组合发现阶段：

```
1. 单品选品（现有）
   ↓
2. 组合发现（新增）
   ↓
3. 组合评分（新增）
   ↓
4. 统一推荐（单品 + 组合）
```

## 8. 实施优先级建议

### Phase 1：数据模型与规则版（P0）
- 新增 Bundle 相关数据模型
- 新增 `BundleDiscoveryService`（纯规则）
- 支持"同品类多件装"场景
- 验证业务价值

### Phase 2：AI 推理版（P1）
- 新增 `BundleDiscoveryAgent`
- 用 Qwen3.5 做互补商品推理
- 用 Qwen3.5 做组合评分
- 用 Qwen3.5 生成组合内容

### Phase 3：数据驱动优化（P2）
- 抓取平台关联数据
- 分析历史销售数据
- 闭环优化

---

# 总体结论

## 1. AlphaShop 整合

**结论**：当前不建议作为核心采购通道，优先接入 1688 官方开放平台。

**保留价值**：
- 人工辅助工具
- 可选情报源（待正式 API 推出）

**架构调整**：
- 抽象层设计保留
- 实现优先级调整：1688 官方 API > AlphaShop

## 2. 组合商品选品

**结论**：Qwen3.5 完全可以做，建议分阶段实施。

**推荐路径**：
1. 短期：规则版验证业务价值
2. 中期：AI 推理版增强能力
3. 长期：数据驱动持续优化

**业务价值**：高（提高客单价、转化率、差异化竞争）

**技术难度**：中等（AI 能力足够，需要补充业务逻辑）

---

# 下一步行动建议

## 立即行动

### 针对 AlphaShop / 采购整合

1. **研究 1688 官方开放平台**
   - 确认企业资质要求
   - 了解接入流程
   - 评估 API 能力覆盖度

2. **更新整合方案优先级**
   - 将 1688 官方 API 提升为 P0
   - 将 AlphaShop 降级为 P2

### 针对组合商品

1. **输出完整技术方案文档**
   - 数据模型设计
   - Agent 设计
   - 实施计划

2. **启动 Phase 1 实施**
   - 新增 Bundle 数据模型
   - 实现规则版组合发现
   - 验证业务价值

## 持续观察

1. **关注 AlphaShop 产品演进**
   - 是否推出正式 API
   - 是否开放开发者门户

2. **评估其他替代方案**
   - 其他 1688 数据聚合服务
   - 其他跨境采购 SaaS 平台

---

# 相关文档索引

## 本次讨论产出文档

1. **AlphaShop 整合方案**
   - `docs/architecture/alphashop-integration-plan.md`
   - 内容：总体策略、抽象层设计、工程化接口、��施计划

2. **AlphaShop Phase 0 验证报告**
   - `docs/architecture/alphashop-phase0-verification.md`
   - 内容：可接入性验证、替代方案、风险评估、最终结论

3. **本次讨论总结**
   - `docs/architecture/session-2026-03-30-summary.md`
   - 内容：完整讨论记录、��论、下一步建议

## 现有相关文档

1. **项目状态报告**
   - `docs/PROJECT_STATUS.md`
   - 最新项目状态、已完成模块、待完成模块

2. **系统架构 v4.0**
   - `docs/architecture/system-architecture-v4.md`
   - 完整技术栈和架构设计

3. **采购服务**
   - `backend/app/services/procurement_service.py`
   - 当前采购服务实现

4. **库存分配服务**
   - `backend/app/services/inventory_allocator.py`
   - 当前库存管理实现

5. **供应商匹配服务**
   - `backend/app/services/supplier_matcher.py`
   - 当前供应商匹配实现

6. **选品 Agent**
   - `backend/app/agents/product_selector.py`
   - 当前选品流程实现

---

# 关键参考资料

## AlphaShop 相关

- AlphaShop 官网：https://www.alphashop.cn/
- Chrome 插件：https://chromewebstore.google.com/detail/1688-alphashop-ai-sourcin/ecpkhbhhpfjkkcedaejmpaabpdgcaegc

## 1688 官方开放平台

- 1688 开放平台：https://aop.alibaba.com/
- 1688 Open Platform：https://open.1688.com/
- 跨境代采解决方案：https://open.1688.com/solution/solutionDetail.htm?solutionKey=1697014160788
- 跨境 ERP 解决方案：https://open.1688.com/solution/solutionDetail.htm?solutionKey=1697015308755

---

**备注**：

本文档记录了 2026-03-30 的完整讨论内容与结论，作为后续实施的参考依据。如有疑问或需要进一步细化，请参考相关文档或重新评估。
