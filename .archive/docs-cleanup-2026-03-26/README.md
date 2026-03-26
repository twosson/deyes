# Deyes 文档导航

> 最后更新: 2026-03-19
> 系统版本: v5.0

---

## 📚 文档总览

### 核心架构文档

1. **[系统架构 v4.0](architecture/system-architecture-v4.md)** ⭐⭐⭐⭐⭐
   - 完整技术栈和架构设计
   - GPU资源分配方案
   - 性能指标和成本分析

2. **[业务优化 v5.0](architecture/business-optimization-v5.md)** ⭐⭐⭐⭐⭐
   - 业务模式深度分析
   - 快速测款策略
   - A/B测试驱动优化
   - 新增模块和功能
   - 1688 / TMAPI 选品系统优化路线

3. **[硬件验证报告](architecture/hardware-validation-8x4090.md)** ⭐⭐⭐⭐
   - 8x4090 性能验证
   - 显存计算和GPU分配
   - 配套硬件采购清单

4. **[Qwen3.5 vs DeepSeek 对比](architecture/qwen3.5-vs-deepseek-ecommerce-analysis.md)** ⭐⭐⭐
   - 模型选型分析
   - 电商场景适配性

### 部署文档

5. **[统一部署指南](../DEPLOYMENT.md)** ⭐⭐⭐⭐⭐
   - 当前仓库唯一部署说明
   - Docker Compose 全栈部署
   - 验证与故障排查

6. **[ComfyUI 完整部署指南](deployment/comfyui-deployment-guide.md)** ⭐⭐⭐⭐
   - 图像生成服务专项部署
   - 模型下载与工作流配置

7. **[实施计划](deployment/implementation-plan.md)** ⭐⭐⭐
   - 4周实施时间表
   - 里程碑和交付物

### 业务文档

8. **[Agent定义](agents/agent-definitions.md)**
   - 24个数字员工岗位定义

9. **[核心业务流程](workflows/core-business-flows.md)**
   - 业务流程设计

---

## 🎯 阅读顺序建议

### 新用户 / 初次了解

1. 先读 [README.md](../README.md) - 项目总览
2. 再读 [业务优化 v5.0](architecture/business-optimization-v5.md) - 理解业务模式
3. 再读 [系统架构 v4.0](architecture/system-architecture-v4.md) - 理解技术架构

### 准备部署

1. 读 [硬件验证报告](architecture/hardware-validation-8x4090.md)
2. 读 [统一部署指南](../DEPLOYMENT.md)
3. 如需图像服务专项配置，再读 [ComfyUI 完整部署指南](deployment/comfyui-deployment-guide.md)

### 准备开发

1. 读 [系统架构 v4.0](architecture/system-architecture-v4.md)
2. 读 [Agent定义](agents/agent-definitions.md)
3. 读 [核心业务流程](workflows/core-business-flows.md)

---

## 🔑 关键结论

### 业务模式

**Deyes 不是单纯的"图片生成工具"，而是：**

- **快速测款系统**: 日测试 1,200+ SKU
- **爆款复刻系统**: 自动复刻高转化率风格
- **A/B测试系统**: 数据驱动优化，爆款率提升 3倍
- **全链路自动化系统**: 从选品到上架的完整自动化

### 技术选型

- **图像生成**: FLUX.1-dev + IPAdapter + ControlNet
- **LLM推理**: SGLang + Qwen3.5-35B-A3B
- **背景移除**: RMBG 1.4
- **虚拟试穿**: IDM-VTON
- **存储**: MinIO + PostgreSQL + Redis + Qdrant

### 性能指标

- **日测款能力**: 1,200个SKU
- **主图生成速度**: 60秒/SKU（3个变体）
- **图片质量**: 92分（专业级）
- **爆款率**: 15%（vs 传统5%）
- **成本降低**: 90%

---

## 📌 当前状态

- ✅ 架构设计完成（v5.0）
- ✅ 硬件验证完成（8x4090）
- ✅ 部署文档完成
- ⏳ 待执行：实际部署和测试

---

**文档版本**: v5.0
**维护状态**: 最新
