'use strict';

/* Creator Production Kit: evidence is an inspectable first-class field.
 * Nothing is auto-publishable; every asset is a sourcing/rights task.
 */
let productionMode='calendar';

function productionStatus(){
  const k=data.production||{}, quality=k.quality||{};
  return '<div class="production-status">'+
    '<div class="production-status-label"><b>Team handoff · Editorial draft</b>'+
    '<span>'+num(quality.recipes_generated)+' recipes · '+num(quality.calendar_slots)+
    ' content slots · '+num(quality.slides_drafted)+' draft slides</span></div>'+
    '<p><b>'+num(quality.ready_to_publish)+' ready to publish.</b> '+num(quality.asset_candidates)+
    ' asset tasks need sourcing/clearance. TikTok/Pinterest reference content is not licensed for reuse. '+
    'Publishing hours and creative variations are proposed experiments, not proven operator strategy.</p>'+
    '</div>';
}

function productionSections(){
  const choices=[
    ['calendar','Content calendar'],['recipes','Recipes & storyboards'],
    ['accounts','Account launch']
  ];
  return '<nav class="production-tabs" aria-label="Production tasks">'+
  choices.map(function(item){
    return '<button data-production-mode="'+item[0]+'" '+(productionMode===item[0]?'class="active"':'')+'>'+
      esc(item[1])+'</button>';
  }).join('')+'</nav>';
}

function recipeEvidence(kitRecipe){
  const e=kitRecipe.evidence||{};
  const grade=kitRecipe.evidence_grade||'single example';
  return '<div class="production-evidence">'+
    badge(grade,grade==='observed_multi_account_structure'?'good':'warn')+
    '<b>'+num(e.family_member_count)+'</b> observed executions · '+
    '<b>'+num(e.distinct_accounts)+'</b> accounts · '+
    'median account-relative views percentile <b>'+pct(e.median_account_relative_views_percentile)+'</b>'+
    ' · low-percentile counterexamples <b>'+num(e.under_account_p35_examples)+'</b>'+
    '<p>Source posts are structural evidence only. Comparisons are observational; '+ 
    'clustering errors and missing posts can change these claims.</p></div>';
}

function productionRecipeCard(r){
  const record=opRecipe(r.family_id);
  return '<article class="production-recipe-card">'+
    '<div class="row">'+badge(r.content_type,'info')+
    badge(r.evidence_grade,r.evidence_grade==='observed_multi_account_structure'?'good':'warn')+
    opLabel(record)+'</div>'+
    '<h3>'+esc(r.title)+'</h3>'+
    '<p><b>New hook draft:</b> '+esc((record||{}).edited_hook||r.new_hook_draft_vi)+'</p>'+
    '<p>'+num((r.slides||[]).length)+' slides/scenes · '+
      num((r.observed_source_posts||[]).length)+' source posts · '+esc(r.creative_kind)+'</p>'+
    '<div class="production-warning">'+
      '<icon></icon>Needs original/licensed assets + factual/editorial review</div>'+
    '<button class="production-primary" data-production-recipe="'+esc(r.recipe_id)+'">Open storyboard & evidence →</button>'+
    '</article>';
}

