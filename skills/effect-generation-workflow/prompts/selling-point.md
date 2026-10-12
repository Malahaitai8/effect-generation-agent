# Step 2：卖点与复刻目标判断

## 1. 步骤目标

1. 基于 Step 1 事实判断视频最有辨识度的核心体验。
2. 选择主卖点，仅在影响复刻时保留次卖点。
3. 把卖点转化为替换、保留、适配和可选内容。
4. 输出供 Step 3/4 使用的控制信号和外观边界，但不选链路、设计节点或提前决定 Prompt 分支。

## 2. 执行边界

- 前置：`workflow.step_1.status == "completed"`，且 Step 1 输出通过 Schema。
- 只基于 Step 1 已记录的视频事实做卖点和复刻目标判断，不悄然重写 Step 1。
- 不选择链路、模型、参数或节点，不把卖点标签固定绑定链路。
- 缺少会改变卖点的事实时停止并建议复查 Step 1，当前不自动回退。

## 3. 输入契约

执行器从 `StepContext.inputs["workflow.step_1.output"]` 提供已经校验的 Step 1 结果。Step 2 只读取该对象：

1. `content_summary`、`narrative_structure` 和 `timeline`：用于理解完整创意和事件顺序。
2. `observations`：用于判断状态、动作、互动、构图、文字和音频事实。
3. `key_frames`：只作为已有事件和状态的可视证据，不用静态帧重新解释连续叙事。
4. `uncertainties`：判断结论必须保留的证据边界。

当不同信息之间存在冲突时，以完整时间线和直接观察事实为准。Step 2 不重新观看原视频后悄然修改 Step 1。

## 4. 执行规则

### 4.1 生成候选卖点并做删除测试

- 用自然语言提出一到三个候选核心体验。
- 每个候选必须引用 `timeline[].event_id`；存在对应关键帧时，同时引用 `key_frames[].frame_id`。
- 删除测试：删除该元素、过程或结构后，视频是否仍保留同一创意和辨识度？

### 4.2 选择主次卖点

- 删除后创意不再成立的候选优先作为主卖点。
- 删除后主创意仍成立、但复刻质量明显下降的可作为次卖点。
- 主卖点必须是一句可独立理解的自然语言；次卖点可为空。
- 两个解释证据接近时，将次选项保存到 `alternative_interpretations`，不伪造确定性。

### 4.3 拆分复刻目标和控制信号

- 先区分“源视频中观察到的主体属性”和“复刻后目标主体必须具备的属性”。源主体的年龄、物种、性别、服装、发型和角色形态只是观察事实，不自动成为复刻要求。
- 只有删除测试证明某项主体属性属于核心卖点、动作成立条件，或当前产品要求已经明确指定时，才要求目标主体继承；否则允许随未来运行时主体自然适配。
- `replace`：需要由未来运行时主体、外观、文字或其他内容替换的对象。
- `preserve`：不保留就会破坏卖点的状态、过程、互动、镜头、文字、场景、音频或必要主体属性。
- `adapt`：应随运行时主体或上下文调整、但不改变核心创意的外观和身体属性。
- `optional`：源视频中存在但不影响卖点，可删除或留待实测的装饰性内容。
- `control_signals` 记录必须精确保留的画面状态、连续过程、物理互动、镜头、文字和音频要求。
- 无法从卖点、动作条件或当前产品要求确认目标主体是否必须年龄化、宠物化或采用特定造型时，将问题写入 `uncertainties`，不得把未确认属性写入 `preserve`。

### 4.4 使用开放卖点标签

标签只用于检索和统计，不代替自然语言卖点，也不与执行链路固定绑定。优先复用已有标签；现有标签无法表达决定性内容时，可新增简短、稳定的 `snake_case` 标签。

初始词表：`identity_or_character_transformation`、`pet_anthropomorphism`、`style_transformation`、`scene_spectacle`、`effect_spectacle`、`state_transformation`、`prop_or_superpower`、`action_performance`、`physical_interaction`、`reveal_or_micro_narrative`、`text_or_symbol_reveal`、`festival_or_ritual`、`camera_or_composition`、`audio_visual_sync`。

只保留会改变案例检索或生产约束的标签。

### 4.5 记录主体外观边界

Step 2 只判断热点内容要求保留、替换、适配或可选的外观属性，不预测生产方案会不会重新设计服装、发型或角色造型。

- 源视频出现的年龄、物种、性别、服装和发型只是观察事实；只有核心卖点依赖时才进入 `preserve`。
- 允许运行时主体自然变化的外观写入 `adapt`。
- 无法从热点内容确定的产品设计选择写入 `uncertainties`，不提前建立 Prompt 分支。
- `appearance_strategy`、Prompt 分支和节点路由由 Step 4 在实际设计方案时决定。

