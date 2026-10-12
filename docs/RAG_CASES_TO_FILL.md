# RAG 多图与视频驱动候选案例待填表

目标：正式案例库中 `multi_image` 和 `reference_video` 各不少于 15 个。

当前正式入库数量：

- 多图驱动：9 个。
- 视频驱动：14 个。
- 单图驱动：22 个。
- 总计：45 个。

补充材料已经完成一轮正式入库。此前预计可直接抽取的部分“首尾帧”案例，经嵌入图片复核后实际是同一张图片重复作为首帧和尾帧，不满足本项目 `multi_image` 的定义，因此没有入库。“偶像来了”已根据用户确认的固定首帧和 Step 4 尾帧入库。多图距离目标还差 6 个，视频驱动距离目标还差 1 个。

填写原则：

- 不需要填写卖点、标签、case ID，也不需要上传图片或视频文件。
- 原文中已经能读到的内容不必重复整理。
- Prompt 请原样粘贴，不改写、不概括。
- 多图驱动必须确认：最终视频模型的同一次调用输入至少两张图片，并且不输入视频。
- 视频驱动必须确认：最终视频模型的同一次调用真实接收参考视频。仅观看成品或参考演示不算视频输入。
- 某项确实不存在时填写“原文无”；看不清或无法确认时填写“无法确认”。

---

## A. 多图驱动候选

当前正式入库 9 个，还差 6 个。现有送标文档、历史交付文档、内部内测文档和 B 端特效需求池已经完成筛选，没有剩余可直接入库的多图案例。后续 6 个需要来自新的案例来源或可读取的工作流。

### 已失效候选：快速横移镜头

该案例仅存在于过期搜索索引，当前文档正文和附件均无法恢复。除非后续取得原始工作流，否则不再作为待填候选。

### 已失效候选：共庆新年

该案例仅存在于过期搜索索引，当前文档正文和附件均无法恢复。除非后续取得原始工作流，否则不再作为待填候选。

### 另外 4 个多图案例

每个只需提供：案例名、整体链路、两张不同图片分别来自哪里、最终视频模型和 Prompt。卖点、标签和节点结构由我整理。

### A1 达康书记同款摇车窗模板（0817，优先）

已知：两次 Kling 3.0 首尾帧生成，再拼接；视频 Prompt 正文可读。

请填写：

```text
Step 1 生图（第一段视频尾帧）工作流里的模型、Prompt、参数：
图像比例2:3
图像质量high
prompt：以 图片1 为基础画面，完整保留其构图、取景范围、车内环境、车体结构、座椅、车窗、摄像机角度、透视关系、光线方向、色调与景深。将 图片1 中的白狗完全移除，不留残影或轮廓痕迹，将 图片2 中的动物替换在原位置。严格保留 图片2 中动物的品种、毛色、花纹、五官比例与体型特征。替换后的动物保持与现实物理世界一致的在画面中的位置与占比，坐姿时惬意地靠在车座椅上，整个身体面朝着它的前方的座椅背；体型比例需与车内空间和座椅尺度相符。头部面向前方座椅靠背，眼神直视镜头，微微眯眼、下巴略抬，以不屑嫌弃的神情斜视镜头并与镜头对视。毛发边缘自然，受光方向、明暗关系、投影与车窗反光均与图片1一致，融合无贴图感，整体为真实拍摄质感。图片的比例和分辨率与短视频竖屏完全一致。

Step 2 生图（第一段视频首帧）工作流里的模型、Prompt、参数：
图像比例2:3
图像质量high
prompt：图片1 是近景画面，图片2 是同一场景的全景参考图。任务：把 图片1 的内容原样扩展为全景，使最终画面的构图、取景范围、镜头视距、主体在画面中的位置与占比、车体在画面中的比例、以及周边道路环境布局，都与 图片2 完全一致。严格保留 图片1 中动物的物种、毛色羽色、花纹、五官比例、体型、坐姿、身体朝向、头部角度与斜视镜头的神情，不做任何改动，也不改变它在车内后排车窗位置的相对关系。图片2 仅用于提供构图、取景比例与环境参考，绝对不要把 图片2 中的白狗带入画面，画面中只允许出现 图片1 中的这只动物，不得出现任何白色犬类或其残影。向外补全的部分需与 图片1 的车身漆面、车窗玻璃、车门线条、后视镜、路面、道路车流、红绿灯、路牌、树木与建筑自然衔接，透视关系、光线方向、明暗关系、色调、景深与颗粒感均与 图片1 保持统一，拼接处无接缝与畸变，整体为真实拍摄质感的一张完整照片。图片的比例和分辨率与短视频竖屏完全一致。

第一次视频调用：
- 首帧来自：step2
- 尾帧来自：step1

第二次视频调用：
- 首帧来自：step1 
- 尾帧来自：无尾帧

其他需要说明的原文冲突：
```

