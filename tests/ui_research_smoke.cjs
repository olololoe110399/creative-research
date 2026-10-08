'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const base = path.resolve(__dirname, '../src/creative_research/intelligence_workspace_static');
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
  'workspace.json':{views:['brief','network','families','intelligence','playbook','experiments','advanced']},
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
  '/api/ai/status':{enabled:false,configured:false},
  '/api/experiments':{entries:[],selected_keys:[],selected_count:0}
};
const context=vm.createContext({
  document:{
    querySelector:one,
    querySelectorAll(){return [];},
    createElement(){return{className:'',textContent:'',remove(){}};}
  },
  fetch:async(url)=>({ok:true,json:async()=>payloads[url]}),
  Intl,Math,Date,JSON,Number,String,Map,Set,Array,Object,
  console,
  setTimeout,
  window:{location:{reload(){}}}
});
const scripts=['product_ui.js','ai_ui.js','research_ui.js','app.js'];
for(const filename of scripts){
  vm.runInContext(fs.readFileSync(path.join(base,filename),'utf8'),
    context,{filename});
}
(async()=>{
  await new Promise(resolve=>setTimeout(resolve,25));
  vm.runInContext('tab="intelligence";render();',context);
  const intelligence=one('#main').innerHTML;
  assert.match(intelligence,/What we know, infer and cannot know/);
  assert.match(intelligence,/Observed/);
  assert.match(intelligence,/Inferred/);
  assert.match(intelligence,/Unknown/);
  assert.match(intelligence,/semantic flags|semantic uncertain/i);
  assert.doesNotMatch(intelligence,/Approve|Human Review/);

  vm.runInContext('tab="playbook";render();',context);
  const playbook=one('#main').innerHTML;
  assert.match(playbook,/Add to My Experiment Plan/);
  assert.match(playbook,/NOT proof|not proven|not proof/i);
  assert.doesNotMatch(playbook,/human-approved|Approve\s*\/\s*Hold/);

  vm.runInContext('tab="experiments";render();',context);
  const plan=one('#main').innerHTML;
  assert.match(plan,/No experiments selected/);
  assert.match(plan,/Open the Operator Playbook/);
  console.log('Research Intelligence / Playbook / My Experiments smoke: PASS');
})().catch(err=>{console.error(err);process.exitCode=1;});
