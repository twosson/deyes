# Deyes 文档导航

> 最后更新: 2026-03-27
> 架构版本: v4.0 | 项目状态: 战略转向 - 从推荐分析到自动化经营

---

## ⚠️ 战略转向说明（2026-03-27）

经过对当前系统的深度复盘，我们确认：

**系统曾经走向了错误方向**：
- ❌ 过度强调推荐页面、分析看板、手动反馈
- ❌ 更像"推荐分析平台"而非"自动化经营系统"
- ❌ 帮人做判断，但没有替人做执行

**新的核心定位**：
- ✅ **AI驱动的自动化经营系统**
- ✅ **自动执行引擎**（自动上架、自动调价、自动暂停、自动换素材）
- ✅ **性能数据反馈闭环**（基于真实转化率/ROI自动优化）
- ✅ **人工审批兜底**（高风险操作需要审批）

**一句话总结**：
> Deyes 的目标不是做一个让老板看图表的系统，而是做一个替老板自动经营店铺的系统。

---

## 📚 文档总览

### 核心项目文档

1. **[项目状态报告](PROJECT_STATUS.md)** ⭐⭐⭐⭐⭐
   - **最新项目状态总览 + 战略转向说明**
   - 已完成模块、待完成模块、90天执行路线图
   - 新优先级排序：自动执行 > 性能反馈 > AI优化
   - **这是当前最重要的项目状态文档**

2. **[核心业务流程](workflows/core-business-flows.md)** ⭐⭐⭐⭐⭐
   - **自动化经营主流程设计**
   - 自动上架、自动调价、自动暂停、自动换素材
   - 性能反馈闭环 + 人工审批工作台
   - **这是理解新业务方向的首选文档**

3. **[系统架构 v4.0](architecture/system-architecture-v4.md)** ⭐⭐⭐⭐⭐
   - 完整技术栈和架构设计
   - GPU资源分配方案
   - 性能指标和成本分析

4. **[研发路线图 2026](roadmap/engineering-roadmap-2026.md)** ⭐⭐⭐⭐⭐
   - **战略转向后的研发优先级**
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

7. **[推荐服务](services/recommendation-service.md)** ⭐⭐
   - 推荐评分算法
   - **注意：现已降级为内部决策服务，不再是主产品形态**
   - 后续应服务于自动上架与审批流，而非独立分析页面

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

---

## 🎯 阅读顺序建议

### 新用户 / 了解当前项目

1. 先读 [README.md](../README.md) - 项目总览
2. 再读 [项目状态报告](PROJECT_STATUS.md) - 先理解战略转向
3. 再读 [核心业务流程](workflows/core-business-flows.md) - 理解自动化经营主流程
4. 再读 [研发路线图 2026](roadmap/engineering-roadmap-2026.md) - 理解技术落地顺序
5. 最后读 [系统架构 v4.0](architecture/system-architecture-v4.md) - 技术架构

### 准备部署

1. 读 [项目状态报告](PROJECT_STATUS.md) - 确认当前待部署模块和新优先级
2. 读 [硬件验证报告](architecture/hardware-validation-8x4090.md)
3. 读 [统一部署指南](../DEPLOYMENT.md)
4. 如需图像服务专项配置，再读 [ComfyUI 完整部署指南](deployment/comfyui-deployment-guide.md)

### 准备开发

1. 读 [项目状态报告](PROJECT_STATUS.md)
2. 读 [核心业务流程](workflows/core-business-flows.md)
3. 读 [研发路线图 2026](roadmap/engineering-roadmap-2026.md)
4. 读 [系统架构 v4.0](architecture/system-architecture-v4.md)
5. 最后读 [推荐服务](services/recommendation-service.md)（仅作为内部服务参考）

---

## 📌 当前状态

### 已完成

- ✅ 核心选品推荐系统完成
- ✅ 需求验证层（Google Trends + Helium 10 可选增强）
- ✅ 推荐系统（评分算法、理由生成、等级判断）
- ✅ 用户反馈机制（接受/拒绝/延后）
- ✅ 推荐分析看板（时间趋势、平台对比、反馈统计）
- ✅ 硬件验证完成（8x4090）
- ✅ 部署文档完成
- ✅ **战略转向确认：从推荐分析到自动化经营**

### 当前最高优先级（P0）

- 🔥 AutoActionEngine（自动上架、自动调价、自动暂停、自动换素材）
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

**Deyes 当前不是单纯的图片生成工具，也不应该只是推荐分析平台，而是：**

- **需求验证优先的选品系统**
- **自动执行驱动的经营系统**
- **性能数据反馈闭环系统**
- **人工审批兜底系统**
- **待部署的 AI 图像生成与多平台自动经营系统**

### 最新战略决策（2026-03-27）

- **推荐系统降级**: RecommendationService 保留，但转为内部决策引擎
- **推荐页面降级**: RecommendationsPage 后续应演进为 ApprovalWorkbench
- **数据看板降级**: 从主产品降为性能监控辅助面板
- **新主战场**: 自动执行、性能反馈、AI优化、审批边界

### 最新交付（2026-03-27）

- **用户反馈机制**: RecommendationFeedback + API + 前端按钮
- **Helium 10 集成框架**: 可选增强 + 自动回退
- **数据看板扩展**: 时间趋势 + 平台对比 + 反馈统计
- **文档战略重构**: 明确从推荐分析转向自动化经营

---

**文档版本**: v7.0
**维护状态**: 最新