### A2 偶像来了（0713／0710，优先）

已知：正文已包含 Step 2–5 的模型和 Prompt；模型列写“可灵3.0首尾帧5s”。

请填写：

```text
最终视频首帧是哪一张图／来自哪个 Step：已有的作为背景的素材图

最终视频尾帧是哪一张图／来自哪个 Step：step4

正文中随 Step 5 展示的两张图片分别是什么：没有step5
- 图片1：
- 图片2：

是否确认最终调用没有参考视频输入：
```


### A4 世界杯哈兰德（0702）

已知：主体基准图 → 9 张分镜图 → Omni 3 多段视频 → 拼接为 18s。不能把整组 11 张图笼统记成一次调用，需要恢复每次调用关系。

请填写：

```text
特效模板-Q版大头球星 工作流提示词整理
工作流 ID: 902952285213298777
链接: https://keffects.staging.kuaishou.com/workflow?id=902952285213298777

结构说明: 8 条分镜替换支路(分镜1-8、11), 分镜6删除，9、10跳过替换直接用原片;
视频链路: 任务1=分镜1-5 生成一段;
任务2拆成三部分: (2a) o3 生成3秒[带球拉远蓄力踢球] + (2b) 原视频片段[用户提供,直接拼接] + (2c) o3 生成3秒[盘腿打坐收尾];
最后 FFMPEG 按 任务1 → 2a → 2b → 2c 顺序拼接。

================================================================================
一、主体基准图 
输入: image1=模板风格参考帧(上传分镜1), image2=用户上传主体图(运行时输入), image3=蓝色球衣图(固定)
================================================================================
Create ONE clean subject reference image for later character replacement. image 1 is a generated template shot from the source effect: use it ONLY for 3D Pixar/Q-version big-head cartoon style, proportions, lighting and render quality; do NOT copy its character identity, pose, action, scene, background or clothing. image 2 is the user's subject: it is the ONLY source for biometric identity, skin tone, face shape, facial features, eye shape, nose, mouth, eyebrows, cheeks, hair color, hairstyle and hairline. Preserve image 2's underlying skin tone exactly; do NOT darken, lighten, tan or recolor it toward image 1 or image 3. image 3 is ONLY the wardrobe reference. The output subject MUST wear the blue soccer jersey from image 3 as the visible upper-body garment: preserve the blue base color, white V-neck/collar, white shoulder stripes/panels, sleeve trim, fabric finish and the large white chest number 9 when visible. Ignore image 3's person identity, face, skin, body, pose, camera, background and scene. STRICT OUTPUT LAYOUT: vertical 9:16 portrait, pure white (#FFFFFF) background, ONE SINGLE subject only. Generate a HALF-BODY / upper-body FRONT VIEW reference portrait: head, hair, face, neck, shoulders, chest and upper torso visible down to about the waist. The subject faces the camera directly in a neutral front-facing pose, centered. Do NOT show full body, legs, knees, socks, shoes, side view, back view, multiple subjects, collage, panels, split screen, text labels, watermarks or UI overlays.

================================================================================
二、逐张分镜替换 生图 prompt(输入: image1=原分镜帧(固定), image2=主体基准图)
================================================================================

--- 分镜 1(带球冲刺) ---
将 image 1 中画面中穿蓝色球服的白人男子替换为 image 2「主体基准图」中的人物。严格保持原分镜主体伸着脖子，弓着腰走路的动作、姿态、构图、景别、镜头角度、主体位置和大小、体育场背景、光照和3D Q版大头风格不变；替换后人物的身材体型、脸部样貌、肤色、发型、蓝色球衣服装颜色和细节全部参考主体基准图。只替换这个穿蓝色球服的白人男子，不替换其他人物，不新增人物。输出一张干净清晰的单帧图。

--- 分镜 2(正面带球突破) ---
将 image 1 中画面中穿蓝色球服的白人男子替换为 image 2「主体基准图」中的人物。严格保持原分镜的正面带球突破动作、身体姿态、头身比例、构图、镜头角度、主体位置和大小、足球位置、体育场背景、光照和3D Q版大头风格不变；替换后人物的身材体型、脸部样貌、肤色、发型和蓝色球衣细节参考主体基准图。只替换这个穿蓝色球服的白人男子，不改变其他内容。输出一张干净清晰的单帧图。

--- 分镜 3(被拉扯球衣挣脱) ---
将 image 1 中画面中穿蓝色球服的白人男子替换为 image 2「主体基准图」中的人物。严格保持原分镜的前倾挣脱动作、被拉扯球衣的姿态、构图、景别、遮挡关系、接触关系、主体位置和大小、草地球场、镜头角度和3D Q版风格不变；替换后人物的身材体型、脸部样貌、肤色、发型和蓝色球衣细节参考主体基准图。只替换这个穿蓝色球服的白人男子，拉扯他的防守球员保持不变。输出一张干净清晰的单帧图。

--- 分镜 4(防守球员骑上肩) ---
将 image 1 中画面中穿蓝色球服的白人男子替换为 image 2「主体基准图」中的人物。严格保持原分镜的承重姿态、身体动作、构图、景别、主体位置和大小、遮挡关系、接触关系、镜头角度、体育场背景、光照和3D Q版大头风格不变；替换后人物的身材体型、脸部样貌、肤色、发型和蓝色球衣细节参考主体基准图。只替换这个穿蓝色球服的白人男子，骑在他身上的防守球员保持不变。输出一张干净清晰的单帧图。

--- 分镜 5(背着防守球员奔跑) ---
将 image 1 中画面中穿蓝色球服的白人男子替换为 image 2「主体基准图」中的人物。严格保持原分镜的背人奔跑动作、肩背承载互动、身体姿态、构图、景别、主体位置和大小、草地/背景、镜头角度、光照和3D Q版风格不变；替换后人物的身材体型、脸部样貌、肤色、发型和蓝色球衣细节参考主体基准图。只替换这个穿蓝色球服的白人男子，被背着的防守球员严格保持不变。输出一张干净清晰的单帧图。

--- 分镜 6(背着防守球员奔跑) ---
将 image 1 中画面中穿蓝色球服的白人男子替换为 image 2「主体基准图」中的人物。严格保持原分镜的背人奔跑动作、肩背承载互动、身体姿态、构图、景别、主体位置和大小、草地/背景、足球样式、镜头角度、光照和3D Q版风格不变；替换后人物的身材体型、脸部样貌、肤色、发型和蓝色球衣细节参考主体基准图。只替换这个穿蓝色球服的白人男子，被背着的防守球员严格保持不变。输出一张干净清晰的单帧图。

--- 分镜 7(短提示词版(只换肢体)) ---

将 image 1 中画面中穿蓝色球服的白人男子的可见腿部/身体部分替换为 image 2「主体基准图」中的人物特征与蓝色球衣造型。严格保持原分镜的腿部动作、脚的位置、足球位置、草地、近景构图、镜头角度、光照和3D Q版风格不变；替换后可见身体、肤色、体型和服装颜色细节参考主体基准图。只替换这个穿蓝色球服的白人男子，不改变足球和背景。输出一张干净清晰的单帧图。

--- 分镜 8(踢球姿态）---
将 image 1 中画面中穿蓝色球服的白人男子替换为 image 2「主体基准图」中的人物；严格保持原分镜主体的蓄力踢球动作，身体姿态、构图、景别、主体位置和大小、草地/背景、镜头角度、光照和3D Q版风格不变；替换后人物的身材体型、脸部样貌、肤色、发型和蓝色球衣细节参考主体基准图。只替换这个穿蓝色球服的白人男子，输出一张干净清晰的单帧图。

--- 分镜 11(盘腿打坐收尾) ---
将 image 1 中画面中穿蓝色球服的白人男子替换为 image 2「主体基准图」中的人物。严格保持原分镜的盘腿打坐姿态、手部位置、静止动作、构图、景别、主体位置和大小、体育场草地背景、镜头角度、光照和3D Q版大头风格不变；替换后人物的身材体型、脸部样貌、肤色、发型和蓝色球衣细节参考主体基准图。只替换这个穿蓝色球服的白人男子，其他所有元素保持不变。输出一张干净清晰的单帧图。

--- 分镜 9、10 ---
不替换，直接使用处理后的原视频

================================================================================
三、视频任务 1 prompt(全局分镜1-5, 共7秒)
================================================================================

Task boundary: this prompt is for ONE independent KEffects video generation task using only the images listed below. Do not refer to any previous segment, previous task, or unseen images. Each shot description must be self-contained and based on its own referenced image. Identity rule: preserve the same main subject identity across main-subject shots and keep supporting subjects distinct. User adaptation: apply the user's requested changes in the relevant shot descriptions. Local shot mapping: this task contains global shots 1-6, but refer to them locally as Shot 1..6 and image_1..image_6. 

[Shot 1 | image: <<<image_1>>> | 2s]
Action: Tracking fast, medium shot. The main subject with an exaggerated large head and custom outfit runs rapidly across a grassy soccer field from left to right, with his neck stretched forward, his back hunched over, and his big head craning ahead of his body as he charges. The subject has an intense, determined expression, leaning forward with aggressive sprinting motions. The background stadium crowd is blurred with strong motion blur. Camera: tracking. Camera speed: fast. Action detail: 从左向右快速奔跑，伸着脖子、弓着腰、大头向前探着冲，步伐迈动幅度大，长发随风向后剧烈飘动。. Emotion: 严肃/坚定. Transition: 镜头切换到正面特写。.
Role anchor: the main subject is the target subject, the same identity as <<<image_1>>>.

[Shot 2 | image: <<<image_2>>> | 1s]
Action: Tracking fast, close-up. The main subject dribbles the soccer ball forward directly toward the camera, leaning side to side rhythmically. Dynamic lighting highlights their face as they maintain a fiercely focused gaze. Camera: tracking. Camera speed: fast. Action detail: 正面奔跑带球，肩膀左右规律性大幅度晃动，目光死死盯住前方。. Emotion: 专注/充满斗志. Transition: 动作连贯，切入到对抗场景。.
Role anchor: the main subject is the target subject, the same identity as <<<image_2>>>.

[Shot 3 | image: <<<image_3>>> | 1s]
Action: Tracking steady, medium shot. A defender aggressively grabs and pulls the back of the main subject's jersey, heavily stretching the fabric backward. The main subject leans forward, struggling intensely to keep running despite the heavy resistance. Camera: tracking. Camera speed: steady. Action detail: subject_2 在后方双手死死拽住 subject_1 的球衣，导致球衣被大幅度向后拉伸；subject_1 身体前倾奋力挣脱。. Emotion: 紧张/胶着. Transition: 动作升级，无缝承接对手跳跃动作。.
Role anchor: this shot contains both the main subject and supporting subject(s); keep them distinct. The main subject is the target identity, and the supporting subject is not the main subject.

[Shot 4 | image: <<<image_4>>> | 1s]
Action: Static shot, medium shot. The defender jumps up and rides onto the main subject's shoulders, tightly wrapping arms around the subject's neck. The main subject hunches slightly under the sudden weight but firmly stays on their feet. Camera: static. Camera speed: steady. Action detail: subject_2 向上跃起，双腿盘住 subject_1，双手环抱其脖子；subject_1 承受重压导致头部稍微前倾。. Emotion: 激烈对抗. Transition: 主角稳住重心继续奔跑。.
Role anchor: this shot contains both the main subject and supporting subject(s); keep them distinct. The main subject is the target identity, and the supporting subject is not the main subject.

[Shot 5 | image: <<<image_5>>> | 1s]
Action: Tracking fast, close-up. The main subject runs forward confidently and effortlessly while carrying the defender on their shoulders. The main subject shows a smug, relaxed smirk, completely unfazed by the struggling defender above. Camera: tracking. Camera speed: fast. Action detail: subject_1 背负着身上的 subject_2 继续平稳且快速地向前奔跑带球，脸上露出一丝轻松的微笑。. Emotion: 游刃有余/得意. Transition: 视线切向脚部的带球动作。.
Role anchor: this shot contains both the main subject and supporting subject(s); keep them distinct. The main subject is the target identity, and the supporting subject is not the main subject.

[Shot 6 | image: <<<image_6>>> | 1s] Action: Tracking fast, extreme close-up. The main subject's short legs run rapidly on the green grass, skillfully pushing and dribbling the glowing soccer ball forward with explosive energy. Camera: tracking. Camera speed: fast. Action detail: 双腿高频率交替奔跑，脚尖精准拨动足球向前滚动。. Emotion: 爆发力. Transition: 脚部蓄力准备射门。. Role anchor: the main subject is the target subject, the same identity as <<<image_6>>>.

================================================================================
四、视频任务 2（链路已调整: 三段结构 = o3生成3秒 + 原视频2s + o3生成3秒）
================================================================================

--- 任务 2a: o3 生成 3 秒(带球拉远 → 蓄力 → 踢球，球飞向镜头) ---
输入: Image 1=腿部特写带球帧, Image 2=蓄力踢球帧, Image 3=主体基准图(主体形象参考)，Image 4=球样式参考

prompt：
The scene opens from the perspective of "Image 1": an extreme close-up shot at grass level showing the sturdy legs of a cartoon-style player in motion—he is wearing blue shorts (imprinted with the number 9) and dark blue socks, and is shod in gold-colored cleats.The camera then smoothly pulls back and rises to reveal the player's full-body image while dribbling, before transitioning to the wind-up kicking pose seen in "Image 2": a view from the rear-side, with the kicking leg drawn back, the body leaning forward, . The camera arcs smoothly around the player, keeping him centered in the frame throughout. Next, he kicks the ball with full force; the ball compresses upon impact and rapidly flies toward the camera, trailing speed lines and flying grass debris. The legs in "Image 1" and the player in "Image 2" represent the same character; consistent features must be maintained, including curly brown hair, a blue number 9 jersey, white shorts, and gold cleats. The subject's appearance, face, hairstyle and jersey details must follow the subject reference in "Image 3". Retain the 3D Pixar-style "big-headed" cartoon aesthetic, the nighttime stadium lighting, and the 9:16 vertical aspect ratio. No additional characters are required. Once the kicking action is complete, the ball must exit the frame entirely—it must not remain near the player.Only one soccer ball may appear in the video; the style of the soccer ball must strictly adhere to Image 4.

--- 任务 2b: 原视频片段(2s) ---
直接使用提供的原视频片段(足球砸脸/防守球员倒地等原片段落), 不走生成, 原样进入拼接。

--- 任务 2c: o3 生成 3 秒(盘腿打坐收尾) ---
输入: 打坐分镜帧(分镜11替换后)

The main blue-jersey subject sits cross-legged on the soccer pitch in a peaceful zen meditation pose, eyes closed, hands on knees, completely still. Slow pull-out full shot. Video ends.

--- 拼接顺序 ---
任务1（6s） → 任务2a(3s) → 任务2b(原视频2s) → 任务2c(3s)，FFMPEG 顺序拼接输出最终成片。
```


