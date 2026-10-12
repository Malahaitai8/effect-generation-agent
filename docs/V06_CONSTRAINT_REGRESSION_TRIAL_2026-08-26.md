# Schema 0.6.0 约束来源回归试跑（2026-08-26）

## 1. 测试目标

本轮主要验证：

1. Step 2 将源主体年龄或形态归入 `replace/adapt` 后，Step 3 是否还会擅自升级为 `must_preserve`。
2. 新的约束 ID 和 `source_refs` 是否会阻碍正常人物链路。
3. Step 2–7 的其他业务语义是否仍然一致。

测试任务使用中性 ID `blind-v06-a` 和 `blind-v06-b`，未在任务 ID、标题或输出目录中暴露链路答案。Step 1 使用已人工确认的同源视频理解；Step 2、3B、4、6 由真实 DeepSeek 调用完成；Step 3A 使用本地 BGE；Step 5 和 Step 7 为确定性执行器。

## 2. 结论摘要

- 两个任务都完成 Step 1–7，批次状态为 `completed`。
- “婴儿形态被 Step 3 越权升级”已解决：泡面案例中年龄、物种和身体形态保持在 `adapt`，Step 3 `must_preserve` 只引用了反转、表情节奏和镜头推近。
- 新的约束来源机制没有阻碍正常链路；两条都正常选择 `single_image`并进入 Step 4–7。
- 但出现严重的 Prompt 语义串案：泡面案例的 Step 6 直接复用了不相关的宠物理发案例 Prompt，最终交付完全不可用。
- 人物呈现分支仍不稳定：浪漫时刻未建立 `presentation_type`，但首帧 Prompt 硬编码了“银色露肩礼服和银色首饰”。
- Step 7 目前只能验证节点、引用、素材和 Prompt 是否存在，无法验证 Prompt 是否与当前任务语义一致。

## 3. `blind-v06-a`：泡面奇遇

### Step 1

- 候选帧：14 张，本任务只抽帧一次。
- [时间线抽帧总览](../outputs/blind-v06-a/video-analysis/timeline-overview.jpg)。
- 关键帧：`frame_0001`、`frame_0006`、`frame_0009`、`frame_0011`、`frame_0014`，分别覆盖吃面起点、吸面中态、表情转折、反应峰值和鼻孔面条终态。

### Step 2

- 主卖点：吃面过程后面条从鼻孔垂下的意外反转。
- `replace`：源视频具体婴儿主体。
- `preserve`：鼻孔面条反转、表情变化节奏、结尾推近。
- `adapt`：年龄、物种、身体形态、服装和帽子随运行时主体适配。

这一步的归类已经纠正了上轮“自动婴儿化”问题。

但 `prompt_branching.reason` 写成“目标主体为宠物、动物或婴儿化形态”，这仍然擅自假定了未来主体类型。正确理由应是“当前方案没有重设计性别化造型，核心动作可用中性 Prompt 表达”。

### Step 3

- 选择：`single_image`。
- `must_preserve` 的三项要求都有合法的 `replication_goal.preserve.<id>` 来源。
- 婴儿年龄、物种和身体形态被放入 `may_change`，未升级为硬约束。

约束来源修复在这里验证通过。但 `selection_reason` 中仍用了“婴儿睁眼张口”来描述首帧，说明自由文本字段仍可能残留源主体假设，只是没有再进入结构化 `must_preserve`。

### Step 4–5

- 节点：`user_image → generate_first_frame → first_frame → generate_video`。
- Step 5 无固定素材，`ready_for_prompting=true`。

Step 2 将面桶和筷子写成“由运行时用户提供或替换”，但 Step 4 并没有定义对应运行时输入槽位。当前产品输入只有用户主体图时，道具应由生图节点生成，而不应虚构“用户提供道具”。

### Step 6–7

这是本轮最严重的问题：

