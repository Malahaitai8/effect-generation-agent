# Step 6：参考视频驱动节点 Prompt

## 目标与边界

仅当链路为 `reference_video`、Step 4 已完成且 Step 5 `ready_for_prompting == true` 时读取。为 Step 4 中每个有 `model` 的生成节点输出可直接执行的 Prompt；确定性节点不输出。

节点输入以 Step 4 `nodes[].inputs` 为唯一事实源。不重新选链路、不新增节点、不重复召回。

## 规则

1. 每个模型节点恰好输出一个 `node_prompt`，模型名与 Step 4 一致。
2. Step 4 最终视频节点直接引用运行时图片时，视频 Prompt 明确运行时图片只负责主体身份，参考视频负责动作、节奏、镜头和事件顺序。
3. Step 4 存在前置生图节点时，生图 Prompt 只建立该节点声明的必要目标视觉状态；视频 Prompt 使用 `subject_image` 保持身份和已建立外观，使用参考视频传递连续过程。
4. 不从源视频自动继承年龄、物种、性别、服装或角色形态；只有 Step 4 节点职责已落实一条经过来源校验的 Step 3 `must_preserve` 时才能写入 Prompt。
5. 节点输入与职责以 Step 4 为准，不得绕过 Step 4 自行增加、删除或合并生图节点。
6. 无路由节点只输出一个 `default`；有路由节点为每个可达条件组合输出完整 Prompt。
7. 遮挡前后身份一致、唯一替换目标等限制直接写入 Prompt。
8. 必需的生成限制直接写入主 Prompt。每个变体只输出一段完整 `prompt`；身份保持、参考视频职责、禁止漂移、避免穿模和镜头限制等排除性约束写在同一段 Prompt 中，不得另建 `negative_prompt` 或“反向提示词”字段。
9. 案例依据集中写入 `prompt_audit`，不参与模型调用。
10. `presentation_type` 路由存在时，前置生图节点按 `female`、`male` 分别落实 Step 4 要求的造型；最终视频节点只有自身也声明该路由时才拆分变体。
11. 最终视频节点不路由 `presentation_type` 时，使用“主体”“保持 subject_image 已建立的外观”等中性表达，由参考视频传递共用动作与时序，不重复描述男女造型。
12. Step 4 没有呈现分支时，不得在 Prompt 中擅自增加只适用于单一性别的服装、发型、身体呈现或角色称谓；发现冲突时返回 `blocked`。
13. 前置生图节点同时输入用户图与热点关键帧时，明确用户图负责身份，关键帧负责起始姿态、景别、场景、道具和空间关系；生成图中只保留目标主体，不得复制热点原主体或生成双主体。后续参考视频仍只负责连续动作、镜头和时序。

## 输出

```json
{
  "node_prompts": [{"node_id": "generate_video", "model": "与 Step 4 一致的模型名", "variants": [{"variant_id": "default", "conditions": {}, "prompt": "按参考视频传递动作、节奏和镜头，将目标主体替换为运行时主体，并在遮挡前后保持身份一致。"}]}],
  "prompt_audit": [{"node_id": "generate_video", "case_refs": [], "notes": []}],
  "case_snapshot_ref": "outputs/<task-id>/case-snapshot.json",
  "coverage_gaps": []
}
```

历史案例 Prompt 只用于学习结构、控制方式和表达经验，不得整段复制，不得引入当前 Step 2/4 没有的主体、道具、场景、动作或特效。`prompt_audit.notes` 不得声称“直接复用”完整案例 Prompt。

`semantic_validation` 由运行时在生成、确定性防复制检查和独立语义复核后追加，本 Prompt 不得自行输出或伪造通过结果。

`completed` 表示所有模型节点的 Prompt 与必需变体完整；否则返回 `blocked`。

输出前确认：`node_prompts[].node_id` 与 Step 4 所有模型节点一一对应；若 Step 4 只有最终视频节点，不得额外生成主体生图 Prompt；若 Step 4 含前置生图节点，两类节点必须分别输出 Prompt。
