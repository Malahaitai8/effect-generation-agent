const originalDashboard = dashboard;
const chainNames = {single_image:"单图驱动",reference_video:"参考视频驱动",multi_image:"多图驱动",unsupported:"需要人工设计"};
const tagNames = {state_transformation:"状态变化",reveal_or_micro_narrative:"微叙事揭示",action_performance:"动作表演",physical_interaction:"物理交互",camera_or_composition:"镜头与构图",pet_anthropomorphism:"宠物拟人",style_transformation:"风格转换",scene_spectacle:"场景奇观",effect_spectacle:"视觉特效"};
const priorityNames = {high:"高优先级",normal:"普通",low:"低优先级"};
const stepNames = {1:"正在理解视频",2:"正在提炼核心卖点",3:"正在选择特效链路",4:"正在设计生成节点",5:"正在准备固定素材",6:"正在编写节点生成指令",7:"正在校验交付方案"};
const nodeNames = {generate_first_frame:"生成视频首帧",generate_subject_image:"生成主体形象",generate_video:"生成特效视频",prepare_reference_video:"准备参考视频"};
const inputNames = {user_image:"用户主体图",user_pet_image:"用户宠物图",first_frame:"视频首帧",subject_image:"主体形象图",reference_video:"参考视频",generated_video:"生成的特效视频",result_video:"生成的特效视频"};
const displayName = (value,map) => map[value] || (value ? "自定义内容" : "无");
const modelName = value => !value ? "无需生成模型" : value.replace(/Kling/gi,"可灵").replace(/Omni/gi,"全能版").replace(/image2/gi,"图像生成模型");
const localizeText = value => String(value||"").replace(/\bCG\b/gi,"三维动画").replace(/\b3D\b/gi,"三维");
const cleanBusinessText = value => localizeText(value)
  .replace(/single_image/gi,"单图驱动").replace(/reference_video/gi,"参考视频驱动")
  .replace(/multi_image/gi,"多图驱动").replace(/unsupported/gi,"当前不支持")
  .replace(/needs_input/gi,"待补充").replace(/Kling/gi,"可灵").replace(/Omni/gi,"全能版")
  .replace(/image2/gi,"图像生成模型")
  .replace(/medium/gi,"中等").replace(/\bimage\b/gi,"图像").replace(/\bvideo\b/gi,"视频")
  .replace(/Manual result required[^\n]*/gi,"该步骤需要补充人工分析结果后继续处理。")
  .replace(/\/[A-Za-z0-9_./\-\u4e00-\u9fa5]+/g,"内部任务文件");
