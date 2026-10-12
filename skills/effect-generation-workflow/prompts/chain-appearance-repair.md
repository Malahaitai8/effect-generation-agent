# Step 4 外观策略修正

根据 `validation_issues` 修正 Step 4 业务 JSON。保持 Step 3 的链路类型、核心控制要求和无关节点设计不变，只修正外观模式、必要的分类节点、节点路由、分支声明及相应职责。

`required_appearance_mode` 是运行时根据已冻结事实计算出的唯一目标模式，必须严格采用，不得重新解释或改写事实。

当 `hotspot_visual_anchor_required == true` 时，必须从 Step 1 `key_frames` 选择一张 `keep_for_downstream: true` 的原分辨率关键帧作为固定参考素材，并让首帧生图节点同时输入运行时用户图和该素材。用户图负责身份，热点帧负责场景、构图、姿态、景别、道具和空间关系。

- `adapt` 不是保留原造型的依据。
- Step 1 已将主体造型列入整体视觉且 Step 2 未将其列为 `optional` 时，不得修复为 `preserve_input`。
- `preserve_input` 不得主动指定新造型。
- `uniform_redesign` 只能用于所有允许主体真正共用的造型。
- 人物呈现且主动设计主题造型时使用 `presentation_specific_redesign`，只让受影响的首帧/生图节点分支；共用动作的视频节点保持不分支。
- `prompt_branching.dimensions` 只接受完整对象数组，不接受字符串或节点简写。人物呈现分支必须写成：

```json
{
  "required": true,
  "reason": "说明为何需要完整人物呈现变体",
  "dimensions": [
    {
      "id": "presentation_type",
      "purpose": "路由人物呈现设计",
      "values": ["female", "male"],
      "affected_stages": ["image_generation"]
    }
  ]
}
```

- 若运行时从用户图判断呈现类型，受影响节点的 `prompt_routing` 必须为 `{"dimensions":[{"dimension_id":"presentation_type","source_ref":"user_image","values":["female","male"]}]}`。只有确实另设分类节点时，`source_ref` 才能引用该节点已声明的输出；不得引用没有来源的 `presentation_type`。共用节点写 `prompt_routing: null`。
- 输出必须完整符合原 Step 4 输出契约，不要输出解释、复核状态或 Markdown。

热点关键帧固定素材使用以下结构；`frame_id` 必须来自 Step 1：

```json
{
  "id": "hotspot_visual_reference",
  "purpose": "为首帧生成提供热点场景、构图、姿态、道具和空间关系参考",
  "required": true,
  "requirements": {
    "source": {"kind": "step1_frame", "frame_id": "frame_0001"},
    "operation": "direct",
    "target": {"media_type": "image"},
    "reference_role": "scene_composition_and_state"
  }
}
```

首帧节点的 `inputs` 必须同时包含运行时用户图 ID 和 `hotspot_visual_reference`。该节点必须选择模型目录中 `supports_multi_reference_images: true` 的图片模型；当前目录中若存在满足条件的模型，不得继续选择该字段为 `false`、缺失或能力未知的模型，也不能仅在 `risks` 中说明后继续提交。模型名称必须使用目录中的 `display_name`。只有目录中完全没有满足条件的模型时，才保留能力缺口并让本步骤阻塞，不得静默删掉参考图。
