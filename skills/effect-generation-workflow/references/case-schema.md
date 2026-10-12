# 历史案例数据规范

案例数据用于 Step 3 卖点召回与链路过滤、Step 4 历史节点参考以及 Step 6 节点 Prompt 参考。正式数据位于项目根目录 `rag/data/cases.jsonl`，每行一个 case；机器校验事实源是 `rag/case.schema.json`。

## 顶层字段及用途

- `case_id`、`case_name`：稳定标识和展示名称。
- `source_ref`：指回原文档及所在章节，供人工核对，不参与相似度计算。
- `primary_selling_point`、`secondary_selling_points`：Step 3A 唯一的主召回文本来源。
- `route_type`：Step 3B 选择链路后的精确过滤字段，只能是 `single_image`、`multi_image` 或 `reference_video`。
- `materials`、`nodes`：Step 4 参考历史节点职责、模型、依赖和素材流；Step 3 只可用最终视频节点输入核验 `route_type`。
- `nodes[].prompts`：Step 6 定位相似历史节点后读取的原始 Prompt，不参与主召回。
- `source_notes`：保存原文冲突或无法确认的信息，不参与主召回。

## Prompt 与节点关系

- Prompt 嵌入所属生成节点，一个节点可以用 `variant` 保存男女、配色、日期或历史版本分支。
- Prompt 继承节点的 `model` 和 `id`，不重复保存这两个字段。
- `classification` 和 `image_processing` 节点不保存 Prompt。`prompt_generation` 用于保存根据用户素材动态生成下游 Prompt 的历史节点及其原始模板；原文没有可读取 Prompt 的必要生成链路不作为正式 case 入库。
- `route_type: multi_image` 仅用于最终视频节点同一次调用明确接收至少两张图片、且不接收参考视频的案例；不能根据上游生图数量或原文所在章节直接判定。
- 不保存图片、视频或附件文件，只保存素材角色、媒体类型和来源类型。

## 链路分类核验

每个 case 恰有一个 `is_final_video_node: true` 的 `video_generation` 节点：

- `single_image`：该节点输入中恰有一张图片且没有视频。
- `multi_image`：该节点输入中至少有两张图片且没有视频；当前自动设计范围限定为两张有序状态图。
- `reference_video`：该节点输入中至少包含一个视频。

上游生图数量和上游参考素材数量不改变 `route_type`。

## 各 Step 的读取边界

- Step 3A：只读取卖点描述和标签计算相似度。
- Step 3B：读取 `route_type` 过滤 Top 6；必要时读取最终视频节点输入核验分类，不展开 Prompt。
- Step 4：读取过滤后 case 的 `materials`、`nodes`、模型和参数，重新设计当前任务链路，不直接照搬。
- Step 6：按当前节点职责、节点类型、模型和输入媒体组合定位历史节点，再读取该节点的 `prompts`；不要求历史节点 ID 与当前节点 ID 相同。

正式 case 必须通过 `rag/case.schema.json` 和案例测试。链接或附件中无法读取的 Prompt 不得用摘要、猜测或占位内容补齐。
