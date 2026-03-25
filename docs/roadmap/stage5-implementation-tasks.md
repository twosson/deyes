# Stage 5 实施任务清单

> 基于研发路线图 Stage 5：多平台统一经营中枢
>
> 目标：让同一 SKU 能跨平台统一管理状态、库存、价格、表现与利润，形成平台策略与地区策略的统一经营层。
>
> 版本: v1.0
> 创建时间: 2026-03-25

---

## 📋 Stage 5 总览

### 核心目标
从“单平台可经营闭环 + ERP Lite 事实层”升级为“多平台统一经营中枢”。

### 关键交付物
1. 平台适配器扩展与统一管理框架
2. PlatformPolicy / CategoryMapping / PricingRule / ContentRule 策略层
3. 多币种与地区化能力
4. 多语言 / 本地化内容基础设施
5. 跨平台 SKU / listing / inventory / pricing / profit 聚合视图

### 预期成果
- 同一 SKU 能在多个平台共享主数据和库存约束
- 平台差异不再散落在 adapter 内，而沉淀为可配置的策略层
- 价格、内容、合规、类目映射可按平台/地区差异化处理
- 经营者能统一查看跨平台状态、表现与利润

---

## 🎯 任务分组

### 分组 A：多平台适配与统一 listing 管理（优先级 P0）
### 分组 B：平台策略层与规则配置（优先级 P0）
### 分组 C：多币种与地区化（优先级 P0）
### 分组 D：多语言与本地化内容（优先级 P1）
### 分组 E：测试与验证（优先级 P0）

---

## 分组 A：多平台适配与统一 listing 管理

### A1. 扩展 PlatformListing 支持多平台统一状态管理

**任务描述**：
完善 `PlatformListing` 模型，使其能更稳定地承载多平台、多地区、多市场的统一管理语义。

**具体工作**：
1. 审视并补充 `PlatformListing` 字段：
   - `platform`
   - `region`
   - `marketplace`
   - `platform_listing_id`
   - `platform_status`
   - `currency`
   - `product_variant_id`
2. 增加必要索引：
   - `platform + marketplace + platform_listing_id`
   - `product_variant_id + platform`
3. 明确 listing 状态与 SKU 的关系
4. 保持旧数据兼容

**涉及文件**：
- 修改：`backend/app/db/models.py`
- 新增：`backend/migrations/versions/00x_platform_listing_multiplatform.py`

**验收标准**：
- [ ] `PlatformListing` 能稳定承载多平台字段
- [ ] 同一 SKU 可映射多个平台 listing
- [ ] migration 可成功执行
- [ ] 旧路径不回退

**预估工作量**：4-6 小时

---

### A2. 实现统一 PlatformRegistry / AdapterResolver

**任务描述**：
建立平台适配器注册与解析机制，避免平台逻辑分散在业务代码中。

**具体工作**：
1. 新增 `PlatformRegistry` 或 `PlatformAdapterResolver`
2. 实现能力：
   - `register_adapter(platform, adapter)`
   - `get_adapter(platform)`
   - `supports_feature(platform, feature_name)`
3. 明确平台能力矩阵：
   - create_listing
   - update_listing
   - sync_inventory
   - sync_price
   - get_listing_metrics
   - get_orders
4. 为 Temu / Amazon / Ozon 等平台预留扩展位

**涉及文件**：
- 新增：`backend/app/services/platform_registry.py`
- 可能修改：现有 platform adapter 相关服务

**验收标准**：
- [ ] 平台适配器可统一注册和解析
- [ ] 能查询平台能力支持情况
- [ ] 新平台扩展不需要改动核心编排代码

**预估工作量**：4-6 小时

---

### A3. 实现 UnifiedListingService

**任务描述**：
创建统一 listing 服务，提供跨平台 listing 创建、更新、同步与查询入口。

**具体工作**：
1. 新增 `UnifiedListingService`
2. 实现方法：
   - `create_listing(platform, product_variant_id, payload)`
   - `update_listing(listing_id, payload)`
   - `sync_listing(listing_id)`
   - `get_listing_snapshot(listing_id)`
3. 调用 `PlatformRegistry` 获取具体 adapter
4. 统一落库 `PlatformListing` 与同步日志

**涉及文件**：
- 新增：`backend/app/services/unified_listing_service.py`

**验收标准**：
- [ ] 可通过统一入口调平台 adapter
- [ ] listing 同步行为可追踪
- [ ] listing 快照结构统一
- [ ] 不破坏现有 PlatformPublisher 基础能力

