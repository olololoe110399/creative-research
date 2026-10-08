'use strict';

/* All model output is displayed as a proposal. Clickable source links resolve
 * against the Lab's existing canonical maps; there is no AI-generated HTML.
 */
let aiServiceStatus=null;
let aiLastReport=null;
let aiPending=null;

function aiModeName(mode){
  return ({
    investigate:'AI Investigate',challenge:'AI Challenge',
    draft_playbook:'AI Draft Playbook',stress_test:'AI Stress Test'
  })[mode]||'AI Research';
}

function aiControlsMarkup(kind,id,modes){
  if(!id)return '';
  const controls=modes.map(function(mode){
    return '<button type="button" class="ai-action" data-ai-mode="'+esc(mode)+
      '" data-ai-kind="'+esc(kind)+'" data-ai-target="'+esc(id)+'">'+
      '<span aria-hidden="true">✦</span> '+esc(aiModeName(mode))+'</button>';
  }).join('');
  return '<section class="ai-controls"><div class="row"><div><b>AI Research Copilot</b>'+
    '<small>Research proposals only · citations checked · human approval required</small></div>'+
    (aiLastReport?'<button class="ai-history-link" data-ai-last="1">Last AI report ↗</button>':'')+'</div>'+
    '<div class="ai-control-row">'+controls+'</div>'+
    '<small class="ai-status-note">'+
      (aiServiceStatus&&aiServiceStatus.enabled?
        (aiServiceStatus.configured?'Gemini enabled with a per-session call limit.':'GEMINI_API_KEY is missing.'):
        'AI calls are off by default. Launch Lab with --ai-enabled to run; evidence previews are free.')+
    '</small></section>';
}

async function aiFetch(path,payload){
  const response=await fetch(path,{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify(payload),
    cache:'no-store'
  });
  const data=await response.json();
  if(!response.ok)throw new Error(data.error||'AI research request failed');
  return data;
}

function aiSourceButton(ref){
  const parts=String(ref||'').split(':');
  const type=parts.shift(),id=parts.join(':');
  const name=esc(type+': '+id);
  if(type==='post')return postButton(id,name);
  if(type==='family')return familyButton(id,name);
  if(type==='hypothesis')return strategyButton(id,name);
  if(type==='pattern')return patternButton(id,name);
  if(type==='knowledge'&&data.knowledgeById&&data.knowledgeById.has(id)){
    return '<button class="link-button" data-knowledge="'+esc(id)+'">'+name+'</button>';
  }
  return '<span class="ai-missing-ref">Evidence unavailable: '+name+'</span>';
}

function aiCitations(refs){
  if(!Array.isArray(refs)||!refs.length)return '<span>Not cited</span>';
  return '<div class="ai-source-links">'+refs.map(aiSourceButton).join('')+'</div>';
}

function aiDrawReport(report){
  aiLastReport=report;
  const answer=report.answer||{};
  const findings=(answer.findings||[]).map(function(f){
    return '<article class="ai-finding">'+
      '<div class="badges">'+badge(f.interpretation,f.interpretation==='counterexample'?'warn':'info')+'</div>'+
      '<p>'+esc(f.statement||'')+'</p>'+aiCitations(f.evidence_refs)+'</article>';
  }).join('');
  const experiments=(answer.experiments||[]).map(function(e,i){
    return '<article class="ai-finding"><h4>Experiment '+(i+1)+'</h4>'+
      '<p>'+esc(e.action||'')+'</p>'+
      '<dl><dt>Measure</dt><dd>'+esc(e.success_metric||'')+'</dd>'+
      '<dt>Stop / recheck</dt><dd>'+esc(e.stop_or_recheck||'')+'</dd></dl>'+
      aiCitations(e.evidence_refs)+'</article>';
  }).join('');
  const bullets=function(arr){return '<ul>'+(arr||[]).map(function(item){return '<li>'+esc(item)+'</li>';}).join('')+'</ul>';};
  const reviewMode=report.mode==='investigate'||report.mode==='challenge';
  drawer(aiModeName(report.mode)+' · Proposal',
    '<div class="badges">'+badge('proposal only','warn')+badge(report.model)+
      badge(report.from_cache?'cached snapshot':'validated output','info')+'</div>'+
    '<p class="method-note"><b>NOT HUMAN REVIEWED.</b> AI cannot approve, reject, or edit knowledge. '+
      'Check each source link and counterexample before accepting any suggestion.</p>'+
    '<h3>Research summary</h3><p>'+esc(answer.summary||'')+'</p>'+
    (reviewMode?'<h3>Suggested review: '+esc(label(answer.proposed_review||'hold'))+'</h3>'+
      '<p>'+esc(answer.review_rationale||'')+'</p>':'')+
    '<h3>Supporting, skeptical and counter evidence</h3>'+
    (findings||'<p>No cited findings returned.</p>')+
    '<h3>Alternative explanations</h3>'+bullets(answer.alternative_explanations)+
    '<h3>Evidence gaps</h3>'+bullets(answer.missing_evidence)+
    (experiments?'<h3>Proposed experiments (not proven operator behavior)</h3>'+experiments:'')+
    '<h3>Reproducibility & limits</h3><dl>'+
      '<dt>Snapshot SHA-256</dt><dd><code>'+esc(report.snapshot_sha256||'')+'</code></dd>'+
      '<dt>Prompt version</dt><dd>'+esc(report.prompt_version)+'</dd>'+
      '<dt>Evidence sources</dt><dd>'+num(report.source_count)+'</dd>'+
      '<dt>Flow pairs sampled</dt><dd>'+num(report.flow_count)+' of '+num(report.available_flow_count)+'</dd>'+
      '<dt>Timestamp</dt><dd>'+esc(report.generated_at)+'</dd></dl>'+
    '<p class="method-note">Sampled flows are not a representative statistical sample. '+
      'Use full population metrics in Research Brief for denominators.</p>'+
    (reviewMode?'<button class="ai-review-draft" data-ai-review-draft="1">'+
      'Return to Human Review with editable AI note (no decision saved)</button>':'')+
    '<button class="ai-history-link" data-ai-reopen-plan="1">Inspect another research mode</button>');
}