### A6–A17 历史首尾帧案例（无需手填）

来源：《送到标注平台标注的特效【至2026/01/04】》。Mario 已确认以下案例的最终视频链路明确标注“首尾帧”，且正文 Prompt 可读，我可以直接抽取：

1. 摩托--后视角、侧视角（1231）
2. 雪地摩托（1231）
3. 变形金刚（1225）
4. 花灯建筑（1225）
5. 春联（1225）
6. 开箱12生肖（1225）
7. 开箱红包（1222）
8. 开箱2026_1（1222）
9. 开箱2026_2（1222）
10. 摩托-后视角转场（1223）
11. 转场-摩托FPV接摩托FPV（1225）
12. 火焰摩托（1231，正文更像单图视频，作为分类核验备选，不计入 15 个承诺）

前 11 个与现有 4 个合计正好达到 15 个；“火焰摩托”只有确认属于多图后才会额外入库。

---

## B. 视频驱动候选

目前可用新增案例为：B1、B2、B3、B6，以及正文可直接抽取的“宠物冲出屏幕”和“醋意摇”。与现有 8 个合计可达到 14 个，还缺 1 个。

### B1 捉弄玩偶2（0707，优先，无需手填）

Mario 已确认正文包含完整生图 Prompt、视频 Prompt、图片输入和参考视频输入。我可以直接抽取，用户无需补充。

