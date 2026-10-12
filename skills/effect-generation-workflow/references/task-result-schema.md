# 任务结果 Schema 与流程约束（当前草案）

## 当前定位

- `schemas/task-result.schema.json` 是当前版本的机器校验规则，不是任务数据文件，也不是不可变的最终设计。
- `outputs/<task-id>/task-result.json` 是一次任务实际读取和写入的状态文件。
- `outputs/<task-id>/case-snapshot.json` 是 Step 3 为当前任务保存的案例快照；其中 `candidates` 保存选链路前的跨链路 Top 6、相似度分数和完整 case。

Schema、节点输入输出和案例结构允许随实现逐步演进。每次结构调整必须同步检查 Prompt 中的字段路径、fixture 和测试；改变已有字段语义或其他破坏兼容性的调整必须升级 `schema_version`，兼容性枚举扩展等变更可保留当前版本并记录影响。

Schema `0.6.0` 将 Step 2 `replication_goal` 的字符串改为带稳定 `id` 的约束对象，并要求 Step 3 `must_preserve` 通过 `source_refs` 引用 `replication_goal.preserve.<id>` 或 `control_signals.<field>.<index>`。运行时拒绝将 `replace/adapt/optional` 内容升级为必保留项。

Schema `0.9.0` 在 Step 4 用三种明确模式表达外观策略：保留输入、统一重设计、按人物呈现分别重设计。人物分支由已经确定的视觉方案推导，不要求 Step 2 提前猜测节点设计，也不依赖成人、宠物或具体案例例外。

本文件说明当前版本的读写和跨 Step 约束。字段的机器结构仍以当前 `schemas/task-result.schema.json` 为准。

## 当前执行与读写约定

1. `TaskStore` 创建、读取、校验和保存 `outputs/<task-id>/task-result.json`，是任务状态的唯一写入者。
2. `WorkflowEngine` 检查前置依赖并根据 `input_refs` 构造当前 Step 的只读 `StepContext`。
3. `StepExecutor` 调用 Prompt、模型或工具，返回 `StepResult(status, output, errors, artifact_updates)`；不得直接修改状态文件。
4. Prompt 只返回当前 Step 的业务 `output`，不读取状态文件、不决定保存路径，也不包装运行状态。
5. `TaskStore` 提交结果前校验完整任务，通过后原子替换；校验或保存失败时保留上一份有效状态。
6. Schema 文件只用于校验，不写入任何任务结果。版本不匹配时必须显式迁移。

## 当前字段交接

| Step | 主要读取 | 写入 |
| --- | --- | --- |
| 1 | `source`、可复用的当前 Step 1 预处理引用 | `workflow.step_1.output` |
| 2 | `workflow.step_1.output` | `workflow.step_2.output` |
| 3 | Step 1、2 输出 | `workflow.step_3.output`，并保存案例快照 |
| 4 | `source`、Step 1–3 输出、案例快照；模型能力由运行资源注入 | `workflow.step_4.output` |
| 5 | Step 1 预处理与关键帧引用、Step 4 完整输出、用户和源素材、素材目录；素材能力由运行资源注入 | `workflow.step_5.output` |
| 6 | Step 1–5 输出、案例快照、模型能力 | `workflow.step_6.output` |
| 7 | Step 1–6 输出 | `workflow.step_7.output` |

每个 Step 使用的具体子字段和用途写在该 Step 的 Prompt 中，避免本文件随每个业务字段变化而重复维护完整清单。

## 案例快照与任务记录

- `task-result.json` 记录任务状态、采用的案例 ID 和案例快照路径。
- `case-snapshot.json` 保存本次召回的完整候选案例内容。
- 当前草案通过 `artifacts.case_snapshot_path` 定位快照文件，通过 `workflow.step_3.output.case_ids` 标识采用的案例。
- `workflow.step_3.output.case_ids` 是 `candidates` 经 `selected_chain` 对 `case.route_type` 精确过滤后的结果，保持原候选顺序，不触发二次召回或补位。
- `case_snapshot_ref` 是 Step 3 输出中的兼容引用；实际文件定位以 `artifacts.case_snapshot_path` 为准，新逻辑不得只依赖该字段定位文件。

