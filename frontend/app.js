/* Constants */

const API='http://127.0.0.1:9090',HEALTH_URL='http://127.0.0.1:9090/api/health';

// Fetch interceptor for debugging
const _origFetch=window.fetch;
window.fetch=function(...args){
  const url=args[0] instanceof Request?args[0].url:String(args[0]);
  console.log('[fetch] →',url,'method=',args[1]?.method||'GET');
  return _origFetch.apply(this,args);
};

let currentConvId=null,isStreaming=false,abortCtrl=null;
let newConvSelectedSlug=null;

let currentSkillSlug=null;

let intakeStep=1,intakeData={name:'',summary:'',personality:''},intakeSlug=null;

let analyzeSlug=null,analyzeSource='text',analyzeFile=null;

let correctionSlug=null,correctionLayer='memory';

const $messages=document.getElementById('messages'),$empty=document.getElementById('empty-state');

const $input=document.getElementById('chat-input'),$sendBtn=document.getElementById('send-btn');

const $convList=document.getElementById('conv-list'),$newBtn=document.getElementById('new-chat-btn');

const $clearBtn=document.getElementById('clear-chat-btn'),$title=document.getElementById('current-title');

const $dot=document.getElementById('server-dot'),$statusText=document.getElementById('server-text');

const $toast=document.getElementById('toast'),$skillPanel=document.getElementById('skill-panel');

const PROVIDER_PRESETS={
  tongyi:{base_url:'https://dashscope.aliyuncs.com/compatible-mode/v1',model:'qwen-plus'},
  deepseek:{base_url:'https://api.deepseek.com/v1',model:'deepseek-chat'},
  openai:{base_url:'https://api.openai.com/v1',model:'gpt-4o'},
  zhipu:{base_url:'https://open.bigmodel.cn/api/paas/v4',model:'glm-4'},
  moonshot:{base_url:'https://api.moonshot.cn/v1',model:'moonshot-v1-8k'},
  yi:{base_url:'https://api.01.ai/v1',model:'yi-lightning'},
  anthropic:{base_url:'https://api.anthropic.com/v1',model:'claude-sonnet-4-20250514'},
};



