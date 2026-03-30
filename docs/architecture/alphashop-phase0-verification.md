# AlphaShop Phase 0 可接入性验证报告

**日期**: 2026-03-30
**验证人**: Claude (Opus 4.6)
**状态**: 验证完成
**结论**: **不建议作为核心采购执行通道接入**

---

## 1. 验证目标

确认 AlphaShop (alphashop.cn / 遨虾) 是否具备可程序化的：

1. 询盘发送与状态同步能力
2. 采购单下单与订单状态同步能力
3. 物流状态回流能力
4. 正式 API 鉴权与文档支持

---

## 2. 验证方法

- 公开网页分析
- 官方文档搜索
- 社区与第三方资料检索
- 1688 官方开放平台对比

---

## 3. 核心发现

### 3.1 AlphaShop 定位

AlphaShop 是阿里巴巴推出的 **面向用户的 AI 助手**，而不是面向开发者的 API 平台。

核心特征：

- 当前处于公测阶段，免费使用
- 主要通过 Web UI 和 Chrome 浏览器插件提供服务
- 定位是"跨境电商 AI 智能体"，而不是"开放 API 平台"
- 覆盖选品、找厂、询盘、设计等环节，但**下单付款仍需用户确认**

### 3.2 API 可用性评估

**结论：无正式公开 API**

证据：

1. **无公开 API 文档**
   - alphashop.cn 没有开发者文档入口
   - 无 OpenAPI / Swagger 规范
   - 无 SDK（Python / JavaScript / Go 等）

2. **无开发者门户**
   - 无 API Key 管理系统
   - 无鉴权文档
   - 无 webhook / callback 机制

3. **无商业 API 套餐**
   - 当前免费公测
   - 无 API 调用计费说明
   - 无企业级 SLA 承诺

4. **社区证据有限**
   - 仅发现一个社区帖子提到疑似 API 端点：
     - `https://api.alphashop.cn/ai.image.translateImagePro/1.0`
     - 使用 Bearer JWT 鉴权（AK/SK）
   - 但这**不是官方文档**，且仅限图片翻译功能
   - 无询盘、下单相关 API 端点证据

### 3.3 功能边界

AlphaShop 当前提供的是：

- **AI 辅助决策**：选品分析、供应商推荐、趋势预测
- **内容生成**：商品描述、营销文案、图片翻译
- **信息聚合**：1688 供应商数据、平台趋势数据

AlphaShop **不提供**：

- 程序化询盘发送
- 程序化下单执行
- 订单状态 API 同步
- 物流状态 API 回流

---

## 4. 可选替代方案

### 4.1 1688 官方开放平台

**推荐指数：⭐⭐⭐⭐⭐**

官方入口：

- https://aop.alibaba.com/
- https://open.1688.com/

已确认能力：

- 跨境代采寻源比价搜索
- 一键铺货
- 自动下单
- 批量支付
- 订单信息同步
- 物流信息查询

官方 solution 文档：

- 跨境代采寻源比价搜索解决方案
  https://open.1688.com/solution/solutionDetail.htm?solutionKey=1697014160788
- 跨境 ERP / 独立站 SaaS 数字化解决方案
  https://open.1688.com/solution/solutionDetail.htm?solutionKey=1697015308755

**优势**：

- 正式 API 文档
- 官方技术支持
- 稳定性保障
- 明确的鉴权与限流规则

**劣势**：

- 需要企业资质申请
- 可能需要阿里云账号
- 接入流程相对复杂

### 4.2 浏览器自动化（不推荐）

如果必须使用 AlphaShop，只能通过浏览器自动化：

- Playwright / Puppeteer / Selenium
- 模拟用户操作
- 解析 HTML 响应

**风险评估：高（8/10）**

| 风险维度 | 等级 | 说明 |
|---------|------|------|
| 稳定性 | 高 | UI 变更会导致脚本失效 |
| 合规性 | 高 | 可能违反服务条款 |
| 维护成本 | 高 | 需持续跟进 UI 变化 |
| 可扩展性 | 高 | 难以支撑高并发场景 |
| 数据一致性 | 中 | 无结构化数据保障 |

### 4.3 人工辅助（推荐作为过渡）

**推荐指数：⭐⭐⭐**

方案：

- Deyes 生成采购需求
- 人工通过 AlphaShop UI 执行询盘/下单
- 人工将结果录入 Deyes

**优势**：

- 合规
- 稳定
- 无技术风险

**劣势**：

- 效率低
- 人工成本高
- 难以规模化

---

## 5. 对 Deyes 整合方案的影响

### 5.1 原计划回顾

原计划将 AlphaShop 作为：

1. **采购执行层**（优先级 P0）
   - 询盘自动化
   - 下单执行
   - 订单状态同步

2. **供应商发现层**（优先级 P1）
   - 供应商候选召回
   - 图搜找货

3. **需求情报增强层**（优先级 P2）
   - 榜单热度
   - 竞品信号

### 5.2 调整建议

#### 建议 A：放弃 AlphaShop 采购执行层接入

**理由**：

- 无正式 API
- 浏览器自动化风险过高
- 不适合作为核心采购通道