**预估工作量**：6-8 小时

---

### A4. 建立跨平台 SKU 经营视图

**任务描述**：
为同一 SKU 聚合多个平台 listing 的状态、库存、价格、表现和利润，形成跨平台经营视图。

**具体工作**：
1. 实现 `get_sku_multiplatform_snapshot(product_variant_id)`
2. 聚合内容：
   - active listings
   - platform statuses
   - prices by platform
   - revenue / profit by platform
   - inventory exposure
3. 返回结构化平台维度数据
4. 供后续经营控制台复用

**涉及文件**：
- 修改：`backend/app/services/operating_metrics_service.py` 或新增 `backend/app/services/multiplatform_hub_service.py`

**验收标准**：
- [ ] 可查询 SKU 的跨平台快照
- [ ] 快照含平台状态、利润、库存等关键信息
- [ ] 数据结构稳定可复用

**预估工作量**：5-7 小时

---

## 分组 B：平台策略层与规则配置

### B1. 设计 PlatformPolicy / PlatformCategoryMapping Schema

**任务描述**：
建立平台策略层，把类目映射、平台约束和经营规则从 adapter 逻辑中抽离出来。

**具体工作**：
1. 设计 `PlatformPolicy`：
   - `id`
   - `platform`
   - `marketplace`
   - `policy_type`
   - `policy_payload`
   - `status`
2. 设计 `PlatformCategoryMapping`：
   - `source_category`
   - `platform_category`
   - `platform`
   - `marketplace`
   - `confidence_score`
3. 明确策略版本和启用状态
4. 支持后续 pricing / content / compliance 规则复用

**涉及文件**：
- 修改：`backend/app/db/models.py`
- 新增：`backend/migrations/versions/00x_platform_policy.py`

**验收标准**：
- [ ] 平台策略与类目映射模型定义完成
- [ ] 可表达多平台差异化配置
- [ ] migration 可成功执行

**预估工作量**：4-6 小时

---

### B2. 设计 PlatformPricingRule / PlatformContentRule Schema

**任务描述**：
把平台差异化定价和内容规则沉淀为独立策略实体。

**具体工作**：
1. 设计 `PlatformPricingRule`：
   - `platform`
   - `marketplace`
   - `region`
   - `min_margin_percentage`
   - `currency_buffer`
   - `fee_overrides`
2. 设计 `PlatformContentRule`：
   - title length
   - banned keywords
   - required attributes
   - image requirements
3. 明确规则作用范围：
   - platform
   - marketplace
   - category
4. 支持启停与版本管理

**涉及文件**：
- 修改：`backend/app/db/models.py`
- 修改：`backend/migrations/versions/00x_platform_policy.py`

**验收标准**：
- [ ] 定价和内容规则模型定义完成
- [ ] 可表达不同平台/地区差异
- [ ] 可用于后续服务读取

**预估工作量**：4-6 小时

---

### B3. 实现 PlatformPolicyService

**任务描述**：
创建平台策略服务，统一读取类目映射、定价规则、内容规则和平台约束。

**具体工作**：
1. 新增 `PlatformPolicyService`
2. 实现方法：
   - `resolve_platform_category(source_category, platform, marketplace)`
   - `get_pricing_rule(platform, marketplace, region, category=None)`
   - `get_content_rule(platform, marketplace, category=None)`
   - `validate_listing_payload(platform, payload)`
3. 提供 fallback 逻辑
4. 保持策略读取简单、可缓存

**涉及文件**：
- 新增：`backend/app/services/platform_policy_service.py`

**验收标准**：
- [ ] 可按平台/地区读取策略
- [ ] 可做基础 payload 校验
- [ ] 类目映射可查询
- [ ] fallback 路径清晰

**预估工作量**：5-7 小时

---

### B4. 把 listing 创建/更新接入策略层

**任务描述**：
在统一 listing 服务或 PlatformPublisher 中消费平台策略层，减少硬编码平台差异。

**具体工作**：
1. 在 listing 创建前调用类目映射规则
2. 在定价前调用平台定价规则
3. 在内容生成/发布前调用内容规则
4. 把校验失败转为结构化错误返回

**涉及文件**：
- 修改：`backend/app/services/unified_listing_service.py`
- 可能修改：`backend/app/agents/platform_publisher.py`

