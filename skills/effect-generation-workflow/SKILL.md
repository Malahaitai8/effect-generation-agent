---
name: effect-generation-workflow
description: 分析设计师提交的热点视频，召回历史案例，选择单图、多图或参考视频链路，并交付节点、素材、模型、Prompt 和风险完整关联的特效生成方案。用于特效链路设计，不执行 Keffect 或结果视频跑批。
---

# 特效生成链路

## 产品边界

直接用户是设计师。当前输入是热点视频和可选固定参考素材，输出是节点化链路方案。未来使用特效时才提供的人物图、宠物图等是 `runtime_inputs`，不是当前必须存在的文件。

- `single_image`：最终视频模型恰好接收一张图。
- `multi_image`：最终视频模型接收两张有序状态图，不接收参考视频。
- `reference_video`：最终视频模型接收连续参考视频，可同时接收主体图。
- `unsupported`：识别边界后停止，不强行降级。

## 全局执行协议

1. `WorkflowEngine` 解析当前 Step 的 `input_refs`，构造只读 `StepContext`。
2. `StepExecutor` 读取当前 Step 文档，调用模型或工具，将业务 JSON 包装为 `StepResult`。
3. Prompt 只使用执行器传入的字段，不读写 `task-result.json`。
4. `TaskStore` 是状态唯一写入者，负责 Schema 校验和原子保存。
5. `needs_input` 只表示源热点视频缺失，或调试模式正在等待人工模型结果；固定素材源、生图或处理能力不可用时使用 `blocked`；`failed` 只用于不可恢复错误。
6. 当前不自动回退已完成 Step。发现上游冲突时保留证据并停止。

运行时读取 [任务结果与流程约束](references/task-result-schema.md)；机器字段约束以项目根目录 `schemas/task-result.schema.json` 为事实源。

## 七步路由

| Step | 任务 | 必须读取 |
|---|---|---|
| 1 | 完整视频客观理解与关键帧筛选 | [vlm-observation.md](prompts/vlm-observation.md) |
| 2 | 主次卖点、复刻目标与控制信号 | [selling-point.md](prompts/selling-point.md) |
| 3A | 只按卖点跨链路召回 Top 6 并保存快照 | [case-retrieval.md](prompts/case-retrieval.md) |
| 3B | 结合视频、卖点和快照选链路 | [chain-selection.md](prompts/chain-selection.md) |
| 4 | 设计节点、模型、运行时槽位和固定素材 | 按链路读取设计文档 |
| 5 | 只准备和验证固定素材 | [material-preparation.md](prompts/material-preparation.md) |
| 6 | 为 Step 4 模型节点逐节点生成 Prompt | 按链路读取 Prompt 文档 |
| 7 | 校验并生成设计师可读节点方案 | [plan-validation-delivery.md](prompts/plan-validation-delivery.md) |

## 链路分支

- `single_image`：Step 4 读取 [单图设计](prompts/chain-single-image-design.md)；Step 6 读取 [单图 Prompt](prompts/chain-single-image-prompt.md)。
- `reference_video`：Step 4 读取 [参考视频设计](prompts/chain-reference-video-design.md)；Step 6 读取 [参考视频 Prompt](prompts/chain-reference-video-prompt.md)。
- `multi_image`：Step 4 读取 [多图设计](prompts/chain-multi-image.md)；Step 6 读取 [多图 Prompt](prompts/chain-multi-image-prompt.md)。
- `unsupported`：记录不支持原因和能力缺口并停止。

Step 3 只执行一次主召回。Step 4 和 Step 6 仅读取同一快照中 Step 3B 已过滤的案例，不再召回。案例读写使用 [案例数据规范](references/case-schema.md)。

Step 2 是“复刻什么”的唯一决策源：四类复刻要求均使用稳定 ID。Step 3 的每个 `must_preserve` 必须引用 Step 2 `preserve` 或 `control_signals`；运行时会阻断将 `replace`、`adapt` 或 `optional` 升级为硬约束的结果。Step 4–6 只落实已验证的约束。

对 `reference_video`，Step 4 还必须判断主体图片只提供身份，还是需要先由生图节点建立已确认的目标视觉状态。两种节点结构都属于参考视频驱动；不得从源视频主体外观自动推导前置生图。

Step 2 只记录热点内容的外观约束；其中 `adapt` 不等于要求保留输入造型。Step 4 在实际节点和视觉方案确定后输出 `appearance_strategy`：只把 Step 2 `preserve` 中的外观约束或设计师明确要求视为“必须保留”，再判断热点角色、主题和整体视觉是否需要目标造型；需要时选择统一重设计或按人物呈现分别重设计。只有后者建立 `presentation_type` 分支，并只路由到真正受影响的节点。Step 6 严格跟随 Step 4，不自行增删分支。

Step 4 还要判断热点关键帧是“理解证据”还是“真实模型输入”。核心首帧依赖较精确的场景、构图、姿态、景别、复杂道具或空间关系时，选择 Step 1 原分辨率关键帧作为固定素材，让前置生图节点同时输入用户身份图与热点视觉参考图；简单场景或允许自由创作时才只输入用户图。前置节点使用多张参考图不改变链路分类，分类仍只看最终视频模型入参。

## 交付

`outputs/<task-id>/` 保存：

- `task-result.json`：完整七步状态与审计记录（Schema `0.9.0`）。
- `case-snapshot.json`：Step 3 实际召回的完整案例快照。
- `materials/`：Step 5 处理的固定素材。
- `production-plan.md`：主要用户交付，按依赖顺序展示节点并内嵌 Prompt。

没有产物或证据时，不得声称模型能力、生成素材或结果视频已验证。