function productionCalendar(k){
  const recipes=byId(k.recipes,'recipe_id');
  const rows=(k.calendar||[]).map(function(slot){
    const r=recipes.get(slot.recipe_id)||{};
    return '<tr>'+
      '<td><b>Day '+num(slot.day)+'</b></td>'+
      '<td>'+badge(slot.pilot_account,'info')+'</td>'+
      '<td><button class="production-recipe-link" data-production-recipe="'+esc(slot.recipe_id)+'">'+esc(r.title||slot.recipe_id)+'</button>'+
      '<small>'+esc(slot.recipe_id)+' · Variant '+esc(slot.variant)+
      ' · hook: '+esc(slot.hook_to_publish_draft_vi||'draft pending')+'</small></td>'+
      '<td>'+esc(label(slot.test_dimension))+'</td>'+
      '<td>'+esc((opSlot(slot)||{}).scheduled_at||slot.planned_local_time||'')+
      '<small>'+esc(slot.timezone||'')+'</small></td>'+
      '<td>'+opLabel(opSlot(slot))+
      '<button class="production-recipe-link" data-edit-operating="slot" data-operating-key="'+
      esc(slot.slot_id)+'">Manage →</button></td>'+
      '</tr>';
  }).join('');
  return '<section class="section">'+
    '<div class="section-head"><div><h2>Plan to test, not a posting promise</h2>'+
    '<p>Every slot is a draft. Test one variable at a time and collect 24h / 72h / 7d outcomes with new tracking.</p></div></div>'+
    '<div class="production-table-scroller"><table class="production-table"><thead><tr>'+
      '<th>Day</th><th>Your account</th><th>Draft to produce</th><th>Test variable</th><th>Proposed slot</th><th>Gate</th>'+
      '</tr></thead><tbody>'+rows+'</tbody></table></div></section>';
}

function productionRecipes(k){
  return '<section class="section"><div class="section-head"><div><h2>Content recipes</h2>'+
    '<p>Editorial Vietnamese drafts generated from observed structures. Open a card to inspect the actual source TikToks and per-slide production directions.</p></div></div>'+
    '<div class="grid">'+(k.recipes||[]).map(productionRecipeCard).join('')+'</div></section>';
}

function productionAccounts(k){
  const cards=(k.account_blueprints||[]).map(function(a){
    const refs=(a.source_account_observations||[]).map(function(ref){
      return '<li>@'+esc(ref.handle)+' · '+num(ref.observed_posts)+' posts · '+
      num(ref.median_views)+' median views · '+num(ref.median_gap_hours)+'h median post gap</li>';
    }).join('');
    const checklist=(a.setup_checklist||[]).map(function(text){
      return '<label class="production-check"><input type="checkbox" disabled> '+esc(text)+'</label>';
    }).join('');
    return '<article class="production-account"><div class="row">'+badge(a.slot_id,'info')+
      badge('proposal, not operator role','warn')+opLabel(opAccount(a.slot_id))+'</div>'+
      '<button class="production-recipe-link" data-edit-operating="account" data-operating-key="'+esc(a.slot_id)+'">Update owned account →</button>'+
      '<h2>'+esc(a.positioning)+'</h2><p><b>Who:</b> '+esc(a.audience)+'</p>'+
      '<p><b>Handle idea:</b> '+esc(a.suggested_handle_pattern)+'</p>'+
      '<p><b>Bio:</b> '+esc(a.bio_draft)+'</p>'+
      '<p><b>Avatar:</b> '+esc(a.avatar_brief)+'</p>'+
      '<p><b>Pillars:</b> '+esc((a.content_pillars||[]).join(' · '))+'</p>'+
      '<p><b>Pilot cadence:</b> '+esc(a.proposed_cadence)+' · '+esc(a.proposed_local_time)+
        ' '+esc(a.time_zone)+' (experimental, not a known best time)</p>'+
      '<h3>Account creation checklist</h3>'+checklist+
      '<details><summary>Observed accounts informing this proposal</summary><ul>'+refs+'</ul></details></article>';
  }).join('');
  return '<section class="section"><div class="section-head"><div><h2>Brand-owned pilot accounts</h2>'+
    '<p>Two distinct research hypotheses to test. These are NOT an instruction to clone anyone’s identity or an assertion about their internal org chart.</p></div></div>'+
    '<div class="grid two">'+cards+'</div></section>';
}