**验收标准**：
- [ ] listing 流程已消费策略层
- [ ] 平台差异化逻辑减少硬编码
- [ ] 失败原因可解释

**预估工作量**：5-7 小时

---

## 分组 C：多币种与地区化

### C1. 设计 ExchangeRate / RegionTaxRule / RegionRiskRule Schema

**任务描述**：
建立多币种和地区规则基础模型，支持后续多地区定价与利润换算。

**具体工作**：
1. 设计 `ExchangeRate`：
   - `base_currency`
   - `target_currency`
   - `rate`
   - `as_of_date`
2. 设计 `RegionTaxRule`：
   - `region`
   - `tax_type`
   - `tax_rate`
   - `threshold`
3. 设计 `RegionRiskRule`：
   - `region`
   - `risk_type`
   - `risk_payload`
4. 明确规则读取优先级

**涉及文件**：
- 修改：`backend/app/db/models.py`
- 新增：`backend/migrations/versions/00x_region_and_currency.py`

**验收标准**：
- [ ] 汇率与地区规则模型定义完成
- [ ] 可表达基础税费与风险规则
- [ ] migration 可成功执行

**预估工作量**：4-6 小时

---

### C2. 实现 CurrencyConverter 服务

**任务描述**：
创建汇率转换服务，为跨平台价格、成本、利润比较提供统一换算能力。

**具体工作**：
1. 新增 `CurrencyConverter`
2. 实现方法：
   - `convert(amount, base_currency, target_currency, as_of_date=None)`
   - `get_rate(base_currency, target_currency, as_of_date=None)`
   - `upsert_rate(...)`
3. 增加缺失汇率 fallback
4. 统一 Decimal 精度与舍入规则

**涉及文件**：
- 新增：`backend/app/services/currency_converter.py`

**验收标准**：
- [ ] 可稳定做币种转换
- [ ] 汇率缺失时有明确 fallback / error
- [ ] 精度规则稳定

**预估工作量**：4-6 小时

---

### C3. 实现地区化定价与利润换算接口

**任务描述**：
让定价和利润服务能够基于平台/地区规则进行换算和约束判断。

**具体工作**：
1. 扩展 pricing / profit 相关服务
2. 支持：
   - 区域税费估算
   - 统一本位币利润比较
   - 平台地区最低利润线判断
3. 输出结构化地区化结果：
   - local price
   - base-currency profit
   - tax estimate
   - risk note
4. 保持为规则型实现

**涉及文件**：
- 修改：`backend/app/services/pricing_service.py`
- 修改：`backend/app/services/profit_ledger_service.py`
- 可能修改：`backend/app/services/platform_policy_service.py`

**验收标准**：
- [ ] 可基于地区规则做价格与利润换算
- [ ] 不同币种结果可比较
- [ ] 输出含税费与利润说明

**预估工作量**：5-7 小时

---

### C4. 建立 Region / Platform 经营聚合接口

**任务描述**：
从多平台经营视图中抽出地区化聚合能力，支持跨市场经营分析。

**具体工作**：
1. 实现：
   - `get_region_performance(region)`
   - `get_platform_region_snapshot(platform, region)`
2. 聚合指标：
   - listing count
   - revenue
   - refund_rate
   - net_profit
   - margin
3. 为 Stage 2 的 platform-region prior 提供更真实数据来源
4. 保持口径清晰可复用

**涉及文件**：
- 修改：`backend/app/services/operating_metrics_service.py`

**验收标准**：
- [ ] 可按地区和平台地区组合聚合经营结果
- [ ] 关键指标结构稳定
- [ ] 可供反馈与策略层复用

**预估工作量**：4-6 小时

---

## 分组 D：多语言与本地化内容

### D1. 设计 LocalizedContent / ContentTemplate / ContentVersion Schema

**任务描述**：
建立本地化内容基础设施，为不同平台、地区和语言输出一致但可变体化的内容。

**具体工作**：
1. 设计 `LocalizedContent`：
   - `product_variant_id`
   - `platform`
   - `region`
   - `language`
   - `content_type`
   - `content_payload`
2. 设计 `ContentTemplate`：
   - template name
   - content type
   - platform scope
   - locale scope
3. 设计 `ContentVersion`：
   - version
   - source template
   - generated_at
4. 明确与 `ContentAsset` 的关系边界

**涉及文件**：
- 修改：`backend/app/db/models.py`
- 新增：`backend/migrations/versions/00x_localized_content.py`

