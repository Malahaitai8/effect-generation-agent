# Step 7：方案验证与交付

## 1. 步骤目标

验证 Step 1–6 形成的链路方案是否完整、可唯一解析且可追溯，再生成设计师可读的 `production-plan.md`。本步骤是确定性校验与排版，不调用模型重写方案。

## 2. 执行边界

- 前置：Step 1–6 完成，且 `workflow.step_5.output.ready_for_prompting == true`。
- 负责：校验引用、依赖、模型、固定素材、Prompt 和案例证据；按 `node_id` 合并 Step 4 节点与 Step 6 Prompt。
- 不负责：重选链路、修改节点、补写缺失 Prompt、执行生成节点或评估结果视频。

## 3. 输入契约

| 字段 | 用途 | 必需 |
|---|---|---|
| `source` | 热点视频标题与路径 | 是 |
| `workflow.step_1.output` | 内容摘要 | 是 |
| `workflow.step_2.output` | 核心卖点 | 是 |
| `workflow.step_3.output` | 链路、理由、案例和风险 | 是 |
| `workflow.step_4.output` | 节点、运行时槽位和固定素材要求 | 是 |
| `workflow.step_5.output` | 固定素材处理结果 | 是 |
| `workflow.step_6.output` | 逐节点 Prompt | 是 |

## 4. 执行规则

1. `runtime_inputs[].id`、`base_materials[].id` 和 `nodes[].outputs[]` 在各自列表内不得重复，三类之间也不得重名。
2. 节点 ID 和 Prompt `node_id` 必须唯一；节点依赖必须指向已定义节点。
3. 节点输入只能引用运行时槽位、固定素材或已定义节点输出。
4. 必需固定素材必须在 Step 5 中为 `ready` 且文件存在；运行时槽位只校验定义，不检查文件。
5. Step 5 `materials` 不得包含运行时槽位或节点输出。
6. Step 4 每个有 `model` 的节点必须恰好有一个 Step 6 `node_prompt`，且模型名一致；确定性节点可没有 Prompt。
7. 无 `prompt_routing` 的模型节点必须只有一个 `default` 变体且条件为空。有路由的节点必须引用 Step 2 已声明维度和可解析的 `source_ref`，Step 6 变体条件必须不重不漏地覆盖所有可达组合。
8. 节点输入以 Step 4 `nodes[].inputs` 为唯一事实源；Step 6 不重复输出素材引用。
9. `prompt_audit[].case_refs` 只能引用 Step 3 `case_ids`，并在交付文末集中展示。
10. 主体按完整生产节点组织：每个节点内展示职责、模型、参数、输入输出、依赖、Prompt 及版本命中条件；案例、素材证据和覆盖缺口放入“方案依据与审计附录”。

## 5. 输出契约

```json
{
  "production_plan_ref": "outputs/<task-id>/production-plan.md",
  "deliverables": ["production_plan", "task_result", "materials"],
  "validation": {"nodes_valid": true, "materials_ready": true, "prompts_complete": true, "case_references_valid": true},
  "open_risks": []
}
```

`production-plan.md` 包含：热点视频与卖点、链路选择与案例、运行时输入槽位、固定素材、执行节点、风险与待确认项。

## 6. 运行状态

- `completed`：所有校验通过，已安全写入交付。
- `blocked`：引用、依赖、固定素材、模型或 Prompt 不完整；保留问题列表，不生成伪交付。
- `failed`：交付文件无法安全写入且不可恢复。

## 7. 输出示例

- 单图：展示 `user_image` 运行时槽位，在 `generate_video` 节点内嵌 Prompt。
- 参考视频：展示 `user_image`、已就绪 `reference_video` 和同时引用两者的节点 Prompt。
- 模型节点缺 Prompt：返回 `blocked`，不输出成功交付。

## 8. 输出前检查

- 三类 ID 和节点/Prompt ID 是否都唯一？
- 节点输入与依赖是否可解析？
- 是否只对固定素材检查文件？
- 每个模型节点的 Prompt 变体是否恰好覆盖所有可达路由？
- 交付是否以节点为中心，而不是堆放 Step JSON？
