# 密钥组件 IoU 拖动交换设计

## 目标

- 密钥组件拖动时，仅当拖动中的组件与目标组件 IoU 大于 0.4 时显示目标高亮。
- 松手时沿用现有排序语义：LLM 组件交换位置，secret 组件按拖动方向插入。
- 将 LLM 卡片标题（例如 `openai/gpt-4o`）从 16px 调整为 14px；模型信息行保持现有字号。

## 方案

在 `frontend/src/pages/KeysPage.tsx` 的指针移动逻辑中，计算拖动组件与每个候选组件的矩形交集面积，并使用：

```text
IoU = intersectionArea / (dragArea + targetArea - intersectionArea)
```

只有 `IoU > 0.4` 的候选组件才可成为 `targetId`，否则清除当前目标高亮。现有 LLM 最近目标选择和 secret 插入方向逻辑保留，但它们只在 IoU 达标后生效。

## 边界行为

- 组件未接触时交集为 0，IoU 为 0，不高亮、不交换。
- IoU 等于 0.4 时不满足严格的大于条件。
- 松手时没有有效目标，组件回到原位置，不提交 reorder。
- 不改变后端排序协议或密钥数据。

## 验证

- TypeScript 类型检查与前端构建。
- 现有密钥页面拖动契约测试。
- Rust 与 e2e 全量测试，记录存量环境失败项。
