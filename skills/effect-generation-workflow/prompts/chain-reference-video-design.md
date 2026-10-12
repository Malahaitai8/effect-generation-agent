# Step 4：参考视频驱动链路设计

## 1. 步骤目标

仅当 `workflow.step_3.output.selected_chain == "reference_video"` 时读取。接受 Step 3 结论，不重新选链路。

设计以热点视频提供连续动作、节奏、镜头或事件顺序的节点链路。本步骤不准备素材、不执行模型、不编写最终 Prompt。

## 2. 执行边界

- 前置：`workflow.step_3.output.selected_chain == "reference_video"`。
- 接受 Step 3 结论，不重选链路或重新召回。
- `risks` 只记录本步骤新增的节点、模型、输入、参考视频或素材风险。链路选择和案例覆盖风险归 Step 3 所有，不得换一种说法重复记录。
- 只落实 Step 3 已通过来源校验的 `control_requirements.must_preserve`；不得从 Step 1 事实或 Step 2 `replace/adapt/optional` 重新派生必保留要求。
- 只定义未来主体图规格，不检查当前用户图姿态或文件。

## 3. 输入契约

使用 `source`、Step 1 的时间线/动作/镜头/交互/关键帧、Step 2 的卖点与控制信号、Step 3 的控制要求与案例，以及模型参考目录。

- 设计师本次提交的热点视频是固定素材来源，写入 `base_materials`。
- 未来特效用户的人物图或宠物图是 `runtime_inputs`，不得判断其实际姿态。
- 生成后的 `subject_image`、`generated_video` 等只是节点输出。

三类 ID 必须全局唯一。

## 4. 执行规则

1. 明确参考视频要传递的连续动作、节奏、表演、镜头和时序。
2. 将热点源视频或明确裁切片段写入 `base_materials`，使用 `source.kind: source_video`。
   其他固定素材只可使用 `step1_frame`、`generated` 或异常业务资产 `business_asset`。
3. 将未来替换主体所需图片写入 `runtime_inputs`，定义可见性、主体数量和身份保持要求。
4. 按“主体输入策略”判断最终视频节点直接引用运行时图片，还是引用前置生图节点的输出。
5. 最终视频节点必须引用参考视频，需要主体时同时引用运行时输入或上游节点输出。
6. `unresolved_materials` 只记录 Agent 无法自动提取、加工或生成的能力缺口，不记录未来用户图。
7. 遮挡、多主体、身体结构差异、快速运镜和复杂交互写入 `risks`。
8. 若前置主体图还要预建参考视频中的精确起始姿态、景别、场景、道具或空间关系，选择一张 Step 1 `keep_for_downstream: true` 的关键帧作为固定视觉参考，让前置生图节点同时输入用户图和该关键帧。用户图负责身份，热点帧负责视觉状态；最终视频节点仍输入生成图与参考视频，因此链路仍是 `reference_video`。该前置节点必须选择模型目录中 `supports_multi_reference_images: true` 的图片模型；该字段为 `false` 或缺失时不得用于双图节点，也不能仅以风险说明代替输入能力。
9. 节点方案确定后，必须选择 `appearance_strategy.mode`：`preserve_input` 保持输入外观，`uniform_redesign` 设计所有主体共用的造型，`presentation_specific_redesign` 设计需要按 `female/male` 分别表达的造型。只有 Step 2 `preserve` 中的外观约束或设计师明确要求才算“保留原造型”，`adapt` 绝不能作为该依据。非人物呈现或真正共用的目标造型选择统一重设计；Step 1 将人物造型列为整体视觉的一部分且 Step 2 未将其列为 `optional` 时，前置节点必须处理该造型并默认按人物呈现分别重设计；没有主动外观设计时才保留输入。动作相同不影响首帧分支，视频节点仍可共用。不能按案例名称或零散关键词选择，也不能声明保持输入却在 Prompt 中指定新造型；只有新背景而无角色造型要求不足以触发重设计。
10. 只有 `mode == presentation_specific_redesign` 时建立 `presentation_type = female/male` 并列出敏感元素；其他模式不得建立该分支且敏感元素必须为空。
11. 建立分支时使用 `prompt_routing.dimensions[]`。直接从用户图判断时，`source_ref` 引用对应运行时图片 ID；只有确实增加分类节点时才引用其已声明输出。将该路由只绑定到真正受影响的模型节点。
12. 最终视频节点仅在不同呈现类型会改变动作、姿态、服装动态、镜头表达或验收标准时路由；如果参考视频负责相同动作和时序、主体图已承载造型，则视频 Prompt 共用。
13. 无分支节点写入 `prompt_routing: null`，并采用与 `appearance_strategy` 一致的中性或输入保持方案。

