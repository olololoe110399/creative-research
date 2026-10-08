'use strict';

/* Evidence and decision presentation for Operator Intelligence Lab.
 * This file is deliberately limited to UI; claims/trust are materialized in
 * operator_product.py and never inferred or promoted in the browser.
 */
function playbookView(){
  const p=data.lab.playbook||{}, steps=p.steps||[];
  const trusted=p.trusted_catalog_playbooks||[];
  const status=p.status==='human_reviewed'?'Human-reviewed source steps':'Research draft · not validated';
  const cards=steps.map(function(s,i){
    const blocked=s.trust_status==='hold'||s.trust_status==='rejected';
    const cls=s.trust_status==='approved'?'good':blocked?'bad':'warn';
    const knowledge=(s.source_knowledge_ids||[]).map(function(id){
      return data.knowledgeById.has(String(id))
        ?'<button class="link-button" data-knowledge="'+esc(id)+'">Knowledge source · '+esc(id)+'</button>':'';
    }).join('');
    return '<article class="playbook-step"><div class="row"><span class="eyebrow">STEP '+(i+1)+'</span>'+badge(s.trust_status,cls)+'</div>'+
      '<h2>'+esc(s.title||s.key)+'</h2>'+
      (s.not_an_operator_claim?'<p class="method-note">Validation protocol only — not evidence about how the operator works.</p>':'')+
      (s.observation?'<h3>Observed hypothesis</h3><p>'+esc(s.observation)+'</p>':'')+
      (s.application_exercise?'<h3>How to test this in your own system</h3><p>'+esc(s.application_exercise)+'</p>':'<p class="method-note">Action withheld: source is held/rejected or evidence is unavailable.</p>')+
      '<h3>Before acting</h3><p>'+esc(s.verification_question||'')+'</p>'+
      (s.source_hypothesis_id?'<div class="link-list">'+strategyButton(s.source_hypothesis_id,'Open claim, counter-evidence and source posts')+knowledge+'</div>':'')+
      (blocked?'<p class="method-note">This source was held/rejected and must not become active guidance.</p>':'')+
      '</article>';
  }).join('');
  const accepted=trusted.map(function(k){
    return data.knowledgeById.has(String(k.knowledge_id))
      ?'<div class="link-list"><div class="badges">'+badge(k.status,k.status==='approved'?'good':'warn')+'</div><button class="link-button" data-knowledge="'+esc(k.knowledge_id)+'">'+esc(k.title||k.knowledge_id)+'</button></div>':'';
  }).join('');
  const guardrails=(p.guardrails||[]).map(function(x){return '<li>'+esc(x)+'</li>';}).join('');
  return pageHead('Operator playbook','From observations to decisions','An evidence-linked plan to TEST, not a claim that the operator follows a proven formula.')+
    '<section class="playbook-intro"><div class="row"><h2>'+esc(status)+'</h2>'+badge((p.approved_source_steps||0)+' of '+(p.observational_source_steps||0)+' observational steps approved',p.status==='human_reviewed'?'good':'warn')+'</div>'+
    '<p>Research exercises stay provisional until their source claims are reviewed. Automated promotion is not human approval. Review can hold/reject a step without changing historical observations.</p>'+
    '<button class="hero-link" data-go="review">Review operating-model claims</button></section>'+
    '<section class="playbook-grid">'+(cards||'<div class="empty-state">No decision steps could be derived from this operator.</div>')+'</section>'+
    '<section class="section"><div class="section-head"><div><h2>Trusted catalog playbooks</h2><p>Only materialized, status-marked knowledge items appear here.</p></div></div>'+
      (accepted||'<div class="empty-state">No promoted or human-approved catalog playbook yet. The research draft above is not a substitute.</div>')+'</section>'+
    '<section class="section claim-box"><h3>Non-negotiable guardrails</h3><ul>'+guardrails+'</ul></section>';
}

function flowGroupHtml(group,kind){
  const flowRows=(group.flows||[]).map(function(f){
    const origin='@'+(f.origin_account||f.origin_account_id||'');
    const target='@'+(f.target_account||f.target_account_id||'');
    const changed=(f.changed_dimensions||[]).join(', ');
    const preserved=(f.preserved_dimensions||[]).join(', ');
    return '<div class="flow-record"><p><b>'+esc(origin)+' → '+esc(target)+'</b> · '+num(f.delay_days)+' days · '+date(f.target_first_seen)+'</p>'+
      '<div class="flow-posts">'+postButton(f.origin_post_uid,'Origin execution')+postButton(f.target_post_uid,'Receiving execution')+'</div>'+
      '<small>Origin percentile '+pct(f.origin_views_percentile_account)+' · receiver percentile '+pct(f.target_views_percentile_account)+'</small>'+
      (preserved?'<small>Preserved: '+esc(preserved)+'</small>':'')+
      (changed?'<small>Changed: '+esc(changed)+'</small>':'')+'</div>';
  }).join('');
  return '<div class="flow-family"><div class="flow-header">'+familyButton(group.family_id,group.family_id)+badge(kind==='origin'?'first observed here':'imported here',kind==='origin'?'info':'violet')+'</div>'+flowRows+'</div>';
}

function roleEvidenceHtml(lineage){
  if(!lineage)return '<div class="empty-state">No direct family flows available.</div>';
  const origin=lineage.origin_families||[], imports=lineage.imported_families||[];
  return '<div class="role-evidence"><p><b>'+num(lineage.origin_family_count)+'</b> originated families / <b>'+num(lineage.imported_family_count)+'</b> imported families (unique family counts; not edge counts)</p>'+
    '<details class="flow-section"><summary>Origin family evidence ('+num(origin.length)+')</summary><div class="flow-list">'+(origin.map(function(g){return flowGroupHtml(g,'origin');}).join('')||'<p>No outbound family.</p>')+'</div></details>'+
    '<details class="flow-section"><summary>Imported family evidence ('+num(imports.length)+')</summary><div class="flow-list">'+(imports.map(function(g){return flowGroupHtml(g,'import');}).join('')||'<p>No inbound family.</p>')+'</div></details>'+
    '<p class="method-note">First observed ≠ proven internal origin or causal distribution. Review posts in both executions.</p></div>';
}

function strategyFlowHtml(s){
  const accounts=((s.flow_evidence||{}).accounts||[]);
  if(!accounts.length)return '';
  return '<h3>Direct cross-account family evidence</h3>'+accounts.map(function(a){
    const node=data.accountById.get(String(a.account_id))||{};
    return '<h4>@'+esc(node.account||a.account_id)+'</h4>'+roleEvidenceHtml(a);
  }).join('');
}