function productionAssets(k){
  const q=k.quality||{};
  const recipes=byId(k.recipes,'recipe_id');
  const rows=(k.asset_bank||[]).map(function(a){
    const recipe=recipes.get(a.recipe_id)||{};
    const key=recipe.family_id+'|'+a.kind+'|'+a.role;
    const source=a.reference_post_uid?postButton(a.reference_post_uid,'Source post'):esc(a.reference_post_uid||'—');
    return '<tr><td><b>'+esc(a.asset_id)+'</b><small>'+esc(a.recipe_id)+'</small></td>'+
      '<td>'+esc(a.kind)+'</td><td>'+esc(a.search_query)+'</td>'+
      '<td>'+source+'</td><td>'+opLabel(opAsset(a,recipe))+
      '<button class="production-recipe-link" data-edit-operating="asset" data-operating-key="'+esc(key)+'">Update rights →</button></td>'+
      '</tr>';
  }).join('');
  const sounds=(k.music_bank||[]).slice(0,30).map(function(sound){
    return '<li><b>'+esc(sound.music_name||sound.music_id||sound.sound_key)+'</b> · '+
      esc(sound.music_author||'unknown author')+' · '+num(sound.observed_post_count||0)+
      ' observed posts · '+badge('rights not verified','warn')+'</li>';
  }).join('');
  const captions=(k.caption_bank||[]).slice(0,12).map(function(c){
    return '<li>'+postButton(c.post_uid,'@'+c.account)+' · '+
      esc(c.caption_reference_only||'')+
      '<small>Observed reference only · not rights-cleared copy</small></li>';
  }).join('');
  const hashtags=(k.hashtag_bank||[]).slice(0,35).map(function(h){
    return badge('#'+h.hashtag+' · '+num(h.observed_post_count)+' posts','info');
  }).join(' ');
  return '<section class="section"><div class="section-head"><div><h2>Reusable asset sourcing tasks</h2>'+
    '<p>Visual search queries are starting points, not Pinterest licenses. Original TikTok covers/music are evidence references, not assets you can reuse automatically.</p></div></div>'+
    '<div class="production-status"><strong>'+
      num(((operatingState||{}).asset_work||[]).filter(a=>a.state==='ready'&&!a.needs_recheck).length)+
    ' team-cleared assets / '+num(q.asset_candidates)+' asset candidates</strong>'+
    '<p>Every image and sound needs its own rights record. Use the ZIP asset clearance template and record proof before production.</p></div>'+
    '<div class="production-table-scroller"><table class="production-table"><thead><tr>'+
    '<th>Asset ID</th><th>Type</th><th>Search brief</th><th>Reference</th><th>Rights</th>'+
    '</tr></thead><tbody>'+rows+'</tbody></table></div>'+
    '<h3>Observed sound bank ('+num((k.music_bank||[]).length)+')</h3>'+
    (sounds?'<ul>'+sounds+'</ul><p class="research-limitation">Showing 30 of '+num((k.music_bank||[]).length)+' sound candidates. Full source IDs and post links are in SOUND_BANK.csv.</p>':
      '<p class="method-note">No historical music metadata in the current export. Use production-kit --raw-root on local scrape archives to recover sound IDs/names; that does not grant music usage rights.</p>')+
    '<h3>Observed caption bank ('+num((k.caption_bank||[]).length)+')</h3>'+
    (captions?'<ul class="production-caption-bank">'+captions+'</ul>':
       '<p class="research-limitation">No source captions were recovered. Do not invent historical captions.</p>')+
    '<h3>Observed hashtag bank ('+num((k.hashtag_bank||[]).length)+')</h3>'+
    (hashtags?'<div class="production-hashtags">'+hashtags+'</div>':
       '<p class="research-limitation">No observed hashtags in this export.</p>')+
    '</section>';
}

