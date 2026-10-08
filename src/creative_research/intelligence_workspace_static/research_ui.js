'use strict';

/* Research is classified by evidence, not researcher approvals. Selecting an
 * experiment records your own intention to test, NOT truth about an operator.
 */
let myExperimentPlan={entries:[],selected_keys:[],selected_count:0};
let experimentLoadError='';

function researchIntelligenceView(){
  const r=data.lab.research_intelligence||{};
  const stats=r.counts||{}, qa=r.family_quality||{}, q=qa.counts||{};
  const observed=(r.observed||[]).map(function(item){
    return '<article class="research-card">'+
      '<div class="row"><b>'+esc(item.title||'Observed evidence')+'</b>'+badge('observed','good')+'</div>'+
      '<p>'+esc(item.statement||'')+'</p>'+
      '<p class="research-limitation"><b>Limit:</b> '+esc(item.limitations||'')+'</p>'+
      '</article>';
  }).join('');
  const inferred=(r.inferred||[]).slice(0,16).map(function(item){
    const sid=String(item.id||'');
    const headline='<button class="research-title" data-strategy="'+esc(sid)+'">'+esc(item.title||item.hypothesis_type||sid)+'</button>';
    return '<article class="research-card"><div class="row">'+headline+badge('inferred','warn')+'</div>'+
      '<p>'+esc(item.claim||'')+'</p>'+
      '<div class="research-meta">Model confidence: '+num(item.confidence_score)+
      ' · Not evidence of operator intent</div>'+
      '<button class="link-button" data-strategy="'+esc(sid)+'">Evidence, counters and alternatives →</button>'+
      '</article>';
  }).join('');
  const unknown=(r.unknown||[]).map(function(item){
    return '<article class="research-card"><div class="row"><b>'+esc(item.title||'Unknown')+'</b>'+badge('unknown')+'</div>'+
      '<p>'+esc(item.statement||'')+'</p>'+
      '<p class="research-limitation"><b>Why:</b> '+esc(item.reason||'')+'</p></article>';
  }).join('');
  const flagged=(qa.items||[]).filter(function(item){
    return item.automated_state!=='structurally_consistent_candidate';
  });
  const familyFlags=flagged.slice(0,12).map(function(item){
    return '<div class="research-quality-item">'+
      familyButton(item.family_id,item.family_id)+
      '<span>'+badge(item.automated_state,item.automated_state==='integrity_gap'?'bad':'warn')+
      ' '+num(item.member_count)+' executions'+
      (item.multilingual?' · multilingual':'')+
      '</span><small>'+esc((item.flags||[]).map(label).join(' · '))+'</small></div>';
  }).join('');
  return pageHead('Research intelligence','What we know, infer and cannot know',
      'No claim approval is required. The engine checks evidence, exposes uncertainty and links directly to sources.')+
    '<div class="research-triad">'+
      '<div><strong>'+num(stats.observed)+'</strong><span>Observed</span><small>Deterministic counts/chronology</small></div>'+
      '<div><strong>'+num(stats.inferred)+'</strong><span>Inferred</span><small>Bounded hypotheses</small></div>'+
      '<div><strong>'+num(stats.unknown)+'</strong><span>Unknown</span><small>Not knowable from public posts</small></div>'+
    '</div>'+
    '<section class="section"><div class="section-head"><div><h2>Observed</h2>'+
      '<p>What the source records and reconciled counts actually show.</p></div></div>'+
      '<div class="grid two">'+(observed||'<div class="empty-state">No observations.</div>')+'</div></section>'+
    '<section class="section"><div class="section-head"><div><h2>Inferred</h2>'+
      '<p>Model interpretations, with counter-evidence and limits—not proven internal intent.</p></div></div>'+
      '<div class="grid two">'+(inferred||'<div class="empty-state">No defensible hypotheses yet.</div>')+'</div></section>'+
    '<section class="section"><div class="section-head"><div><h2>Unknown</h2>'+
      '<p>These questions cannot be truth-certified by a public TikTok dataset.</p></div></div>'+
      '<div class="grid two">'+unknown+'</div></section>'+
    '<section class="section"><div class="section-head"><div><h2>Automated family-quality diagnostics</h2>'+
      '<p>Multilingual normalized signatures and clustering evidence; no manual approval queue.</p></div></div>'+
      '<div class="research-quality-summary">'+
        badge(num(q.repeated_families_checked)+' repeated families checked','info')+
        badge(num(q.multilingual_families)+' multilingual')+
        badge(num(q.semantic_uncertain)+' semantic flags','warn')+
        badge(num(q.integrity_gaps)+' integrity gaps',q.integrity_gaps?'bad':'good')+
      '</div>'+
      '<p class="research-limitation">Diagnostic flags do not prove a bad match. Ambiguous pairs can be reassessed by the upstream calibrated family-judge pipeline; this screen never starts an AI model or requests manual approval.</p>'+
      '<div class="research-quality-list">'+
        (familyFlags||'<div class="empty-state">No flagged repeated families in this snapshot.</div>')+
      '</div></section>'+
    '<section class="section"><div class="section-head"><div><h2>Turn research into experiments</h2>'+
      '<p>Choose what is worth testing on your accounts; you are not approving an operator claim.</p></div>'+
      '<button class="hero-link research-go" data-go="playbook">Open Operator Playbook →</button>'+
      '</div></section>';
}

