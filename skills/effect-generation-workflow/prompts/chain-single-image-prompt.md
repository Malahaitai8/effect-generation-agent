# Step 6：单图驱动节点 Prompt

## 目标与边界

仅当链路为 `single_image`、Step 4 已完成且 Step 5 `ready_for_prompting == true` 时读取。为 Step 4 中每个有 `model` 的生成节点输出可直接执行的 Prompt；确定性节点不输出。

节点输入以 Step 4 `nodes[].inputs` 为唯一事实源。不重新选链路、不新增节点、不重复召回。

## 规则

1. 每个模型节点恰好输出一个 `node_prompt`，`node_id` 和 `model` 与 Step 4 一致。
2. 无 `prompt_routing` 的节点只输出一个 `default` 变体，`conditions: {}`。
3. 有路由的节点对所有可达条件组合输出不重不漏、可独立执行的完整 Prompt。
4. 生成内容限制写入 Prompt；时长、画幅等调用参数留在 Step 4。
5. 必需的生成限制直接写入主 Prompt。每个变体只输出一段完整 `prompt`；身份保持、禁止漂移、避免穿模和镜头限制等排除性约束写在同一段 Prompt 中，不得另建 `negative_prompt` 或“反向提示词”字段。
6. 案例依据以节点为单位写入 `prompt_audit`，不参与模型调用。
   - 案例 Prompt 只用于学习结构、控制方式和表达经验，不是当前任务答案。
   - 不得整段复制案例 Prompt；不得引入当前 Step 2/4 没有的主体、道具、场景、动作或特效。
   - `prompt_audit.notes` 只说明借鉴的控制经验，不得声称“直接复用”完整案例 Prompt。
7. `presentation_type` 路由存在时，受影响的生图节点必须为 `female`、`male` 输出两份语义完整、可独立执行的 Prompt；不能只替换“男/女”称谓，必须落实 Step 4 指定的服装、发型、饰品、身体呈现或角色造型差异。
8. 视频节点没有 `presentation_type` 路由时，只使用“人物”“主体”“保持首帧造型”等中性表达，不重新硬编码男女外观；动作和验收要求相同就共用 Prompt。
9. Step 4 没有呈现分支时，任何 Prompt 都不得擅自写入露肩礼服、男士西装、女性长发等仅适用于单一呈现类型的设计；发现节点职责与分支契约冲突时返回 `blocked`，不得自行新增变体。
10. Step 2 `replication_goal.adapt` 中明确随运行时主体变化的年龄、物种、性别和身体形态不得固定成源视频属性。`uniform_redesign` 可以统一服装、道具或场景，但主体仍以输入图为准，不得无依据写成婴幼儿、成人、宠物或特定物种。
11. 当前节点同时输入运行时用户图与热点关键帧时，Prompt 必须明确两张图的职责：用户图只提供需要保留的身份、脸部或主体特征；热点关键帧提供场景、构图、姿态、景别、道具和空间关系。输出应以用户主体替换热点帧中的原主体，而不是融合成双主体，也不得把热点原主体身份带入结果。

## 输出

```json
{
  "node_prompts": [{"node_id": "generate_video", "model": "与 Step 4 一致的模型名", "variants": [{"variant_id": "default", "conditions": {}, "prompt": "从节点声明的单张输入图开始生成目标动作与特效，保持主体身份、构图和场景一致。"}]}],
  "prompt_audit": [{"node_id": "generate_video", "case_refs": [], "notes": []}],
  "case_snapshot_ref": "outputs/<task-id>/case-snapshot.json",
  "coverage_gaps": []
}
```

`semantic_validation` 由运行时在生成、确定性防复制检查和独立语义复核后追加，本 Prompt 不得自行输出或伪造通过结果。

`completed` 表示所有模型节点的 Prompt 与必需变体完整；否则返回 `blocked`。