**验收标准**：
- [ ] 本地化内容模型定义完成
- [ ] 可表达多语言标题/卖点/详情内容
- [ ] migration 可成功执行

**预估工作量**：4-6 小时

---

### D2. 实现 LocalizationService

**任务描述**：
创建本地化服务，统一生成、存取和校验平台/地区内容版本。

**具体工作**：
1. 新增 `LocalizationService`
2. 实现方法：
   - `create_localized_content(...)`
   - `get_localized_content(...)`
   - `validate_localized_content(platform, locale, payload)`
   - `list_content_versions(...)`
3. 对接 `PlatformContentRule`
4. 处理缺失语言时的 fallback

**涉及文件**：
- 新增：`backend/app/services/localization_service.py`

**验收标准**：
- [ ] 可创建和查询本地化内容
- [ ] 可根据平台规则做校验
- [ ] 缺失 locale 时有 fallback

**预估工作量**：5-7 小时

---

### D3. 把 listing 发布流程接入本地化内容

**任务描述**：
让多平台 listing 发布不再直接依赖单一内容版本，而能消费平台/地区对应的本地化内容。

**具体工作**：
1. 在 listing 创建时解析 locale / marketplace
2. 从 `LocalizationService` 读取对应内容
3. 如果缺失则 fallback 到默认内容版本
4. 把实际使用内容版本记录到 listing metadata

**涉及文件**：
- 修改：`backend/app/services/unified_listing_service.py`
- 可能修改：`backend/app/agents/platform_publisher.py`

**验收标准**：
- [ ] 发布流程可使用本地化内容
- [ ] 缺失时 fallback 稳定
- [ ] 使用了哪个内容版本可追踪

**预估工作量**：4-6 小时

---

## 分组 E：测试与验证

### E1. 新增统一 listing 与平台策略测试

**任务描述**：
覆盖 PlatformRegistry、UnifiedListingService 和 PlatformPolicyService 的核心行为。

**具体工作**：
新增测试：
- `test_platform_registry_resolves_registered_adapter`
- `test_unified_listing_service_creates_listing_via_registry`
- `test_platform_policy_service_resolves_category_mapping`
- `test_listing_creation_consumes_platform_policy_rules`

**涉及文件**：
- 新增：`backend/tests/test_platform_registry.py`
- 新增：`backend/tests/test_unified_listing_service.py`
- 新增：`backend/tests/test_platform_policy_service.py`

**验收标准**：
- [ ] listing 与平台策略测试全部通过
- [ ] 适配器注册和策略消费路径被覆盖

**预估工作量**：5-7 小时

---

### E2. 新增多币种与地区化测试

**任务描述**：
验证汇率转换、税费规则和地区化利润换算逻辑。

**具体工作**：
新增测试：
- `test_currency_converter_returns_expected_rate`
- `test_currency_converter_handles_missing_rate`
- `test_region_tax_rule_affects_pricing_output`
- `test_profit_ledger_snapshot_can_be_converted_to_base_currency`
- `test_platform_region_snapshot_returns_expected_metrics`

**涉及文件**：
- 新增：`backend/tests/test_currency_converter.py`
- 修改：`backend/tests/test_profit_ledger_service.py`
- 修改：`backend/tests/test_operating_metrics_service.py`

**验收标准**：
- [ ] 多币种与地区化测试全部通过
- [ ] 汇率和税费边界被覆盖

**预估工作量**：5-7 小时

---

### E3. 新增本地化内容测试

**任务描述**：
验证本地化内容模型、版本管理和发布接入逻辑。

**具体工作**：
新增测试：
- `test_create_localized_content_for_platform_locale`
- `test_validate_localized_content_uses_platform_rule`
- `test_listing_publish_uses_localized_content_when_available`
- `test_listing_publish_falls_back_to_default_content_version`

**涉及文件**：
- 新增：`backend/tests/test_localization_service.py`
- 修改：`backend/tests/test_platform_publisher.py` 或相关测试文件

**验收标准**：
- [ ] 本地化内容测试全部通过
- [ ] fallback 和版本选择路径被覆盖

**预估工作量**：4-6 小时

---

### E4. 新增跨平台经营聚合测试

**任务描述**：
验证 SKU 跨平台快照、平台地区快照和策略层兼容行为。