function currentExperiments(){
  return new Set((myExperimentPlan||{}).selected_keys||[]);
}

function researchPlaybookView(){
  const research=data.lab.research_intelligence||{}, rows=research.experiment_candidates||[];
  const selected=currentExperiments();
  const cards=rows.map(function(item,i){
    const key=String(item.key||'');
    const active=selected.has(key);
    const linked=item.related_hypothesis_id;
    return '<article class="playbook-step">'+
      '<div class="row"><span class="eyebrow">EXPERIMENT '+(i+1)+'</span>'+
      badge(item.basis==='inferred'?'hypothesis-informed':'method only',item.basis==='inferred'?'warn':'')+'</div>'+
      '<h2>'+esc(item.title||key)+'</h2>'+
      '<p><b>What to try:</b> '+esc(item.application_exercise||'')+'</p>'+
      '<p><b>Measure:</b> '+esc(item.suggested_metric||'')+'</p>'+
      '<p><b>Stop/recheck:</b> '+esc(item.stop_or_recheck||'')+'</p>'+
      '<p class="research-limitation">This is a proposed experiment, NOT proof it worked for this operator or will work for you.</p>'+
      (linked?strategyButton(linked,'Inspect related inference →'):'')+
      '<button class="research-experiment-button" data-exp-key="'+esc(key)+'" data-exp-action="'+(active?'remove':'add')+'">'+
      (active?'Remove from My Experiment Plan':'Add to My Experiment Plan')+'</button>'+
      '</article>';
  }).join('');
  return pageHead('Operator playbook','Choose what to test, not what to approve',
      'Suggested experiments derive from observed/inferred research and stay provisional until you collect your own outcomes.')+
    '<div class="playbook-intro"><div class="row"><div><h2>Evidence-linked ideas</h2>'+
      '<p>The system generates candidate experiments automatically. Human approval of an operator hypothesis is never a prerequisite.</p></div>'+
      badge(num(rows.length)+' candidates','info')+'</div>'+
      '<button class="hero-link research-go" data-go="experiments">My Experiment Plan ('+num(selected.size)+') →</button>'+
      '</div>'+
    '<div class="playbook-grid">'+(cards||'<div class="empty-state">No experiment suggestions available.</div>')+'</div>'+
    '<p class="research-limitation">Research evidence is observational. Direct tests and outcome measures belong to your own accounts; avoid copying original creative verbatim.</p>';
}