function fmtTime(iso){if(!iso)return'';return new Date(iso).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'});}

function showToast(msg,duration=3000){$toast.textContent=msg;$toast.classList.add('show');setTimeout(()=>$toast.classList.remove('show'),duration);}

function scrollToBottom(){$messages.scrollTop=$messages.scrollHeight;}

function setSendState(loading){isStreaming=loading;$sendBtn.disabled=loading;$input.disabled=loading;}

function escHtml(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}

function autoResize(){$input.style.height='auto';$input.style.height=Math.min($input.scrollHeight,120)+'px';}

function formatAiContent(text){
  if(!text)return'';
  text=text.replace(/<think(?:ing)?\b>[\s\S]*?<\/think(?:ing)?>/gi,'');
  text=text.replace(/\n{3,}/g,'\n\n');
  return escHtml(text).replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>').replace(/\n/g,'<br>');
}



async function checkServer(){
  console.log('[checkServer] called');
  try{

    const _c=new AbortController();

    const _t=setTimeout(()=>_c.abort(),2000);

    const r=await fetch(HEALTH_URL,{signal:_c.signal});

    clearTimeout(_t);

    if(r.ok){const d=await r.json();$dot.className='ok';$statusText.textContent=d.llama==='ready'?'后端已连接':'后端运行中(llama未就绪)';}

    else{$dot.className='';$statusText.textContent='后端未连接';}

  }catch(e){

    if(e.name!=='AbortError'){$dot.className='';$statusText.textContent='后端未连接';}

  }

}checkServer();setInterval(checkServer,8000);
console.log('[init] checkServer started, HEALTH_URL='+HEALTH_URL+', API='+API);

function toggleSkillPanel(){

  const isOpen=!$skillPanel.classList.contains('collapsed');
  $skillPanel.classList.toggle('collapsed');
  document.getElementById('mode-toggle-btn').classList.toggle('active',!isOpen);
  if(!isOpen)loadSkills();

}



async function loadConversations(){

  try{

    const r=await fetch(API+'/api/conversations');const convs=await r.json();

    $convList.innerHTML='';

    if(convs.length===0){$convList.innerHTML='<div style="padding:16px;text-align:center;color:var(--text-muted);font-size:12px">暂无对话</div>';return;}

    convs.forEach(c=>{

      const el=document.createElement('div');

      el.className='conv-item'+(c.id===currentConvId?' active':'');

      el.innerHTML="<div class='conv-info'><div class='conv-title'>"+escHtml(c.title)+"</div><div class='conv-meta'>"+c.message_count+" 条消息 "+fmtTime(c.updated_at)+"</div></div><button class='conv-delete' data-id='"+escHtml(c.id)+"' title='删除'>x</button>";

      el.querySelector('.conv-info').addEventListener('click',()=>switchConv(c.id));

      el.querySelector('.conv-delete').addEventListener('click',e=>{e.stopPropagation();deleteConv(c.id);});

      $convList.appendChild(el);

    });

  }catch(err){console.error('loadConversations failed:',err);}

}



async function switchConv(id){

  currentConvId=id;

  const r=await fetch(API+'/api/conversations/'+id);const data=await r.json();

  const skillSlug=data.skill_slug||null;

  if(skillSlug&&skillSlug!==currentSkillSlug){

    currentSkillSlug=skillSlug;
    toggleSkillPanel();

  }

  $title.textContent=data.title||'对话';

  renderMessages(data.messages||[]);

  document.querySelectorAll('.conv-item').forEach(el=>{el.classList.toggle('active',el.querySelector('.conv-delete')?.dataset.id===id);});

}



async function newConversation(){openNewConvModal();}

function openNewConvModal(){
  newConvSelectedSlug=currentSkillSlug||null;
  const $modal=document.getElementById('new-conv-modal');
  const $list=document.getElementById('new-conv-char-list');
  $list.innerHTML='<div class="char-select-empty">加载中…</div>';
  $modal.classList.add('open');
  loadConversations();
  loadSkillsForNewConv();
}
async function loadSkillsForNewConv(){
  try{
    const resp=await fetch(API+'/api/skills');
    const skills=await resp.json();
    const $list=document.getElementById('new-conv-char-list');
    if(skills.length===0){
      $list.innerHTML='<div class="char-select-empty">还没有角色，请先创建</div>';
      return;
    }
    $list.innerHTML='';
    skills.forEach(s=>{
      const el=document.createElement('div');
      el.className='char-select-item'+(s.slug===newConvSelectedSlug?' selected':'');
      el.dataset.slug=s.slug;
      el.innerHTML='<div class="char-select-avatar">'+escHtml((s.name||s.slug).slice(0,1))+'</div><div class="char-select-info"><div class="char-select-name">'+escHtml(s.name||s.slug)+'</div><div class="char-select-desc">'+(s.summary||'暂无描述')+'</div></div>';
      el.addEventListener('click',()=>selectNewConvChar(s.slug));
      $list.appendChild(el);
    });
  }catch(e){console.error('loadSkillsForNewConv error',e);}
}
function closeNewConvModal(){document.getElementById('new-conv-modal').classList.remove('open');}
function selectNewConvChar(slug){
  newConvSelectedSlug=slug;
  document.querySelectorAll('#new-conv-char-list .char-select-item').forEach(el=>{
    el.classList.toggle('selected',el.dataset.slug===slug);
  });
  // 选择角色后立即预览角色详情
  if(slug) loadSkillDetail(slug);
}
async function startNewConvWithSelection(){
  closeNewConvModal();
  currentConvId=null;$title.textContent='新建对话';
  $messages.innerHTML='';$messages.appendChild($empty);$empty.style.display='';
  if(newConvSelectedSlug&&newConvSelectedSlug!==currentSkillSlug){
    await selectSkill(newConvSelectedSlug);
    showToast('已切换到角色：'+(currentSkillSlug||''));
  }else{
    currentSkillSlug=null;
    showToast('新建空白对话');
  }
  document.querySelectorAll('.conv-item').forEach(el=>el.classList.remove('active'));
}

async function deleteConv(id){

  try{await fetch(API+'/api/conversations/'+id,{method:'DELETE'});

    if(currentConvId===id)newConversation();await loadConversations();

  }catch(err){console.error(err);}

}

function clearChat(){

  $messages.innerHTML='';$messages.appendChild($empty);$empty.style.display='';

  currentConvId=null;$title.textContent='新建对话';

}



function renderMessages(messages){

  $messages.innerHTML='';

  if(!messages||messages.length===0){$messages.appendChild($empty);$empty.style.display='';return;}

  $empty.style.display='none';

  messages.forEach(m=>appendMessage(m.role,m.content,true));

  scrollToBottom();

}

function appendMessage(role,content,silent){

  const row=document.createElement('div');row.className='msg-row '+role;

  const initial=role==='user'?'我':(currentSkillSlug?currentSkillSlug[0].toUpperCase():'X');

  row.innerHTML="<div class='avatar'>"+escHtml(initial)+"</div><div class='bubble'>"+(role==='user'?escHtml(content):formatAiContent(content))+"</div>";

  $messages.appendChild(row);if(!silent)scrollToBottom();return row;

}



async function sendMessage(){

  const text=$input.value.trim();if(!text||isStreaming)return;

  $input.value='';autoResize();

  appendMessage('user',text);setSendState(true);

  const typingRow=appendMessage('ai','',false);

  typingRow.querySelector('.bubble').innerHTML='<div class="typing-indicator"><span></span><span></span><span></span></div>';

  try{

    const endpoint=currentSkillSlug?'/api/skills/'+currentSkillSlug+'/run':'/api/chat';

    const resp=await fetch(API+endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text,conversation_id:currentConvId})});

    if(!resp.ok){const e=await resp.json().catch(()=>({}));throw new Error(e.detail||'HTTP '+resp.status);}

    const data=await resp.json();

    if(data.conversation_id)currentConvId=data.conversation_id;

    typingRow.querySelector('.bubble').innerHTML=formatAiContent(data.response);

    scrollToBottom();await loadConversations();

  }catch(err){

    const lastRow=$messages.lastElementChild;

    if(lastRow&&lastRow.querySelector('.typing-indicator'))lastRow.remove();

    showToast('发送失败：'+err.message);console.error(err);

  }finally{setSendState(false);}

}