const readableInstruction = (value,node) => {const text=String(value||""),letters=(text.match(/[A-Za-z]/g)||[]).length;if(text&&letters/Math.max(text.length,1)<.25)return localizeText(text);const inputs=(node.inputs||[]).map(x=>displayName(x,inputNames)).join("、")||"已准备素材",outputs=(node.outputs||[]).map(x=>displayName(x,inputNames)).join("、")||"目标内容";return `以${inputs}为基础，使用${modelName(node.model)}生成${outputs}。保持主体身份、造型、场景和构图稳定，按核心卖点完成连续且物理合理的画面变化。`;};
const readableExclusion = value => {const text=String(value||""),letters=(text.match(/[A-Za-z]/g)||[]).length;return !text?"":letters/Math.max(text.length,1)<.25?localizeText(text):"避免主体身份漂移、肢体畸变、道具穿模、画面闪烁和镜头突变。";};
const progressCopy = work => ({pending: ["等待开始", "任务已创建，即将开始分析参考视频。"],analyzing:[stepNames[work.agent_task.current_step]||"正在分析","分析完成后会自动进入方案审核。"],needs_input:["等待补充内容",(work.agent_task.issues||[])[0]?.message||"请补充任务所需内容。"],pending_review:["方案已生成，等待设计审核","请检查链路、节点、Prompt 和风险后提交审核。"],editing:["设计师正在修改","修改保存后，系统会重新校验方案完整性。"],deliverable:["方案可交付","完整性校验已通过，可确认交付。"],completed:["方案已交付","当前版本已冻结，后续修改将产生新版本。"],failed:["处理失败",(work.agent_task.issues||[])[0]?.message||"请重试当前任务。"],unsupported:["需要人工设计","当前需求超出自动化链路能力，请由设计师接管。"]}[work.business_status]||["等待处理","请稍后刷新任务状态。"]);
function handleVideoError(video){const box=video.closest(".video-box");box.innerHTML=`<div class="video-fallback"><b>原视频暂时无法播放</b><small>可继续查看下方参考帧</small></div>`;}
async function loadReferenceFrames(id){const container=document.querySelector("#reference-frames");if(!container)return;try{const data=await api(`/api/tasks/${id}/reference-frames`),frames=data.frames||[];if(!frames.length){container.innerHTML=`<img class="timeline-overview" src="/api/tasks/${id}/timeline-preview" alt="时间线总览" onerror="this.replaceWith(Object.assign(document.createElement('p'),{className:'muted',textContent:'暂无可用参考帧'}))">`;return}container.innerHTML=frames.map((frame,index)=>`<button type="button" class="reference-frame${index===0?" active":""}" data-time="${Number(frame.timestamp_seconds)||0}" title="${esc(frame.description||"关键参考帧")}"><img src="${esc(frame.url)}" alt="${esc(frame.description||frame.frame_id)}"><span>${Math.max(0,Number(frame.timestamp_seconds)||0).toFixed(1)}s</span></button>`).join("");container.querySelectorAll(".reference-frame").forEach(button=>button.onclick=()=>{container.querySelectorAll(".reference-frame").forEach(item=>item.classList.toggle("active",item===button));const player=document.querySelector(".video-box video");if(player){player.currentTime=Number(button.dataset.time)||0;player.pause();}})}catch(error){container.innerHTML=`<p class="muted">参考帧加载失败：${esc(error.message)}</p>`;}}
function enableNodeEditing(plan){document.querySelectorAll(".detailed-node").forEach((card,index)=>{const node=plan.nodes[index],prompt=(plan.node_prompts||[]).find(item=>item.node_id===node.id);card.dataset.nodeId=node.id;const name=card.querySelector(".node-title b"),nameInput=document.createElement("input");nameInput.className="node-name-input";nameInput.value=node.display_name||name.textContent;name.replaceWith(nameInput);const modelCell=card.querySelector("dl dd"),modelInput=document.createElement("input");modelInput.className="node-model-input";modelInput.value=modelName(node.model);modelCell.replaceChildren(modelInput);card.querySelectorAll(".instruction-copy").forEach((block,variantIndex)=>{const paragraph=block.querySelector("p"),area=document.createElement("textarea");area.className="node-prompt-input";area.dataset.variantIndex=variantIndex;area.value=paragraph?.textContent||"";paragraph?.replaceWith(area);});});}

