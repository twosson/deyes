# Deyes 文档导航

> 最后更新: 2026-03-29
> 架构版本: v4.0 | 项目状态: 需求优先选品架构 + 自动化经营方向

---

## 📚 文档总览

### 核心项目文档

1. **[项目状态报告](PROJECT_STATUS.md)** ⭐⭐⭐⭐⭐
   - **最新项目状态总览**（2026-03-29 更新）
   - 已完成模块、待完成模块、最新功能交付
   - 需求上下文集成完成状态
   - **这是当前最重要的项目状态文档**

2. **[核心业务流程](workflows/core-business-flows.md)** ⭐⭐⭐⭐⭐
   - 需求验证优先选品流程
   - 自动化经营主流程设计
   - 自动上架、自动调价、自动暂停、自动换素材
   - 性能反馈闭环 + 人工审批工作台

3. **[系统架构 v4.0](architecture/system-architecture-v4.md)** ⭐⭐⭐⭐⭐
   - 完整技术栈和架构设计
   - GPU资源分配方案
   - 性能指标和成本分析

4. **[研发路线图 2026](roadmap/engineering-roadmap-2026.md)** ⭐⭐⭐⭐⭐
   - 研发优先级与阶段规划
   - AutoActionEngine + PerformanceDataLoop + AIOptimizationEngine
   - API-first, RPA-second 原则

5. **[产品选品优化 v1](architecture/product-selection-optimization-v1.md)** ⭐⭐⭐⭐
   - 需求验证优先策略
   - Helium 10 集成、季节性日历、动态关键词生成
   - 选品系统优化路线

6. **[硬件验证报告](architecture/hardware-validation-8x4090.md)** ⭐⭐⭐⭐
   - 8x4090 性能验证
   - 显存计算和GPU分配
   - 配套硬件采购清单

### 服务文档

7. **[推荐服务](services/recommendation-service.md)** ⭐⭐⭐
   - 内部推荐排序服务
   - 评分算法与需求上下文集成
   - **定位：内部决策引擎，不再作为主产品形态**

8. **[季节性日历](services/seasonal-calendar.md)**
   - 90 天前瞻日历
   - 节假日权重配置

9. **[关键词生成器](services/keyword-generator.md)**
   - 趋势关键词生成
   - 长尾关键词扩展

### 部署文档

10. **[统一部署指南](../DEPLOYMENT.md)** ⭐⭐⭐⭐⭐
   - **当前仓库唯一权威部署说明**
   - Docker Compose 全栈部署
   - 前后端、数据库、AI 服务统一部署

11. **[ComfyUI 完整部署指南](deployment/comfyui-deployment-guide.md)** ⭐⭐⭐⭐
   - ComfyUI 图像生成服务专项部署
   - 模型下载与工作流配置

### 业务与规划文档

12. **[Agent定义](agents/agent-definitions.md)**
   - 24个数字员工岗位定义

13. **[路线图总览](roadmap/roadmap-index.md)**
   - Stage 1-6 完整规划
   - 产品路线图与研发路线图入口

14. **[双模式经营架构实施计划](roadmap/dual-mode-operations-plan.md)** ⭐⭐⭐⭐⭐
   - Temu `pre_order` 与传统 `stock_first` 双模式设计
   - 自研 ERP Lite 内核边界
   - 素材/本地化/平台派生的实施方案
   - 可直接作为后续开发入口

---

## 🎯 阅读顺序建议

### 新用户 / 了解当前项目

1. 先读 [README.md](../README.md) - 项目总览
2. 再读 [项目状态报告](PROJECT_STATUS.md) - 当前状态与最新交付
3. 再读 [核心业务流程](workflows/core-business-flows.md) - 理解需求优先选品流程
4. 再读 [研发路线图 2026](roadmap/engineering-roadmap-2026.md) - 理解技术落地顺序
5. 最后读 [系统架构 v4.0](architecture/system-architecture-v4.md) - 技术架构

### 准备部署

1. 读 [项目状态报告](PROJECT_STATUS.md) - 确认当前待部署模块
2. 读 [硬件验证报告](architecture/hardware-validation-8x4090.md)
3. 读 [统一部署指南](../DEPLOYMENT.md)
4. 如需图像服务专项配置，再读 [ComfyUI 完整部署指南](deployment/comfyui-deployment-guide.md)

### 准备开发

1. 读 [项目状态报告](PROJECT_STATUS.md)
2. 读 [核心业务流程](workflows/core-business-flows.md)
3. 读 [研发路线图 2026](roadmap/engineering-roadmap-2026.md)
4. 读 [双模式经营架构实施计划](roadmap/dual-mode-operations-plan.md)
5. 读 [系统架构 v4.0](architecture/system-architecture-v4.md)
6. 最后读 [推荐服务](services/recommendation-service.md)（仅作为内部服务参考）

---

## 📌 当前状态

### 已完成

- ✅ 核心选品推荐系统完成
- ✅ 需求验证层（Google Trends + Helium 10 可选增强）
- ✅ 需求上下文集成（定价、风控、推荐排序）
- ✅ 推荐系统（评分算法、理由生成、等级判断）
- ✅ 硬件验证完成（8x4090）
- ✅ 部署文档完成

### 当前最高优先级（P0）

- 🔥 回归测试可观测性增强
- 🔥 PerformanceDataLoop（ListingPerformanceDaily / AssetPerformanceDaily）
- 🔥 AIOptimizationEngine（基于真实ROI/转化率自动优化）
- 🔥 多平台API集成（Temu / Amazon / AliExpress）
- 🔥 ApprovalWorkbench（人工审批兜底）

### 待完成

- ⏳ ComfyUI 图像生成服务部署
- ⏳ SGLang LLM 推理服务部署
- ⏳ MinIO / Qdrant 服务部署
- ⏳ AutoActionEngine 自动执行层
- ⏳ PerformanceDataLoop 性能数据采集
- ⏳ ApprovalWorkbench 审批工作台
- ⏳ 端到端自动经营流程验证

---

## 🔑 关键结论

### 当前项目定位

**Deyes 是：**
- **需求验证优先的选品系统**
- **自动执行驱动的经营系统**
- **性能数据反馈闭环系统**
- **人工审批兜底系统**
- **待部署的 AI 图像生成与多平台自动经营系统**

### 最新交付（2026-03-29）

- **需求上下文集成完成**：定价、风控、推荐排序已纳入需求发现质量
- **推荐服务定位调整**：降级为内部决策引擎，不再作为主产品形态
- **测试状态**：本地测试通过 42 个（风险 + 竞争 + 推荐服务）

---

**文档版本**: v8.0
**维护状态**: 最新