async function loadSkills(){

  try{const resp=await fetch(API+'/api/skills');if(!resp.ok)return;renderSkillList(await resp.json());}

  catch(e){console.error('loadSkills error',e);}

}

function renderSkillList(skills){

  const $list=document.getElementById('skills-list');

  if(!skills||!skills.length){

    $list.innerHTML='<div class="skills-empty"><div class="skills-empty-icon">x</div><div class="skills-empty-text">还没有角色？<br>点击上方创建角色开始</div></div>';return;

  }

  $list.innerHTML=skills.map(s=>'<div class="skill-card '+(s.slug===currentSkillSlug?'active':'')+'" data-slug="'+escHtml(s.slug)+'" onclick=\'selectSkill("'+escHtml(s.slug)+'")\'><div class="skill-card-name">'+escHtml(s.name)+'</div><div class="skill-card-meta"><span>'+s.created_at?.slice(0,10)+' v'+s.version+'</span><span class="skill-card-status '+(s.has_skill?'ready':s.has_memory?'incomplete':'empty')+'">'+(s.has_skill?'就绪':s.has_memory?'部分':'未开始')+'</span><span class="skill-card-source '+(s.source==='import'?'cloud':'local')+'">'+(s.source==='import'?'API':'本地')+'</span></div></div>').join('');

}

async function selectSkill(slug){

  currentSkillSlug=slug;

  document.querySelectorAll('.skill-card').forEach(el=>{el.classList.toggle('active',el.dataset.slug===slug);});

  const data=await loadSkillDetail(slug);

  if(data){showToast('已切换到角色：'+(data.name||slug));}

}

async function loadSkillDetail(slug){
  try{
    const resp=await fetch(API+'/api/skills/'+slug);if(!resp.ok)return null;const data=await resp.json();renderSkillDetail(data);return data;
  }catch(e){console.error('loadSkillDetail error',e);return null;}
}

