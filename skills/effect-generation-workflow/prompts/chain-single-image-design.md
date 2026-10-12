# Step 4：单图驱动链路设计

## 1. 步骤目标

仅当 `workflow.step_3.output.selected_chain == "single_image"` 时读取。接受 Step 3 结论，不重新选链路。

把热点视频的卖点设计为可执行节点，确定模型、输入输出、依赖、基础参数、运行时输入和固定素材。本步骤不准备素材、不执行模型、不编写最终 Prompt。

## 2. 执行边界

- 前置：`workflow.step_3.output.selected_chain == "single_image"`。
- 接受 Step 3 结论，不重新选链路或召回案例。
- `risks` 只记录本步骤新增的节点、模型、输入或素材风险。链路选择、案例覆盖和“失败时改用其他链路”等风险归 Step 3 所有，不得换一种说法重复记录。
- 只落实 Step 3 已通过来源校验的 `control_requirements.must_preserve`；不得从 Step 1 事实或 Step 2 `replace/adapt/optional` 重新派生必保留要求。
- 只定义未来运行时输入规格，不检查当前用户图内容或文件。

## 3. 输入契约

执行器提供 `source`、Step 1 的客观理解/时间线/关键帧、Step 2 的卖点与控制信号、Step 3 的链路理由与案例、案例快照和模型参考目录。

热点视频是当前设计任务的输入。未来使用特效时才提供的人物图、宠物图等不在 `source.metadata.materials` 中查找，必须定义为 `runtime_inputs`。

### 三类数据角色

- `runtime_inputs`：未来特效运行时由终端用户提供的输入槽位，只定义类型、用途和规格。
- `base_materials`：本次方案固定复用、由 Agent 从热点视频提取、加工或生成的素材。正常流程不要求设计师补充视频以外的素材。
- `nodes[].outputs`：未来执行链路时的节点产物，不得重复写入前两类。

三类 ID 必须全局唯一。

## 4. 执行规则

1. 根据目标效果定义未来需要的用户图输入槽位，不得声称已检查其实际内容。
2. 用户图可直接作为最终视频图片输入时，最终节点直接引用该 `runtime_input`。
3. 需要换装、换景、姿态或构图标准化时，设计上游生图节点，其输出才是最终视频节点的唯一图片输入。
4. 最终视频节点必须恰好引用一张图片，不得引用参考视频。
   - 运行时 `user_image` 只保证提供主体身份和已声明的基础可见性，不得假设它已经包含热点所需的姿态、道具、场景、构图或特效。
   - 若核心起始画面需要用户图未保证存在的姿态、道具、场景关系或构图，必须先设计生图/图像处理节点生成 `first_frame`，最终视频节点不得直接使用 `user_image`。
   - 只有核心视频能从任意符合 `runtime_inputs[].requirements` 的用户图直接开始，且无需预建道具、场景、姿态或构图时，才能使用 `user_image → generate_video`。
5. 只把节点之外的固定素材写入 `base_materials`；`first_frame`、`subject_image` 等节点输出不是基础素材。
   固定素材的 `source.kind` 只使用 `source_video`、`step1_frame`、`generated` 或异常业务资产 `business_asset`。