**具体工作**：
新增测试：
- `test_get_sku_multiplatform_snapshot_returns_all_platforms`
- `test_get_platform_region_snapshot_returns_profit_and_refund_metrics`
- `test_stage5_policy_layer_does_not_break_stage4_profit_flow`
- `test_stage5_multiplatform_hub_keeps_stage2_feedback_dimensions_consistent`

**涉及文件**：
- 修改：`backend/tests/test_operating_metrics_service.py`
- 修改：`backend/tests/test_feedback_aggregator.py`

**验收标准**：
- [ ] 跨平台经营聚合测试全部通过
- [ ] Stage 2 / 4 旧逻辑不回退

**预估工作量**：4-6 小时

---

### E5. Stage 5 回归验证套件

**任务描述**：
建立 Stage 5 的回归命令与验证 checklist。

**建议命令**：
```bash
python -m pytest backend/tests/test_platform_registry.py -v
python -m pytest backend/tests/test_unified_listing_service.py -v
python -m pytest backend/tests/test_platform_policy_service.py -v
python -m pytest backend/tests/test_currency_converter.py -v
python -m pytest backend/tests/test_localization_service.py -v
python -m pytest backend/tests/test_operating_metrics_service.py -v
```

**涉及文件**：
- 新增：`docs/roadmap/stage5-verification-checklist.md`

**验收标准**：
- [ ] 核心回归命令明确
- [ ] 手工验证 checklist 明确
- [ ] Stage 1-4 主链路不回退

**预估工作量**：2-3 小时

---

## 📊 任务优先级与依赖关系

### 第一批（并行）
- A1（PlatformListing 多平台扩展）
- B1（PlatformPolicy / CategoryMapping Schema）
- C1（ExchangeRate / RegionRule Schema）
- D1（LocalizedContent Schema）

### 第二批（依赖第一批）
- A2（PlatformRegistry）
- B2（PlatformPricingRule / ContentRule）
- B3（PlatformPolicyService）
- C2（CurrencyConverter）
- D2（LocalizationService）

### 第三批（依赖第二批）
- A3（UnifiedListingService）
- A4（跨平台 SKU 经营视图）
- B4（listing 流程接入策略层）
- C3（地区化定价与利润换算）
- D3（listing 发布接入本地化内容）
- E1 / E2（平台策略与地区化测试）

### 第四批（依赖第三批）
- C4（Region / Platform 经营聚合）
- E3 / E4（本地化与跨平台聚合测试）
- E5（回归验证）

---

## 📈 工作量估算

| 分组 | 任务数 | 预估总工时 | 建议人员 |
|------|--------|-----------|---------|
| A | 4 | 19-27h | 后端 |
| B | 4 | 18-26h | 后端 |
| C | 4 | 17-25h | 后端 |
| D | 3 | 13-19h | 后端 + 内容策略 |
| E | 5 | 20-29h | 测试 + 后端 |
| **总计** | **20** | **87-126h** | **2-3 人** |

按 2-3 人并行投入，Stage 5 可作为从“单平台可经营”升级到“多平台统一经营中枢”的主开发包推进。

---

## ✅ Stage 5 退出标准

### 功能完整性
- [ ] 同一 SKU 可关联多个平台 listing
- [ ] `PlatformPolicyService` 可稳定提供平台策略
- [ ] `CurrencyConverter` 可支持多币种换算
- [ ] 本地化内容可用于不同平台/地区发布
- [ ] 可查询 SKU 的跨平台经营快照

### 统一经营能力
- [ ] 平台差异化逻辑已从 adapter 中部分抽离到策略层
- [ ] 多平台状态、价格、表现、利润可统一查看
- [ ] 地区化税费与利润比较可工作
- [ ] 平台地区表现可作为反馈维度复用

### 稳定性
- [ ] 现有单平台主链路不退化
- [ ] 平台策略和本地化缺失时有 fallback
- [ ] 汇率缺失或地区规则缺失时有明确处理路径
- [ ] Stage 2-4 反馈、利润、库存能力不回退

### 测试覆盖
- [ ] 平台注册与统一 listing 测试全部通过
- [ ] 多币种与地区化测试全部通过
- [ ] 本地化内容测试全部通过
- [ ] Stage 1-4 核心回归不受影响

---

## 🚀 下一步

完成 Stage 5 后，下一步进入 **Stage 6：自动化经营控制平面**，让系统从“统一管理”升级为“自动发现异常、自动执行动作、人只处理例外”。

---

**文档版本**: v1.0
**创建时间**: 2026-03-25
**维护者**: Deyes 研发团队