function renderSkillDetail(s){

  const $panel=document.getElementById('skill-detail-panel');

  const initial=(s.name||s.slug||'?')[0].toUpperCase();

  const canChat=s.has_skill;

  const memText=s.memory?escHtml(s.memory):'<div class="skill-section-empty">尚未生成</div>';

  const perText=s.persona?escHtml(s.persona):'<div class="skill-section-empty">尚未生成</div>';

  const skillText=s.skill_md?escHtml(s.skill_md):'<div class="skill-section-empty">尚未生成</div>';

  $panel.innerHTML=

    '<div class="skill-detail-header"><div class="skill-detail-avatar">'+escHtml(initial)+'</div><div class="skill-detail-info"><div class="skill-detail-name">'+escHtml(s.name||s.slug)+'</div><div class="skill-detail-summary">'+escHtml(s.profile?.summary||'暂无简介')+'</div><div class="skill-detail-version">创建人: '+s.created_at?.slice(0,10)+' v'+s.version+' <span class="skill-card-source '+(s.source==="import"?"cloud":"local")+'">'+(s.source==="import"?"在线模型":"本地模型")+'</span></div></div></div>'+

    '<div class="skill-detail-actions">'+

      '<button class="skill-action-btn" onclick=\'startSkillChat("'+escHtml(s.slug)+'")\' '+(canChat?'':'disabled style="opacity:0.4"')+'>聊天: '+escHtml(s.name||s.slug)+'</button>'+

      '<button class="skill-action-btn" onclick=\'openAnalyzeModal("'+escHtml(s.slug)+'")\'>导入材料分析</button>'+

      '<button class="skill-action-btn" onclick=\'openCorrectionModal("'+escHtml(s.slug)+'")\' '+( !s.has_memory&&!s.has_persona?'disabled style="opacity:0.4"':'')+'>纠正记忆</button>'+

      '<button class="skill-action-btn danger" onclick=\'deleteSkill("'+escHtml(s.slug)+'")\'>删除</button>'+

    '</div>';

  if(s.has_memory||s.has_persona){

    $panel.innerHTML+='<div class="detail-tabs">'+

      '<div class="detail-tab active" onclick=\'switchDetailTab("memory",this)\'>关系记忆</div>'+

      '<div class="detail-tab" onclick=\'switchDetailTab("persona",this)\'>人物性格</div>'+

      '<div class="detail-tab" onclick=\'switchDetailTab("skill",this)\'>SKILL.md</div>'+

    '</div>'+

    '<div class="detail-tab-content active" id="detail-memory"><div class="skill-section-body">'+memText+'</div></div>'+

    '<div class="detail-tab-content" id="detail-persona"><div class="skill-section-body">'+perText+'</div></div>'+

    '<div class="detail-tab-content" id="detail-skill"><div class="skill-section-body" style="max-height:400px">'+skillText+'</div></div>';

  }else{

    $panel.innerHTML+='<div class="skill-section"><div class="skill-section-empty" style="padding:20px;text-align:center">还没有记忆数据<br><span style="font-size:11px">点击导入材料分析开始生成</span></div></div>';

  }

}

function switchDetailTab(tab,el){

  document.querySelectorAll('.detail-tab').forEach(t=>t.classList.remove('active'));

  document.querySelectorAll('.detail-tab-content').forEach(c=>c.classList.remove('active'));

  el.classList.add('active');document.getElementById('detail-'+tab)?.classList.add('active');

}

function startSkillChat(slug){

  currentSkillSlug=slug;

  const badge=document.getElementById('skill-tag-badge');if(badge)badge.remove();

  const b=document.createElement('span');b.id='skill-tag-badge';

  b.style.cssText='font-size:11px;background:var(--accent-soft);color:var(--accent);padding:2px 8px;border-radius:4px;white-space:nowrap;margin-left:8px;';

  b.textContent='skill: '+slug;$title.appendChild(b);

  document.querySelectorAll('.conv-item').forEach(el=>el.classList.remove('active'));

}

async function deleteSkill(slug){

  if(!confirm('确定要删除「Skill、'+slug+'」吗？此操作不可恢复。'))return;

  try{

    const resp=await fetch(API+'/api/skills/'+slug,{method:'DELETE'});

    if(!resp.ok){const e=await resp.json().catch(()=>({}));throw new Error('删除失败');}

    showToast('Skill 已删除');currentSkillSlug=null;await loadSkills();

    document.getElementById('skill-detail-panel').innerHTML='<div class="skills-empty"><div class="skills-empty-icon">x</div><div class="skills-empty-text">选择左侧 Skill 查看详情</div></div>';

  }catch(err){showToast('删除失败：'+err.message);console.error(err);}

}