const taskUi={mode:"view",dirty:false,taskId:null,version:null,expanded:new Set(),savedAt:null,error:""};
function setInlineError(message=""){taskUi.error=message;const box=document.querySelector("#action-error");if(box){box.textContent=message;box.hidden=!message;}}
function setDirty(value){taskUi.dirty=!!value;const badge=document.querySelector("#save-state");if(badge){badge.textContent=taskUi.dirty?"有未保存修改":taskUi.savedAt?`已保存 · ${taskUi.savedAt}`:"尚未修改";badge.classList.toggle("dirty",taskUi.dirty);}document.querySelectorAll("[data-requires-clean]").forEach(button=>button.disabled=taskUi.dirty);window.onbeforeunload=taskUi.dirty?()=>"当前方案还有未保存修改。":null;}
function markTaskDirty(){setDirty(true);setInlineError("");}
function bindDirtyEvents(){document.querySelectorAll("#selling,#chain,#reason,.node-name-input,.node-model-input,.node-prompt-input").forEach(control=>{control.addEventListener("input",markTaskDirty);control.addEventListener("change",markTaskDirty);});}
function togglePrompt(nodeId,force){const card=[...document.querySelectorAll(".detailed-node")].find(item=>item.dataset.nodeId===nodeId);if(!card)return;const open=force===undefined?!card.classList.contains("prompt-open"):force;card.classList.toggle("prompt-open",open);const button=card.querySelector(".prompt-toggle");if(button)button.textContent=open?"收起 Prompt":"展开 Prompt";if(open)taskUi.expanded.add(nodeId);else taskUi.expanded.delete(nodeId);}
function toggleAllPrompts(open){document.querySelectorAll(".detailed-node").forEach(card=>togglePrompt(card.dataset.nodeId,open));}
function enterEditMode(){if(taskUi.mode==="edit")return;taskUi.mode="edit";document.querySelector(".task-layout")?.classList.add("is-editing");document.querySelectorAll(".view-only").forEach(el=>el.hidden=true);document.querySelectorAll(".edit-only").forEach(el=>el.hidden=false);setDirty(false);setInlineError("");}
function cancelTaskEdit(){taskUi.mode="view";taskUi.dirty=false;window.onbeforeunload=null;task(taskUi.taskId);}
function rememberBatchView(){if(!location.hash.startsWith("#batches/"))return;sessionStorage.setItem("effectBatchView",JSON.stringify({hash:location.hash,search:document.querySelector("#search")?.value||"",status:document.querySelector("#status-filter")?.value||"",scrollY:window.scrollY}));}
function restoreBatchView(){let state;try{state=JSON.parse(sessionStorage.getItem("effectBatchView")||"null");}catch{return}if(!state||state.hash!==location.hash)return;const search=document.querySelector("#search"),status=document.querySelector("#status-filter");if(search)search.value=state.search;if(status)status.value=state.status;if(search&&status)filterRows();requestAnimationFrame(()=>window.scrollTo(0,state.scrollY||0));}
const baseRoute=route;
route=async function(page,id){const leavingTask=location.hash.startsWith("#task/")&&(page!=="task"||id!==taskUi.taskId);if(leavingTask&&taskUi.dirty&&!confirm("当前方案还有未保存修改，确定离开吗？"))return;if(page==="task")rememberBatchView();if(leavingTask){taskUi.dirty=false;window.onbeforeunload=null;}return baseRoute(page,id);};
window.effectTaskActions={edit:enterEditMode,cancel:cancelTaskEdit,save:()=>saveTask(taskUi.taskId,taskUi.version),submit:()=>submitReview(taskUi.taskId,taskUi.version),deliver:()=>deliver(taskUi.taskId,taskUi.version),prompt:togglePrompt,all:toggleAllPrompts};
dashboard = async function () {
  await originalDashboard();
  document.querySelectorAll(".tag").forEach(label=>{const parts=label.textContent.split("·"),key=parts[0].trim(),count=parts[1]?.trim();label.textContent=`${tagNames[key]||"其他特征"}${count?` · ${count}`:""}`;});
  const hero = document.querySelector(".hero"), primary = hero?.querySelector("button.primary");
  if (hero && primary) {
    const actions = document.createElement("div"); actions.className = "hero-actions";
    const demo = document.createElement("button"); demo.className = "secondary";
    demo.textContent = "加载真实试跑结果"; demo.onclick = seedDemo;
    actions.append(demo, primary); hero.append(actions);
  }
};

createBatch = function () {
  title.textContent = "新建批次";
  app.innerHTML = `<div class="panel form-card compact-create"><div class="panel-head"><div><p class="eyebrow">新建分析批次</p><h3>批量导入热点视频</h3><p class="muted">只需命名批次并选择视频，创建人将根据当前账号自动记录。</p></div><span class="account-chip" id="creator-chip">正在读取账号…</span></div><form id="batch-form"><label class="field full batch-name-field"><span>批次名称</span><input name="name" required autofocus placeholder="例：七夕热点视频第 1 批"></label><label class="field full" style="margin-top:18px"><span>热点视频</span><div class="dropzone"><div class="upload-icon">↑</div><b>拖入多条视频，或点击选择</b><p class="muted">支持常见视频格式</p><input type="file" name="videos" multiple accept="video/*" required><div id="file-count" class="file-count">尚未选择视频</div></div></label><div class="actions"><button type="button" class="secondary" onclick="route('dashboard')">取消</button><button class="primary" type="submit">创建并开始分析</button></div></form></div>`;
  document.querySelector("#batch-form").onsubmit = submitBatch;
  const input = document.querySelector('input[name="videos"]');
  input.onchange = () => document.querySelector("#file-count").textContent = input.files.length ? `已选择 ${input.files.length} 条视频` : "尚未选择视频";
  api("/api/session").then(s => document.querySelector("#creator-chip").textContent = `创建人 · ${s.username}`);
};

async function seedDemo(event) {
  try {
    const button = event?.currentTarget;
    if (button) { button.disabled = true; button.textContent = "正在准备演示…"; }
    const batch = await api("/api/demo/real-results", {method:"POST", body:"{}"});
    toast("已从历史输出加载真实试跑结果"); route("batches", batch.batch_id);
  } catch (error) { toast(error.message); }
}

api("/api/session").then(s => {
  const label=document.querySelector(".identity span"), avatar=document.querySelector(".identity b");
  if(label)label.textContent=s.username;if(avatar)avatar.textContent="我";
});