## 5. 输出契约

只返回下列业务 JSON；执行器将其作为 `StepResult.output` 提交，运行时负责状态与 Schema 校验：

```json
{
  "primary_selling_point": {
    "description": "",
    "tags": [],
    "evidence_event_ids": [],
    "evidence_frame_ids": [],
    "removal_test": "",
    "confidence": 0.0
  },
  "secondary_selling_points": [],
  "replication_goal": {
    "replace": [{"id": "source_subject", "description": "原视频的具体主体由运行时用户主体替换"}],
    "preserve": [{"id": "noodle_sneeze_reversal", "description": "吸面、喷嚏到鼻孔出现面条的连续反转"}],
    "adapt": [{"id": "subject_age_and_form", "description": "年龄、物种和身体形态随运行时主体自然适配"}],
    "optional": [{"id": "background_decoration", "description": "不影响反转的背景装饰"}]
  },
  "control_signals": {
    "critical_visual_states": [],
    "continuous_processes": [],
    "physical_interactions": [],
    "camera_requirements": [],
    "text_requirements": [],
    "audio_requirements": []
  },
  "alternative_interpretations": [],
  "uncertainties": []
}
```

字段类型必须严格遵守：

- `alternative_interpretations` 是“完整卖点对象”数组；每项必须和 `primary_selling_point` 使用相同结构，包含 `description`、`tags`、`evidence_event_ids`、`evidence_frame_ids`、`removal_test` 和 `confidence`。如果无法形成完整候选卖点，返回空数组，不要输出简化说明对象。
- `uncertainties` 是字符串数组，例如 `["飘落物可能是花瓣或心形粒子，但不影响核心卖点"]`；不得输出 `{ "description": "..." }` 等对象。
- `replication_goal` 的四个子字段均为约束对象数组，每项必须包含稳定的 `id` 和自洽的 `description`；`id` 在四类中全局唯一，只使用小写英文、数字和下划线。
- `control_signals` 的各子字段仍为字符串数组。
- 不得改变字段类型，也不得增加输出契约之外的字段。

### 输出限制

- 不重写 Step 1 事实，不使用无对应事件或关键帧的虚构证据。
- 不选择链路、模型、参数或生产节点。
- 不把卖点标签与链路绑定，例如不因为主体是宠物就直接选参考视频驱动。
- 不为了符合格式强制生成次卖点或性别分支。
- `alternative_interpretations` 中的每一项必须是完整卖点对象；`uncertainties` 中的每一项必须是字符串。两者不得混用 Step 1 的不确定性对象结构。
- 不将外观推断写成用户自述或身份事实。
- 不因源视频演员或动物呈现出某种年龄、物种、性别、服装或角色造型，就默认要求未来运行时主体继承。
- 每个需要下游执行的核心要求都要在 `replication_goal` 中有唯一 ID；后续 Step 只能引用这些 ID，不得换个说法重新定义复刻目标。

## 6. 运行状态

- `completed`：主卖点、复刻目标、控制信号和证据引用完整，业务 JSON 通过 Schema。
- `blocked`：Step 1 事实不足以支持卖点判断；记录 `observation_revision_required` 及所缺事实。
- `failed`：不可恢复的执行器或保存错误。

## 7. 输出示例

生日车窗视频的简化主卖点：

```json
{
  "description": "车窗升降依次揭示 Happy、人物吹蜡烛和 Birthday，组成完整的生日祝福",
  "tags": ["reveal_or_micro_narrative", "state_transformation", "physical_interaction", "text_or_symbol_reveal"],
  "evidence_event_ids": ["evt_001", "evt_002", "evt_003", "evt_004"],
  "evidence_frame_ids": ["frame_0001", "frame_0008", "frame_0012", "frame_0018"],
  "removal_test": "如果删除车窗升降和前后文字揭示，只保留吹蜡烛，原视频的分段生日祝福创意不再成立",
  "confidence": 0.9
}
```

## 8. 输出前检查

- 主卖点是自然语言结论，而不是单一标签吗？
- 每个卖点都有真实 `event_id`、可用时有真实 `frame_id`，并完成删除测试吗？
- 复刻目标是否区分替换、保留、适配和可选内容？
- 是否区分了源视频主体属性与复刻后目标主体属性，并为必须继承的属性提供卖点、动作条件或产品要求证据？
- 输出中是否没有链路、模型、节点或最终 Prompt？
