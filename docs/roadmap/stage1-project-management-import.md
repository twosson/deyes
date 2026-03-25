# Stage 1 项目管理导入说明

> 文件：`docs/roadmap/stage1-project-management-import.csv`
>
> 用途：把 Stage 1 development backlog 转成通用导入表，便于导入 Jira、Linear、飞书项目等工具。

---

## 1. 字段说明

CSV 当前包含以下字段：

| 字段 | 说明 |
|------|------|
| `ID` | backlog 唯一编号，如 `S1-A1` |
| `Title` | 卡片标题 |
| `Type` | 工作类型，如 Schema / Service / Test / Platform |
| `Batch` | 所属执行批次 |
| `Owner Lane` | 建议责任 lane |
| `Dependencies` | 依赖项 |
| `External Dependency` | 外部 blocker 或前置条件 |
| `Status` | 初始状态，来自 backlog 文档 |
| `PR` | 推荐归属 PR 切分 |
| `Epic` | 默认填充为 `Stage 1` |
| `Milestone` | 默认映射到 `Batch 1-4` |
| `Feature Group` | 默认映射到 `分组 A-E` |
| `Description` | 更完整的任务说明 |

---

## 2. 推荐映射方式

### Jira

建议映射为：
- Epic → `Epic`
- Summary → `Title`
- Issue Type → `Type`
- Fix Version / Sprint / Milestone → `Batch`
- Component / Team → `Owner Lane`
- Labels → `Feature Group`
- Description → `Description`
- Linked Issues / issue links → `Dependencies`（导入后再补）
- Status → `Status`

### Linear

建议映射为：
- Project → `Stage 1`
- Title → `Title`
- Description → `Description`
- State → `Status`
- Cycle / Milestone → `Batch`
- Team / Assignee Group → `Owner Lane`
- Labels → `Type`, `Feature Group`
- Relation / blocked by → `Dependencies`（导入后补）

### 飞书项目

建议映射为：
- 项目 → `Stage 1`
- 工作项标题 → `Title`
- 工作项类型 → `Type`
- 迭代 → `Batch`
- 负责人泳道 → `Owner Lane`
- 标签 → `Feature Group`
- 描述 → `Description`
- 前置关系 → `Dependencies`
- 状态 → `Status`

---

## 3. 使用建议

### 直接导入前建议

1. 先把 `Status` 字段值映射到你的项目管理工具状态枚举
   - `ready`
   - `todo`
   - `blocked`

2. 先确认 `Owner Lane` 是否要拆成：
   - Team
   - Component
   - Assignee Group

3. `Dependencies` 当前是文本字段
   - 如果项目工具支持依赖导入，可二次转换
   - 如果不支持，建议先导入后再批量补链路

4. `PR` 字段更适合作为：
   - label
   - custom field
   - 或导入后删除

---

## 4. 当前适合直接开工的卡片

优先级最高、且无外部 blocker 的是：
- `S1-A1`
- `S1-A2`
- `S1-A3`
- `S1-B1`
- `S1-B2`

这组任务对应 Stage 1 Batch 1，可作为首批建卡与开工入口。

---

## 5. 后续可继续补的导入表

如果你需要，我可以继续生成：
1. `stage2-project-management-import.csv`
2. `stage3-project-management-import.csv`
3. `stage4-project-management-import.csv`
4. `stage5-project-management-import.csv`
5. `stage6-project-management-import.csv`
6. 合并版 `roadmap-master-import.csv`

---

**版本**: v1.0
**创建时间**: 2026-03-25
**维护者**: Deyes 研发团队