const originalBatches = batches;
batches = async function (id) {
  await originalBatches(id);
  document.querySelectorAll("tbody tr").forEach(row => {
    const cells=row.querySelectorAll("td"); if(cells.length<5)return;
    const rawPriority=cells[0].querySelector("small")?.textContent;
    if(rawPriority)cells[0].querySelector("small").textContent=priorityNames[rawPriority]||"普通";
    const progress=cells[1].querySelector("small"); if(progress){const n=Number((progress.textContent.match(/\d+/)||[])[0]);progress.textContent=stepNames[n]||"等待继续处理";}
    const route=cells[3].querySelector(".route");if(route)route.textContent=chainNames[route.textContent]||"待选择";
  });
  document.querySelectorAll("th").forEach(th=>{if(th.textContent==="Agent 结论")th.textContent="智能分析结论";});
  document.querySelectorAll(".panel-head .muted").forEach(p=>p.textContent=p.textContent.replace("未标注来源 · 未分组 · ",""));
  restoreBatchView();
};

task = async function (id) {
  nav(""); const w=await api(`/api/tasks/${id}`),p=structuredClone(w.plan),t=w.agent_task,video=t.source?.video_uri||"";
  title.textContent="单条特效方案";
  const prompts=Object.fromEntries((p.node_prompts||[]).map(x=>[x.node_id,x]));
  p.summary=localizeText(p.summary);
  p.selection_reason=cleanBusinessText(p.selection_reason);
  if(p.primary_selling_point?.description)p.primary_selling_point.description=localizeText(p.primary_selling_point.description);
  p.risks=(p.risks||[]).map(r=>typeof r==="string"?cleanBusinessText(r):r);
  (t.issues||[]).forEach(issue=>issue.message=cleanBusinessText(issue.message));
  (w.validation||[]).forEach(issue=>issue.message=cleanBusinessText(issue.message));
  const progress=progressCopy(w);
  (p.nodes||[]).forEach(node=>{const instruction=prompts[node.id];(instruction?.variants||[]).forEach(variant=>{variant.prompt=readableInstruction(variant.prompt,node);});});
  const nodes=(p.nodes||[]).map((n,index)=>{const instruction=prompts[n.id];return `<div class="node detailed-node"><div class="node-title"><span>${index+1}</span><b>${esc(displayName(n.id,nodeNames))}</b></div><dl><dt>使用模型</dt><dd>${esc(modelName(n.model))}</dd><dt>所需内容</dt><dd>${esc((n.inputs||[]).map(x=>displayName(x,inputNames)).join("、")||"无")}</dd><dt>产出内容</dt><dd>${esc((n.outputs||[]).map(x=>displayName(x,inputNames)).join("、")||"无")}</dd></dl>${instruction?`<div class="instruction"><b>生成指令</b>${instruction.variants.map((v,i)=>`<div class="instruction-copy">${instruction.variants.length>1?`<small>版本 ${i+1}</small>`:""}<p>${esc(v.prompt||"待补充")}</p></div>`).join("")}</div>`:`<p class="muted node-wait">当前节点的生成指令尚未完成。</p>`}</div>`}).join("");
  app.innerHTML=`<div class="task-layout"><aside class="left sticky"><div class="section-card evidence-card"><h3>原视频</h3><div class="video-box">${video?`<video controls preload="metadata" src="/api/tasks/${id}/media"></video>`:"待上传"}</div><div class="reference-frame-head"><b>参考帧</b><small>点击定位原视频</small></div><div id="reference-frames" class="reference-frames"><span class="muted">正在读取参考帧…</span></div><b class="source-title">${esc(t.source?.title||"未命名视频")}</b><p class="muted">${esc(p.summary||"正在理解视频内容")}</p></div><div class="section-card"><h3>当前进度</h3><p class="muted">${stepNames[t.current_step]||"等待处理"}</p><p class="muted">${(t.issues||[]).map(i=>esc(i.message)).join("<br>")||"暂无需要处理的异常"}</p></div></aside><section class="editor"><div class="section-card"><h3>1. 核心卖点</h3><textarea id="selling">${esc(p.primary_selling_point?.description||"")}</textarea><p class="muted">标签：${(p.primary_selling_point?.tags||[]).map(x=>`<span class="tag">${esc(tagNames[x]||"其他特征")}</span>`).join("")||"暂无"}</p></div><div class="section-card"><h3>2. 特效链路选择</h3><select id="chain"><option value="single_image">单图驱动</option><option value="reference_video">参考视频驱动</option><option value="multi_image">多图驱动</option><option value="unsupported">需要人工设计</option></select><textarea id="reason" style="margin-top:10px" placeholder="链路选择理由">${esc(p.selection_reason||"")}</textarea></div><div class="section-card"><h3>3. 输入与素材</h3><b>未来使用特效时提供</b><p class="muted">${p.runtime_inputs.map(x=>esc(displayName(x.id,inputNames))).join("、")||"无"}</p><b>本次方案已准备素材</b><p class="muted">${p.base_materials.map(x=>esc(displayName(x.id,inputNames))).join("、")||"无"}</p></div><div class="section-card"><h3>4. 生成节点与指令</h3>${nodes||`<div class="empty-stage"><b>${stepNames[t.current_step]||"正在处理"}</b><p>完成链路设计后，这里会按执行顺序展示节点，并在每个节点内展示对应的生成指令。</p></div>`}</div><div class="section-card"><h3>5. 风险与交付</h3>${p.risks.map(r=>`<div class="issue">${esc(typeof r==="string"?r:"存在一项待验证风险")}</div>`).join("")||`<p class="muted">暂无已记录风险</p>`}</div></section><aside class="right sticky"><div class="section-card"><h3>交付校验</h3>${w.validation.length?w.validation.map(i=>`<div class="issue">${esc(i.message)}</div>`).join(""):`<div class="ok">✓ 当前方案结构完整</div>`}<div class="actions" style="display:grid"><button class="secondary" onclick="saveTask('${id}',${w.version})">保存草稿</button><button class="secondary" onclick="submitReview('${id}',${w.version})">提交审核</button><button class="primary" onclick="deliver('${id}',${w.version})">确认交付</button></div></div><div class="section-card"><h3>版本记录</h3><div class="timeline">${w.revisions.map((r,i)=>`<div><b>修订版本 ${w.revisions.length-i}</b><br>${esc(r.actor)} · ${new Date(r.created_at).toLocaleString()}</div>`).join("")||`<div>智能分析原始版本</div>`}</div></div></aside></div>`;
  const progressCard=document.querySelector(".task-layout .left .section-card:nth-child(2)");
  progressCard.classList.add("progress-card");progressCard.innerHTML=`<h3>任务状态</h3><strong>${esc(progress[0])}</strong><p class="muted">${esc(progress[1])}</p>`;
  document.querySelectorAll(".instruction > b:first-child").forEach(label=>label.textContent="Prompt");
  const materialCard=document.querySelector(".editor .section-card:nth-child(3)");
  materialCard.innerHTML=`<h3>3. 输入与素材</h3><div class="material-line"><b>用户输入</b><span>${p.runtime_inputs.map(x=>esc(displayName(x.id,inputNames))).join("、")||"无"}</span></div><div class="material-line"><b>默认输入素材</b><span>${p.base_materials.map(x=>esc(displayName(x.id,inputNames))).join("、")||"无"}</span></div>`;
  enableNodeEditing(p);
  const player=document.querySelector(".video-box video");if(player)player.onerror=()=>handleVideoError(player);
  loadReferenceFrames(id);
  document.querySelector("#chain").value=p.selected_chain||"single_image";window.currentWork=w;window.currentDisplayPlan=p;
};