async function aiPreview(mode,source_type,source_id){
  const request={mode:mode,source_type:source_type,source_id:source_id};
  aiPending=request;
  drawer(aiModeName(mode),'Preparing read-only evidence plan…');
  try{
    const {plan}=await aiFetch('/api/ai/plan',request);
    if(aiPending!==request)return;
    const provider=(aiServiceStatus&&aiServiceStatus.enabled&&aiServiceStatus.configured);
    drawer(aiModeName(mode)+' · Evidence plan',
      '<div class="badges">'+badge('No tokens charged for planning','good')+'</div>'+
      '<p>The local research engine selected a bounded set of supporting and '+
      'counterexample evidence. A subsequent model call may incur Gemini charges.</p>'+
      '<dl><dt>Operator target</dt><dd>'+esc(source_type+': '+source_id)+'</dd>'+
      '<dt>Evidence sources</dt><dd>'+num(plan.source_count)+'</dd>'+
      '<dt>Flow pairs</dt><dd>'+num(plan.flow_count)+' / '+num(plan.available_flow_count)+' available</dd>'+
      '<dt>Estimated input tokens (upper bound)</dt><dd>'+num(plan.estimated_input_tokens_upper_bound)+'</dd>'+
      '<dt>Max output tokens</dt><dd>'+num(plan.max_output_tokens)+'</dd>'+
      '<dt>Model</dt><dd>'+esc(plan.model)+'</dd></dl>'+
      '<p class="method-note">Token estimate is not a price quote. There are no automatic retries. '+
      'The evidence is sampled; no raw files or keys are exposed to the browser.</p>'+
      '<button class="ai-action" data-ai-confirm="1" '+(!provider?'disabled':'')+'>'+
        'Run '+esc(aiModeName(mode))+' (one model attempt)</button>'+
      (!provider?'<p>To enable: set GEMINI_API_KEY and run creative-research lab --open --ai-enabled.</p>':''));
  }catch(e){
    drawer(aiModeName(mode)+' · Evidence unavailable',
      '<p class="method-note">'+esc(e.message)+'</p>'+
      '<p>No AI call was made; check the target and regenerated Lab evidence.</p>');
  }
}

async function aiConfirm(){
  if(!aiPending)return;
  const request=aiPending;
  drawer(aiModeName(request.mode),'Analyzing the bounded evidence sample…');
  try{
    const result=await aiFetch('/api/ai/run',request);
    aiPending=null;
    aiDrawReport(result.report);
    const status=await fetch('/api/ai/status',{cache:'no-store'}).then(r=>r.json());
    aiServiceStatus=status;
  }catch(e){
    drawer('AI research did not validate',
      '<p class="method-note">'+esc(e.message)+'</p>'+
      '<p>No human-review decision or trusted knowledge was changed. '+
      'If a citation was invented or the model failed, the report is rejected rather than published.</p>');
  }
}

function aiDraftReviewNote(){
  const r=aiLastReport;
  if(!r||!['investigate','challenge'].includes(r.mode))return;
  const key=r.source_type+':'+r.source_id;
  if(!data.reviewBySource.has(key))return;
  openReview(key);
  const note=$('#review-note');
  if(note){
    const a=r.answer||{};
    note.value=('UNVERIFIED AI suggestion: '+(a.proposed_review||'hold')+
      '. '+(a.review_rationale||'')+
      ' Verify original sources and document your OWN judgment before submitting.').slice(0,2500);
  }
  toast('Editable AI note inserted. Approval checkbox remains unchecked.');
}

function wireAiControls(){
  document.querySelectorAll('[data-ai-mode]').forEach(function(button){
    button.onclick=function(){
      aiPreview(button.dataset.aiMode,button.dataset.aiKind,button.dataset.aiTarget);
    };
  });
  document.querySelectorAll('[data-ai-confirm]').forEach(function(button){
    button.onclick=aiConfirm;
  });
  document.querySelectorAll('[data-ai-last]').forEach(function(button){
    button.onclick=function(){if(aiLastReport)aiDrawReport(aiLastReport);};
  });
  document.querySelectorAll('[data-ai-review-draft]').forEach(function(button){
    button.onclick=aiDraftReviewNote;
  });
  document.querySelectorAll('[data-ai-reopen-plan]').forEach(function(button){
    button.onclick=function(){if(aiLastReport)aiPreview(
      aiLastReport.mode,aiLastReport.source_type,aiLastReport.source_id);};
  });
}

fetch('/api/ai/status',{cache:'no-store'}).then(function(response){
  return response.json();
}).then(function(status){
  aiServiceStatus=status;
}).catch(function(){
  aiServiceStatus={enabled:false,configured:false};
});
