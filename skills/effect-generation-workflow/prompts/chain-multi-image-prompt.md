# Step 6：多图驱动节点 Prompt

## 目标与边界

仅当链路为 `multi_image`、Step 4 已完成且 Step 5 `ready_for_prompting == true` 时读取。沿用其他链路的 Prompt 公共契约，为 Step 4 中每个有 `model` 的生成节点输出可直接执行的 Prompt；确定性节点不输出。

节点、输入、顺序、模型和路由以 Step 4 为唯一事实源。不重新选链路、不新增节点、不重复召回。

## 多图差异规则

1. 每个模型节点恰好输出一个 `node_prompt`；模型名、路由覆盖、案例审计、防复制和语义复核规则与另外两种链路一致。
2. 最终视频 Prompt 必须分别说明第一张图的起始状态职责、第二张图的结束状态职责，以及从前者到后者的连续变化过程。
3. 两张图是有序状态，不得描述为可交换的普通参考图；不得交换 Step 4 `inputs` 的顺序。
4. 明确过渡过程中必须保持的身份、主体数量、关键物体和场景连续性，并落实 Step 3 `must_preserve`。
5. 只描述 Step 2/4 已确认的转变、动作、特效和镜头，不用 Prompt 修补未在 Step 4 解决的首尾图结构冲突。
6. 上游生图节点只生成其职责声明的状态图，不得越权生成另一个状态或改写最终视频节点。
7. 接口、输入规格或顺序未经真实试跑的能力缺口写入 `coverage_gaps`，不得声称已验证。
8. `presentation_type` 等分支只作用于 Step 4 已声明路由的节点；无路由视频节点使用中性表达并保持两张状态图已建立的外观。

## 输出

```json
{
  "node_prompts": [{"node_id": "generate_video", "model": "与 Step 4 一致的模型名", "variants": [{"variant_id": "default", "conditions": {}, "prompt": "以第一张 start_frame 为视频起始状态，连续完成已确认的变化过程，并在结尾准确到达第二张 end_frame；保持主体身份、主体数量和关键场景关系连续一致。"}]}],
  "prompt_audit": [{"node_id": "generate_video", "case_refs": [], "notes": []}],
  "case_snapshot_ref": "outputs/<task-id>/case-snapshot.json",
  "coverage_gaps": ["双图接口和输入顺序待真实试跑"]
}
```

历史案例 Prompt 只用于学习结构、控制方式和表达经验，不得整段复制，不得引入当前 Step 2/4 没有的内容。`semantic_validation` 由运行时追加，不得自行输出或伪造通过结果。

`completed` 表示所有模型节点及路由变体完整；否则返回 `blocked`。

输出前确认：Prompt 节点与 Step 4 模型节点一一对应；最终视频 Prompt 明确两个输入的不同职责和顺序；历史案例没有被整段复制。