6. 模型只能来自模型参考目录；选择理由必须区分案例观察与已验证能力。节点同时接收两张或更多参考图片时，所选模型必须在目录中明确标记 `supports_multi_reference_images: true`；不能用风险说明代替这一输入能力。
7. `unresolved_materials` 只记录 Agent 暂时无法自动获得的固定素材能力缺口，不用于向设计师索要普通参考图。
8. 判断首帧是否需要热点视觉锚点：如果核心画面依赖较精确的场景、构图、主体姿态、景别、复杂道具或空间关系，且 Step 1 有可用关键帧，必须选择一张 `keep_for_downstream: true` 的原分辨率帧写入 `base_materials`，并让首帧节点同时输入运行时用户图和该固定参考图。用户图负责身份，热点帧负责场景、构图、状态与道具关系。简单背景或允许自由创作时可以只输入用户图。这里的双图发生在前置生图节点，不改变最终视频节点的 `single_image` 分类。
9. 节点方案确定后，必须从三种外观模式中选择一种并输出 `appearance_strategy.mode`：
   - `preserve_input`：保持运行时主体原有服装、发型、饰品和身体呈现，Prompt 不得另行指定这些内容；
   - `uniform_redesign`：主动设计所有主体共用的造型，设计不依赖人物呈现类型；
   - `presentation_specific_redesign`：主动设计的服装、发型、饰品或身体呈现需要按 `female/male` 分别表达。
   按以下顺序选择，不得依据案例名称或零散关键词：
   1. 只有 Step 2 `replication_goal.preserve` 中明确引用原穿搭/造型，或设计师明确要求保留时，才视为“要求保留原造型”；`adapt` 表示允许随运行时主体调整，绝不能据此声称 Step 2 要求保留。节点只是换脸/身份替换且不负责重建外观时，也选择 `preserve_input`；
   2. 目标角色不是人物呈现，或目标造型对所有允许主体确实完全相同，选择 `uniform_redesign`；
   3. Step 1 明确把主体服装、发型、饰品或身体呈现记录为整体视觉风格的一部分，且 Step 2 没有将其列为 `optional` 时，首帧方案必须处理这套角色造型；目标角色是人物呈现时默认选择 `presentation_specific_redesign`。动作完全相同不改变这个结论，视频节点仍可共用；
   4. 没有主动设计主体外观时才选择 `preserve_input`。
   不能一边声明保留输入外观，一边在下游 Prompt 指定新造型。只有新背景而没有角色造型要求，不足以触发重设计。
10. 只有 `mode == presentation_specific_redesign` 时建立 `presentation_type = female/male` 分支，并列出 `presentation_sensitive_elements`；其他模式该数组必须为空。
11. 建立分支时，在真正受影响的模型节点上写入 `prompt_routing`。直接从用户图判断时，`dimension_id` 写 `presentation_type`、`source_ref` 写 `user_image`；只有确实增加独立分类节点时才引用其输出。`source_ref` 必须引用已定义的运行时输入 ID 或上游节点输出 ID。
12. 视频节点只有在不同呈现类型会改变动作、姿态、服装动态、镜头表达或验收标准时才路由；若只需保持上游首帧造型，使用共用视频 Prompt。
13. 无分支节点写入 `prompt_routing: null`，并采用与 `appearance_strategy` 一致的中性或输入保持方案。

## 5. 输出契约

```json
{
  "nodes": [{"id": "generate_video", "role": "基于单张用户图生成目标视频", "model": "模型目录中的 display_name", "model_selection_reason": "案例观察与待确认能力", "inputs": ["user_image"], "outputs": ["generated_video"], "dependencies": [], "parameters": {"aspect_ratio": "9:16"}, "prompt_routing": null}],
  "runtime_inputs": [{"id": "user_image", "media_type": "image", "purpose": "提供未来特效用户的主体身份", "required": true, "requirements": {"subject_clear": true}}],
  "base_materials": [],
  "unresolved_materials": [],
  "appearance_strategy": {"mode": "preserve_input", "reason": "保留输入主体外观", "presentation_sensitive_elements": [], "shared_elements": ["动作", "镜头", "场景", "特效"]},
  "prompt_branching": {"required": false, "reason": "没有会随人物呈现产生实质差异的设计元素", "dimensions": []},
  "risks": []
}
```

`nodes`、`runtime_inputs`、`base_materials`、`unresolved_materials`、`appearance_strategy`、`prompt_branching`、`risks` 均为必填。不得输出素材状态、实际用户图路径或最终 Prompt。

### 变体：需要前置生图

`generate_first_frame` 引用 `user_image` 并输出 `first_frame`；`generate_video` 只引用 `first_frame` 并依赖前者。`first_frame` 只是节点输出，不得写入 `base_materials`。

若首帧需要热点视觉锚点，则将关键帧作为真实模型输入，而不是只在 Prompt 中描述：