/* ━━ Intake Wizard ━━*/

function openIntakeModal(){

  intakeStep=1;intakeData={name:'',summary:'',personality:''};intakeSlug=null;

  document.getElementById('intake-name').value='';
  document.getElementById('intake-summary').value='';
  document.getElementById('intake-personality').value='';

  updateIntakeUI();document.getElementById('intake-modal').classList.add('open');

  setTimeout(()=>document.getElementById('intake-name').focus(),100);

}

function closeIntakeModal(){document.getElementById('intake-modal').classList.remove('open');}

function updateIntakeUI(){

  for(let i=1;i<=3;i++){

    const dot=document.getElementById('step-dot-'+i),content=document.getElementById('intake-step-'+i);

    dot.className='step-dot'+(i<intakeStep?' done':i===intakeStep?' active':'');

    content.className='step-content'+(i===intakeStep?' active':'');

  }

  document.getElementById('intake-prev-btn').style.display=intakeStep>1?'':'none';

  const nb=document.getElementById('intake-next-btn');

  nb.textContent=intakeStep===3?'创建':'下一步';

}

async function intakeNextStep(){

  if(intakeStep===1){

    const name=document.getElementById('intake-name').value.trim();

    if(!name){showToast('请输入花名');return;}

    intakeData.name=name;intakeStep=2;

  }else if(intakeStep===2){

    intakeData.summary=document.getElementById('intake-summary').value.trim();
    intakeStep=3;

  }else if(intakeStep===3){

    intakeData.personality=document.getElementById('intake-personality').value.trim();

    const resp=await fetch(API+'/api/skills/intake',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:intakeData.name,summary:intakeData.summary,personality:intakeData.personality})});
    if(!resp.ok){const e=await resp.json().catch(()=>({}));showToast('创建失败：'+e.detail);return;}
    const data=await resp.json();intakeSlug=data.slug;

    const autoMaterial=[intakeData.summary,intakeData.personality].filter(Boolean).join('\n\n').trim();

    if(autoMaterial){
      showToast('正在生成角色关系与性格，请稍候...');
      const createBtn=document.getElementById('intake-next-btn');
      const prevCreateText=createBtn.textContent;
      createBtn.disabled=true;createBtn.textContent='生成中...';

      try{
        await fetch(API+'/api/skills/'+intakeSlug+'/analyze-memory',{
          method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({raw_material:autoMaterial,source_type:'text'})
        });
      }catch(err){
        console.error('auto analyze failed',err);
        showToast('角色创建成功，但自动分析失败，请稍后手动分析');
      }

      createBtn.disabled=false;createBtn.textContent=prevCreateText;
    }

    await loadSkills();selectSkill(intakeSlug);
    await loadSkillDetail(intakeSlug);

    closeIntakeModal();
    showToast('「'+intakeData.name+'」角色生成完成！');

    setTimeout(()=>openAnalyzeModal(intakeSlug),300);return;

  }

  updateIntakeUI();

}

function intakePrevStep(){if(intakeStep>1){intakeStep--;updateIntakeUI();}}



/* ━━ Analyze Modal ━━*/

function openAnalyzeModal(slug){

  analyzeSlug=slug;analyzeSource='text';analyzeFile=null;

  document.getElementById('analyze-material').value='';

  document.getElementById('file-info').style.display='none';

  document.getElementById('analyze-progress').classList.remove('active');

  document.getElementById('analyze-run-btn').disabled=false;

  document.getElementById('analyze-run-btn').textContent='开始分析';

  document.querySelectorAll('.source-btn').forEach(btn=>{btn.classList.toggle('active',btn.dataset.source==='text');});

  updateFileMode();

  const s=slug||'';

  document.getElementById('analyze-modal-title').textContent=s?'分析「'+s+'」的材料':'导入材料 生成记忆';

  document.getElementById('analyze-modal').classList.add('open');

  setTimeout(()=>document.getElementById('analyze-material').focus(),100);

}

function closeAnalyzeModal(){document.getElementById('analyze-modal').classList.remove('open');}

