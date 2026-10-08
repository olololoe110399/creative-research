'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const base = path.resolve(__dirname, '../src/creative_research/intelligence_workspace_static');
const markup = fs.readFileSync(path.join(base,'index.html'),'utf8');
assert.doesNotMatch(markup,/script src="ai_ui\.js"/);
assert.doesNotMatch(markup,/Insight Review|Human Review|AI Research Copilot/);
const requested = [];
const nodes = new Map();
const one = (key) => {
  if(key === '#search' || key === '#family-filter')return null;
  if(!nodes.has(key))nodes.set(key,{
    innerHTML:'',textContent:'',classList:{toggle(){}},
    appendChild(){},value:'',onclick:null
  });
  return nodes.get(key);
};
const lab={
  research_brief:{
    operator:{operator_id:'OP1',name:'Fixture',verified:true},
    stats:{accounts:2,posts:2,families:1,repeated_families:1,
      cross_account_repeated_families:1,propagation_events:1},
    hero:{title:'Selective reuse hypothesis',summary:'Caveated research'},
    key_findings:[],guardrails:[]
  },
  account_network:{nodes:[],edges:[]},
  family_highlights:[],
  review:{items:[],reviewed_items:[]},
  research_intelligence:{
    operator_id:'OP1',
    counts:{observed:1,inferred:1,unknown:1,experiment_candidates:1},
    observed:[{id:'coverage',title:'Research coverage',
      statement:'Two posts on two accounts',limitations:'Public coverage only'}],
    inferred:[{id:'STR1',title:'Selective reuse',
      claim:'One family crossed accounts',confidence_score:.7,
      hypothesis_type:'selective_cross_account_reuse_model'}],
    unknown:[{id:'intent',title:'Internal intent',
      statement:'Testing workflow unknown',reason:'No private directives'}],
    family_quality:{counts:{
      repeated_families_checked:1,multilingual_families:1,
      semantic_uncertain:1,integrity_gaps:0
    },items:[{family_id:'F1',member_count:2,multilingual:true,
      automated_state:'semantic_uncertain',flags:['multilingual_identity_needs_independent_check']}]},
    experiment_candidates:[{
      key:'explore',title:'Explore a concept',
      application_exercise:'Try a new execution on your own account',
      basis:'inferred',suggested_metric:'Account percentile',
      stop_or_recheck:'Review good and bad outcomes',
      related_hypothesis_id:'STR1',experiment_not_proven:true
    }]
  }
};
const payloads={
  'workspace.json':{workspace_schema_version:'operator-intelligence-lab-v3',
    views:['production','assets','results','evidence']},
  'overview.json':{counts:{}},
  'accounts.json':{accounts:[]},
  'timeline.json':{operator_windows:[],account_windows:[],comparisons:[]},
  'families.json':{families:[{family_id:'F1',member_count:2,members:[]}]},
  'patterns.json':{patterns:[]},
  'strategies.json':{strategies:[{hypothesis_id:'STR1',title:'Selective reuse',
    claim:'One family crossed accounts',evidence_links:[],pattern_links:[]}]},
  'knowledge.json':{knowledge:[]},
  'evidence.json':{posts:[]},
  'lab.json':lab,
  'production.json':{
    schema_version:'creator-production-kit-v1',operator_id:'OP1',
    quality:{recipes_generated:1,slides_drafted:2,calendar_slots:1,
      ready_to_publish:0,asset_candidates:2,assets_with_verified_rights:0},
    recipes:[{recipe_id:'REC-001',family_id:'F1',
      title:'Original study routine',new_hook_draft_vi:'My own study plan',
      content_type:'slideshow',creative_kind:'schedule',
      evidence_grade:'observed_multi_account_structure',
      evidence:{family_member_count:2,distinct_accounts:2,
        median_account_relative_views_percentile:.5,
        under_account_p35_examples:1},
      hook_mechanism_reference:'Persona-specific study schedule',
      new_caption_draft_vi:'What study routine fits your day?',
      proposed_hashtags:['#study'],
      observed_source_posts:[{post_uid:'P1',account:'alpha',views:100,
        url:'https://www.tiktok.com/@alpha/video/111'}],
      slides:[{slide_number:1,role:'hook',asset_id:'AST-001-01',
        new_draft_text_vi:'Different learning needs, different plans',
        production_visual_brief:'Make original desk photo',
        visual_search_query:'original study desk',source_text_reference_only:'source hook'},
        {slide_number:2,role:'body',asset_id:'AST-001-02',
        new_draft_text_vi:'Make a plan for your own needs',
        production_visual_brief:'Make original planner',
        visual_search_query:'planner',source_text_reference_only:'source body'}]
    }],
    calendar:[{day:1,slot_id:'PUB-001',pilot_account:'PILOT-A',
      recipe_id:'REC-001',family_id:'F1',variant:'A',
      test_dimension:'hook wording',planned_local_time:'19:00',
      timezone:'Asia/Ho_Chi_Minh'}],
    account_blueprints:[{slot_id:'PILOT-A',positioning:'Study tips',
      audience:'Students',suggested_handle_pattern:'study.topic.brand',
      bio_draft:'Study notes',avatar_brief:'Original photo',
      content_pillars:['study'],proposed_cadence:'Every two days',
      proposed_local_time:'19:00',time_zone:'Asia/Ho_Chi_Minh',
      setup_checklist:[],source_account_observations:[]}],
    asset_bank:[{asset_id:'AST-001-01',recipe_id:'REC-001',
      kind:'image',search_query:'desk image',
      reference_post_uid:'P1',rights_status:'not_verified'}],
    music_bank:[],suspected_false_splits:[],lessons:[]
  },
  '/api/operating':{
    schema_version:'operator-operating-state-v1',operator_id:'OP1',revision:0,
    recipe_work:[{family_id:'F1',state:'not_started',needs_recheck:false}],
    slot_work:[{slot_id:'PUB-001',state:'not_started',needs_recheck:false}],
    asset_work:[{asset_key:'F1|image|slide_1',state:'not_started',needs_recheck:false}],
    account_work:[{slot_id:'PILOT-A',state:'not_started',needs_recheck:false}],
    stale_work:{},stale_count:0,outcomes:[],legacy_experiments:[]
  }
};
const documentMock={

    querySelector:one,
    querySelectorAll(){return [];},
    createElement(){return{className:'',textContent:'',remove(){}};}
};
const context=vm.createContext({
  document:documentMock,
  fetch:async(url)=>{
    requested.push(url);
    if(url.startsWith('/api/ai/'))throw new Error('Lab must not request AI APIs');
    return {ok:true,json:async()=>payloads[url]};
  },
  Intl,Math,Date,JSON,Number,String,Map,Set,Array,Object,
  console,
  setTimeout,
  window:{location:{reload(){}}}
});
const scripts=Array.from(markup.matchAll(/<script src="([^"]+)"[^>]*><\/script>/g),match=>match[1]);
assert.deepEqual(scripts,['product_ui.js','research_ui.js','operating_ui.js','production_ui.js','app.js']);
for(const filename of scripts){
  vm.runInContext(fs.readFileSync(path.join(base,filename),'utf8'),
    context,{filename});
}
(async()=>{
  await new Promise(resolve=>setTimeout(resolve,25));
  const nav=Array.from(markup.matchAll(/data-tab="([^"]+)"/g),m=>m[1]);
  assert.deepEqual(nav,['production','assets','results','evidence']);
  assert.equal(vm.runInContext('tab',context),'production');
  assert.match(one('#main').innerHTML,/Download live team handoff ZIP/);
  assert.match(one('#main').innerHTML,/Content calendar/);
  assert.match(one('#main').innerHTML,/Manage/);

  vm.runInContext('productionMode="recipes";tab="production";render();',context);
  assert.match(one('#main').innerHTML,/Original study routine/);
  vm.runInContext('drawer=function(title,body){window.lastDrawer={title,body};};openProductionRecipe("REC-001");',context);
  assert.match(context.window.lastDrawer.body,/My own study plan/);
  assert.match(context.window.lastDrawer.body,/DRAFT · not publishable/);
  assert.match(context.window.lastDrawer.body,/https:\/\/www.tiktok.com\/\@alpha\/video\/111/);
  assert.match(context.window.lastDrawer.body,/Edit owned copy/);

  vm.runInContext('tab="assets";render();',context);
  const assets=one('#main').innerHTML;
  assert.match(assets,/Asset Library/);
  assert.match(assets,/Update rights/);
  assert.match(assets,/music|sound/i);

  vm.runInContext('tab="results";render();',context);
  const results=one('#main').innerHTML;
  assert.match(results,/Results & Learnings/);
  assert.match(results,/No first-party outcomes yet/);
  assert.match(results,/Export live team handoff ZIP/);

  vm.runInContext('tab="evidence";evidenceMode="intelligence";render();',context);
  const intelligence=one('#main').innerHTML;
  assert.match(intelligence,/Evidence Explorer/);
  assert.match(intelligence,/What we know, infer and cannot know/);
  assert.match(intelligence,/Observed/);
  assert.match(intelligence,/Inferred/);
  assert.match(intelligence,/Unknown/);
  assert.match(intelligence,/semantic flags|semantic uncertain/i);

  vm.runInContext('openFamily("F1");',context);
  assert.doesNotMatch(context.window.lastDrawer.body,/Investigate further with AI|AI Research Copilot|data-deep-ai-/);
  assert.equal(requested.filter(url=>url.startsWith('/api/ai/')).length,0);
  assert.equal(requested.filter(url=>url==='/api/experiments').length,0);
  assert.equal(requested.filter(url=>url==='/api/operating').length,1);

  for(const page of [intelligence,results,assets,one('#main').innerHTML]){
    assert.doesNotMatch(page,/AI Research Copilot|Investigate further with AI|Human Review|data-deep-ai-/);
  }
  console.log('Four-tab Production / Asset Library / Results / Evidence smoke: PASS');
  console.log('No duplicate experiment API, no model calls, source evidence retained: PASS');

})().catch(err=>{console.error(err);process.exitCode=1;});