### B2 捉弄玩偶（0707，优先，无需手填）

Mario 已确认正文包含完整生图 Prompt、视频 Prompt、图片输入和参考视频输入。我可以直接抽取，用户无需补充。

### B3 南非舞（0702，优先）

已知：视频 2.6 动作控制，720p，打开原声，人物朝向与参考视频一致。

请填写：

```text
用户输入图片的作用：人物形象参考，让用户输入的参考图中的人物像参考视频一样跳舞

参考视频的作用（动作／镜头／节奏／其他）：动作、节奏

完整视频 Prompt：无提示词，模型本身有能力

动作控制参数（除已知内容外）：无

视频时长：8s

是否存在上游生图节点；如有，粘贴模型、参数和 Prompt：无
```


### B6 摇车窗吹蜡烛（0729，待确认）

已知：正文有场景参考图和 `916带BGM参考视频.mp4`，但模型列与 Prompt 缺失。

请填写：

```text
完整整体链路：

最终视频模型、时长、分辨率和参数：视频3.0 omni；1080p；9s；原声打开

该参考视频是否作为模型真实输入，而不只是演示样例：是

用户输入图片及作用：替换参考视频中的人物主体

场景参考图的作用：无场景参考图

最终视频 Prompt：把视频[视频]中的蜡烛人物的任务换成图片[图片]中大的主体人物

上游节点模型、参数和 Prompt（如有）：
```