function experimentPlanView(){
  const entries=(myExperimentPlan||{}).entries||[];
  const cards=entries.map(function(row){
    const item=row.candidate||{},key=String(row.key||'');
    return '<article class="playbook-step">'+
      '<div class="row"><b>'+esc(item.title||key)+'</b>'+badge(row.needs_recheck?'needs recheck':row.state,row.needs_recheck?'warn':'good')+'</div>'+
      '<p>'+esc(item.application_exercise||'')+'</p>'+
      (row.needs_recheck?'<p class="method-note">Research evidence changed. Remove and reselect this item before updating results.</p>':'')+
      '<p><b>Measure:</b> '+esc(item.suggested_metric||'')+'</p>'+
      '<label class="research-field-label">Your progress'+
        '<select data-exp-state="'+esc(key)+'">'+
        ['planned','running','evaluated','abandoned'].map(function(v){
          return '<option value="'+v+'" '+(row.state===v?'selected':'')+'>'+esc(label(v))+'</option>';
        }).join('')+'</select></label>'+
      '<label class="research-field-label">Actual metric observed (your own data)'+
        '<input data-exp-metric="'+esc(key)+'" maxlength="2000" placeholder="e.g. 7-day account-relative views percentile" value="'+esc(row.metric_observed||'')+'"></label>'+
      '<label class="research-field-label">What happened / caveats'+
        '<textarea data-exp-notes="'+esc(key)+'" maxlength="2000" rows="3" placeholder="Record wins, losses and missing evidence">'+esc(row.notes||'')+'</textarea></label>'+
      '<div class="research-action-row">'+
        '<button class="research-experiment-button" data-exp-key="'+esc(key)+'" data-exp-action="progress" '+(row.needs_recheck?'disabled':'')+'>Save my results</button>'+
        '<button class="research-experiment-button remove" data-exp-key="'+esc(key)+'" data-exp-action="remove">Remove</button>'+
      '</div></article>';
  }).join('');
  return pageHead('My Experiment Plan','What you actually want to try',
      'This is your first-party research plan, not a verification of the observed operator.')+
    '<div class="research-triad"><div><strong>'+num(entries.length)+'</strong><span>Selected experiments</span>'+
    '<small>Local and private, no operator approval</small></div></div>'+
    (experimentLoadError?'<p class="method-note">'+esc(experimentLoadError)+'</p>':'')+
    '<div class="playbook-grid">'+(cards||'<div class="empty-state">No experiments selected. Open the Operator Playbook and choose an idea to test.</div>')+'</div>'+
    '<div class="section"><button class="hero-link research-go" data-go="playbook">Browse suggested experiments →</button></div>';
}

async function reloadExperimentPlan(){
  try{
    const response=await fetch('/api/experiments',{cache:'no-store'});
    const result=await response.json();
    if(!response.ok)throw new Error(result.error||'Experiment Plan unavailable');
    myExperimentPlan=result;
    experimentLoadError='';
  }catch(e){
    experimentLoadError=e.message;
  }
  if(tab==='playbook'||tab==='experiments')render();
}

async function editExperimentPlan(key,action){
  const payload={key,action};
  if(action==='progress'){
    const state=document.querySelector('[data-exp-state="'+key+'"]');
    const notes=document.querySelector('[data-exp-notes="'+key+'"]');
    const metric=document.querySelector('[data-exp-metric="'+key+'"]');
    payload.state=state?state.value:'planned';
    payload.notes=notes?notes.value:'';
    payload.metric_observed=metric?metric.value:'';
  }
  try{
    const response=await fetch('/api/experiments',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(payload),cache:'no-store'
    });
    const result=await response.json();
    if(!response.ok)throw new Error(result.error||'Experiment Plan change failed');
    myExperimentPlan=result.plan;
    experimentLoadError='';
    toast(action==='add'?'Added to your experiment plan.':
      action==='remove'?'Removed from plan.':'First-party experiment notes saved.');
    render();
  }catch(e){
    experimentLoadError=e.message;
    toast('Experiment plan: '+e.message);
  }
}

function wireResearchControls(){
  document.querySelectorAll('[data-exp-key]').forEach(function(button){
    button.onclick=function(){
      editExperimentPlan(button.dataset.expKey,button.dataset.expAction);
    };
  });
  document.querySelectorAll('[data-go]').forEach(function(button){
    if(button.classList.contains('research-go')){
      button.onclick=function(){tab=button.dataset.go;render();};
    }
  });
}
