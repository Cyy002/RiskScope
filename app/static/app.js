'use strict';
const P='demo-chamber';
// One-click launcher passes the local demo token in the URL fragment (#token=...); store it for this tab and strip it from the address bar.
(()=>{const m=location.hash.match(/(?:^#|&)token=([^&]+)/);if(m){sessionStorage.setItem('riskscope_token',decodeURIComponent(m[1]));history.replaceState(null,'',location.pathname+location.search)}})();
const state={token:sessionStorage.getItem('riskscope_token')||'',user:null,role:null,page:'overview',lastAnalysis:null};
const el=id=>document.getElementById(id);
const e=x=>String(x??'').replace(/[&<>"']/g, ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const val=id=>el(id)?.value?.trim()||'';
const pretty=x=>JSON.stringify(x,null,2);
const badge=(v,color='gray')=>`<span class="badge ${color}">${e(v)}</span>`;
function message(text){const t=el('toast');t.textContent=text;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),4500)}
async function request(path,options={}){
 const headers={'Authorization':'Bearer '+state.token,...(options.body?{'Content-Type':'application/json'}:{}),...options.headers};
 const response=await fetch(path,{...options,headers,cache:'no-store'});
 let json;try{json=await response.json()}catch{json={detail:'伺服器回傳非 JSON'}}
 if(!response.ok)throw new Error(typeof json.detail==='string'?json.detail:`HTTP ${response.status}: ${pretty(json.detail||json)}`);
 return json;
}
const api=path=>`/api/projects/${P}${path}`;
function error(err){message('操作失敗：'+err.message);console.error(err)}
function loginVisible(visible){el('login').classList.toggle('hidden',!visible)}
async function login(token){state.token=token;const data=await request('/api/me');state.user=data.user;state.role=data.projects.find(p=>p.id===P)?.role||null;
 if(!state.role)throw new Error('此帳號沒有 demo-chamber 專案存取權限');
 sessionStorage.setItem('riskscope_token',token);el('identity').textContent=state.user.display_name+' · '+state.role;
 loginVisible(false);await render();}
function logout(){sessionStorage.removeItem('riskscope_token');state.token='';state.user=null;state.role=null;el('token').value='';loginVisible(true)}
function title(eyebrow,head,desc,extra=''){return `<div class="head"><div><div class="eyebrow">${e(eyebrow)}</div><h1>${e(head)}</h1><div class="subtitle">${e(desc)}</div></div><div class="btnrow">${extra}</div></div>`}
function list(items,formatter,empty='目前沒有紀錄'){return items.length?items.map(formatter).join(''):`<div class="muted tiny">${e(empty)}</div>`}
function stat(label,num,foot){return `<div class="card"><div class="stat-label">${e(label)}</div><div class="stat-num">${e(num)}</div><div class="stat-foot">${e(foot)}</div></div>`}
function date(x){return String(x||'').replace('T',' ').slice(0,19)}
function stBadge(s){return badge(s,({fail:'red',blocked:'red',pending:'amber',unknown:'amber',stale:'amber',approved:'blue',pass:'green',executed:'green',completed:'green'}[s]||'gray'))}
async function overview(){
 const [o,al,history]=await Promise.all([request(api('/overview')),request(api('/alerts')),request(api('/analyses'))]);
 const t=o.tasks;
 let html=title('PROJECT DASHBOARD','研發決策總覽','以可驗證的合成資料建立決策依據，保留人工審核與版本追蹤。',`<button class="primary" id="start-analysis">＋ 新增決策分析</button>`);
 html+=`<div class="grid stats">${stat('授權文件',o.visible_documents,'依來源 ACL 過濾')}${stat('開啟的風險提醒',o.open_alerts,'僅系統內提醒')}${stat('歷史分析',history.analyses.length,'最多列出近期 50 筆')}${stat('資料修訂版',`v${o.project.data_revision}`,'版本變更會讓舊審核失效')}</div>`;
 html+=`<div class="section grid two"><div class="card"><div class="section-title"><h2>工作項目狀態</h2>${badge('模擬資料','blue')}</div><div class="table-wrap"><table><thead><tr><th>工作項目</th><th>狀態</th><th>最後更新</th></tr></thead><tbody>${t.map(x=>`<tr><td><strong>${e(x.task_id)}</strong></td><td>${stBadge(x.state)}</td><td>${e(date(x.updated_at))}</td></tr>`).join('')}</tbody></table></div></div><div class="card"><h2>最近的主動提醒</h2>${list(al.alerts.slice(0,4),x=>`<div class="item"><div class="item-head"><span class="item-title">${e(x.title)}</span>${badge(x.status,'amber')}</div><div class="item-desc">${e(x.body)}</div><div class="item-meta">${e(date(x.created_at))}</div></div>`,'目前沒有新提醒')}<div class="divider"></div><div class="note">目前為合成案例 PoC，通知、工期及工程決策皆不代表企業實際狀態。</div></div></div>`;
 html+=`<div class="section"><div class="section-title"><h2>最近分析</h2></div><div class="card">${list(history.analyses.slice(0,5),x=>`<div class="item spaced"><div><div class="item-title">${e(x.question)}</div><div class="item-meta">${e(date(x.created_at))} · 風險 ${e(x.risk_count)} 項 · rev ${e(x.project_revision)}</div></div><button class="ghost analysis-open" data-id="${e(x.id)}">檢視 →</button></div>`,'尚未執行分析')}</div></div>`;
 el('content').innerHTML=html;el('start-analysis').onclick=()=>setPage('analysis');document.querySelectorAll('.analysis-open').forEach(b=>b.onclick=()=>openAnalysis(b.dataset.id));
}
const FOCUS=[['motor_upgrade','馬達升級與負載'],['power','電源選型'],['driver','驅動器'],['firmware','韌體保護'],['mechanical','機構干涉'],['thermal','熱設計'],['supplier','供應商交期'],['requirements','需求修訂'],['test_failure','測試失敗'],['unrelated','無關零件（負例）']];
async function analysis(){
 let html=title('DECISION ANALYSIS','決策前風險推演','提出決策問題，取得確定性規格檢核、可追溯來源、連鎖影響與待釐清事項。');
 html+=`<div class="grid two"><div class="card"><h2>建立新的分析</h2><form id="analysis-form"><div class="form-line"><label for="question">你想評估的決策</label><textarea id="question" required minlength="3">客戶要求提高自動化設備負載，但不希望延後交期。能否只更換 M-02 馬達並沿用現有電源？</textarea></div><div class="form-grid"><div class="form-line"><label for="focus">評估情境</label><select id="focus">${FOCUS.map(([key,label])=>`<option value="${key}">${e(label)}</option>`).join('')}</select></div><div class="form-line"><label for="priority">管理優先序</label><select id="priority"><option value="品質,交期,成本">品質 → 交期 → 成本</option><option value="交期,品質,成本">交期 → 品質 → 成本</option><option value="成本,品質,交期">成本 → 品質 → 交期</option></select></div></div><div class="form-line"><label class="form-note"><input type="checkbox" id="local-model" style="width:auto;vertical-align:middle;margin-right:6px">使用可用的本機 Ollama 做文字補充（預設關閉）</label></div><button class="primary large" type="submit" id="submit-analysis">開始分析　→</button></form></div><div class="card"><h2>分析流程與安全界線</h2><div class="item"><div class="item-title"><span class="circle">1</span> 權限過濾</div><div class="item-desc">資料來源逐筆比對專案成員和文件 ACL，撤權立即生效。</div></div><div class="item"><div class="item-title"><span class="circle">2</span>工具檢核</div><div class="item-desc">單位換算、額定電流、來源版本採確定性程式驗證。</div></div><div class="item"><div class="item-title"><span class="circle">3</span>風險與方案</div><div class="item-desc">分開事實、推論、假設及未知；不憑空計算工期。</div></div><div class="item"><div class="item-title"><span class="circle">4</span>人工審核</div><div class="item-desc">模擬任務修改需管理者核准，版本變動後必須重審。</div></div></div></div><div id="analysis-output"></div>`;
 el('content').innerHTML=html;
 el('analysis-form').onsubmit=async(ev)=>{ev.preventDefault();const b=el('submit-analysis');b.disabled=true;b.textContent='分析中…';try{const result=await request(api('/analyze'),{method:'POST',body:JSON.stringify({question:val('question'),focus:val('focus'),priorities:val('priority').split(','),use_local_llm:el('local-model').checked})});state.lastAnalysis=result;renderAnalysis(result);message('分析完成，已儲存含版本資訊的紀錄');}catch(err){error(err)}finally{b.disabled=false;b.textContent='開始分析　→'}};
 if(state.lastAnalysis)renderAnalysis(state.lastAnalysis);
}
function renderAnalysis(a){
 const target=el('analysis-output');if(!target)return;
 const check=a.checks[0];let html=`<div class="section"><div class="section-title"><h2>分析結果</h2><div class="btnrow">${stBadge(a.decision_status)}<button class="secondary" id="export-analysis">匯出分析 JSON</button></div></div>`;
 if(check?.numbers){let n=check.numbers;html+=`<div class="hero-check"><div><div class="eyebrow" style="color:#a8c5ed">CONTINUOUS LOAD CHECK</div><div class="big">${e(n.total_current_a)}A <span>/ ${e(n.limit_current_a)}A 額定</span></div><div class="sub">${e(check.reason)}。計算：${e(n.motor_current_a)} + ${e(n.other_current_a)} = ${e(n.total_current_a)} A；${e(n.total_power_w)} W / ${e(n.limit_power_w)} W。超額並不代表設備必然跳脫。</div></div><div>${stBadge(check.status)}</div></div>`}
 if(check?.status==='unknown')html+=`<div class="note warning">確定性檢核：未知／無法驗證。${e(check.reason)}；不可使用過期或未授權數值。</div>`;
 html+=`<div class="section grid two"><div class="card"><h2>已知事實與來源</h2>${list(a.facts,x=>`<div class="item"><div class="item-title">${e(x.claim)}</div><div class="item-meta">${e(x.basis)} · ${e(x.sources.map(y=>`${y.source_id} v${y.source_version}`).join(', '))}</div></div>`,'尚無可確認的數值事實')}<div class="divider"></div><h3>合理推論</h3>${list(a.inferences,x=>`<div class="item-desc" style="margin:10px 0">· ${e(x)}</div>`,'無')}</div><div class="card"><h2>風險與未知</h2><div class="risk-list">${list(a.risks,x=>`<div class="risk ${x.severity==='high'?'high':''}"><div class="spaced"><strong>${e(x.id)}</strong>${stBadge(x.state)}</div><div class="item-desc">${e(x.message)}</div></div>`,'無已辨識風險')}</div><div class="divider"></div><h3>尚未確認</h3>${list(a.unknowns,x=>`<div class="item-desc">· <strong>${e(x.topic)}</strong>：${e(x.reason)}</div>`,'請依下方追問補充')}</div></div>`;
 if(a.options?.length)html+=`<div class="section grid two"><div class="card"><h2>方案比較</h2>${a.options.map(x=>`<div class="option"><div class="spaced"><strong>方案 ${e(x.id)}｜${e(x.title)}</strong>${stBadge(x.hard_constraint)}</div><div class="item-desc">${e(x.comment)}</div></div>`).join('')}<div class="note warning">方案 B、C 只是待驗證選項，不能因排除 A 就當成已核准。</div></div><div class="card"><h2>建議主動追問</h2><ol class="detail">${a.questions_to_manager.map(x=>`<li>${e(x)}</li>`).join('')}</ol><h3>本次評估假設</h3>${list(a.assumptions,x=>`<div class="item-desc">· ${e(x)}</div>`,'無特定假設')}</div></div>`;
 const imp=a.impacts||[];
 html+=`<div class="section card"><div class="section-title"><h2>可追溯工程依賴</h2>${badge('非必然影響','amber')}</div>${list(imp,x=>`<div><div class="mini-label">${e(x.root)} · ${e(x.path_count)} 條路徑 / ${e(x.affected_nodes.length)} 個節點</div><div style="margin-top:8px">${list(x.paths.filter(p=>p.nodes.length>=3).slice(0,8),p=>`<div class="path">${p.nodes.map(e).join(' → ')} <span class="muted tiny">(${p.evidence.map(y=>e(y.source_id)+' v'+e(y.source_version)).join(', ')})</span></div>`,'無兩層以上的授權依賴路徑')}</div></div>`,'此焦點無既有依賴')}</div>`;
 html+=`<div class="section card"><div class="section-title"><h2>人工審核／模擬操作</h2>${badge('不會修改真實系統','blue')}</div><div class="note">申請只建立待核准任務，不會執行。管理者須在「人工審核」分別核准及執行。</div><form id="action-form" class="form-grid" style="margin-top:18px"><div><label for="task-id">指定模擬任務</label><select id="task-id"><option>TEST-01</option><option>PROCURE-01</option><option>ASSEMBLY-01</option><option>RELEASE-01</option></select></div><div><label for="task-state">建議狀態</label><select id="task-state"><option value="blocked">blocked｜等待確認</option><option value="in_progress">in_progress｜進行中</option><option value="planned">planned｜規劃中</option><option value="done">done｜已完成</option></select></div><div class="btnrow"><button class="secondary" type="submit">提出模擬變更申請</button></div></form></div></div>`;
 target.innerHTML=html;
 el('export-analysis').onclick=()=>{const blob=new Blob([pretty(a)],{type:'application/json'}),url=URL.createObjectURL(blob),anchor=document.createElement('a');anchor.href=url;anchor.download=`risk-analysis-${a.analysis_id}.json`;anchor.click();URL.revokeObjectURL(url)};
 el('action-form').onsubmit=async(ev)=>{ev.preventDefault();try{const result=await request(api('/actions'),{method:'POST',body:JSON.stringify({analysis_id:a.analysis_id,task_id:val('task-id'),new_state:val('task-state'),idempotency_key:`ui-${crypto.randomUUID()}`})});message('已送出待審核動作：'+result.action_id)}catch(ex){error(ex)}};
}
function chatBubble(role,text,meta=''){return `<div class="item spaced chat-${role}"><div><div class="item-title">${role==='user'?'你':'Agent'}</div><div class="item-desc">${e(text).replace(/\n/g,'<br>')}</div>${meta?`<div class="item-meta tiny">${meta}</div>`:''}</div></div>`}
function chatSessionId(){if(!state.chatSessionId)state.chatSessionId='chat-'+crypto.randomUUID().slice(0,8);return state.chatSessionId}
async function renderChatTranscript(){
 const box=el('chat-transcript');if(!box)return;
 try{
  const h=await request(api(`/sessions/${encodeURIComponent(chatSessionId())}`));
  const statusBadge=badge(h.session.status==='open'?'對話持續中，尚待補充資訊':'本輪已完成',h.session.status==='open'?'amber':'green');
  box.innerHTML=`<div class="spaced"><h3>對話紀錄 · ${e(chatSessionId())}</h3>${statusBadge}</div>`+
   h.turns.map(t=>chatBubble('user',t.question)+(t.redacted
     ?chatBubble('agent','（來源文件權限已變更，此回覆內容已遮蔽，無法再次顯示）',e(date(t.created_at))+' · '+badge('已遮蔽','amber'))
     :chatBubble('agent',t.reply,e(date(t.created_at))+' · '+badge(t.reply_source==='llm_phrased'?'本機 LLM 轉述':'確定性模板','blue')))).join('');
 }catch(err){box.innerHTML=`<div class="muted tiny">尚無對話紀錄，請在下方輸入你的第一個問題。</div>`}
}
async function chat(){
 let html=title('INTERACTIVE AGENT','對話式風險分析 Agent','用自然語言連續對話；Agent 缺資料會主動追問，管理者補齊授權或規格後，在同一個對話繼續即可恢復分析。');
 html+=`<div class="note warning">這裡的「Agent」只負責用自然語言轉述下方確定性分析結果；授權、數值計算、風險判斷與人工審核完全由確定性程式控制，LLM 不會也不能代替執行。若本機未設定 Ollama，系統會改用固定模板回覆（下方會標示來源）。</div>`;
 html+=`<div class="grid two"><div class="card"><h2>對話</h2><div id="chat-transcript" class="chat-box"></div><form id="chat-form" style="margin-top:14px"><div class="form-line"><label for="chat-message">你的訊息</label><textarea id="chat-message" required minlength="1" placeholder="例如：我想評估把 M-02 馬達升級，目前資料夠嗎？"></textarea></div><div class="form-grid"><div class="form-line"><label for="chat-focus">評估情境</label><select id="chat-focus">${FOCUS.map(([key,label])=>`<option value="${key}">${e(label)}</option>`).join('')}</select></div><div class="form-line"><label class="form-note"><input type="checkbox" id="chat-local-llm" checked style="width:auto;vertical-align:middle;margin-right:6px">允許用本機 Ollama 解析您提供的數值並轉述回覆（未設定時自動改用固定模板，且無法解析補充數值）</label></div></div><button class="primary large" type="submit" id="chat-send">送出　→</button></form></div><div class="card"><h2>這個對話 session</h2><div class="item-desc">目前 session_id：<code>${e(chatSessionId())}</code></div><div class="btnrow" style="margin-top:12px"><button class="secondary" id="chat-new-session">開啟新對話</button></div><div class="divider"></div><div class="note">同一個 session_id 底下，Agent 會記住上一輪缺少什麼資訊；您也可以直接在對話裡提供數值（例如「電源電流 10A」），Agent 會嘗試解析並記住，供本次對話試算使用——但這不會寫入正式規格，管理者仍可在「資料與證據」頁面用既有流程正式確認後取代它。</div></div></div>`;
 el('content').innerHTML=html;
 await renderChatTranscript();
 el('chat-new-session').onclick=()=>{state.chatSessionId=null;chatSessionId();renderChatTranscript()};
 el('chat-form').onsubmit=async(ev)=>{
  ev.preventDefault();const b=el('chat-send');const msg=val('chat-message');if(!msg)return;b.disabled=true;b.textContent='Agent 思考中…';
  try{
   await request(api('/chat'),{method:'POST',body:JSON.stringify({message:msg,session_id:chatSessionId(),focus:val('chat-focus'),use_local_llm:el('chat-local-llm').checked})});
   el('chat-message').value='';await renderChatTranscript();
  }catch(err){error(err)}finally{b.disabled=false;b.textContent='送出　→'}
 };
}
async function openAnalysis(id){setPage('analysis');try{state.lastAnalysis=await request(api(`/analyses/${encodeURIComponent(id)}`));renderAnalysis(state.lastAnalysis)}catch(err){error(err)}}
async function impact(){
 let html=title('DEPENDENCY TRACE','工程影響追蹤','沿有來源的相依關係向下追蹤；路徑去重、循環阻擋及版本檢查。');
 html+=`<div class="card"><form id="impact-form" class="form-grid"><div><label for="root">變更來源節點</label><select id="root"><option>M-02</option><option>PS-01</option><option>DRIVER-01</option><option>SUPPLIER-01</option><option>REQ-01</option><option>THERMAL-01</option><option>TEST-FAIL-01</option><option>ISOLATED-01</option></select></div><div style="display:flex;align-items:flex-end"><button class="primary" type="submit">追蹤受影響路徑 →</button></div></form></div><div class="section" id="impact-output"></div>`;
 el('content').innerHTML=html;el('impact-form').onsubmit=async(ev)=>{ev.preventDefault();try{const r=await request(api('/impact/'+encodeURIComponent(val('root'))));el('impact-output').innerHTML=`<div class="grid thirds">${stat('影響節點',r.affected_nodes.length,'僅顯示有證據的節點')}${stat('已知路徑',r.path_count,'最高 120 條')}${stat('受抑制循環',r.suppressed.cycle,'避免重複遍歷')}</div><div class="section card"><h2>${e(r.root)} 的路徑證據 ${r.truncated?badge('已達顯示上限','amber'):''}</h2>${list(r.paths,x=>`<div class="path">${x.nodes.map(e).join(' → ')}<br><span class="tiny muted">${x.evidence.map(y=>`${e(y.dependency_id)} / ${e(y.source_id)} v${y.source_version}`).join(' · ')}</span></div>`,'沒有已證實、已授權的影響路徑')}<div class="divider"></div><div class="note">${e(r.explanation)}　跳過：過期 ${r.suppressed.stale}、越權 ${r.suppressed.unauthorized}、循環 ${r.suppressed.cycle}。</div></div>`}catch(err){error(err)}};
 el('impact-form').dispatchEvent(new Event('submit',{cancelable:true}));
}
async function docs(){
 const x=await request(api('/documents'));
 let html=title('KNOWLEDGE & PROVENANCE','已授權的文件來源','僅載入目前帳號可存取的文件；每個版本獨立記錄來源與 SHA-256。');
 html+=`<div class="card"><div class="spaced"><h2>文件資料庫</h2>${badge(x.documents.length+' 份可見','blue')}</div>${list(x.documents,d=>`<div class="item"><div class="item-head"><div><div class="item-title">${e(d.title)}</div><div class="item-meta">${e(d.id)} · ${e(d.category)} · v${e(d.version)} · ${e(date(d.updated_at))}</div></div><div>${badge(d.classification,d.classification==='confidential'?'red':'blue')}</div></div><div class="item-desc clamped">${e(d.body)}</div></div>`,'目前沒有已授權文件')}</div>`;
 html+=`<div class="section note">若文件改版，原先依賴該版本的規格數值和依賴邊會被標示為過期，必須由管理者重新驗證。文件內容只視為資料，不執行其中的指令。</div>`;
 el('content').innerHTML=html;
}
async function actions(){
 const x=await request(api('/actions'));
 let html=title('HUMAN APPROVAL','人工審核中心','申請、核准與執行分為三個明確步驟；僅 manager 可以核准或執行。');
 html+=`<div class="note warning">操作範圍只限本機的 simulated_tasks。每次執行前會重新檢查角色、核准狀態與資料版本。</div><div class="section card"><h2>申請清單</h2>${list(x.actions,a=>`<div class="item"><div class="item-head"><div><div class="item-title">${e(a.payload.task_id)} → ${e(a.payload.new_state)}</div><div class="item-meta">由 ${e(a.requested_by)} 提出 · Rev ${e(a.project_revision)} · ${e(date(a.created_at))}</div><div class="item-meta tiny">${e(a.id)}</div></div>${stBadge(a.state)}</div><div class="btnrow" style="margin-top:11px">${state.role==='manager'&&a.state==='pending'?`<button class="secondary act" data-id="${e(a.id)}" data-mode="approve">核准</button><button class="danger act" data-id="${e(a.id)}" data-mode="reject">拒絕</button>`:''}${state.role==='manager'&&a.state==='approved'?`<button class="primary act" data-id="${e(a.id)}" data-mode="execute">執行模擬變更</button>`:''}</div></div>`,'目前沒有待處理或歷史申請')}</div>`;
 el('content').innerHTML=html;
 document.querySelectorAll('.act').forEach(b=>b.onclick=async()=>{if(!confirm('確定要'+({approve:'核准',reject:'拒絕',execute:'執行模擬操作'}[b.dataset.mode])+'？'))return;try{const path=api(`/actions/${encodeURIComponent(b.dataset.id)}`);const res=await request(path+(b.dataset.mode==='execute'?'/execute':'/review'),{method:'POST',...(b.dataset.mode==='execute'?{}:{body:JSON.stringify({approve:b.dataset.mode==='approve'})})});message('操作結果：'+res.state);await actions()}catch(err){error(err)}});
}
async function events(){
 const [alerts,events]=await Promise.all([request(api('/alerts')),request(api('/events'))]);
 let html=title('EVENT MONITORING','合成事件監測','透過事件 ID 去重，更新專案訊號並重跑相同分析流程；只建立內部提醒。');
 html+=`<div class="grid two"><div class="card"><h2>模擬資料異動</h2><form id="event-form"><div class="form-line"><label for="event-key">變更來源</label><select id="event-key"><option value="supplier_lead_days">供應商交期（天）</option><option value="test_pass">測試結果（pass/fail/unknown）</option></select></div><div class="form-line"><label for="event-value">新數值</label><input id="event-value" value="18" placeholder="18"></div><div class="form-line"><label for="event-id">事件識別碼（重複 ID 不重複處理）</label><input id="event-id" value="" placeholder="輸入任意唯一事件 ID"></div><button type="submit" class="primary large">送出合成更新並重新分析</button></form></div><div class="card"><h2>流程說明</h2><div class="flow"><span>事件收到</span>→<span>驗證身分</span>→<span>比較差異</span>→<span>增加資料版次</span>→<span>重新分析</span>→<span>內部提醒</span></div><div class="divider"></div><div class="note">這裡沒有連接 Jira、Email、供應商或真實產線。重複事件回傳既有結果，使用相同 ID 卻送入不同內容會遭拒絕。</div></div></div>`;
 html+=`<div class="section grid two"><div class="card"><h2>內部提醒</h2>${list(alerts.alerts.slice(0,12),a=>`<div class="item"><div class="item-head"><strong>${e(a.title)}</strong>${badge(a.status,'amber')}</div><div class="item-desc">${e(a.body)}</div><div class="item-meta">${e(date(a.created_at))}</div></div>`,'尚無提醒')}</div><div class="card"><h2>事件接收紀錄</h2>${list(events.events.slice(0,12),v=>`<div class="item"><div class="item-title">${e(v.signal_key)}：${e(v.old_value)} → ${e(v.new_value)}</div><div class="item-meta">${e(v.external_event_id)} · ${e(date(v.created_at))}</div></div>`,'尚無事件')}</div></div>`;
 el('content').innerHTML=html;
 el('event-id').value='evt-'+new Date().toISOString().replace(/[^0-9]/g,'').slice(0,14);
 el('event-key').onchange=()=>{el('event-value').value=val('event-key')==='test_pass'?'fail':'18'};
 el('event-form').onsubmit=async(ev)=>{ev.preventDefault();try{const res=await request(api('/events'),{method:'POST',body:JSON.stringify({event_source:'ui-manual',external_event_id:val('event-id'),signal_key:val('event-key'),value:val('event-value')})});message(res.deduplicated?'重複事件已去重':res.analysis_status==='completed'?'事件已保存並完成重新分析':res.analysis_status==='skipped_no_risk'?'測試通過，無需產生失敗風險提醒':res.analysis_status==='skipped_no_change'?'數值未變更，無需重新分析':'已建立待處理提醒');await events()}catch(err){error(err)}};
}
async function audit(){
 if(state.role!=='manager'){el('content').innerHTML=title('AUDIT','操作稽核','僅有 manager 可查看專案所有稽核資訊。')+`<div class="empty">沒有稽核管理權限</div>`;return}
 const x=await request(api('/audit'));let html=title('AUDIT TRAIL','安全與操作稽核','權限修改、文件版本、風險分析、審核與模擬寫入均建立事件紀錄。');
 html+=`<div class="card table-wrap"><table><thead><tr><th>時間</th><th>使用者</th><th>操作</th><th>對象</th><th>額外資訊</th></tr></thead><tbody>${x.logs.map(log=>`<tr><td class="nowrap">${e(date(log.created_at))}</td><td>${e(log.actor_id)}</td><td>${e(log.operation)}</td><td>${e(log.target)}</td><td class="tiny">${e(log.details_json)}</td></tr>`).join('')}</tbody></table></div>`;el('content').innerHTML=html;
}
async function render(){el('content').innerHTML='<div class="empty">資料載入中…</div>';try{await ({overview,analysis,chat,impact,docs,actions,events,audit}[state.page]||overview)()}catch(ex){el('content').innerHTML='<div class="empty">無法載入頁面：'+e(ex.message)+'</div>';error(ex)}}
async function setPage(page){state.page=page;document.querySelectorAll('#nav button').forEach(n=>n.classList.toggle('active',n.dataset.page===page));await render()}
document.querySelectorAll('#nav button').forEach(b=>b.onclick=()=>setPage(b.dataset.page));
el('logout').onclick=logout;
el('login-button').onclick=async()=>{el('login-error').textContent='';try{await login(val('token'))}catch(err){el('login-error').textContent=err.message;logout()}};
el('token').addEventListener('keydown',ev=>{if(ev.key==='Enter')el('login-button').click()});
if(state.token){login(state.token).catch(()=>logout())}else loginVisible(true);