function productionLearnings(k){
  const lessons=(k.lessons||[]).map(function(l){
    const families=(l.source_family_ids||[]).map(function(id){return familyButton(id,id);}).join('');
    const posts=(l.source_post_uids||[]).slice(0,6).map(function(id){return postButton(id,id);}).join('');
    return '<article class="research-card">'+
      '<div class="row"><b>'+esc(l.statement)+'</b>'+badge(l.kind,l.kind==='observed'?'good':'warn')+'</div>'+
      '<h3>What to test</h3><p>'+esc(l.action)+'</p>'+
      '<h3>Evidence boundary</h3><p>'+esc(l.qualification)+'</p>'+
      '<div class="link-list">'+families+posts+'</div></article>';
  }).join('');
  const falseSplits=(k.suspected_false_splits||[]).slice(0,12).map(function(f){
    return '<div class="production-false-split">'+
      familyButton(f.family_a,f.family_a)+' ↔ '+familyButton(f.family_b,f.family_b)+
      '<span>'+esc((f.accounts||[]).join(' / '))+'</span>'+
      '<small>Candidate only. Exact hook and sequence, not visually verified.</small></div>';
  }).join('');
  return '<section class="section"><div class="section-head"><div><h2>Learnings grounded in data</h2>'+
    '<p>Every actionable recommendation links back to actual family/post evidence, with explicit alternatives.</p></div></div>'+
    '<div class="grid two">'+lessons+'</div>'+
    '<h2>Possible family false splits · '+num((k.suspected_false_splits||[]).length)+'</h2>'+
    '<p>Do not merge automatically. These are pairs of different account singletons with equal normalized hooks, source products and slide roles.</p>'+
    '<div class="production-false-list">'+(falseSplits||'<p>No candidate split found by this conservative rule.</p>')+'</div>'+
    '</section>';
}

function productionView(){
  const k=data.production||{}, q=k.quality||{}, op=operatingState||{};
  return pageHead('Production Kit','Turn observed creative into work for your team',
     'Original-account launch, source-linked slide recipes, an experimental calendar, asset-clearance work and first-party learnings. No AI clicks or human truth approvals.',
     '<a class="production-download" href="/api/operating/export">↓ Download live team handoff ZIP</a>')+
    '<div class="metric-grid">'+
      metricCard('Recipe drafts',num(q.recipes_generated),'source posts attached')+
      metricCard('New slide drafts',num(q.slides_drafted),'with visual directions')+
      metricCard('Planned posts',num(q.calendar_slots),'experiment slots')+
      metricCard('Original accounts',num((k.account_blueprints||[]).length),'pilot proposals')+
      metricCard('Asset tasks',num(q.asset_candidates),'rights remain unverified')+
      metricCard('Team tasks saved',num(op.revision||0),'survive rebuilds')+
    '</div>'+
    productionStatus()+
    (operatingError?'<p class="method-note">'+esc(operatingError)+'</p>':'')+
    (op.stale_count?'<p class="method-note">'+num(op.stale_count)+' saved team records require source recheck; none are silently reassigned.</p>':'')+
    productionSections()+
    (productionMode==='calendar'?productionCalendar(k):
     productionMode==='recipes'?productionRecipes(k):productionAccounts(k));
}