saveTask = async function(id,version){const plan=structuredClone(window.currentWork.plan);plan.primary_selling_point=plan.primary_selling_point||{};plan.primary_selling_point.description=document.querySelector("#selling").value;plan.selected_chain=document.querySelector("#chain").value;plan.selection_reason=document.querySelector("#reason").value;document.querySelectorAll(".detailed-node").forEach((card,index)=>{const node=plan.nodes[index],shown=window.currentDisplayPlan.nodes[index];node.display_name=card.querySelector(".node-name-input").value.trim()||displayName(node.id,nodeNames);const modelValue=card.querySelector(".node-model-input").value.trim();if(modelValue!==modelName(shown.model))node.model=modelValue;const prompt=(plan.node_prompts||[]).find(item=>item.node_id===node.id),shownPrompt=(window.currentDisplayPlan.node_prompts||[]).find(item=>item.node_id===shown.id);card.querySelectorAll(".node-prompt-input").forEach((area,variantIndex)=>{const originalShown=shownPrompt?.variants?.[variantIndex]?.prompt||"";if(area.value!==originalShown&&prompt?.variants?.[variantIndex])prompt.variants[variantIndex].prompt=area.value;});});try{await api(`/api/tasks/${id}/revisions`,{method:"POST",body:JSON.stringify({plan,actor:"设计师",reason:"工作台结构化修改",expected_version:version})});toast("草稿已保存");task(id)}catch(error){toast(error.message)}};