## 状态原则

- 一次任务只维护一份 `task-result.json`。
- 七个 Step 共享该文件，通过 `input_refs` 引用前序结果。
- 尚未执行的 Step 使用 `status: pending` 和 `output: null`。
- Step 开始时递增 `attempt`，并写入 `started_at`。
- Step 成功后使用 `status: completed`，写入结构化 `output` 和 `completed_at`。
- 只有源热点视频缺失或调试模式等待人工模型结果时使用 `needs_input`。固定素材源、自动生图或处理能力不可用时使用 `blocked`；不因未来运行时用户图不存在而暂停。
- 当前恢复只重试当前 Step，不自动清除或回退已完成 Step。
- Step 5 发现素材事实与设计矛盾时使用 `blocked` 和 `design_revision_required`，在 `details` 中记录证据与建议复查的 Step。
- Step 1、2、4、6 的人工文件交换无结果时使用 `needs_input`；人工响应由运行时读取并通过 TaskStore 提交，不能直接写状态文件。

## 跨 Step 约束

1. Step 2 只能在 Step 1 完成后运行。
2. Step 3 只能在 Step 1、2 完成后运行。
3. Step 3 的 `main_retrieval_count` 最大为 1；重试 Step 3 时复用已有任务快照，除非此前召回未成功落盘。
4. Step 3 只选择链路类型，不写节点、模型参数和最终 Prompt。
5. Step 4 必须引用 Step 3 的选择结果和案例快照，只输出节点、模型、依赖和素材规划。
6. Step 4 必须区分 `runtime_inputs`、Agent 管理的固定 `base_materials` 和 `nodes[].outputs`，三类 ID 不得重复。Step 5 只处理 `base_materials`，优先从热点视频提取、加工或自动生成，不要求 `runtime_inputs` 当前存在文件。
   默认复用 Step 1 保存的候选帧；异常定点提取不得覆盖 Step 1 manifest。
7. Step 6 只有在 Step 5 的 `ready_for_prompting` 为 `true` 时才可开始。
8. Step 6 复用 Step 3 的同一案例快照；`coverage_gaps` 只记录历史案例覆盖缺口，当前 MVP 不在 Step 4 或 Step 6 补充召回。
9. Step 7 分别校验运行时输入定义、固定素材文件和节点输出；所有模型节点必须恰好有一个 Prompt，交付主体只展示执行信息，案例与验证证据放入审计附录。
10. 当 Step 3 选择 `multi_image` 时，Step 4–6 按双图有序状态边界执行；选择 `unsupported` 时不进入 Step 4–6，并返回可解释的待人工处理结果。
11. Step 4 在节点方案确定后输出 `appearance_strategy` 和必要的运行时分支；不从主体类别或案例名称直接决定分支。
12. Step 4 判断热点关键帧是否需要成为真实模型输入。需要视觉锚定时，关键帧以 `base_materials` 中 `source.kind: step1_frame` 的固定素材表示，前置生图节点同时引用运行时身份图和该素材；不得只在 Prompt 中描述关键帧内容。
13. Step 5 将上述关键帧从 Step 1 原分辨率文件复制到任务素材目录并验证；Step 6 明确每张输入图的职责。
12. `presentation_type` 首先路由受影响的生图节点；视频节点仅在动作、姿态、服装动态、镜头或验收标准也不同时路由。
13. Step 4 使用 `prompt_routing` 将维度绑定到真正受影响的节点及可解析 `source_ref`；Step 6 为每个可达条件组合输出可独立执行的 `variant`。

这些约束应由 Agent 运行时状态机校验，而不是在 Prompt 中依赖模型自觉遵守。
