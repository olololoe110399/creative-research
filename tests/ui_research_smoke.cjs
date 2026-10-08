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
let enabledAI = false;
let aiScriptsLoaded = 0;
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
  '/api/ai/plan':{ok:true,plan:{
    review_question:'Is this hypothesis evidence-backed?',
    source_count:4,flow_count:1,available_flow_count:1,
    estimated_input_tokens_approx:1200,input_chars:2400,max_input_chars:42000,
    max_output_tokens:3200,model:'gemini-3.5-flash-lite'
  }},
  '/api/experiments':{entries:[],selected_keys:[],selected_count:0}
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
    return {
      ok:true,
      json:async()=>url==='/api/ai/status'
        ?{enabled:enabledAI,configured:enabledAI}
        :payloads[url]
    };
  },
  Intl,Math,Date,JSON,Number,String,Map,Set,Array,Object,
  console,
  setTimeout,
  window:{location:{reload(){}}}
});
documentMock.head={appendChild(script){
  assert.equal(script.src,'ai_ui.js');
  aiScriptsLoaded+=1;
  vm.runInContext(fs.readFileSync(path.join(base,script.src),'utf8'),context,{filename:script.src});
  script.onload();
}};
const scripts=Array.from(markup.matchAll(/<script src="([^"]+)"[^>]*><\/script>/g),match=>match[1]);
assert.deepEqual(scripts,['product_ui.js','research_ui.js','app.js']);
for(const filename of scripts){
  vm.runInContext(fs.readFileSync(path.join(base,filename),'utf8'),
    context,{filename});
}
(async()=>{
  await new Promise(resolve=>setTimeout(resolve,25));
  assert.equal(requested.filter(url=>url==='/api/ai/status').length,0);
  assert.equal(aiScriptsLoaded,0);
  vm.runInContext('tab="intelligence";render();',context);
  const intelligence=one('#main').innerHTML;
  assert.match(intelligence,/What we know, infer and cannot know/);
  assert.match(intelligence,/Observed/);
  assert.match(intelligence,/Inferred/);
  assert.match(intelligence,/Unknown/);
  assert.match(intelligence,/semantic flags|semantic uncertain/i);
  assert.doesNotMatch(intelligence,/Approve|Human Review|AI Research Copilot/);
  assert.match(intelligence,/Investigate further with AI \(optional\)/);

  vm.runInContext('tab="playbook";render();',context);
  const playbook=one('#main').innerHTML;
  assert.match(playbook,/Add to My Experiment Plan/);
  assert.match(playbook,/NOT proof|not proven|not proof/i);
  assert.doesNotMatch(playbook,/human-approved|Approve\s*\/\s*Hold|AI Research Copilot/);

  vm.runInContext('tab="experiments";render();',context);
  const plan=one('#main').innerHTML;
  assert.match(plan,/No experiments selected/);
  assert.match(plan,/Open the Operator Playbook/);
  // Clicking optional AI while disabled checks local capabilities but does not
  // download the model UI or initiate a paid inference.
  const aiClick='{dataset:{deepAiKind:"hypothesis",deepAiId:"STR1",deepAiMode:"investigate"},disabled:false}';
  await vm.runInContext('launchOptionalAI('+aiClick+')',context);
  assert.equal(aiScriptsLoaded,0);
  assert.equal(requested.filter(url=>url==='/api/ai/status').length,1);
  assert.equal(requested.filter(url=>url==='/api/ai/run').length,0);

  // Explicit opt-in: load the tool exactly once and preview evidence only.
  enabledAI=true;
  vm.runInContext('drawer=function(title,body){window.lastDrawer={title,body};};',context);
  await vm.runInContext('launchOptionalAI('+aiClick+')',context);
  await new Promise(resolve=>setTimeout(resolve,25));
  assert.equal(aiScriptsLoaded,1);
  assert.equal(requested.filter(url=>url==='/api/ai/plan').length,1);
  assert.equal(requested.filter(url=>url==='/api/ai/run').length,0);
  assert.match(context.window.lastDrawer.body,/No tokens charged for planning/);
  console.log('Research Intelligence + optional on-demand AI smoke: PASS');
})().catch(err=>{console.error(err);process.exitCode=1;});
