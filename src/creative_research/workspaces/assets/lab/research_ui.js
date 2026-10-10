'use strict';

/* Research is classified by evidence, not researcher approvals. Selecting an
 * experiment records your own intention to test, NOT truth about an operator.
 */
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
      '<button class="hero-link research-go" data-go="production">Open Production Recipes →</button>'+
      '</div></section>';
}