const contentName=value=>inputNames[value]||value||"无";
const nodePrompt=(plan,nodeId)=>(plan.node_prompts||[]).find(item=>item.node_id===nodeId);
function recomputeNodeDependencies(plan){const owner={};(plan.nodes||[]).forEach(node=>(node.outputs||[]).forEach(output=>owner[output]=node.id));(plan.nodes||[]).forEach(node=>{node.dependencies=[...new Set((node.inputs||[]).map(input=>owner[input]).filter(id=>id&&id!==node.id))];node.needs_input=!(node.inputs||[]).length;});}
function renderPlanNodes(){
  const section=document.querySelector(".nodes-section"),plan=taskUi.editPlan;if(!section||!plan)return;
  const runtime=[...(plan.runtime_inputs||[]),...(plan.base_materials||[])].map(item=>item.id);
  const cards=(plan.nodes||[]).map((node,index)=>{
    const available=[...runtime];for(let i=0;i<index;i++)available.push(...(plan.nodes[i].outputs||[]));
    const prompt=nodePrompt(plan,node.id),promptText=prompt?.variants?.[0]?.prompt||"";
    const choices=available.map(value=>`<label><input type="checkbox" value="${esc(value)}" ${(node.inputs||[]).includes(value)?"checked":""}> <span>${esc(contentName(value))}</span></label>`).join("")||`<span class="muted">暂无可选内容</span>`;
    return `<div class="node detailed-node${node.needs_input?" node-needs-input":""}" data-node-id="${esc(node.id)}"><div class="node-title"><span>${index+1}</span><b class="view-only">${esc(node.display_name||displayName(node.id,nodeNames))}</b><input class="node-name-input edit-only" hidden value="${esc(node.display_name||displayName(node.id,nodeNames))}"><button type="button" class="text-button danger-text edit-only delete-node" hidden>删除</button></div><dl><dt>使用模型</dt><dd><span class="view-only">${esc(modelName(node.model))}</span><input class="node-model-input edit-only" hidden value="${esc(node.model||"")}" placeholder="填写模型名称"></dd><dt>所需内容</dt><dd><span class="view-only">${esc((node.inputs||[]).map(contentName).join("、")||"无")}</span><div class="node-input-picker edit-only" hidden>${choices}</div></dd><dt>产出内容</dt><dd><span class="view-only">${esc((node.outputs||[]).map(contentName).join("、")||"无")}</span><input class="node-output-input edit-only" hidden value="${esc((node.outputs||[]).join("、"))}" placeholder="多个产出用顿号分隔"></dd></dl>${node.needs_input?`<div class="node-warning">需要补充输入后才能提交审核</div>`:""}<div class="instruction"><div class="prompt-head"><b>Prompt</b><button type="button" class="text-button prompt-toggle">${taskUi.expanded.has(node.id)?"收起 Prompt":"展开 Prompt"}</button></div><div class="prompt-content"><div class="instruction-copy"><p class="view-only prompt-copy">${esc(promptText||"待补充")}</p><textarea class="node-prompt-input edit-only" hidden placeholder="填写该节点的 Prompt">${esc(promptText)}</textarea></div></div></div></div>`;
  }).join("");
  section.innerHTML=`<div class="section-heading"><h3>4. 生成节点与指令</h3><div><button type="button" class="text-button edit-only add-node" hidden>＋ 新增节点</button><button type="button" class="text-button" data-all="open">全部展开</button><button type="button" class="text-button" data-all="close">全部收起</button></div></div>${cards||`<div class="empty-stage"><b>尚未添加生成节点</b><p>进入编辑模式后，可新增第一个节点。</p></div>`}`;
  section.querySelector('[data-all="open"]')?.addEventListener("click",()=>toggleAllPrompts(true));section.querySelector('[data-all="close"]')?.addEventListener("click",()=>toggleAllPrompts(false));section.querySelector(".add-node")?.addEventListener("click",addPlanNode);
  section.querySelectorAll(".detailed-node").forEach(card=>{
    const node=plan.nodes.find(item=>item.id===card.dataset.nodeId);card.classList.toggle("prompt-open",taskUi.expanded.has(node.id));
    card.querySelector(".prompt-toggle").onclick=()=>togglePrompt(node.id);
    card.querySelector(".node-name-input").oninput=e=>{node.display_name=e.target.value;markTaskDirty();};
    card.querySelector(".node-model-input").oninput=e=>{node.model=e.target.value;markTaskDirty();};
    card.querySelector(".node-prompt-input").oninput=e=>{let item=nodePrompt(plan,node.id);if(!item){item={node_id:node.id,model:node.model,variants:[{prompt:"",negative_prompt:""}]};plan.node_prompts.push(item);}item.variants[0].prompt=e.target.value;markTaskDirty();};
    card.querySelectorAll(".node-input-picker input").forEach(input=>input.onchange=()=>{node.inputs=[...card.querySelectorAll(".node-input-picker input:checked")].map(item=>item.value);recomputeNodeDependencies(plan);markTaskDirty();renderPlanNodes();});
    card.querySelector(".node-output-input").oninput=markTaskDirty;card.querySelector(".node-output-input").onchange=e=>renameNodeOutputs(node.id,e.target.value);
    card.querySelector(".delete-node").onclick=()=>deletePlanNode(node.id);
  });
  if(taskUi.mode==="edit"){document.querySelector(".task-layout")?.classList.add("is-editing");section.querySelectorAll(".view-only").forEach(el=>el.hidden=true);section.querySelectorAll(".edit-only").forEach(el=>el.hidden=false);}
}
function addPlanNode(){const plan=taskUi.editPlan,id=`custom_node_${Date.now()}`;plan.nodes.push({id,display_name:"新生成节点",role:"",model:"",inputs:[],outputs:[],dependencies:[],parameters:{},needs_input:true});plan.node_prompts=plan.node_prompts||[];plan.node_prompts.push({node_id:id,model:"",variants:[{prompt:"",negative_prompt:""}]});markTaskDirty();renderPlanNodes();}
function renameNodeOutputs(nodeId,value){const plan=taskUi.editPlan,node=plan.nodes.find(item=>item.id===nodeId),before=[...(node.outputs||[])],after=value.split(/[、,，]/).map(item=>item.trim()).filter(Boolean);const reserved=new Set([...(plan.runtime_inputs||[]),...(plan.base_materials||[])].map(item=>item.id));const used=new Set(plan.nodes.filter(item=>item.id!==nodeId).flatMap(item=>item.outputs||[]));const duplicate=after.find((item,index)=>reserved.has(item)||used.has(item)||after.indexOf(item)!==index);if(duplicate){setInlineError(`产出内容“${duplicate}”已存在，请换一个名称。`);renderPlanNodes();return;}node.outputs=after;before.forEach((old,index)=>{const replacement=after[index];plan.nodes.forEach(other=>{if(other.id===nodeId)return;other.inputs=(other.inputs||[]).flatMap(input=>input===old?(replacement?[replacement]:[]):[input]);});});recomputeNodeDependencies(plan);markTaskDirty();renderPlanNodes();}
function deletePlanNode(nodeId){const plan=taskUi.editPlan,node=plan.nodes.find(item=>item.id===nodeId),outputs=node?.outputs||[],affected=plan.nodes.filter(item=>item.id!==nodeId&&((item.dependencies||[]).includes(nodeId)||(item.inputs||[]).some(input=>outputs.includes(input))));const detail=affected.length?`\n将同时清理 ${affected.map(item=>item.display_name||displayName(item.id,nodeNames)).join("、")} 的相关输入引用。`:"";if(!confirm(`确定删除“${node.display_name||displayName(node.id,nodeNames)}”吗？${detail}`))return;plan.nodes=plan.nodes.filter(item=>item.id!==nodeId);plan.node_prompts=(plan.node_prompts||[]).filter(item=>item.node_id!==nodeId);plan.nodes.forEach(item=>{item.inputs=(item.inputs||[]).filter(input=>!outputs.includes(input));item.dependencies=(item.dependencies||[]).filter(id=>id!==nodeId);});recomputeNodeDependencies(plan);affected.forEach(removed=>{const current=plan.nodes.find(item=>item.id===removed.id);if(current)current.needs_input=true;});markTaskDirty();renderPlanNodes();}