function setSource(source,btn){analyzeSource=source;document.querySelectorAll('.source-btn').forEach(b=>b.classList.remove('active'));btn.classList.add('active');}

function handleFileSelect(event){

  const file=event.target.files[0];if(!file)return;analyzeFile=file;

  const sizeKB=(file.size/1024).toFixed(1);

  document.getElementById('file-info').style.display='flex';

  document.getElementById('file-info').innerHTML='已选: '+escHtml(file.name)+' ('+sizeKB+' KB) <span style="color:var(--text-faint);margin-left:8px">将调用微信解析器分析</span>';

  event.target.value='';

  updateFileMode();

}

function handleFileDrop(event){

  event.preventDefault();event.currentTarget.classList.remove('dragover');

  const file=event.dataTransfer.files[0];if(!file)return;analyzeFile=file;

  const sizeKB=(file.size/1024).toFixed(1);

  document.getElementById('file-info').style.display='flex';

  document.getElementById('file-info').innerHTML='已选: '+escHtml(file.name)+' ('+sizeKB+' KB) <span style="color:var(--text-faint);margin-left:8px">将调用微信解析器分析</span>';

  updateFileMode();

}

function updateFileMode(){

  const btn=document.getElementById('analyze-run-btn');
  const hint=document.getElementById('file-mode-hint');

  if(analyzeFile){
    btn.textContent='📄 文件分析';
    if(hint)hint.style.display='block';
  }else{
    btn.textContent='开始分析';
    if(hint)hint.style.display='none';
  }

}

async function runAnalyzeCurrent(){

  if(!analyzeSlug){showToast('请先选择或创建一个Skill');return;}

  const btn=document.getElementById('analyze-run-btn');
  const material=document.getElementById('analyze-material').value.trim();

  btn.disabled=true;btn.textContent='分析中...';
  document.getElementById('analyze-progress').classList.add('active');

  try{

    let rawMaterial=material;
    let sourceType=analyzeSource;

    // 有文件时：先调 import-file 解析，再用解析结果做分析
    if(analyzeFile){
      setProgress(1,'active');
      document.getElementById('prog-1').querySelector('span:last-child').textContent='解析文件...';

      const form=new FormData();
      form.append('file',analyzeFile);
      form.append('source_type',analyzeSource);

      const importResp=await fetch(API+'/api/skills/'+analyzeSlug+'/import-file',{method:'POST',body:form});
      if(!importResp.ok){const e=await importResp.json().catch(()=>({}));throw new Error(e.detail||'文件解析失败');}
      const importData=await importResp.json();

      if(importData.returncode!==0){throw new Error('文件解析失败:'+importData.output);}
      if(!importData.parsed_content){throw new Error('未获取到解析内容');}

      rawMaterial=importData.parsed_content;
      setProgress(1,'done');
      document.getElementById('prog-1').querySelector('span:last-child').textContent='分析关系记忆...';
    }

    if(analyzeSource==='text'){
      if(!rawMaterial){
        rawMaterial='[无材料，仅基于角色简介与性格做轻量分析]';
      }
    }else if(!rawMaterial){showToast('请提供原始材料');btn.disabled=false;btn.textContent='开始分析';return;}

    const memResp=await fetch(API+'/api/skills/'+analyzeSlug+'/analyze-memory',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({raw_material:rawMaterial,source_type:sourceType})});

    if(!memResp.ok){const e=await memResp.json().catch(()=>({}));throw new Error(e.detail||'Memory分析失败');}

    setProgress(1,'done');setProgress(2,'done');
    showToast('分析完成！');closeAnalyzeModal();
    await loadSkillDetail(analyzeSlug);await loadSkills();

  }catch(err){
    showToast('分析失败：'+err.message);console.error(err);
    btn.disabled=false;
    btn.textContent=analyzeFile?'📄 文件分析':'开始分析';
  }

}

function setProgress(step,state){

  const el=document.getElementById('prog-'+step),bar=document.getElementById('bar-'+step);

  el.className='progress-step '+state;

  if(state==='active'){bar.style.width='60%';}else if(state==='done'){bar.style.width='100%';}

}



/* ━━ Correction Modal ━━*/