### 4.1 主体输入策略

按以下顺序完成判断：

1. 按 Step 2 `replication_goal` 的 ID 和 Step 3 `source_refs` 落实目标主体的保留、替换和适配边界；不得把源视频主体的年龄、物种、性别、服装或角色造型自动当作目标要求。
2. 明确最终视频节点的主体图片只需提供“身份参考”，还是必须在视频开始前“预先建立目标视觉状态”。
3. 若图片只承担人物身份、宠物身份、脸型、毛色或品种参考，最终视频节点直接引用 `user_image` 或 `user_pet_image`。
4. 若 Step 2 已确认视频开始前必须建立特定造型、服装、关键道具、姿态、景别、身体可见范围或主体与场景的初始关系，设计前置生图节点，输出 `subject_image` 供最终视频节点使用。
5. “让画面更精致”“提供更多创意选择”或没有具体控制对象的“提高稳定性”不能作为增加生图节点的理由。
6. 模型能力不明确、又不存在必须预建的视觉状态时，默认直接使用运行时图片，并在 `risks` 记录待真实试跑的能力缺口，不无依据加重链路。
7. 存在前置生图节点时，其 `role` 和 `model_selection_reason` 必须说明它补充了哪些最终视频节点必需条件；不能只写“标准化”或“优化图片”。

历史案例只能用于核验模型是否观察到相应用法，不能替代当前 Step 2 的复刻目标。案例中曾先生图，不代表当前任务也必须先生图。

## 5. 输出契约

```json
{
  "nodes": [{"id": "generate_video", "role": "使用热点视频的动作与镜头替换主体", "model": "模型目录中的 display_name", "model_selection_reason": "案例中观察到参考视频主体替换用途，接口待确认", "inputs": ["reference_video", "user_image"], "outputs": ["generated_video"], "dependencies": [], "parameters": {}, "prompt_routing": null}],
  "runtime_inputs": [{"id": "user_image", "media_type": "image", "purpose": "提供未来特效用户的主体身份", "required": true, "requirements": {"single_subject": true, "subject_clear": true}}],
  "base_materials": [{"id": "reference_video", "purpose": "提供热点动作、节奏和镜头时序", "required": true, "requirements": {"source": {"kind": "source_video"}, "operation": "direct", "target": {"media_type": "video", "format": "mov"}}}],
  "unresolved_materials": [],
  "appearance_strategy": {"mode": "preserve_input", "reason": "运行时图片只提供身份，视频模型负责替换并保持输入外观", "presentation_sensitive_elements": [], "shared_elements": ["动作", "镜头", "时序", "场景"]},
  "prompt_branching": {"required": false, "reason": "当前节点不主动设计会随人物呈现变化的外观", "dimensions": []},
  "risks": []
}
```

只允许输出 `nodes`、`runtime_inputs`、`base_materials`、`unresolved_materials`、`appearance_strategy`、`prompt_branching`、`risks`。对主体标准化变体，上游节点引用 `user_image` 并输出 `subject_image`；`subject_image` 不得写入 `base_materials`。

## 6. 运行状态

- `completed`：参考视频固定素材、主体运行时槽位、节点和模型完整。
- `blocked`：最终模型无法接收参考视频、Agent 缺少固定素材能力，或链路边界与 Step 3 冲突。

## 7. 输出示例

### 7.1 只需要身份参考