**替代方案**：

- 优先接入 **1688 官方开放平台**
- 保留 `ManualProcurementProvider` 作为人工通道
- 暂不实施 AlphaShop 采购执行层

#### 建议 B：降级 AlphaShop 为"辅助情报源"

**可保留的价值**：

1. **供应商发现增强**（如果有图搜 API）
   - 仅限有正式 API 的功能
   - 作为 `SupplierDiscoveryProvider` 的一个可选源

2. **图片翻译增强**（如果有正式 API）
   - 作为 `AssetDerivationService` 的可选增强
   - 仅用于高价值 SKU

3. **人工辅助工具**
   - 运营人员使用 AlphaShop UI 做市场调研
   - 结果手动录入 Deyes

#### 建议 C：优先接入 1688 官方开放平台

**新优先级**：

1. **P0：1688 官方 API 接入**
   - 供应商搜索
   - 询盘发送
   - 下单执行
   - 订单状态同步

2. **P1：Deyes 采购体系完善**
   - `SupplierInquiry` 模型
   - `InquiryService` 服务
   - `ProcurementExecutionProvider` 抽象
   - `Alibaba1688ProcurementProvider` 实现

3. **P2：AlphaShop 可选增强**
   - 仅接入有正式 API 的功能
   - 作为辅助情报源，不作为核心通道

---

## 6. 下一步行动建议

### 立即行动

1. **调研 1688 官方开放平台**
   - 确认企业资质要求
   - 了解接入流程
   - 评估 API 能力覆盖度

2. **更新整合方案文档**
   - 将 AlphaShop 从 P0 降级为 P2
   - 将 1688 官方 API 提升为 P0
   - 更新架构设计

3. **保留抽象层设计**
   - `ProcurementExecutionProvider` 抽象仍然有效
   - 只是第一个实现从 `AlphaShopProvider` 改为 `Alibaba1688Provider`

### 暂缓行动

1. **暂不实施 AlphaShop 采购执行层**
2. **暂不实施浏览器自动化方案**
3. **暂不投入 AlphaShop 深度集成**

### 持续观察

1. **关注 AlphaShop 产品演进**
   - 是否推出正式 API
   - 是否开放开发者门户
   - 是否提供企业级服务

2. **评估其他替代方案**
   - 其他 1688 数据聚合服务
   - 其他跨境采购 SaaS 平台

---

## 7. 风险评估总结

| 方案 | 可行性 | 稳定性 | 合规性 | 维护成本 | 推荐度 |
|-----|--------|--------|--------|---------|--------|
| **AlphaShop 正式 API** | ❌ 不存在 | N/A | N/A | N/A | ⭐ |
| **AlphaShop 浏览器自动化** | ⚠️ 可行但脆弱 | ❌ 低 | ⚠️ 风险 | ❌ 高 | ⭐⭐ |
| **1688 官方开放平台** | ✅ 可行 | ✅ 高 | ✅ 合规 | ✅ 低 | ⭐⭐⭐⭐⭐ |
| **人工辅助** | ✅ 可行 | ✅ 高 | ✅ 合规 | ⚠️ 中 | ⭐⭐⭐ |

---

## 8. 最终结论

### 核心判断

**AlphaShop 当前不适合作为 Deyes 的核心采购执行通道。**

### 推荐路径

1. **优先接入 1688 官方开放平台**
2. **保留 AlphaShop 作为可选辅助情报源**（仅限有正式 API 的功能）
3. **保留人工通道作为 fallback**

### 架构调整

原设计的抽象层仍然有效，只需调整实现优先级：

- `ProcurementExecutionProvider` 抽象 ✅ 保留
- `Alibaba1688ProcurementProvider` ⬆️ 提升为 P0
- `AlphaShopProcurementProvider` ⬇️ 降级为 P2（待正式 API 推出）
- `ManualProcurementProvider` ✅ 保留

---

## 9. 参考资料

### AlphaShop 官方

- AlphaShop 官网：https://www.alphashop.cn/
- Chrome 插件：https://chromewebstore.google.com/detail/1688-alphashop-ai-sourcin/ecpkhbhhpfjkkcedaejmpaabpdgcaegc
- 移动应用：https://play.google.com/store/apps/details?id=com.accio.android.app

### 1688 官方开放平台

- 1688 开放平台：https://aop.alibaba.com/
- 1688 Open Platform：https://open.1688.com/
- 跨境代采解决方案：https://open.1688.com/solution/solutionDetail.htm?solutionKey=1697014160788
- 跨境 ERP 解决方案：https://open.1688.com/solution/solutionDetail.htm?solutionKey=1697015308755

### 第三方资料

- AlphaShop 产品介绍：https://aicost.org/product/alphashop
- 遨虾市场分析：https://aixzd.com/alphashop
- Fecify 1688 集成文档：https://www.fecify.com/doc/cn-1.0/fecify-merchant-admin-sync-data-alibaba-1688.html

---

**备注**：

本验证报告基于 2026-03-30 的公开信息。如 AlphaShop 后续推出正式 API，应重新评估接入可行性。