const renderedTask=task;
task=async function(id){
  if(taskUi.taskId!==id)taskUi.savedAt=null;
  taskUi.mode="view";taskUi.dirty=false;taskUi.taskId=id;taskUi.expanded.clear();window.onbeforeunload=null;
  await renderedTask(id);taskUi.version=window.currentWork.version;taskUi.editPlan=structuredClone(window.currentDisplayPlan);
  const work=window.currentWork,sourceTitle=work.agent_task.source?.title||work.agent_task.source?.video_uri?.split("/").pop()?.replace(/\.[^.]+$/,"")||"未命名视频",progress=progressCopy(work);
  title.textContent=`${sourceTitle}特效复刻方案`;document.querySelector("#task-meta")?.remove();const meta=document.createElement("p");meta.id="task-meta";meta.className="task-meta";meta.innerHTML=`<span>上传者：${esc(work.uploader||"未知")}</span><span>上传时间：${esc(new Date(work.uploaded_at||work.created_at).toLocaleString())}</span><span class="task-status-pill">${esc(progress[0])}</span>`;title.insertAdjacentElement("afterend",meta);
  document.querySelector(".task-layout .left .section-card:nth-child(2)")?.remove();
  const selling=document.querySelector("#selling"),chain=document.querySelector("#chain"),reason=document.querySelector("#reason");[selling,chain,reason].forEach(control=>{if(control){control.classList.add("edit-only");control.hidden=true;}});if(selling)selling.insertAdjacentHTML("beforebegin",`<div class="view-only readable-copy">${esc(selling.value||"暂无")}</div>`);if(chain){const summary=document.createElement("div");summary.className="view-only chain-summary";summary.innerHTML=`<b>${esc(chainNames[chain.value]||"待选择")}</b><p>${esc(reason?.value||"暂无选择理由")}</p>`;chain.parentElement.insertBefore(summary,chain);}
  const nodeSection=document.querySelector(".editor .section-card:nth-child(4)");nodeSection?.classList.add("nodes-section");renderPlanNodes();
  const actionCard=document.querySelector(".task-layout .right .section-card:first-child");if(actionCard){const heading=actionCard.querySelector("h3"),actions=actionCard.querySelector(".actions");heading.outerHTML=`<div class="action-heading"><h3>交付校验</h3><span id="save-state">${taskUi.savedAt?`已保存 · ${taskUi.savedAt}`:"尚未修改"}</span></div>`;actions.outerHTML=`<div id="action-error" class="inline-error" hidden></div><div class="actions view-only" style="display:grid"><button class="secondary edit-plan">编辑方案</button><button class="secondary submit-plan" data-requires-clean>提交审核</button><button class="primary deliver-plan" data-requires-clean>确认交付</button></div><div class="actions edit-only" hidden style="display:grid"><button class="primary save-plan">保存草稿</button><button class="secondary cancel-plan">取消修改</button></div>`;actionCard.querySelector(".edit-plan").onclick=enterEditMode;actionCard.querySelector(".submit-plan").onclick=()=>submitReview(id,taskUi.version);actionCard.querySelector(".deliver-plan").onclick=()=>deliver(id,taskUi.version);actionCard.querySelector(".save-plan").onclick=()=>saveTask(id,taskUi.version);actionCard.querySelector(".cancel-plan").onclick=cancelTaskEdit;actionCard.parentElement.classList.add("task-actions");}
  bindDirtyEvents();setDirty(false);
};