function openProductionRecipe(id){
  const k=data.production||{};
  const r=(k.recipes||[]).find(function(item){return item.recipe_id===id;});
  if(!r)return;
  const live=opRecipe(r.family_id);
  const slides=(r.slides||[]).map(function(slide){
    return '<article class="production-slide">'+
      '<div class="row"><b>Slide/scene '+num(slide.slide_number)+' · '+esc(label(slide.role))+'</b>'+
      badge(slide.asset_id,'warn')+'</div>'+
      '<h3>Your original overlay / starting draft</h3><p>'+
        esc(((live||{}).slides||{})[String(slide.slide_number)]||slide.new_draft_text_vi)+'</p>'+
      '<h3>Original visual direction</h3><p>'+esc(slide.production_visual_brief)+'</p>'+
      '<p class="production-visual-query"><b>Search query:</b> '+esc(slide.visual_search_query)+'</p>'+
      '<div class="production-search-links">'+
      '<a href="https://www.pinterest.com/search/pins/?q='+encodeURIComponent(slide.visual_search_query)+'" target="_blank" rel="noopener noreferrer">Pinterest moodboard ↗</a>'+
      '<a href="https://unsplash.com/s/photos/'+encodeURIComponent(slide.visual_search_query.trim().replaceAll(' ','-'))+'" target="_blank" rel="noopener noreferrer">Search original stock alternative ↗</a>'+
      '</div><small>Search results are inspiration only. Check the original rights/license before downloading and posting.</small>'+
      '<details><summary>What source media showed (reference only)</summary>'+
      '<p>'+esc(slide.source_text_reference_only)+'</p>'+
      '<p>'+esc(slide.source_visual_description)+'</p></details>'+
      '</article>';
  }).join('');
  const links=(r.observed_source_posts||[]).map(function(post){
    return '<div>'+postButton(post.post_uid,'@'+post.account+' · '+num(post.views)+' views')+
      (post.url?'<a href="'+esc(post.url)+'" target="_blank" rel="noopener noreferrer">Original ↗</a>':'')+
      '</div>';
  }).join('');
  drawer(r.title,
    '<div class="badges">'+badge(r.recipe_id,'info')+
    badge(r.evidence_grade,r.evidence_grade==='observed_multi_account_structure'?'good':'warn')+
    badge('DRAFT · not publishable','bad')+'</div>'+
    '<p><b>Source family:</b> '+esc(r.family_id)+' '+familyButton(r.family_id,'Inspect family →')+'</p>'+
    recipeEvidence(r)+
    '<h3>Observed creative mechanism</h3><p>'+esc(r.hook_mechanism_reference)+'</p>'+
    '<h3>Your edited hook / draft</h3><p>'+esc((live||{}).edited_hook||r.new_hook_draft_vi)+'</p>'+
    '<button class="production-primary" data-edit-operating="recipe" data-operating-key="'+esc(r.family_id)+'">Edit owned copy & editorial signoff →</button>'+
    '<h3>Source posts</h3><div class="production-source-links">'+links+'</div>'+
    '<h3>Production storyboard</h3>'+slides+
    '<h3>New caption draft</h3><p>'+esc((live||{}).edited_caption||r.new_caption_draft_vi)+'</p>'+
    '<p><b>Proposed hashtags:</b> '+esc((r.proposed_hashtags||[]).join(' '))+'</p>'+
    '<p class="method-note">Before publishing: fact-check overlays, create original/cleared visuals, clear your music and record any promotional disclosures. Never copy source media verbatim.</p>'+
    '<a class="production-download" href="/api/operating/export">↓ Get editable briefs & saved team work</a>'
  );
  wireOperatingControls();
}

function wireProductionControls(){
  document.querySelectorAll('[data-production-mode]').forEach(function(button){
    button.onclick=function(){productionMode=button.dataset.productionMode;render();};
  });
  document.querySelectorAll('[data-production-recipe]').forEach(function(button){
    button.onclick=function(){openProductionRecipe(button.dataset.productionRecipe);};
  });
  wireOperatingControls();
}

function assetLibraryView(){
  return pageHead('Asset Library','Source and clear every visual and sound',
    'Observed sources are evidence. Only team-sourced originals/cleared licenses become production-ready.',
    '<a class="production-download" href="/api/operating/export">↓ Export asset and rights tasks</a>')+
    productionAssets(data.production||{});
}
function evidenceExplorerView(){
  const modes=[
    ['brief','Research brief'],['families','Creative families'],
    ['network','Account network'],['intelligence','Observed / Inferred / Unknown'],
    ['advanced','Raw lineage']
  ];
  return pageHead('Evidence Explorer','Why does the production kit recommend this?',
    'Inspect actual family/post links, performance denominators, alternative explanations and unknowns.')+
    '<nav class="production-tabs">'+modes.map(function(item){
      return '<button data-evidence-mode="'+item[0]+'" '+(evidenceMode===item[0]?'class="active"':'')+'>'+esc(item[1])+'</button>';
    }).join('')+'</nav>'+
    (evidenceMode==='families'?familiesView():
     evidenceMode==='network'?networkView():
     evidenceMode==='intelligence'?researchIntelligenceView():
     evidenceMode==='advanced'?advancedView():briefView());
}
function wireOperatingControls(){
  document.querySelectorAll('[data-edit-operating]').forEach(function(b){
    b.onclick=function(){openOperatingForm(b.dataset.editOperating,b.dataset.operatingKey);};
  });
  document.querySelectorAll('[data-evidence-mode]').forEach(function(b){
    b.onclick=function(){evidenceMode=b.dataset.evidenceMode;render();};
  });
}
