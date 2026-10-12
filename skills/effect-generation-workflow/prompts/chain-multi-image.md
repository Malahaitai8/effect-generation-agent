# Step 4：多图驱动链路设计

## 1. 步骤目标

仅当 `workflow.step_3.output.selected_chain == "multi_image"` 时读取。接受 Step 3 结论，不重新选链路。

沿用单图与参考视频设计的公共契约，把两个必须精确控制的有序视觉状态设计为可执行节点。本步骤不准备素材、不执行模型、不编写最终 Prompt。

## 2. 执行边界

- 只落实 Step 3 已通过来源校验的 `control_requirements.must_preserve`，不得从 Step 2 的 `replace`、`adapt` 或 `optional` 新增硬约束。
- `required_image_states` 必须为 `2`，`temporal_reference_required` 必须为 `false`。
- 最终视频节点恰好输入两张图片，不得输入参考视频；三张以上、无明确顺序或混合视频调用返回 `blocked` 并建议复查 Step 3。
- 运行时输入、固定素材和节点输出的职责与另外两种链路完全一致，三类 ID 必须全局唯一。
- `risks` 只记录本步骤新增的节点、模型、接口、输入顺序或素材风险。链路选择、案例覆盖和“失败时改用其他链路”等风险归 Step 3 所有，不得重复记录。

## 3. 输入契约

使用执行器提供的 `source`、Step 1 客观理解、Step 2 卖点与控制信号、Step 3 链路理由与过滤案例、案例快照和模型参考目录。

- `runtime_inputs`：未来运行时由终端用户提供的图片或结构化输入，只定义规格，不检查当前文件。
- `base_materials`：本次方案固定复用、从热点视频提取或自动生成的素材。
- `nodes[].outputs`：未来运行链路产生的状态图和视频，不得重复写入前两类。

两张最终输入可以来自上述任意图片来源组合；方案不要求一定存在运行时用户图或前置生图节点。

## 4. 多图差异规则

1. 先按当前任务定义两个有序状态各自必须控制的内容，再决定图片来源；不得先照搬历史案例节点。
2. 使用语义化 ID 表达顺序和角色，例如 `start_frame`/`end_frame`、`close_frame`/`wide_frame`；不得使用 `image_1`/`image_2`。
3. 最终视频节点的 `inputs` 按起始状态、结束状态排列，并写入 `parameters.input_mode: "first_last_frame"`。
4. 两张图必须能连续过渡。身份、主体数量、画幅、关键物体和场景关系存在冲突时，在上游节点解决；无法解决则 `blocked`。
5. 原始运行时图片只有在其规格已保证目标状态时才能直接进入最终节点；否则先生成相应状态图。
6. 固定首尾图按其他链路的固定素材规则写入 `base_materials`，来源只使用 `source_video`、`step1_frame`、`generated` 或异常业务资产 `business_asset`。
7. 模型只能来自模型目录。案例只证明观察到相似用法；接口、图片顺序、规格或参数未验证时允许完成设计，但必须写入 `risks`。
8. `appearance_strategy`、Prompt 分支和 `prompt_routing.dimensions[]` 完全沿用单图与参考视频规则：`preserve_input` 保留输入外观，`uniform_redesign` 使用所有主体共用的造型，`presentation_specific_redesign` 才建立人物呈现分支；只路由真正受影响的节点。
9. 分支由当前节点方案中真实存在的外观设计差异决定，不从主体类别或案例名称推断。

## 5. 输出契约

输出字段与其他 Step 4 分支一致：

```json
{
  "nodes": [{"id": "generate_video", "role": "从起始状态连续过渡到结束状态", "model": "模型目录中的双图视频候选模型", "model_selection_reason": "历史案例观察到首尾帧用法；真实接口待试跑", "inputs": ["start_frame", "end_frame"], "outputs": ["generated_video"], "dependencies": [], "parameters": {"input_mode": "first_last_frame"}, "prompt_routing": null}],
  "runtime_inputs": [
    {"id": "start_frame", "media_type": "image", "purpose": "提供有序起始状态", "required": true, "requirements": {}},
    {"id": "end_frame", "media_type": "image", "purpose": "提供有序结束状态", "required": true, "requirements": {}}
  ],
  "base_materials": [],
  "unresolved_materials": [],
  "appearance_strategy": {"mode": "preserve_input", "reason": "两个状态沿用输入主体外观", "presentation_sensitive_elements": [], "shared_elements": ["起始状态", "结束状态", "过渡动作"]},
  "prompt_branching": {"required": false, "reason": "没有会改变双图 Prompt 的外观差异", "dimensions": []},
  "risks": ["双图接口、输入顺序和规格仍需真实试跑确认"]
}
```

只允许输出 `nodes`、`runtime_inputs`、`base_materials`、`unresolved_materials`、`appearance_strategy`、`prompt_branching`、`risks`。节点输出不得写入素材列表，不得输出实际运行时图片路径或最终 Prompt。

## 6. 运行状态

- `completed`：两个状态、来源、顺序、节点、模型和素材要求完整，未知接口能力已作为风险记录。
- `blocked`：不满足双图边界、状态无法连续、缺少必需固定素材能力，或现有能力无法形成可执行方案。

## 7. 输出前检查

- 是否严格复用公共三类数据角色、分支和模型规则？
- 最终视频节点是否恰好输入两张图片、没有视频输入，并声明 `first_last_frame`？
- 两张图是否具有明确、语义化且有序的状态角色？
- `required_image_states` 是否为 2，且两个状态都能追溯到输入或上游输出？
- 是否没有因案例中存在某个节点，就为当前任务机械增加该节点？
