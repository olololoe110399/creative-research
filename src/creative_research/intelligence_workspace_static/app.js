'use strict';

const $ = function(s){ return document.querySelector(s); };
const esc = function(v){ return String(v == null ? '' : v).replace(/[&<>"']/g,function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); };
const label = function(v){ return v == null ? '--' : String(v).replaceAll('_',' '); };
const num = function(v){ return v == null ? '--' : new Intl.NumberFormat('en-US',{maximumFractionDigits:1}).format(v); };
const pct = function(v){ return v == null ? '--' : new Intl.NumberFormat('en-US',{style:'percent',maximumFractionDigits:1}).format(v); };
const date = function(v){ if(!v)return '--'; const d=new Date(v); return Number.isNaN(d.getTime())?String(v):d.toLocaleDateString('en-US',{year:'numeric',month:'short',day:'numeric'}); };
const json = function(v){ try{return JSON.stringify(v,null,2);}catch(e){return String(v);} };
const metric = function(name,value,sub){ return '<div class="metric"><small>'+esc(name)+'</small><strong>'+value+'</strong><span>'+esc(sub||'')+'</span></div>'; };
const badge = function(v,cls){ return v?'<span class="badge '+(cls||'')+'">'+esc(label(v))+'</span>':''; };
const confClass = function(v){ return v==='high'?'confidence-high':v==='medium'?'confidence-medium':'confidence-low'; };
const statusClass = function(v){ return (v==='approved'||v==='promoted')?'active':v==='review_candidate'?'review':(v==='rejected'||v==='hold')?'reject':''; };

let data = {};
let tab = 'overview';
let query = '';
let filter = '';

function byId(rows,key){ const m=new Map(); (rows||[]).forEach(function(r){ if(r&&r[key]!=null)m.set(String(r[key]),r); }); return m; }

function initMaps(){
  data.postById=byId(data.evidence.posts,'post_uid');
  data.familyById=byId(data.families.families,'family_id');
  data.patternById=byId(data.patterns.patterns,'pattern_id');
  data.strategyById=byId(data.strategies.strategies,'hypothesis_id');
  data.knowledgeById=byId(data.knowledge.knowledge,'knowledge_id');
}

function renderCounts(){
  const c=data.overview.counts||{};
  $('#counts').textContent=(c.posts||0)+' posts · '+(c.accounts||0)+' accounts · '+(c.families||0)+' families · '+(c.active_knowledge_items||0)+' active knowledge';
}

function overviewView(){
  const c=data.overview.counts||{};
  const k=data.overview.active_knowledge_by_type||{};
  const statuses=data.overview.knowledge_status_counts||{};
  const operatorCards=(data.overview.operators||[]).map(function(o){
    return '<article class="panel"><div class="row"><b>'+esc(o.name||o.operator_id)+'</b>'+badge(o.verified?'verified':'unverified',o.verified?'active':'')+'</div><p>'+esc(o.operator_id||'')+'</p><div class="stats">'+badge((o.observed_accounts||0)+' accounts')+badge((o.observed_posts||0)+' posts')+'</div></article>';
  }).join('');
  const bars=Object.entries(k).map(function(entry){ return '<div class="bar"><span>'+esc(label(entry[0]))+'</span><div class="track"><div class="fill" style="width:'+Math.min(100,entry[1]*12)+'%"></div></div><b>'+esc(entry[1])+'</b></div>'; }).join('');
  const statusText=Object.entries(statuses).map(function(entry){ return badge(entry[0]+': '+entry[1],statusClass(entry[0])); }).join('');
  return '<section class="intro"><h1>Operator intelligence map</h1><p>Read the operator from evidence upward: accounts, timeline, creative families, patterns, strategy hypotheses, then knowledge. This workspace does not create new conclusions.</p></section>'+
    '<div class="metric-grid">'+metric('Posts',num(c.posts),'canonical evidence')+metric('Accounts',num(c.accounts),'verified portfolio')+metric('Families',num(c.families),'creative concepts')+metric('Patterns',num(c.patterns),'recurring observations')+metric('Strategy hypotheses',num(c.strategy_hypotheses),'reviewable claims')+metric('Change points',num(c.strategy_change_points),'material timeline shifts')+metric('Knowledge',num(c.knowledge_items),'all statuses')+metric('Active knowledge',num(c.active_knowledge_items),'approved + promoted')+'</div>'+
    '<div class="grid two"><section class="panel"><h2>Operators</h2><div class="grid two">'+operatorCards+'</div></section><section class="panel"><h2>Active knowledge</h2><div class="bars">'+(bars||'<p>No active knowledge yet.</p>')+'</div><h3>Status audit</h3><div class="badges">'+statusText+'</div></section></div>';
}

function accountsView(){
  const rows=data.accounts.accounts||[];
  return '<section class="intro"><h1>Accounts</h1><p>Compare account baselines, cadence, family-flow role evidence, and account-scoped strategy hypotheses.</p></section><div class="table"><table><thead><tr><th>Account</th><th>Posts</th><th>Median views</th><th>Median gap</th><th>Origin</th><th>Receiver</th><th>Amplifier</th><th>Profile</th><th>Strategies</th></tr></thead><tbody>'+
    rows.map(function(r){ const p=r.performance_baseline||{},c=r.cadence_summary||{},role=r.role_evidence||{}; return '<tr><td><b>'+esc(r.account||r.account_id)+'</b><br><small class="muted">'+esc(r.account_id||'')+'</small></td><td>'+num(r.observed_posts)+'</td><td>'+num(p.median_views)+'</td><td>'+num(c.median_gap_hours)+'h</td><td>'+pct(role.originator_signal)+'</td><td>'+pct(role.receiver_signal)+'</td><td>'+pct(role.amplifier_signal)+'</td><td>'+badge(role.descriptive_profile,role.evidence_strength==='high'?'active':'review')+'</td><td>'+num((r.strategy_hypotheses||[]).length)+'</td></tr>'; }).join('')+
    '</tbody></table></div>';
}

function timelineView(){
  const windows=(data.timeline.operator_windows||[]).slice().sort(function(a,b){ return String(a.window_start_local).localeCompare(String(b.window_start_local)); });
  const changes=data.timeline.change_points||[];
  const changeMap=new Map(changes.map(function(c){ return [String(c.current_period_id),c]; }));
  const rows=windows.map(function(w){ const ch=changeMap.get(String(w.period_id)); const angle=w.top_content_angle||'--'; const hook=w.top_hook_technique||'--'; return '<div class="timeline-row '+(ch?'change':'')+'"><div><b>'+esc(w.period_id)+'</b><small class="muted">'+num(w.posts)+' posts</small></div><div><div class="badges">'+badge(angle)+badge(hook)+badge(w.top_format)+badge(w.top_product_placement_style)+'</div><p>Product '+pct(w.product_rate)+' · CTA '+pct(w.cta_rate)+' · '+num(w.posts_per_active_day)+' posts/active day · '+num(w.family_origins)+' family origins · '+num(w.imported_family_entries)+' imports</p>'+(ch?'<p><b>Change:</b> '+esc(label(ch.changed_dimensions_json||''))+'</p>':'')+'</div><div>'+(ch?'<b class="confidence-medium">'+num(ch.change_score)+'</b>':'')+'</div></div>'; }).join('');
  return '<section class="intro"><h1>Strategy timeline</h1><p>Fixed historical windows with deterministic content/operating distributions. Highlighted rows crossed the change threshold; they are not semantic strategy labels.</p></section><div class="timeline-list">'+(rows||'<p>No timeline data.</p>')+'</div>';
}

function familyCard(f){
  const perf=f.median_views_percentile_account;
  return '<article class="card" data-family="'+esc(f.family_id)+'"><div class="row"><b>'+esc(f.family_id)+'</b>'+badge(f.family_confidence,f.family_confidence==='high'?'active':'review')+'</div><h3>'+esc(f.core_hook_text||f.core_angle||'Creative family')+'</h3><p>'+esc(label(f.core_angle))+' · origin '+esc(f.origin_account||'--')+'</p><div class="badges">'+badge((f.member_count||0)+' members')+badge((f.accounts_count||0)+' accounts')+badge(f.cross_account?'cross account':'single account')+badge('median pct '+pct(perf))+'</div></article>';
}
function familiesView(){
  const rows=(data.families.families||[]).filter(function(r){ const s=JSON.stringify(r).toLowerCase(); return !query||s.includes(query.toLowerCase()); }).sort(function(a,b){ return (b.member_count||0)-(a.member_count||0); });
  return '<section class="intro"><h1>Creative families</h1><p>Repeated executions of candidate shared concepts. Open a family to inspect members and cross-account propagation.</p></section>'+searchBar('Search family, hook, angle...')+'<div class="grid">'+rows.map(familyCard).join('')+'</div>';
}

function patternCard(p){
  return '<article class="card" data-pattern="'+esc(p.pattern_id)+'"><div class="row"><b>'+esc(p.pattern_id)+'</b>'+badge(p.evidence_strength,p.evidence_strength==='high'?'active':'review')+'</div><h3>'+esc(p.title||p.pattern_type)+'</h3><p>'+esc(p.observation||'')+'</p><div class="badges">'+badge(p.pattern_type)+badge('n='+num(p.sample_size))+badge('effect '+num(p.effect_size))+badge('support '+pct(p.support_rate))+'</div></article>';
}
function patternsView(){
  let rows=data.patterns.patterns||[];
  rows=rows.filter(function(r){ return (!filter||r.pattern_type===filter)&&(!query||JSON.stringify(r).toLowerCase().includes(query.toLowerCase())); });
  const types=[...new Set((data.patterns.patterns||[]).map(function(r){return r.pattern_type;}).filter(Boolean))].sort();
  return '<section class="intro"><h1>Patterns</h1><p>Structured recurring observations. Every pattern remains non-causal and links to evidence.</p></section>'+filterBar(types,'All pattern types')+'<div class="grid">'+rows.map(patternCard).join('')+'</div>';
}

function strategyCard(s){
  return '<article class="card" data-strategy="'+esc(s.hypothesis_id)+'"><div class="row"><b>'+esc(s.hypothesis_id)+'</b><span class="'+confClass(s.confidence_band)+' score">'+num(s.confidence_score)+'</span></div><h3>'+esc(s.title||s.hypothesis_type)+'</h3><p>'+esc(s.claim||'')+'</p><div class="badges">'+badge(s.hypothesis_type)+badge(s.confidence_band)+badge(s.promotion_readiness)+'</div></article>';
}
function strategiesView(){
  const rows=(data.strategies.strategies||[]).filter(function(r){return !query||JSON.stringify(r).toLowerCase().includes(query.toLowerCase());});
  return '<section class="intro"><h1>Strategy hypotheses</h1><p>Interpretations promoted from patterns with confidence, counter evidence, and alternative explanations. They are still hypotheses.</p></section>'+searchBar('Search strategy hypothesis...')+'<div class="grid">'+rows.map(strategyCard).join('')+'</div>';
}

function knowledgeCard(k){
  return '<article class="card" data-knowledge="'+esc(k.knowledge_id)+'"><div class="row"><b>'+esc(k.knowledge_id)+'</b>'+badge(k.knowledge_status,statusClass(k.knowledge_status))+'</div><h3>'+esc(k.title||k.knowledge_type)+'</h3><p>'+esc(k.statement||'')+'</p><div class="badges">'+badge(k.knowledge_type)+badge(k.subtype)+badge(k.confidence_band)+'</div></article>';
}
function knowledgeView(){
  let rows=data.knowledge.knowledge||[];
  rows=rows.filter(function(r){ return (!filter||r.knowledge_status===filter)&&(!query||JSON.stringify(r).toLowerCase().includes(query.toLowerCase())); });
  const statuses=[...new Set((data.knowledge.knowledge||[]).map(function(r){return r.knowledge_status;}).filter(Boolean))].sort();
  return '<section class="intro"><h1>Knowledge bank</h1><p>Strategies, rules, lessons, templates, and playbooks. Status is part of the contract: rejected/hold remain visible for audit.</p></section>'+filterBar(statuses,'All statuses')+'<div class="grid">'+rows.map(knowledgeCard).join('')+'</div>';
}

function evidenceView(){
  const rows=(data.evidence.posts||[]).filter(function(r){ return !query||JSON.stringify(r).toLowerCase().includes(query.toLowerCase()); }).slice(0,500);
  return '<section class="intro"><h1>Evidence</h1><p>Canonical posts enriched with creative interpretation, relative performance, family membership, and sequence. Search returns up to 500 rows.</p></section>'+searchBar('Search post, account, hook, topic, family...')+'<div class="table"><table><thead><tr><th>Post</th><th>Account</th><th>Date</th><th>Hook / topic</th><th>Angle</th><th>Account pct</th><th>Family</th><th>Original</th></tr></thead><tbody>'+
    rows.map(function(r){ const c=r.creative||{},p=r.performance||{},f=r.family||{}; return '<tr data-post="'+esc(r.post_uid)+'"><td><button class="link-button" data-open-post="'+esc(r.post_uid)+'">'+esc(r.post_uid)+'</button></td><td>'+esc(r.account||'')+'</td><td>'+date(r.created_at)+'</td><td class="wrap">'+esc(c.hook_text||c.topic||'')+'</td><td>'+esc(label(c.content_angle))+'</td><td>'+pct(p.views_percentile_account)+'</td><td>'+esc(f.family_id||'--')+'</td><td>'+(r.url?'<a href="'+esc(r.url)+'" target="_blank" rel="noopener">Open</a>':'--')+'</td></tr>'; }).join('')+
    '</tbody></table></div>';
}

function searchBar(placeholder){
  return '<div class="toolbar"><input id="search" placeholder="'+esc(placeholder)+'" value="'+esc(query)+'"></div>';
}
function filterBar(values,title){
  return '<div class="toolbar"><input id="search" placeholder="Search..." value="'+esc(query)+'"><select id="filter"><option value="">'+esc(title)+'</option>'+values.map(function(v){return '<option value="'+esc(v)+'" '+(filter===v?'selected':'')+'>'+esc(label(v))+'</option>';}).join('')+'</select></div>';
}

function prettyObject(obj){
  return '<pre>'+esc(json(obj))+'</pre>';
}

function drawer(title,body){
  document.body.insertAdjacentHTML('beforeend','<div class="drawer-bg" id="drawer-bg"><aside class="drawer"><button id="drawer-close">Close</button><h2>'+esc(title)+'</h2>'+body+'</aside></div>');
  $('#drawer-close').onclick=function(){ $('#drawer-bg').remove(); };
  $('#drawer-bg').onclick=function(e){ if(e.target.id==='drawer-bg')e.currentTarget.remove(); };
  wireDrawerLinks();
}

function postButton(postId,labelText){
  if(!postId||!data.postById.has(String(postId)))return '';
  return '<button class="link-button" data-open-post="'+esc(postId)+'">'+esc(labelText||postId)+'</button>';
}
function familyButton(familyId){
  if(!familyId||!data.familyById.has(String(familyId)))return '';
  return '<button class="link-button" data-open-family="'+esc(familyId)+'">'+esc(familyId)+'</button>';
}
function patternButton(patternId,relation){
  if(!patternId||!data.patternById.has(String(patternId)))return '';
  return '<button class="link-button" data-open-pattern="'+esc(patternId)+'">'+esc(patternId)+' · '+esc(relation||'pattern')+'</button>';
}

function openFamily(id){
  const f=data.familyById.get(String(id)); if(!f)return;
  const members=(f.members||[]).map(function(m){return postButton(m.post_uid,(m.account||'')+' · '+m.post_uid+' · '+(m.hook_text||m.topic||''));}).join('');
  const prop=(f.propagation||[]).map(function(p){return '<div class="panel"><b>'+esc(p.origin_account||'')+' → '+esc(p.target_account||'')+'</b><p>'+num(p.delay_from_family_origin_days)+' days · changed '+esc(label(p.changed_dimensions_json||''))+'</p>'+postButton(p.target_first_post_uid,'Open target evidence')+'</div>';}).join('');
  drawer(id,'<p>'+esc(f.core_hook_text||f.core_angle||'')+'</p><div class="badges">'+badge((f.member_count||0)+' members')+badge((f.accounts_count||0)+' accounts')+badge('cohesion '+num(f.anchor_cohesion_mean))+'</div><h3>Core</h3>'+prettyObject({angle:f.core_angle,hook_formula:f.core_hook_formula,creative_formula:f.core_creative_formula,sequence:f.core_sequence_roles_json})+'<h3>Members</h3><div class="link-list">'+members+'</div><h3>Propagation</h3><div class="link-list">'+(prop||'<p>No cross-account propagation.</p>')+'</div>');
}

function openPattern(id){
  const p=data.patternById.get(String(id)); if(!p)return;
  const links=(p.evidence_links||[]).map(function(l){ return '<div>'+postButton(l.post_uid,(l.link_role||'evidence')+' · '+(l.post_uid||''))+familyButton(l.family_id)+'</div>'; }).join('');
  drawer(id,'<h3>'+esc(p.title||'')+'</h3><p>'+esc(p.observation||'')+'</p><dl><dt>Type</dt><dd>'+esc(label(p.pattern_type))+'</dd><dt>Evidence strength</dt><dd>'+esc(label(p.evidence_strength))+'</dd><dt>Sample</dt><dd>'+num(p.sample_size)+'</dd><dt>Support rate</dt><dd>'+pct(p.support_rate)+'</dd><dt>Effect</dt><dd>'+num(p.effect_size)+'</dd><dt>Causal claim</dt><dd>'+esc(String(p.causal_claim))+'</dd></dl><h3>Metrics</h3>'+prettyObject(p.metrics||{})+'<h3>Counter evidence</h3>'+prettyObject(p.counter_evidence||{})+'<h3>Evidence links</h3><div class="link-list">'+links+'</div>');
}

function openStrategy(id){
  const s=data.strategyById.get(String(id)); if(!s)return;
  const patterns=(s.pattern_links||[]).map(function(l){return patternButton(l.pattern_id,l.relation);}).join('');
  const posts=(s.evidence_links||[]).map(function(l){return postButton(l.post_uid,(l.relation||'evidence')+' · '+(l.post_uid||''));}).join('');
  drawer(id,'<h3>'+esc(s.title||'')+'</h3><p>'+esc(s.claim||'')+'</p><dl><dt>Confidence</dt><dd>'+num(s.confidence_score)+' · '+esc(label(s.confidence_band))+'</dd><dt>Readiness</dt><dd>'+esc(label(s.promotion_readiness))+'</dd><dt>Status</dt><dd>'+esc(label(s.status))+'</dd><dt>Causal claim</dt><dd>'+esc(String(s.causal_claim))+'</dd></dl><h3>Evidence summary</h3>'+prettyObject(s.evidence_summary||{})+'<h3>Counter evidence</h3>'+prettyObject(s.counter_evidence||{})+'<h3>Alternative explanations</h3><ul>'+(s.alternative_explanations||[]).map(function(x){return '<li>'+esc(x)+'</li>';}).join('')+'</ul><h3>Patterns</h3><div class="link-list">'+patterns+'</div><h3>Evidence posts</h3><div class="link-list">'+posts+'</div>');
}

function openKnowledge(id){
  const k=data.knowledgeById.get(String(id)); if(!k)return;
  const sources=(k.source_links||[]).map(function(l){ const sid=l.source_id; if(data.strategyById.has(String(sid)))return '<button class="link-button" data-open-strategy="'+esc(sid)+'">'+esc(sid)+' · strategy source</button>'; return '<div>'+esc(l.source_type)+': '+esc(sid)+'</div>'; }).join('');
  const evidence=(k.evidence_links||[]).map(function(l){return '<div>'+patternButton(l.pattern_id,l.relation)+postButton(l.post_uid,l.post_uid)+familyButton(l.family_id)+'</div>';}).join('');
  drawer(id,'<div class="badges">'+badge(k.knowledge_type)+badge(k.knowledge_status,statusClass(k.knowledge_status))+badge(k.confidence_band)+'</div><h3>'+esc(k.title||'')+'</h3><p>'+esc(k.statement||'')+'</p><h3>Guidance</h3><p>'+esc(k.actionable_guidance||'')+'</p><h3>Payload</h3>'+prettyObject(k.payload||{})+'<h3>Exceptions</h3><ul>'+(k.exceptions||[]).map(function(x){return '<li>'+esc(x)+'</li>';}).join('')+'</ul><h3>Counter evidence</h3>'+prettyObject(k.counter_evidence||{})+'<h3>Sources</h3><div class="link-list">'+sources+'</div><h3>Evidence</h3><div class="link-list">'+evidence+'</div>');
}

function openPost(id){
  const p=data.postById.get(String(id)); if(!p)return;
  const c=p.creative||{},perf=p.performance||{},fam=p.family||{};
  const seq=(p.sequence||[]).map(function(s){return '<div><b>'+num(s.position)+' · '+esc(label(s.role))+'</b><p>'+esc(s.primary_text||s.overlay_text||s.spoken_summary||'')+'</p><small>'+esc(label(s.visual_type))+'</small></div>';}).join('');
  drawer(id,'<p>'+esc(p.account||'')+' · '+date(p.created_at)+'</p><div class="badges">'+badge(c.content_angle)+badge(c.hook_technique)+badge(c.content_format||c.video_format)+badge(fam.family_id)+'</div><h3>'+esc(c.hook_text||c.topic||'')+'</h3><dl><dt>Views</dt><dd>'+num(p.views)+'</dd><dt>Account percentile</dt><dd>'+pct(perf.views_percentile_account)+'</dd><dt>Operator percentile</dt><dd>'+pct(perf.views_percentile_operator)+'</dd><dt>Formula</dt><dd>'+esc(c.creative_formula||'')+'</dd><dt>Product</dt><dd>'+esc(label(c.product_placement_style))+'</dd><dt>CTA</dt><dd>'+esc(label(c.cta_type))+'</dd></dl>'+(p.url?'<p><a href="'+esc(p.url)+'" target="_blank" rel="noopener">Open original post</a></p>':'')+'<h3>Sequence</h3><div class="sequence">'+seq+'</div>');
}

function wireDrawerLinks(){
  document.querySelectorAll('[data-open-post]').forEach(function(b){b.onclick=function(){openPost(b.dataset.openPost);};});
  document.querySelectorAll('[data-open-family]').forEach(function(b){b.onclick=function(){openFamily(b.dataset.openFamily);};});
  document.querySelectorAll('[data-open-pattern]').forEach(function(b){b.onclick=function(){openPattern(b.dataset.openPattern);};});
  document.querySelectorAll('[data-open-strategy]').forEach(function(b){b.onclick=function(){openStrategy(b.dataset.openStrategy);};});
}

function wire(){
  const search=$('#search'); if(search)search.oninput=function(){query=search.value;render();};
  const fil=$('#filter'); if(fil)fil.onchange=function(){filter=fil.value;render();};
  document.querySelectorAll('[data-family]').forEach(function(b){b.onclick=function(){openFamily(b.dataset.family);};});
  document.querySelectorAll('[data-pattern]').forEach(function(b){b.onclick=function(){openPattern(b.dataset.pattern);};});
  document.querySelectorAll('[data-strategy]').forEach(function(b){b.onclick=function(){openStrategy(b.dataset.strategy);};});
  document.querySelectorAll('[data-knowledge]').forEach(function(b){b.onclick=function(){openKnowledge(b.dataset.knowledge);};});
  document.querySelectorAll('[data-open-post]').forEach(function(b){b.onclick=function(){openPost(b.dataset.openPost);};});
}

function render(){
  document.querySelectorAll('nav button').forEach(function(b){b.classList.toggle('active',b.dataset.tab===tab);});
  const views={overview:overviewView,accounts:accountsView,timeline:timelineView,families:familiesView,patterns:patternsView,strategies:strategiesView,knowledge:knowledgeView,evidence:evidenceView};
  $('#main').innerHTML=views[tab]();
  wire();
  renderCounts();
}

document.querySelectorAll('nav button').forEach(function(b){b.onclick=function(){tab=b.dataset.tab;query='';filter='';render();};});

Promise.all([
  fetch('workspace.json').then(function(r){return r.json();}),
  fetch('overview.json').then(function(r){return r.json();}),
  fetch('accounts.json').then(function(r){return r.json();}),
  fetch('timeline.json').then(function(r){return r.json();}),
  fetch('families.json').then(function(r){return r.json();}),
  fetch('patterns.json').then(function(r){return r.json();}),
  fetch('strategies.json').then(function(r){return r.json();}),
  fetch('knowledge.json').then(function(r){return r.json();}),
  fetch('evidence.json').then(function(r){return r.json();})
]).then(function(values){
  data.manifest=values[0];
  data.overview=values[1];
  data.accounts=values[2];
  data.timeline=values[3];
  data.families=values[4];
  data.patterns=values[5];
  data.strategies=values[6];
  data.knowledge=values[7];
  data.evidence=values[8];
  initMaps();
  render();
}).catch(function(e){
  $('#main').innerHTML='<h1>Workspace unavailable</h1><pre>'+esc(e.message)+'</pre>';
});