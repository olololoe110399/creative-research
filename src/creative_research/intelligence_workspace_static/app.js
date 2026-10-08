'use strict';

const $ = function(s){ return document.querySelector(s); };
const esc = function(v){ return String(v == null ? '' : v).replace(/[&<>"']/g,function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); };
const label = function(v){ return v == null || v === '' ? '—' : String(v).replaceAll('_',' '); };
const num = function(v){ return v == null || Number.isNaN(Number(v)) ? '—' : new Intl.NumberFormat('en-US',{maximumFractionDigits:1}).format(Number(v)); };
const pct = function(v){ return v == null || Number.isNaN(Number(v)) ? '—' : new Intl.NumberFormat('en-US',{style:'percent',maximumFractionDigits:1}).format(Number(v)); };
const date = function(v){ if(!v)return '—'; const d=new Date(v); return Number.isNaN(d.getTime())?String(v):d.toLocaleDateString('en-US',{year:'numeric',month:'short',day:'numeric'}); };
const json = function(v){ try{return JSON.stringify(v,null,2);}catch(e){return String(v);} };
const clamp = function(v,a,b){ return Math.max(a,Math.min(b,v)); };

let data = {};
let tab = 'production';
let query = '';
let familyFilter = 'all';
let advancedMode = 'strategies';

function byId(rows,key){ const m=new Map(); (rows||[]).forEach(function(r){ if(r&&r[key]!=null)m.set(String(r[key]),r); }); return m; }
function badge(v,cls){ return v?'<span class="badge '+(cls||'')+'">'+esc(label(v))+'</span>':''; }
function confidenceBadge(band,score){ const cls=band==='high'?'good':band==='medium'?'warn':'bad'; return badge((band||'confidence')+(score!=null?' · '+num(score):''),cls); }
function roleClass(role){ return String(role||'').includes('origin')?'origin':String(role||'').includes('receiver')?'receiver':'mixed'; }
function toast(message){ const root=$('#toast-root'); if(!root)return; const el=document.createElement('div'); el.className='toast'; el.textContent=message; root.appendChild(el); setTimeout(function(){el.remove();},3600); }

function initMaps(){
  data.postById=byId(data.evidence.posts,'post_uid');
  data.familyById=byId(data.families.families,'family_id');
  data.patternById=byId(data.patterns.patterns,'pattern_id');
  data.strategyById=byId(data.strategies.strategies,'hypothesis_id');
  data.knowledgeById=byId(data.knowledge.knowledge,'knowledge_id');
  data.accountById=byId(data.lab.account_network.nodes,'account_id');
}

function setHeader(){
  const brief=data.lab.research_brief||{}, op=brief.operator||{}, stats=brief.stats||{};
  $('#project-name').textContent=(op.name||op.operator_id||'Research project')+
    (op.verified?' · account group confirmed':'')+' · Research v3';
  $('#research-meta').textContent=(stats.posts||0)+' posts · '+(stats.accounts||0)+' accounts · '+(stats.propagation_events||0)+' observed reuse events';
  const inferred=(data.lab.research_intelligence||{}).counts?.inferred||0;
  const indicator=$('#research-count');
  if(indicator)indicator.textContent=inferred?String(inferred):'';
}

function metricCard(name,value,sub){
  return '<div class="metric-card"><small>'+esc(name)+'</small><strong>'+value+'</strong><span>'+esc(sub||'')+'</span></div>';
}

function pageHead(eyebrow,title,copy,side){
  return '<div class="page-head"><div><div class="eyebrow">'+esc(eyebrow)+'</div><h1>'+esc(title)+'</h1><p>'+esc(copy||'')+'</p></div>'+(side||'')+'</div>';
}

function briefView(){
  const b=data.lab.research_brief||{}, hero=b.hero||{}, s=b.stats||{};
  const score=hero.confidence_score==null?0:clamp(Number(hero.confidence_score)*100,0,100);
  const findings=(b.key_findings||[]).slice(0,8).map(function(f){
    return '<article class="finding-card" data-strategy="'+esc(f.hypothesis_id)+'"><div class="row"><span class="eyebrow">'+esc(label(f.hypothesis_type))+'</span>'+confidenceBadge(f.confidence_band,f.confidence_score)+badge('inferred','warn')+'</div><h3>'+esc(f.title||label(f.hypothesis_type))+'</h3><p>'+esc(f.claim||'')+'</p></article>';
  }).join('');
  const canSay=(b.key_findings||[]).slice(0,5).map(function(f){
    return '<div class="claim-item"><span class="claim-icon info">?</span><div><b>'+esc(f.title||label(f.hypothesis_type))+'</b><span>'+esc(f.claim||'')+'</span></div></div>';
  }).join('');
  const cannot=(b.guardrails||[]).map(function(g){
    return '<div class="claim-item"><span class="claim-icon no">!</span><div><b>'+esc(g.title||'Guardrail')+'</b><span>'+esc(g.detail||'')+'</span></div></div>';
  }).join('');
  const topFamilies=(data.lab.family_highlights||[]).slice(0,6).map(familyCard).join('');
  const accounts=(data.lab.account_network.nodes||[]).slice().sort(function(a,b){
    const sa=Math.max(a.originator_signal||0,a.receiver_signal||0), sb=Math.max(b.originator_signal||0,b.receiver_signal||0);
    return sb-sa;
  }).slice(0,6).map(accountCard).join('');
  return pageHead('Research brief','What this operator appears to be doing','A decision-oriented summary generated from the evidence chain. Every statement below can be opened back to its source evidence.')+
    '<section class="hero"><div><div class="eyebrow">'+esc(hero.eyebrow||'Operating model')+'</div><h2>'+esc(hero.title||'Research model is forming')+'</h2><p>'+esc(hero.summary||'')+'</p></div><div class="hero-side"><div class="confidence-ring" style="--score:'+score+'%"><span>'+num(hero.confidence_score)+'</span></div>'+(hero.hypothesis_id?'<button class="hero-link" data-strategy="'+esc(hero.hypothesis_id)+'">See why we believe this</button>':'')+'</div></section>'+
    '<div class="metric-grid">'+
      metricCard('Posts analyzed',num(s.posts),'canonical evidence')+
      metricCard('Declared accounts',num(s.accounts),'researcher-confirmed grouping')+
      metricCard('Creative concepts',num(s.families),'family candidates')+
      metricCard('Repeated concepts',num(s.repeated_families),pct(s.repeated_family_rate)+' of concepts')+
      metricCard('Cross-account repeats',num(s.cross_account_repeated_families),pct(s.cross_account_share_of_repeated)+' of repeats')+
      metricCard('Reuse events',num(s.propagation_events),'observed chronology')+
    '</div>'+
    '<section class="section"><div class="section-head"><div><h2>Most useful findings</h2><p>High-leverage interpretations before lower-level analytics.</p></div></div><div class="grid">'+(findings||'<div class="empty-state">No operating-model findings yet.</div>')+'</div></section>'+
    '<section class="section claims"><div class="claim-box"><h3>What the evidence suggests (hypotheses)</h3><p>These are evidence-linked interpretations, not verified operator intent. Check sources, counterexamples and alternatives.</p><div class="claim-list">'+(canSay||'<p>No grounded hypotheses yet.</p>')+'</div></div><div class="claim-box"><h3>What we should not claim</h3><div class="claim-list">'+cannot+'</div></div></section>'+
    '<section class="section"><div class="section-head"><div><h2>Creative ideas worth inspecting</h2><p>The strongest repeated families, visualized as executions rather than rows.</p></div><button class="hero-link" data-go="families" style="background:#fff;color:#17191d;border-color:#d3d8e0">Open library</button></div><div class="grid">'+topFamilies+'</div></section>'+
    '<section class="section"><div class="section-head"><div><h2>Account roles at a glance</h2><p>Observed origin/receiver asymmetry, not internal org-chart labels.</p></div><button class="hero-link" data-go="network" style="background:#fff;color:#17191d;border-color:#d3d8e0">Open network</button></div><div class="grid">'+accounts+'</div></section>';
}

function accountCard(a){
  const cls=roleClass(a.role_label), role=cls==='origin'?'Origin leaning':cls==='receiver'?'Receiver leaning':'Mixed / insufficient';
  return '<article class="account-card" data-account="'+esc(a.account_id)+'"><div class="row"><div>'+badge(role,cls==='origin'?'info':cls==='receiver'?'violet':'')+'</div>'+badge(a.evidence_strength||'descriptive')+'</div><h3>@'+esc(a.account||a.account_id)+'</h3><p>'+num(a.flow_observations)+' cross-account observations · '+num(a.posts)+' posts</p><div class="role-bars"><div class="role-bar"><span>Origin</span><div class="role-track"><div class="role-fill origin" style="width:'+clamp((a.originator_signal||0)*100,0,100)+'%"></div></div><b>'+pct(a.originator_signal)+'</b></div><div class="role-bar"><span>Receiver</span><div class="role-track"><div class="role-fill receiver" style="width:'+clamp((a.receiver_signal||0)*100,0,100)+'%"></div></div><b>'+pct(a.receiver_signal)+'</b></div></div></article>';
}

function networkPositions(nodes){
  const groups={origin:[],mixed:[],receiver:[]};
  nodes.forEach(function(n){groups[roleClass(n.role_label)].push(n);});
  const out=new Map(), xs={origin:185,mixed:600,receiver:1015};
  Object.keys(groups).forEach(function(g){
    const rows=groups[g];
    rows.forEach(function(n,i){
      const gap=440/(rows.length+1);
      out.set(String(n.account_id),{x:xs[g],y:40+gap*(i+1),group:g});
    });
  });
  return out;
}

function networkSvg(){
  const nodes=data.lab.account_network.nodes||[], edges=data.lab.account_network.edges||[], pos=networkPositions(nodes);
  const lines=edges.map(function(e){
    const a=pos.get(String(e.origin_account_id)), b=pos.get(String(e.target_account_id)); if(!a||!b)return '';
    const width=1.2+Math.min(7,(e.events||1)*.7), opacity=.24+Math.min(.55,(e.events||1)*.06);
    return '<path class="network-edge" data-edge="'+esc(e.origin_account_id)+'|'+esc(e.target_account_id)+'" d="M '+a.x+' '+a.y+' C '+((a.x+b.x)/2)+' '+a.y+', '+((a.x+b.x)/2)+' '+b.y+', '+b.x+' '+b.y+'" stroke-width="'+width+'" opacity="'+opacity+'" marker-end="url(#arrow)"><title>'+esc((e.origin_account||e.origin_account_id)+' → '+(e.target_account||e.target_account_id)+': '+(e.events||0)+' observed events')+'</title></path>';
  }).join('');
  const nodeEls=nodes.map(function(n){
    const p=pos.get(String(n.account_id)); if(!p)return '';
    const labelText='@'+(n.account||n.account_id), short=labelText.length>18?labelText.slice(0,17)+'…':labelText;
    return '<g class="network-node '+p.group+'" data-account="'+esc(n.account_id)+'" transform="translate('+p.x+','+p.y+')"><circle r="42"></circle><text text-anchor="middle" y="-2">'+esc(short)+'</text><text class="node-sub" text-anchor="middle" y="15">'+esc(label(n.role_label))+'</text></g>';
  }).join('');
  return '<svg class="network-svg" viewBox="0 0 1200 520" role="img" aria-label="Cross-account creative reuse network"><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3.5" orient="auto"><polygon points="0 0, 8 3.5, 0 7" fill="#9aa7b8"></polygon></marker></defs><text x="185" y="28" text-anchor="middle" fill="#667085" font-size="12">ORIGIN LEANING</text><text x="600" y="28" text-anchor="middle" fill="#667085" font-size="12">MIXED</text><text x="1015" y="28" text-anchor="middle" fill="#667085" font-size="12">RECEIVER LEANING</text>'+lines+nodeEls+'</svg>';
}

function networkView(){
  const nodes=data.lab.account_network.nodes||[], edges=(data.lab.account_network.edges||[]).slice(0,12);
  const edgeCards=edges.map(function(e){return '<article class="edge-card"><b>@'+esc(e.origin_account||e.origin_account_id)+' → @'+esc(e.target_account||e.target_account_id)+'</b><small>'+num(e.events)+' observed events · '+num(e.families)+' families · median '+num(e.median_delay_days)+' days</small></article>';}).join('');
  return pageHead('Account network','How creative ideas move across accounts','The graph shows observed family chronology. It is useful for spotting asymmetry, but does not claim that one account caused another to publish.')+
    '<div class="network-legend"><span><i class="legend-dot origin"></i>origin leaning</span><span><i class="legend-dot receiver"></i>receiver leaning</span><span><i class="legend-dot mixed"></i>mixed / insufficient</span><span>Line thickness = observed reuse events</span></div>'+
    '<section class="network-shell">'+networkSvg()+'</section>'+
    '<section class="section"><div class="section-head"><div><h2>Account roles</h2><p>Click an account for the evidence and strategy hypotheses behind its role.</p></div></div><div class="account-role-list">'+nodes.map(accountCard).join('')+'</div></section>'+
    '<section class="section"><div class="section-head"><div><h2>Strongest observed flows</h2><p>Most frequent origin → receiver relationships in the family chronology.</p></div></div><div class="edge-list">'+edgeCards+'</div></section>';
}

function familyThumbs(f){
  const ids=(f.members||[]).map(function(m){return m.post_uid;}).slice(0,3);
  if(!ids.length)return '<div class="preview-placeholder">No preview</div>';
  return ids.map(function(id){
    const p=data.postById.get(String(id))||{}, prev=p.preview||{}, src=prev.thumbnail_url||prev.thumbnail_path;
    return src?'<img class="lab-media" src="'+esc(src)+'" loading="lazy" alt="">':'<div class="preview-placeholder">'+esc(p.account||'post')+'</div>';
  }).join('');
}

function familyCard(f){
  const full=data.familyById?data.familyById.get(String(f.family_id)):null, row=full||f;
  return '<article class="family-card" data-family="'+esc(row.family_id)+'"><div class="family-preview">'+familyThumbs(row)+'</div><div class="family-body"><div class="row"><div>'+badge((row.member_count||0)+' executions','info')+'</div>'+badge((row.accounts_count||0)+' accounts')+'</div><h3>'+esc(row.core_hook_text||row.title||row.core_angle||'Repeated creative concept')+'</h3><p>'+esc(label(row.core_angle))+(row.origin_account?' · first seen @'+esc(row.origin_account):'')+'</p><div class="badges">'+badge(row.cross_account?'cross-account':'single-account',row.cross_account?'good':'')+(row.languages_count?badge(row.languages_count+' languages'):'')+'</div></div></article>';
}

function familiesView(){
  let rows=(data.families.families||[]).filter(function(f){return (f.member_count||0)>1;});
  if(familyFilter==='cross')rows=rows.filter(function(f){return !!f.cross_account;});
  if(familyFilter==='largest')rows=rows.filter(function(f){return (f.member_count||0)>=3;});
  if(query)rows=rows.filter(function(f){return JSON.stringify(f).toLowerCase().includes(query.toLowerCase());});
  rows.sort(function(a,b){return (b.member_count||0)-(a.member_count||0)||(b.accounts_count||0)-(a.accounts_count||0);});
  return pageHead('Creative library','Repeated ideas, shown as executions','Browse concepts that were actually reused. Open a family to compare hooks, accounts, chronology, and original evidence.')+
    '<div class="toolbar"><input id="search" placeholder="Search hook, concept, account…" value="'+esc(query)+'"><select id="family-filter"><option value="all">All repeated families</option><option value="cross" '+(familyFilter==='cross'?'selected':'')+'>Cross-account only</option><option value="largest" '+(familyFilter==='largest'?'selected':'')+'>3+ executions</option></select></div>'+
    '<div class="grid">'+(rows.map(familyCard).join('')||'<div class="empty-state">No families match this view.</div>')+'</div>';
}

function advancedView(){
  const tabs=['strategies','patterns','evidence','knowledge','timeline'];
  let body='';
  if(advancedMode==='strategies'){
    body='<div class="grid">'+(data.strategies.strategies||[]).map(function(s){return '<article class="finding-card" data-strategy="'+esc(s.hypothesis_id)+'"><div class="row">'+badge(label(s.hypothesis_type))+confidenceBadge(s.confidence_band,s.confidence_score)+'</div><h3>'+esc(s.title||s.hypothesis_id)+'</h3><p>'+esc(s.claim||'')+'</p></article>';}).join('')+'</div>';
  }else if(advancedMode==='patterns'){
    body='<div class="grid">'+(data.patterns.patterns||[]).map(function(p){return '<article class="finding-card" data-pattern="'+esc(p.pattern_id)+'"><div class="row">'+badge(label(p.pattern_type))+badge(p.evidence_strength)+'</div><h3>'+esc(p.title||p.pattern_id)+'</h3><p>'+esc(p.observation||'')+'</p></article>';}).join('')+'</div>';
  }else if(advancedMode==='knowledge'){
    body='<div class="grid">'+(data.knowledge.knowledge||[]).map(function(k){return '<article class="finding-card" data-knowledge="'+esc(k.knowledge_id)+'"><div class="row">'+badge(k.knowledge_type)+badge(k.knowledge_status,k.knowledge_status==='approved'?'good':k.knowledge_status==='promoted'||k.knowledge_status==='review_candidate'?'warn':'bad')+'</div><h3>'+esc(k.title||k.knowledge_id)+'</h3><p>'+esc(k.statement||'')+'</p></article>';}).join('')+'</div>';
  }else if(advancedMode==='timeline'){
    body='<div class="table"><table><thead><tr><th>Period</th><th>Posts</th><th>Top angle</th><th>Product</th><th>CTA</th><th>Family origins</th><th>Imports</th></tr></thead><tbody>'+(data.timeline.operator_windows||[]).map(function(w){return '<tr><td>'+esc(w.period_id)+'</td><td>'+num(w.posts)+'</td><td>'+esc(label(w.top_content_angle))+'</td><td>'+pct(w.product_rate)+'</td><td>'+pct(w.cta_rate)+'</td><td>'+num(w.family_origins)+'</td><td>'+num(w.imported_family_entries)+'</td></tr>';}).join('')+'</tbody></table></div>';
  }else{
    const rows=(data.evidence.posts||[]).slice(0,500);
    body='<div class="table"><table><thead><tr><th>Post</th><th>Account</th><th>Date</th><th>Hook / topic</th><th>Family</th><th>Views</th></tr></thead><tbody>'+rows.map(function(p){const c=p.creative||{},f=p.family||{};return '<tr><td><button class="link-button" data-post="'+esc(p.post_uid)+'">'+esc(p.post_uid)+'</button></td><td>@'+esc(p.account||'')+'</td><td>'+date(p.created_at)+'</td><td class="wrap">'+esc(c.hook_text||c.topic||'')+'</td><td>'+esc(f.family_id||'—')+'</td><td>'+num(p.views)+'</td></tr>';}).join('')+'</tbody></table></div>';
  }
  return pageHead('Advanced','Raw research layers','Use these views when you need the underlying hypothesis, pattern, timeline, knowledge, or post-level evidence.')+
    '<div class="advanced-tabs">'+tabs.map(function(t){return '<button data-advanced="'+t+'" class="'+(advancedMode===t?'active':'')+'">'+esc(label(t))+'</button>';}).join('')+'</div>'+body;
}

function drawer(title,body){
  const old=$('#drawer-bg'); if(old)old.remove();
  document.body.insertAdjacentHTML('beforeend','<div class="drawer-bg" id="drawer-bg"><aside class="drawer"><div class="drawer-top"><div><div class="eyebrow">Evidence detail</div><h2>'+esc(title)+'</h2></div><button class="drawer-close" id="drawer-close">Close</button></div>'+body+'</aside></div>');
  $('#drawer-close').onclick=function(){$('#drawer-bg').remove();};
  $('#drawer-bg').onclick=function(e){if(e.target.id==='drawer-bg')e.currentTarget.remove();};
  wire();
}

function postButton(postId,text){
  if(!postId||!data.postById.has(String(postId)))return '';
  return '<button class="link-button" data-post="'+esc(postId)+'">'+esc(text||postId)+'</button>';
}
function familyButton(id,text){
  if(!id||!data.familyById.has(String(id)))return '';
  return '<button class="link-button" data-family="'+esc(id)+'">'+esc(text||id)+'</button>';
}
function patternButton(id,text){
  if(!id||!data.patternById.has(String(id)))return '';
  return '<button class="link-button" data-pattern="'+esc(id)+'">'+esc(text||id)+'</button>';
}
function strategyButton(id,text){
  if(!id||!data.strategyById.has(String(id)))return '';
  return '<button class="link-button" data-strategy="'+esc(id)+'">'+esc(text||id)+'</button>';
}

function openAccount(id){
  const a=data.accountById.get(String(id)); if(!a)return;
  const strats=(a.strategy_hypotheses||[]).map(function(s){return strategyButton(s.hypothesis_id,s.title||s.hypothesis_type);}).join('');
  drawer('@'+(a.account||id),
    '<div class="badges">'+badge(label(a.role_label),roleClass(a.role_label)==='origin'?'info':roleClass(a.role_label)==='receiver'?'violet':'')+badge(a.evidence_strength||'descriptive')+'</div>'+
    '<h3>Observed role evidence</h3><dl><dt>Cross-account observations</dt><dd>'+num(a.flow_observations)+'</dd><dt>Origin signal</dt><dd>'+pct(a.originator_signal)+'</dd><dt>Receiver signal</dt><dd>'+pct(a.receiver_signal)+'</dd><dt>Amplifier signal</dt><dd>'+pct(a.amplifier_signal)+'</dd></dl>'+
    '<h3>Interpretation</h3><p>'+esc(roleClass(a.role_label)==='origin'?'This account repeatedly appears as the first observed account for reused families. Treat this as origin/exploration evidence, not proof that the operator deliberately uses it as a testing account.':roleClass(a.role_label)==='receiver'?'This account repeatedly receives families first observed elsewhere. Receiving behavior is not enough to call it a scaling account.':'Current cross-account flow is mixed or the sample is not asymmetric enough for a strong role claim.')+'</p>'+
    '<h3>Traceable role denominator</h3>'+(!a.lineage_matches_summary?'<p class="method-note">Warning: role summary and direct family lineage do not agree; do not trust this role until resolved.</p>':'')+roleEvidenceHtml(a.role_lineage)+
    '<h3>Strategy hypotheses</h3><div class="link-list">'+(strats||'<p>No account-level strategy hypothesis.</p>')+'</div>');
}

function openFamily(id){
  const f=data.familyById.get(String(id)); if(!f)return;
  const members=(f.members||[]).map(function(m){
    const p=data.postById.get(String(m.post_uid))||{}, c=p.creative||{};
    return '<div>'+postButton(m.post_uid,'@'+(m.account||p.account||'')+' · '+(c.hook_text||m.hook_text||m.post_uid))+'</div>';
  }).join('');
  const prop=(f.propagation||[]).map(function(p){
    const kept=(function(){try{return JSON.parse(p.preserved_dimensions_json||'[]');}catch(e){return [];}})();
    const changed=(function(){try{return JSON.parse(p.changed_dimensions_json||'[]');}catch(e){return [];}})();
    return '<div class="panel"><b>@'+esc(p.origin_account||'')+' → @'+esc(p.target_account||'')+'</b><p>'+num(p.delay_from_family_origin_days)+' days after first observed family post</p>'+
      '<div class="flow-posts">'+postButton(p.family_origin_post_uid,'Open origin execution')+postButton(p.target_first_post_uid,'Open receiving execution')+'</div>'+
      '<small>Origin percentile '+pct(p.origin_views_percentile_account)+' · receiver percentile '+pct(p.target_first_views_percentile_account)+'</small>'+
      '<p>Preserved: '+esc(kept.join(', ')||'unknown')+' · Changed: '+esc(changed.join(', ')||'unknown')+'</p></div>';
  }).join('');
  drawer(f.core_hook_text||f.family_id,
    '<div class="family-preview" style="border-radius:14px;margin:10px 0 18px">'+familyThumbs(f)+'</div>'+
    '<div class="badges">'+badge((f.member_count||0)+' executions','info')+badge((f.accounts_count||0)+' accounts')+badge(f.cross_account?'cross-account':'single-account',f.cross_account?'good':'')+'</div>'+
    '<h3>What appears preserved</h3><dl><dt>Angle</dt><dd>'+esc(label(f.core_angle))+'</dd><dt>Hook formula</dt><dd>'+esc(label(f.core_hook_formula))+'</dd><dt>Creative formula</dt><dd>'+esc(label(f.core_creative_formula))+'</dd><dt>First observed account</dt><dd>@'+esc(f.origin_account||'—')+'</dd></dl>'+
    '<h3>Executions</h3><div class="link-list">'+members+'</div>'+
    '<p class="research-limitation">Creative family matches are algorithmic candidates based on normalized creative and sequence evidence, not proof of identical visual execution or operator intent.</p>'+
    '<h3>Cross-account chronology</h3><div class="link-list">'+(prop||'<p>No cross-account propagation in this family.</p>')+'</div>');
}

function openPattern(id){
  const p=data.patternById.get(String(id)); if(!p)return;
  const links=(p.evidence_links||[]).slice(0,100).map(function(l){return postButton(l.post_uid,(l.link_role||'evidence')+' · '+(l.post_uid||''))+familyButton(l.family_id,l.family_id);}).join('');
  drawer(p.title||id,'<div class="badges">'+badge(label(p.pattern_type))+badge(p.evidence_strength,p.evidence_strength==='high'?'good':'warn')+'</div><p>'+esc(p.observation||'')+'</p><dl><dt>Sample</dt><dd>'+num(p.sample_size)+'</dd><dt>Support rate</dt><dd>'+pct(p.support_rate)+'</dd><dt>Effect size</dt><dd>'+num(p.effect_size)+'</dd><dt>Causal claim</dt><dd>'+esc(String(p.causal_claim))+'</dd></dl><h3>Metrics</h3><pre>'+esc(json(p.metrics||{}))+'</pre><h3>Counter evidence</h3><pre>'+esc(json(p.counter_evidence||{}))+'</pre><h3>Evidence</h3><div class="link-list">'+links+'</div>');
}

function openStrategy(id){
  const s=data.strategyById.get(String(id)); if(!s)return;
  const patterns=(s.pattern_links||[]).map(function(l){return patternButton(l.pattern_id,(l.relation||'support')+' · '+l.pattern_id);}).join('');
  const posts=(s.evidence_links||[]).slice(0,120).map(function(l){return postButton(l.post_uid,(l.relation||'evidence')+' · '+(l.post_uid||''))+familyButton(l.family_id,l.family_id);}).join('');
  drawer(s.title||id,'<div class="badges">'+confidenceBadge(s.confidence_band,s.confidence_score)+badge(label(s.hypothesis_type))+badge(s.promotion_readiness)+'</div><h3>Claim</h3><p>'+esc(s.claim||'')+'</p><h3>Why</h3><pre>'+esc(json(s.evidence_summary||{}))+'</pre><h3>Possible alternatives</h3><ul>'+(s.alternative_explanations||[]).map(function(x){return '<li>'+esc(x)+'</li>';}).join('')+'</ul><h3>Counter evidence</h3><pre>'+esc(json(s.counter_evidence||{}))+'</pre><h3>Supporting / counter patterns</h3><div class="link-list">'+patterns+'</div>'+strategyFlowHtml(s)+'<h3>Evidence posts and families</h3><div class="link-list">'+posts+'</div>');
}

function openKnowledge(id){
  const k=data.knowledgeById.get(String(id)); if(!k)return;
  const sources=(k.source_links||[]).map(function(l){return data.strategyById.has(String(l.source_id))?strategyButton(l.source_id,'Strategy source · '+l.source_id):'<div>'+esc(l.source_type)+': '+esc(l.source_id)+'</div>';}).join('');
  drawer(k.title||id,'<div class="badges">'+badge(k.knowledge_type)+badge(k.knowledge_status,k.knowledge_status==='approved'?'good':k.knowledge_status==='promoted'||k.knowledge_status==='review_candidate'?'warn':'bad')+confidenceBadge(k.confidence_band,k.confidence_score)+'</div><p>'+esc(k.statement||'')+'</p><h3>Practical guidance</h3>'+(k.knowledge_status==='rejected'||k.knowledge_status==='hold'?'<p class="method-note">Legacy catalog annotation: guidance withheld. This is not evidence of operator intent.</p>':'<p>'+esc(k.actionable_guidance||'')+'</p>')+'<h3>Exceptions / caveats</h3><ul>'+(k.exceptions||[]).map(function(x){return '<li>'+esc(x)+'</li>';}).join('')+'</ul><h3>Counter evidence</h3><pre>'+esc(json(k.counter_evidence||{}))+'</pre><h3>Source</h3><div class="link-list">'+sources+'</div>');
}

function openPost(id){
  const p=data.postById.get(String(id)); if(!p)return;
  const c=p.creative||{}, perf=p.performance||{}, fam=p.family||{}, prev=p.preview||{}, src=prev.thumbnail_url||prev.thumbnail_path, video=prev.video_url||prev.video_path;
  const seq=(p.sequence||[]).map(function(s){return '<div><b>'+num(s.position)+' · '+esc(label(s.role))+'</b><p>'+esc(s.primary_text||s.overlay_text||s.spoken_summary||'')+'</p><small>'+esc(label(s.visual_type))+'</small></div>';}).join('');
  const media=video?'<video class="post-preview-large lab-media" controls preload="metadata" '+(src?'poster="'+esc(src)+'"':'')+'><source src="'+esc(video)+'"></video>':src?'<img class="post-preview-large lab-media" src="'+esc(src)+'" alt="">':'<div class="empty-state">Archived media is unavailable for this post.</div>';
  drawer('@'+(p.account||'')+' · '+(c.hook_text||p.post_uid),media+'<div class="badges">'+badge(c.content_angle)+badge(c.hook_technique)+badge(fam.family_id)+(prev.thumbnail_source?badge(prev.thumbnail_source,'info'):'')+'</div><dl><dt>Date</dt><dd>'+date(p.created_at)+'</dd><dt>Views</dt><dd>'+num(p.views)+'</dd><dt>Account percentile</dt><dd>'+pct(perf.views_percentile_account)+'</dd><dt>Topic</dt><dd>'+esc(c.topic||'—')+'</dd><dt>Creative formula</dt><dd>'+esc(c.creative_formula||'—')+'</dd></dl>'+(p.url?'<p><a href="'+esc(p.url)+'" target="_blank" rel="noopener">Open original TikTok ↗</a></p>':'')+'<h3>Sequence</h3><div class="sequence">'+seq+'</div>');
}

function openEdge(key){
  const parts=key.split('|'), edge=(data.lab.account_network.edges||[]).find(function(e){return String(e.origin_account_id)===parts[0]&&String(e.target_account_id)===parts[1];});
  if(!edge)return;
  const fams=(edge.family_ids||[]).map(function(id){return familyButton(id,id);}).join('');
  drawer('@'+(edge.origin_account||parts[0])+' → @'+(edge.target_account||parts[1]),'<div class="badges">'+badge((edge.events||0)+' events','info')+badge((edge.families||0)+' families')+badge('median '+num(edge.median_delay_days)+' days')+'</div><h3>Observed families</h3><div class="link-list">'+fams+'</div><p>This is chronology inside matched creative families, not a causal claim about publishing decisions.</p>');
}

function wire(){
  document.querySelectorAll('.lab-media').forEach(function(media){
    media.addEventListener('error',function(){
      const placeholder=document.createElement('div');
      placeholder.className='preview-placeholder';
      placeholder.textContent='Media unavailable';
      media.replaceWith(placeholder);
    },{once:true});
  });
  document.querySelectorAll('[data-go]').forEach(function(b){b.onclick=function(){tab=b.dataset.go;query='';render();};});
  document.querySelectorAll('[data-strategy]').forEach(function(b){b.onclick=function(){openStrategy(b.dataset.strategy);};});
  document.querySelectorAll('[data-pattern]').forEach(function(b){b.onclick=function(){openPattern(b.dataset.pattern);};});
  document.querySelectorAll('[data-family]').forEach(function(b){b.onclick=function(){openFamily(b.dataset.family);};});
  document.querySelectorAll('[data-account]').forEach(function(b){b.onclick=function(){openAccount(b.dataset.account);};});
  document.querySelectorAll('[data-knowledge]').forEach(function(b){b.onclick=function(){openKnowledge(b.dataset.knowledge);};});
  document.querySelectorAll('[data-post]').forEach(function(b){b.onclick=function(){openPost(b.dataset.post);};});
  document.querySelectorAll('[data-edge]').forEach(function(b){b.onclick=function(){openEdge(b.dataset.edge);};});
  document.querySelectorAll('[data-advanced]').forEach(function(b){b.onclick=function(){advancedMode=b.dataset.advanced;render();};});
  const search=$('#search'); if(search)search.oninput=function(){query=search.value;render();};
  const ff=$('#family-filter'); if(ff)ff.onchange=function(){familyFilter=ff.value;render();};
  wireResearchControls();
  wireProductionControls();
}

function render(){
  document.querySelectorAll('.primary-nav button').forEach(function(b){b.classList.toggle('active',b.dataset.tab===tab);});
  const views={brief:briefView,network:networkView,families:familiesView,
    production:productionView,
    intelligence:researchIntelligenceView,playbook:researchPlaybookView,
    experiments:experimentPlanView,advanced:advancedView};
  $('#main').innerHTML=views[tab]();
  wire();
}

document.querySelectorAll('.primary-nav button').forEach(function(b){
  b.onclick=function(){tab=b.dataset.tab;query='';render();};
});

Promise.all([
  fetch('workspace.json',{cache:'no-store'}).then(function(r){return r.json();}),
  fetch('overview.json',{cache:'no-store'}).then(function(r){return r.json();}),
  fetch('accounts.json',{cache:'no-store'}).then(function(r){return r.json();}),
  fetch('timeline.json',{cache:'no-store'}).then(function(r){return r.json();}),
  fetch('families.json',{cache:'no-store'}).then(function(r){return r.json();}),
  fetch('patterns.json',{cache:'no-store'}).then(function(r){return r.json();}),
  fetch('strategies.json',{cache:'no-store'}).then(function(r){return r.json();}),
  fetch('knowledge.json',{cache:'no-store'}).then(function(r){return r.json();}),
  fetch('evidence.json',{cache:'no-store'}).then(function(r){return r.json();}),
  fetch('lab.json',{cache:'no-store'}).then(function(r){return r.json();}),
  fetch('production.json',{cache:'no-store'}).then(function(r){return r.json();})
]).then(function(values){
  if(values[0].workspace_schema_version!=='operator-intelligence-lab-v3'||
     !values[9]||!values[9].research_intelligence||
     !values[10]||values[10].schema_version!=='creator-production-kit-v1'){

    throw new Error('Old workspace detected. Run intelligence-build --from-stage workspace --force, then restart Lab.');
  }
  data.manifest=values[0];
  data.overview=values[1];
  data.accounts=values[2];
  data.timeline=values[3];
  data.families=values[4];
  data.patterns=values[5];
  data.strategies=values[6];
  data.knowledge=values[7];
  data.evidence=values[8];
  data.lab=values[9];
  data.production=values[10];
  initMaps();
  setHeader();
  render();
  reloadExperimentPlan();
}).catch(function(e){
  $('#main').innerHTML='<div class="empty-state"><h2>Research lab unavailable</h2><p>'+esc(e.message)+'</p></div>';
});