- `generate_first_frame` 的 Prompt 要求主体坐在白色桌面，理发师准备用黑色理发披风包裹主体。
- `generate_video` 的 Prompt 进一步写了披风、染发膏、锡纸、红外线灯、吹风机和包租婆卷发。
- 这些内容来自召回的 `duck_hairdressing` 案例，与泡面、筷子、表情反应和鼻孔面条完全无关。
- Prompt 审计还明确写了“直接复用 duck_hairdressing 案例 Prompt”，说明 Step 6 把 RAG 案例误当成了可整段复制的任务答案。
- Step 7 仍然将任务标记为完成，因为它只校验 Prompt 存在、节点对应和引用合法，不校验 Prompt 与当前卖点的语义一致性。

因此，这条任务虽然技术状态为 `completed`，但业务结果判定为**不可用**。

- [用户最终方案](../outputs/blind-v06-a/production-plan.md)
- [完整七步状态](../outputs/blind-v06-a/task-result.json)
- [RAG 快照](../outputs/blind-v06-a/case-snapshot.json)

## 4. `blind-v06-b`：浪漫时刻

### Step 1–3

- 候选帧：10 张，[时间线抽帧总览](../outputs/blind-v06-b/video-analysis/timeline-overview.jpg)。
- 主卖点：蛋糕下降、人物托接、心形花束散成花瓣并以微笑托蛋糕收束的浪漫惊喜。
- Step 2 将人物年龄、性别、服装、发型和身体形态放入 `adapt`。
- Step 3 选择 `single_image`，三条 `must_preserve` 全部引用合法的 Step 2 `preserve` ID。

约束来源机制正常。

### Step 4–7

- 节点：`user_image → 可图 2.1 人像参考 → first_frame → Kling 2.5 Turbo → generated_video`。
- Step 5 无固定素材，`ready_for_prompting=true`。
- Step 6 的蛋糕下降、托接、花束散落和结束微笑与本任务一致，没有出现案例串案。

但人物呈现分支仍有明确冲突：

- Step 2 输出 `prompt_branching.required=false`。
- Step 4 没有为生图节点配置 `presentation_type` 路由。
- Step 6 的唯一 `default` 首帧 Prompt 却写入“银色露肩礼服、银色首饰”，是明显的单一女性造型，不是适用所有运行时主体的中性设计。

因此，该方案的动作链路和 Prompt 主题基本正确，但人物呈现分支不可直接上线，业务结果判定为**需要修正后可用**。

- [用户最终方案](../outputs/blind-v06-b/production-plan.md)
- [完整七步状态](../outputs/blind-v06-b/task-result.json)
- [RAG 快照](../outputs/blind-v06-b/case-snapshot.json)

## 5. 耗时

- `blind-v06-a` 有效 Step 2–7 运行时间约 39 秒。
- `blind-v06-b` 有效 Step 2–7 运行时间约 49 秒。
- 整个批次的墙钟时间约 27 分钟，其中大部分是首次调用时的受限网络失败、等待授权和 Hugging Face 联网探测，不是 Agent 稳定运行耗时。
- 设置 `HF_HUB_OFFLINE=1` 并复用本地 BGE 后，Embedding 权重立即加载。

## 6. 下一步优先级

1. **Step 6 任务语义一致性**：案例 Prompt 只能提供写法和控制经验，不得整段复制。应要求每个主体、道具、动作、场景和状态都能回指当前 Step 2/4，并在 Step 7 增加语义验收。
2. **无分支 Prompt 守卫**：`prompt_branching.required=false` 时，生图 Prompt 不能包含只适用某一人物呈现类型的服装、发型、配饰和身体设计；否则应阻断并要求重做 Step 2/4。
3. **消除自由文本残留越权**：Step 3 `selection_reason` 也应使用“运行时主体”而不是源主体年龄/物种，避免后续节点从自由文本重新学回错误假设。
4. **运行时输入一致性**：Step 2 不得写“用户提供道具”而 Step 4 又不定义对应槽位。当前只有主体图输入时，其他道具由节点生成或作为固定素材。

本轮不应继续优化链路分类；两条的 `single_image` 判断都可接受。当前最高优先级是防止 Step 6 串案，否则即使前五步正确，最终交付仍可能完全不可用。