saveTask=async function(id,version){const plan=structuredClone(taskUi.editPlan);plan.primary_selling_point=plan.primary_selling_point||{};plan.primary_selling_point.description=document.querySelector("#selling").value;plan.selected_chain=document.querySelector("#chain").value;plan.selection_reason=document.querySelector("#reason").value;recomputeNodeDependencies(plan);try{setInlineError("");await api(`/api/tasks/${id}/revisions`,{method:"POST",body:JSON.stringify({plan,actor:"设计师",reason:"工作台结构化修改",expected_version:version})});taskUi.savedAt=new Date().toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"});setDirty(false);toast("草稿已保存");await task(id)}catch(error){setInlineError(error.message.includes("version")||error.message.includes("冲突")?"方案已被其他人更新。你的修改仍保留，请复制当前内容或刷新后重新编辑。":`保存失败：${error.message}`)}};

const baseSubmitReview=submitReview,baseDeliver=deliver;
submitReview=async function(id,version){if(taskUi.dirty){setInlineError("请先保存当前修改，再提交审核。");return}return baseSubmitReview(id,version)};
deliver=async function(id,version){if(taskUi.dirty){setInlineError("请先保存当前修改，再确认交付。");return}if((window.currentWork?.validation||[]).length){setInlineError("当前方案仍有校验问题，暂不能确认交付。");return}return baseDeliver(id,version)};

// app.js 会先渲染初始页，这里用中文展示层重新渲染当前页。
const currentRoute = location.hash.slice(1).split("/");
route(currentRoute[0] || "dashboard", currentRoute[1]);
