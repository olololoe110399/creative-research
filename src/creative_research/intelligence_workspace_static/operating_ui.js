'use strict';

/* ONE first-party operating store. Research/source kit stays immutable.
 * Every save uses optimistic revision guards; no Gemini or approval workflow.
 */
let operatingState=null;
let operatingError='';

function opFind(collection,key,field){
  const rows=(operatingState||{})[collection]||[];
  return rows.find(function(item){return item[field]===key;})||null;
}
function opRecipe(family){return opFind('recipe_work',family,'family_id');}
function opAsset(asset,recipe){
  return opFind('asset_work',String(recipe.family_id)+'|'+asset.kind+'|'+asset.role,'asset_key');
}
function opSlot(slot){return opFind('slot_work',slot.slot_id,'slot_id');}
function opAccount(id){return opFind('account_work',id,'slot_id');}
function opLabel(item){
  if(!item||item.state==='not_started')return badge('not started','warn');
  if(item.needs_recheck)return badge('source changed · recheck','bad');
  const good=['ready','published','active','editorial_checked'];
  return badge(item.state,good.includes(item.state)?'good':'warn');
}
async function reloadOperating(){
  try{
    const resp=await fetch('/api/operating',{cache:'no-store'});
    const value=await resp.json();
    if(!resp.ok)throw new Error(value.error||'Operating workspace is unavailable');
    operatingState=value;
    operatingError='';
  }catch(error){
    operatingError=error.message;
  }
  if(['production','assets','results'].includes(tab))render();
}
async function saveOperating(payload){
  if(!operatingState){toast('Operating state is unavailable. Reload Lab.');return;}
  try{
    const resp=await fetch('/api/operating',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      cache:'no-store',
      body:JSON.stringify({expected_revision:operatingState.revision,...payload})
    });
    const value=await resp.json();
    if(!resp.ok)throw new Error(value.error||'Save failed');
    operatingState=value.operating;
    operatingError='';
    toast('Team work saved outside the research export.');
    render();
  }catch(err){
    operatingError=err.message;
    toast('Unable to save: '+err.message);
  }
}
function opField(name,value,labelText,kind){
  const tag=kind==='textarea'?'textarea':'input';
  const v=esc(value||'');
  return '<label class="research-field-label">'+esc(labelText)+
    (kind==='textarea'?'<textarea rows="3" data-operating-field="'+name+'">'+v+'</textarea>':
      '<input data-operating-field="'+name+'" value="'+v+'" maxlength="3000">')+
    '</label>';
}
function opSelect(name,options,current,labelText){
  return '<label class="research-field-label">'+esc(labelText)+'<select data-operating-field="'+name+'">'+
    options.map(function(v){
      return '<option value="'+esc(v)+'"'+(v===current?' selected':'')+'>'+esc(label(v))+'</option>';
    }).join('')+'</select></label>';
}
function openOperatingForm(kind,id){
  const kit=data.production||{};
  let head='',form='',status=null;
  if(kind==='recipe'){
    const r=(kit.recipes||[]).find(x=>x.family_id===id);
    if(!r)return;
    status=opRecipe(id);
    head='Edit your original copy · '+r.recipe_id;
    form=opField('edited_hook',(status||{}).edited_hook||r.new_hook_draft_vi,'New first-slide hook','input')+
      opField('edited_caption',(status||{}).edited_caption||r.new_caption_draft_vi,'New caption','textarea')+
      opField('editorial_checked_by',(status||{}).editorial_checked_by||'','Editor name (checks YOUR content, not operator intent)','input')+
      opField('notes',(status||{}).notes||'','Team notes','textarea');
  }else if(kind==='asset'){
    const a=(kit.asset_bank||[]).find(function(asset){
      const rec=(kit.recipes||[]).find(r=>r.recipe_id===asset.recipe_id);
      return rec&&rec.family_id+'|'+asset.kind+'|'+asset.role===id;
    });
    if(!a)return;
    const rec=(kit.recipes||[]).find(r=>r.recipe_id===a.recipe_id);
    status=opAsset(a,rec);
    head='Asset clearance · '+a.asset_id;
    form='<p>Visual / audio sourcing: '+esc(a.search_query)+'</p>'+
      '<p class="method-note">Pinterest/TikTok reference is NOT usage permission. Team must provide original/valid license evidence. No state auto-authorizes posting.</p>'+
      opSelect('state',['needed','sourced','rights_checked','editorial_checked','ready'],
        (status||{}).state||'needed','Asset status')+
      opField('location',(status||{}).location,'Owned file or cleared asset URL','input')+
      opField('license_evidence',(status||{}).license_evidence,'Actual license/permission evidence','input')+
      opField('license_scope',(status||{}).license_scope,'Scope (must include TikTok)','input')+
      opField('rights_checked_by',(status||{}).rights_checked_by,'Team rights reviewer','input')+
      opField('editorial_checked_by',(status||{}).editorial_checked_by,'Team editorial reviewer','input')+
      opField('notes',(status||{}).notes,'Asset notes','textarea');
  }else if(kind==='slot'){
    const slot=(kit.calendar||[]).find(s=>s.slot_id===id);
    if(!slot)return;
    status=opSlot(slot);
    head='Publishing task · '+id;
    form='<p><b>Recipe:</b> '+esc(slot.recipe_id)+' · '+esc(slot.hook_to_publish_draft_vi||'')+'</p>'+
      opSelect('state',['draft','in_production','ready','published','skipped'],
        (status||{}).state||'draft','Task state')+
      opField('owner',(status||{}).owner||'','Assigned teammate','input')+
      opField('published_url',(status||{}).published_url||'','Actual TikTok post URL (required for published)','input')+
      opField('published_at',(status||{}).published_at||'','Published ISO time (required for published)','input')+
      opField('notes',(status||{}).notes||'','Production notes','textarea')+
      '<p class="method-note">Ready/Published requires team editorial check and all original/licensed assets marked ready.</p>';
  }else if(kind==='account'){
    const a=(kit.account_blueprints||[]).find(row=>row.slot_id===id);
    if(!a)return;
    status=opAccount(id);
    head='Account launch · '+id;
    form=opSelect('state',['planned','created','active','retired'],
        (status||{}).state||'planned','Account status')+
      opField('handle',(status||{}).handle||'','Owned TikTok handle','input')+
      opField('notes',(status||{}).notes||'','Team account notes','textarea');
  }else if(kind==='outcome'){
    const slot=(kit.calendar||[]).find(s=>s.slot_id===id);
    if(!slot)return;
    status=opSlot(slot);
    head='Actual result · '+id;
    if(!status||status.state!=='published'||status.needs_recheck){
      toast('Mark this slot Published with its real post URL before recording results.');return;
    }
    form='<p><b>Source:</b> YOUR OWN post, not the researched operator.</p>'+
      opSelect('age_hours',['24','72','168'],'24','Time since publication (hours)')+
      opField('views','','Observed views','input')+
      opField('saves','','Observed saves','input')+
      opField('shares','','Observed shares','input')+
      opField('age_matched_baseline','','Views on comparable posts at the same age','input')+
      opField('notes','','What happened and why it might not generalize','textarea')+
      '<p class="method-note">One post or higher views does not prove a causal creative advantage.</p>';
  }else return;
  const stale=status&&status.needs_recheck;
  drawer(head,
    (stale?'<p class="method-note">The source recipe/slot changed after rebuild. Old work is preserved, but edits are blocked until evidence recheck.</p>':'')+
    '<div class="production-operating-form" data-operating-form="'+esc(kind)+'" data-operating-key="'+esc(id)+'">'+
    form+'<button class="production-primary" data-operating-save="'+esc(kind)+'"'+(stale?' disabled':'')+'>Save team work</button></div>'
  );
  document.querySelectorAll('[data-operating-save]').forEach(function(button){
    button.onclick=function(){
      const parent=button.closest('[data-operating-form]');
      if(!parent)return;
      const fields={};
      parent.querySelectorAll('[data-operating-field]').forEach(function(control){
        fields[control.dataset.operatingField]=control.value;
      });
      saveOperating({action:kind,key:id,...fields});
    };
  });
}
function resultsAndLearningsView(){
  const kit=data.production||{}, op=operatingState||{};
  const outcomes=(op.outcomes||[]).slice().reverse().map(function(r){
    return '<tr><td>'+esc(r.slot_id)+'</td><td><a href="'+esc(r.published_url||'#')+
      '" target="_blank" rel="noopener noreferrer">Your post ↗</a></td>'+
      '<td>'+num(r.age_hours)+'h</td><td>'+num(r.views)+'</td>'+
      '<td>'+num(r.views_vs_baseline)+'×</td>'+
      '<td>'+num(r.saves_per_view)+'</td><td>'+esc(r.notes||'')+'</td></tr>';
  }).join('');
  const legacy=(op.legacy_experiments||[]).map(function(x){
    return '<li>'+esc(x.key)+' · '+esc(x.state||'planned')+
      ' · Imported historical plan; not automatically mapped to a new recipe</li>';
  }).join('');
  const published=(kit.calendar||[]).filter(function(s){
    const rec=opSlot(s);
    return rec&&rec.state==='published'&&!rec.needs_recheck;
  }).map(function(s){
    return '<button class="production-primary" data-edit-operating="outcome" data-operating-key="'+
      esc(s.slot_id)+'">+ Result for '+esc(s.slot_id)+'</button>';
  }).join(' ');
  return pageHead('Results & Learnings','Measure your published content',
     'One durable first-party outcome store, separate from operator research. Rebuilds do not erase it.',
     '<a class="production-download" href="/api/operating/export">↓ Export live team handoff ZIP</a>')+
    (operatingError?'<p class="method-note">'+esc(operatingError)+'</p>':'')+
    (op.stale_count?'<p class="method-note">'+num(op.stale_count)+' team records need source recheck. Historical work is preserved, not transferred to a different recipe.</p>':'')+
    '<section class="section"><h2>Outcomes collected ('+num((op.outcomes||[]).length)+')</h2>'+
      '<p>Use the same observation age (24h, 72h, 7d) for each comparison, not raw lifetime views.</p>'+
      '<div class="production-result-actions">'+published+'</div>'+
      '<div class="production-table-scroller"><table class="production-table"><thead><tr>'+
      '<th>Slot</th><th>Actual post</th><th>Age</th><th>Views</th><th>vs own baseline</th><th>Save rate</th><th>Notes</th></tr></thead><tbody>'+
      (outcomes||'<tr><td colspan="7">No first-party outcomes yet. Publish an original cleared post, then log its metrics.</td></tr>')+
      '</tbody></table></div></section>'+
    (legacy?'<section class="section"><h2>Migrated historical experiment selections</h2><ul>'+legacy+
      '</ul><p>Read-only import from previous My Experiments; no data silently discarded.</p></section>':'')+
    productionLearnings(kit);
}
