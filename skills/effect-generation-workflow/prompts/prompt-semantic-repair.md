# Step 6 Prompt 语义修正

你只修正已指出的 Step 6 Prompt 语义问题，返回一份完整的 Step 6 业务 JSON。

- 以 Step 2 卖点与复刻目标、Step 3 必保留要求和 Step 4 节点图为唯一任务事实。
- 删除所有没有当前任务依据的主体、道具、场景、动作、造型和效果。
- 历史案例只能提供结构、控制经验和写法，不得整段复制案例 Prompt。
- 严格保持 Step 4 的 `node_id`、`model`、节点数量和路由，不新增或删除节点。
- 严格遵循 Step 4 `appearance_strategy.mode`、`prompt_branching` 和 `prompt_routing`；不得在 `preserve_input` 中新增造型，不得将人物呈现敏感设计伪装成统一造型。
- Step 2 `adapt` 中要求随运行时主体变化的年龄、物种、性别和身体形态不得被固定成源视频属性；统一造型只能统一可共享的服装、道具和场景，不得强制主体变成婴幼儿、成人、宠物或特定物种。
- 生图节点同时输入用户图和热点关键帧时，必须把用户图写成身份来源、热点帧写成场景/构图/姿态/道具关系来源，并明确以用户主体替换热点原主体、避免双主体。
- Step 4 声明的受影响阶段、节点路由和 Step 6 变体必须一致；不得把共用 Prompt 的节点擅自分支。
- `prompt_audit` 说明借鉴了哪些控制经验，不得声称“直接复用”完整案例 Prompt。

只返回 `node_prompts`、`prompt_audit`、`case_snapshot_ref` 和 `coverage_gaps`，不返回 `semantic_validation`。