function openCorrectionModal(slug){

  correctionSlug=slug;correctionLayer='memory';

  document.getElementById('corr-original').value='';

  document.getElementById('corr-correction').value='';

  document.getElementById('corr-note').value='';

  document.querySelectorAll('.corr-layer-btn').forEach(btn=>{btn.classList.toggle('active',btn.dataset.layer==='memory');});

  document.getElementById('correction-modal').classList.add('open');

}

function closeCorrectionModal(){document.getElementById('correction-modal').classList.remove('open');}

function setCorrLayer(layer,btn){correctionLayer=layer;document.querySelectorAll('.corr-layer-btn').forEach(b=>b.classList.remove('active'));btn.classList.add('active');}

async function applyManualCorrection(){

  if(!correctionSlug)return;

  const original=document.getElementById('corr-original').value.trim();

  const correction=document.getElementById('corr-correction').value.trim();

  const note=document.getElementById('corr-note').value.trim();

  if(!original||!correction){showToast('请填写纠正内容');return;}

  try{

    const resp=await fetch(API+'/api/skills/'+correctionSlug+'/correction',{

      method:'POST',headers:{'Content-Type':'application/json'},

      body:JSON.stringify({layer:correctionLayer,original,correction,user_note:note})});

    if(!resp.ok){const e=await resp.json().catch(()=>({}));throw new Error(e.detail||'纠正失败');}

    closeCorrectionModal();showToast('纠正已应用');await loadSkillDetail(correctionSlug);

  }catch(err){showToast('纠正失败：'+err.message);console.error(err);}

}



/* Init */
console.log('[init] starting, API='+API+', HEALTH_URL='+HEALTH_URL);
loadConversations();loadSkills();$input.focus();
console.log('[init] loadConversations/loadSkills fired');

$input.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMessage();}});

$input.addEventListener('input',autoResize);

$newBtn.addEventListener('click',newConversation);
console.log('[init] done');

window.onerror=function(msg,url,line){console.error('[globalError]',msg,'line',line);};

/* ── Settings Modal ── */
let _settingsCache = null;

async function openSettingsModal(){
  const $modal = document.getElementById('settings-modal');
  $modal.classList.add('open');
  try {
    const resp = await fetch(API + '/api/settings');
    const data = await resp.json();
    _settingsCache = data;
    document.getElementById('settings-base-url').value = data.base_url || '';
    document.getElementById('settings-api-key').value = '';
    document.getElementById('settings-api-model').value = data.api_model || 'qwen-plus';
    document.getElementById('settings-provider').value = '';
    updateApiStatusBadge(data.enabled);
  } catch(e) { console.error('load settings failed', e); }
}

function closeSettingsModal(){
  document.getElementById('settings-modal').classList.remove('open');
}

function onProviderChange(){
  const val = document.getElementById('settings-provider').value;
  if(val && PROVIDER_PRESETS[val]){
    const p = PROVIDER_PRESETS[val];
    document.getElementById('settings-base-url').value = p.base_url;
    document.getElementById('settings-api-model').value = p.model;
  }
}

function updateApiStatusBadge(enabled){
  const badge = document.getElementById('api-status-badge');
  if(enabled){
    badge.className = 'api-status on';
    badge.textContent = '已启用';
  } else {
    badge.className = 'api-status off';
    badge.textContent = '未启用';
  }
}

async function saveSettings(){
  const baseUrl = document.getElementById('settings-base-url').value.trim();
  const apiKey = document.getElementById('settings-api-key').value.trim();
  const apiModel = document.getElementById('settings-api-model').value.trim();
  const btn = document.getElementById('settings-save-btn');
  btn.disabled = true;
  btn.textContent = '保存中…';
  try {
    const resp = await fetch(API + '/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_base_url: baseUrl, api_key: apiKey, api_model: apiModel })
    });
    const data = await resp.json();
    if(!resp.ok) throw new Error(data.detail || '保存失败');
    _settingsCache = { enabled: data.enabled, base_url: baseUrl, api_model: apiModel, api_key_display: apiKey ? apiKey.slice(0,4)+'****' : '' };
    updateApiStatusBadge(data.enabled);
    showToast(data.message || '配置已保存');
    closeSettingsModal();
  } catch(err){
    showToast('保存失败：'+err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = '保存配置';
  }
}





