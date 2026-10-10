'use strict';

/* Evidence and decision presentation for Operator Intelligence Lab.
 * This file is deliberately limited to UI; claims/trust are materialized in
 * operator_product.py and never inferred or promoted in the browser.
 */
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