### B7 宠物冲出屏幕（无需手填）

Mario 已确认正文包含完整视频模型、参数、参考视频输入、用户图和背景图输入及完整 Prompt，我可以直接抽取。

### B8 醋意摇（无需手填）

已知为视频 2.6 动作控制、720p、打开原声、人物朝向与参考视频一致。正文没有 Prompt；按与“南非舞”相同的无 Prompt 动作控制链路整理。

### B9 最后一个视频驱动案例（仍需提供）

Mario 已穷尽当前可访问的送标文档，没有找到第 15 个可闭合案例。若你在其他文档或工作流中看到一个参考视频驱动案例，只需填写：

```text
特效名称：

整体链路原文：

最终视频模型、时长、分辨率和参数：

参考视频是否作为模型真实输入：

用户图片及作用：

最终视频 Prompt（没有则写“无提示词”）：

上游节点模型和 Prompt（没有则写“无”）：
```

---

## 填写完成后的处理

收到填写结果后，我会：

1. 按最终视频节点真实输入重新核验链路类型。
2. 提炼卖点和标签，不要求人工标注。
3. 将 Prompt 归属到对应节点，不放在 case 顶层。
4. 只把链路闭合、Prompt 可定位的案例写入正式案例库。
5. 校验两类正式案例是否均达到 15 个；被淘汰的候选会说明原因，不用数量掩盖分类问题。