```json
{
  "nodes": [
    {
      "id": "generate_video",
      "role": "使用参考视频的动作、镜头和时序替换主体身份",
      "model": "支持参考视频与主体图片输入的候选模型",
      "model_selection_reason": "历史能力记录包含参考视频主体替换；当前图片只承担身份参考",
      "inputs": ["reference_video", "user_image"],
      "outputs": ["generated_video"],
      "dependencies": [],
      "parameters": {},
      "prompt_routing": null
    }
  ],
  "runtime_inputs": [{"id": "user_image", "media_type": "image", "purpose": "提供运行时主体身份", "required": true, "requirements": {"single_subject": true, "subject_clear": true}}],
  "base_materials": [{"id": "reference_video", "purpose": "提供连续动作、镜头和时序", "required": true, "requirements": {"source": {"kind": "source_video"}, "operation": "direct", "target": {"media_type": "video", "format": "mov"}}}],
  "unresolved_materials": [],
  "appearance_strategy": {"mode": "preserve_input", "reason": "用户图只承担身份参考并保持输入外观", "presentation_sensitive_elements": [], "shared_elements": ["动作", "镜头", "时序", "场景"]},
  "prompt_branching": {"required": false, "reason": "没有主动设计可变外观", "dimensions": []},
  "risks": []
}
```

### 7.2 必须预建目标视觉状态

```json
{
  "nodes": [
    {
      "id": "prepare_subject_image",
      "role": "建立 Step 2 已确认的目标造型、身体可见范围和关键道具起始关系",
      "model": "支持身份参考与目标状态生成的候选图片模型",
      "model_selection_reason": "最终视频开始前必须具备指定视觉状态，不能只把原始用户图当身份参考",
      "inputs": ["user_image"],
      "outputs": ["subject_image"],
      "dependencies": [],
      "parameters": {},
      "prompt_routing": null
    },
    {
      "id": "generate_video",
      "role": "保持已建立的主体状态并继承参考视频的动作、镜头和时序",
      "model": "支持参考视频与主体图片输入的候选模型",
      "model_selection_reason": "参考视频负责连续过程，subject_image 负责身份与已确认的起始视觉状态",
      "inputs": ["reference_video", "subject_image"],
      "outputs": ["generated_video"],
      "dependencies": ["prepare_subject_image"],
      "parameters": {},
      "prompt_routing": null
    }
  ],
  "runtime_inputs": [{"id": "user_image", "media_type": "image", "purpose": "提供运行时主体身份", "required": true, "requirements": {"single_subject": true, "subject_clear": true}}],
  "base_materials": [{"id": "reference_video", "purpose": "提供连续动作、镜头和时序", "required": true, "requirements": {"source": {"kind": "source_video"}, "operation": "direct", "target": {"media_type": "video", "format": "mov"}}}],
  "unresolved_materials": [],
  "appearance_strategy": {"mode": "uniform_redesign", "reason": "预建所有主体共用的统一目标状态", "presentation_sensitive_elements": [], "shared_elements": ["主体状态", "动作", "镜头", "时序"]},
  "prompt_branching": {"required": false, "reason": "预建状态对所有主体共用", "dimensions": []},
  "risks": []
}
```

需裁片时，`reference_video` 仍是固定素材，并在要求中明确 `clip`。

人物呈现分支的路由格式与单图设计一致：分类节点输出 `presentation_type`，受影响节点使用 `prompt_routing.dimensions[]`，每项完整填写 `dimension_id`、`source_ref` 和 `values`。同时完整输出 `appearance_strategy` 和 `prompt_branching`。不得使用单数 `dimension` 简写；无模型节点的 `model_selection_reason` 也必须是字符串。

## 8. 输出前检查

- 最终视频节点是否实际引用连续参考视频？
- 未来主体图是否只定义为 `runtime_inputs`？
- 是否先区分了“身份参考”和“预先建立目标视觉状态”，并为前置生图给出明确、必要的控制条件？
- 是否避免从源视频主体外观或笼统稳定性担忧推导出不必要的生图节点？
- 节点输出是否没有重复写入 `base_materials`？
- 遮挡、多主体、身体结构、快速运镜和互动风险是否已记录？
- `appearance_strategy` 与 `prompt_branching` 是否一致，人物呈现分支是否只作用于实际受影响节点？
