# 链路选择纠错与泳池水枪复测记录

## 1. 本次修正了什么

原规则对“连续动作、道具物理互动、运镜”的权重过高，容易把可由单张首图和时序 Prompt 完成的方案误判为参考视频驱动。

修正后的决策原则是“最小充分控制”：

1. 分类始终以最终视频生成节点的实际媒体入参为边界，不看上游执行了多少次生图或视频理解。
2. 先评估一张精心设计的首图能否固定主体、外观、姿态、道具、场景、构图和风格。
3. 再评估剩余动态能否被拆成少量、有序、可执行、可验收的 Prompt 指令。
4. 端杯饮用、放杯转头、持水枪喷水、下蹲或侧身，以及推近、环绕、拉远运镜，只要不要求逐帧轨迹复刻，都可能属于 `single_image`。
5. “有连续动作”、“有道具互动”、“有镜头运动”都不是 `reference_video` 的充分条件。
6. 只有当非线性复杂动作、精确节拍、多主体配合、镜头-主体强耦合或无法文字化的轨迹本身是不可替代卖点，且热点视频会实际输入最终视频模型时，才选 `reference_video`。
7. 两种方案都能支持核心卖点时，优先输入更少、链路更简单、历史验证更充分的方案。
8. 高相似已验证案例如果使用更简单的链路，它是“无需升级控制”的强证据，除非当前视频有明确的额外复杂性。

修改文件：`skills/effect-generation-workflow/prompts/chain-selection.md`。

## 2. 泳池水枪为什么是压力用例

该视频同时包含：

- 镜头快速推近人物面部和水枪；
- 镜头绕主体进行接近 360 度环绕；
- 镜头拉回中景；
- 人物从直立变为侧身屈膝/单膝姿态；
- 手持水枪并持续喷出笔直水柱；
- 泳池、烟花、水花和动态光影。

如果仍使用旧的“动作越多越应该参考视频”倾向，它极易被误判。

## 3. 复测的 Step 1–7 结果

### Step 1：视频观察

- 时长 4.77 秒，1188 × 1186，无音轨。
- 一次性抽取 11 张候选帧。
- 识别出“建立姿态 → 快速推近 → 环绕 → 拉远 → 侧身屈膝喷水”的三段时间线。

### Step 2：卖点理解

- 主卖点：将用户变成夏夜泳池派对 CG 角色，手持水枪喷出强力水柱，通过推近、环绕和拉远展示有张力的姿态。
- 允许不逐帧复刻环绕轨迹和烟花绽放节奏，但需保留镜头阶段、水枪、水柱和终段姿态。

### Step 3A：真实 RAG 召回

Top 6 按顺序为：

1. `pool_water_gun_2`，`single_image`；
2. `jet_ski`，`single_image`；
3. `qixi_sky_lantern`，`single_image`；
4. `magpie_bridge_confession`，`multi_image`；
5. `summer_fireworks`，`single_image`；
6. `time_space_magpie_bridge`，`single_image`。

Top 1 精确召回到正式同名案例“泳池水枪2”。该案例的已验证链路为：

```text
用户人像
→ 呈现/性别分支识别
→ 可图 2.1 人像参考生成 first_frame
→ Kling 2.5 Turbo 只输入 first_frame 生成视频
```

### Step 3B：链路判断

- 结果：`single_image`。
- `temporal_reference_required = false`。
- `required_image_states = 1`。
- 最终同链路案例：`pool_water_gun_2`、`jet_ski`、`qixi_sky_lantern`、`summer_fireworks`、`time_space_magpie_bridge`。
- 关键理由：主体、服装、水枪、泳池、烟花和初始构图可由一张首图承载；剩余动态可被分解为有序文本指令，不要求原视频逐帧轨迹。

### Step 4：节点设计

```text
classify_presentation
→ generate_first_frame（可图 2.1 人像参考）
→ generate_video（Kling 2.5 Turbo）
```

- 运行时槽位只有 `user_portrait`。
- `first_frame` 是上游节点输出，不是基础素材或额外用户输入。
- 最终 `generate_video.inputs = ["first_frame"]`。

### Step 5：素材准备

- 本次设计任务没有额外固定素材需要处理。
- 未来用户人像是运行时槽位，不因当前无文件而暂停。
- `ready_for_prompting = true`。

### Step 6：节点 Prompt

- `generate_first_frame` Prompt 根据 female/male 分支定义服装与呈现，固定用户身份、水枪、泳池、烟花和初始构图。
- `generate_video` Prompt 明确“仅使用 first_frame，不输入热点参考视频”，再按顺序描述推近、环绕、拉远、分支姿态和喷水。

### Step 7：校验和交付

- 任务状态：`completed`。
- 节点、运行时输入、上游节点输出、Prompt 和案例引用均通过校验。
- 保留的真实试跑风险主要是 360 度环绕时的背面一致性和水柱-枪口连接。

## 4. 结论

这次复测表明，修正后的 Step 3 已不再因为“动作多、有环绕运镜、有道具互动”直接选参考视频。它正确识别了：

- 一张首图可以承载绝大部分高信息；
- 剩余动态可以被 Prompt 明确表达；
- 产品目标是复刻核心卖点，不是无条件逐帧复刻热点轨迹；
- 精确召回到的已验证同名案例证明单图链路可行。

因此“泳池水枪”最终被正确判定为 `single_image`。

## 5. 可追溯产物

- 设计师交付：`outputs/trial-pool-water-gun/production-plan.md`
- Step 1–7 完整状态：`outputs/trial-pool-water-gun/task-result.json`
- 真实 RAG 快照：`outputs/trial-pool-water-gun/case-snapshot.json`
- 时间线总览：`outputs/trial-pool-water-gun/video-analysis/timeline-overview.jpg`

## 6. Schema 0.4.0 Prompt 分支复测

后续复测将 Prompt 分支从自然语言条件句升级为通用运行协议：

```text
Step 2：声明必要的运行时分支维度
→ Step 4：理解节点输出分支值，生成节点声明 prompt_routing
→ Step 6：为所有可达条件组合生成独立 variants
→ Step 7：校验不重不漏并分别展示
```

该协议不写死性别、配色或某个案例动作：

- 分支维度 ID、取值和受影响节点均由当前热点分析决定；
- 只有实质改变 Prompt 的运行时属性才创建分支；
- 不为配色、款式或运营扩展生成额外变体；
- 历史设计师动作仅作为案例证据，当前变体动作可按核心卖点与模型稳定性重新设计。

在泳池水枪的实例中，Agent 根据运行时人像需要声明了 `presentation_type` 维度，并为生图和生视频节点各产出两份完整 Prompt。生视频动作没有强制复刻历史案例的“抬腿”或“单膝跪地”，而是保留推近、环绕、拉远、持枪喷水等核心卖点，同时使用更稳定的终段姿态。

复测结果：

- Schema：`0.4.0`；
- 链路：`single_image`；
- 任务：`completed`；
- 生图 Prompt 变体：2；
- 生视频 Prompt 变体：2；
- Step 7 路由条件覆盖校验：通过。

新产物：

- 设计师交付：`outputs/trial-pool-water-gun-v04/production-plan.md`
- 完整状态：`outputs/trial-pool-water-gun-v04/task-result.json`
- RAG 快照：`outputs/trial-pool-water-gun-v04/case-snapshot.json`
