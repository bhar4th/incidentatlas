/** Run: node browser/test-parity.mjs
 * Uses only Node built-ins and Python's stdlib. No server or npm install needed.
 */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {analyze,STRATEGIES,parseImport,MAX_IMPORT_BYTES,normalizeEvent,validateAnalysis} from './engine.mjs';

const root=fileURLToPath(new URL('../',import.meta.url));
const read=name=>JSON.parse(readFileSync(new URL('../'+name,import.meta.url),'utf8'));
const scenarios=read('fixtures/scenarios.json').scenarios;
const expected=read('fixtures/demo-results.json').strategy_results;
let fixtureChecks=0;
for(const strategy of Object.keys(STRATEGIES))for(const scenario of scenarios){
  assert.deepEqual(analyze(scenario.events,{strategy}),expected[strategy][scenario.id],`${scenario.id}/${strategy}: saved Python result`);
  fixtureChecks++;
}

// Live differential checks independently exercise missing telemetry, boundaries,
// exact duplicate collapse, conflicting IDs, invalid rows, and an empty stream.
const cases=[];
for(const scenario of scenarios){
  const events=scenario.events;
  const end=new Date(Date.parse(scenario.started_at)+180000).toISOString();
  const variants=[
    {name:'without-spans',events:events.filter(e=>e.kind!=='span')},
    {name:'logs-only',events:events.filter(e=>e.kind==='log')},
    {name:'first-three-minutes',events,options:{start:scenario.started_at,end}},
    {name:'duplicate-and-invalid',events:[...events,events[0],{...events[0],message:'different content'},null,{kind:'metric',timestamp:scenario.started_at,service:'x'}]},
    {name:'empty',events:[]},
  ];
  for(const variant of variants)for(const strategy of Object.keys(STRATEGIES))cases.push({...variant,name:`${scenario.id}/${variant.name}/${strategy}`,options:{...variant.options,strategy}});
}
const pythonCode=`import json,sys
from incidentatlas.engine import analyze
cases=json.load(sys.stdin)
json.dump([analyze(c['events'],**c.get('options',{})) for c in cases],sys.stdout)
`;
const pythonResults=JSON.parse(execFileSync(process.env.PYTHON??'python3',['-c',pythonCode],{cwd:root,input:JSON.stringify(cases),maxBuffer:32*1024*1024,encoding:'utf8'}));
for(let i=0;i<cases.length;i++)assert.deepEqual(analyze(cases[i].events,cases[i].options),pythonResults[i],cases[i].name);

assert.deepEqual(parseImport(JSON.stringify({events:scenarios[0].events})),scenarios[0].events);
assert.throws(()=>parseImport(' '.repeat(MAX_IMPORT_BYTES+1)),/5 MiB/);
assert.throws(()=>parseImport('{"resourceSpans":[]}'),/normalized events only/);
assert.throws(()=>analyze([],{strategy:'not-a-strategy'}),/strategy must/);
assert.throws(()=>analyze([],{start:'2026-09-27T00:00:00Z',end:'2026-09-26T00:00:00Z'}),/start must/);
assert.throws(()=>normalizeEvent({service:'x',timestamp:'2026-09-26T00:00:00'}),/timezone/);
const tampered=structuredClone(analyze(scenarios[0].events));
tampered.hypotheses[0].supporting_evidence[0].event_id='does-not-exist';
assert.throws(()=>validateAnalysis(tampered),/unsupported evidence/);
console.log(`PASS: ${fixtureChecks} saved fixture results + ${cases.length} live Python parity cases + import/validation boundary checks.`);