```json
{
  "base_materials": [{
    "id": "hotspot_visual_reference",
    "purpose": "提供热点场景、构图、姿态、道具和空间关系参考",
    "required": true,
    "requirements": {
      "source": {"kind": "step1_frame", "frame_id": "来自 Step 1 的 frame_id"},
      "operation": "direct",
      "target": {"media_type": "image"},
      "reference_role": "scene_composition_and_state"
    }
  }],
  "nodes": [{"id": "generate_first_frame", "inputs": ["user_image", "hotspot_visual_reference"]}]
}
```

上例只展示相关字段，实际输出仍需提供完整节点。必须选择模型目录中 `supports_multi_reference_images: true` 的图片模型，并使用其 `display_name`。该字段为 `false` 或缺失的模型不能用于同时输入用户图与热点参考帧；不能只写入 `risks` 后继续提交，也不得静默删掉参考图。

### 变体：人物呈现类型只影响首帧

路由字段必须使用完整结构，不能写成 `{ "dimension": ..., "source_ref": ... }` 简写。无模型的分类节点仍必须将 `model_selection_reason` 写为字符串。

```json
{
  "nodes": [
    {
      "id": "classify_presentation",
      "role": "从运行时人物图得到人物呈现类型",
      "model": null,
      "model_selection_reason": "运行时属性理解节点，不调用生成模型",
      "inputs": ["user_image"],
      "outputs": ["presentation_type"],
      "dependencies": [],
      "parameters": {},
      "prompt_routing": null
    },
    {
      "id": "generate_first_frame",
      "role": "按人物呈现类型设计服装、发型和角色造型并生成首帧",
      "model": "模型目录中的图片模型",
      "model_selection_reason": "案例观察与待确认能力",
      "inputs": ["user_image", "presentation_type"],
      "outputs": ["first_frame"],
      "dependencies": ["classify_presentation"],
      "parameters": {},
      "prompt_routing": {
        "dimensions": [
          {
            "dimension_id": "presentation_type",
            "source_ref": "presentation_type",
            "values": ["female", "male"]
          }
        ]
      }
    },
    {
      "id": "generate_video",
      "role": "保持首帧已建立的造型并生成男女共用动作",
      "model": "模型目录中的视频模型",
      "model_selection_reason": "案例观察与待确认能力",
      "inputs": ["first_frame"],
      "outputs": ["generated_video"],
      "dependencies": ["generate_first_frame"],
      "parameters": {},
      "prompt_routing": null
    }
  ],
  "appearance_strategy": {"mode": "presentation_specific_redesign", "reason": "首帧方案主动设计人物造型，且具体呈现需要分别表达", "presentation_sensitive_elements": ["服装剪裁", "发型", "饰品"], "shared_elements": ["动作", "镜头", "场景", "道具", "特效时序"]},
  "prompt_branching": {"required": true, "reason": "服装、发型和饰品需要不同的完整生图 Prompt", "dimensions": [{"id": "presentation_type", "purpose": "路由人物呈现设计", "values": ["female", "male"], "affected_stages": ["image_generation"]}]}
}
```

## 6. 运行状态

- `completed`：节点图、三类 ID、模型与素材要求完整。
- `blocked`：Agent 缺少必需的固定素材能力，或现有能力无法构成符合单图边界的链路。

## 7. 输出示例

- 直接单图视频：`user_image → generate_video`，无固定素材。
- 前置首帧生成：`user_image → generate_first_frame → first_frame → generate_video`。
- 若最终节点必须接收参考视频，返回 `blocked` 并请求复查 Step 3。

## 8. 输出前检查

- 最终视频节点是否恰好引用一个图片输入，且不引用参考视频？
- 是否错把任意用户身份图当成了已具备热点姿态、道具、场景和构图的首帧？
- 三类 ID 是否唯一，节点输入和依赖是否可解析？
- 是否没有输出实际用户图路径、素材状态或最终 Prompt？
- `appearance_strategy` 与 `prompt_branching` 是否一致，人物造型分支是否只路由到真正受影响的节点？
