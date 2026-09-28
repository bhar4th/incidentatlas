/** Browser replay engine for normalized IncidentAtlas events.
 * Pure computation: no fixture labels, scenario IDs, network, or model calls.
 * Mirrors incidentatlas/engine.py (rules-v0.1). Scores are not probabilities.
 */
export const STRATEGIES = Object.freeze({
  balanced: {signal:.55, temporal:.15, graph:.20, keywords:.10},
  temporal: {signal:.45, temporal:.35, graph:.10, keywords:.10},
  graph: {signal:.45, temporal:.10, graph:.35, keywords:.10},
  keyword: {signal:.45, temporal:.10, graph:.10, keywords:.35},
});
export const MAX_IMPORT_BYTES = 5 * 1024 * 1024;
const MAX_EVENTS = 100000;
const ERROR_LEVELS = new Set(['error','critical']);
const isObject = v => v !== null && typeof v === 'object' && !Array.isArray(v);
const compare = (a,b) => a < b ? -1 : a > b ? 1 : 0;
const epoch = value => Date.parse(value) / 1000;
const evidence = (event,reason) => ({event_id:event.id,reason});
const uniq = values => [...new Set(values)];
const dedup = items => [...new Map(items.map(item=>[item.event_id,item])).values()];
// Compensated summation keeps the four weighted factors aligned with math.fsum.
function sum(values) {
  let total=0,correction=0;
  for(const value of values){
    const next=total+value;
    correction+=Math.abs(total)>=Math.abs(value)?(total-next)+value:(value-next)+total;
    total=next;
  }
  return total+correction;
}
const round = (value, digits=0) => {
  const scale=10**digits, n=value*scale, lo=Math.floor(n);
  return (n-lo===.5 ? lo+(lo%2) : Math.round(n))/scale;
};
// Python's :g display uses six significant digits by default.
const g = value => {
  if (!Number.isFinite(value)) return String(value);
  if (value === 0) return Object.is(value,-0) ? '-0' : '0';
  const exponent=Math.floor(Math.log10(Math.abs(value)));
  if(exponent < -4 || exponent >= 6) return value.toExponential(5).replace(/(\.\d*?)0+e/,'$1e').replace(/\.e/,'e').replace(/e([+-])(\d)$/,'e$10$2');
  return Number(value.toPrecision(6)).toString();
};

/** Deterministic synchronous SHA-256, usable without a secure-context API. */
function sha256(text) {
  const bytes=new TextEncoder().encode(text), size=Math.ceil((bytes.length+9)/64)*64;
  const buffer=new Uint8Array(size); buffer.set(bytes); buffer[bytes.length]=128;
  const view=new DataView(buffer.buffer), bits=bytes.length*8;
  view.setUint32(size-8,Math.floor(bits/2**32)); view.setUint32(size-4,bits>>>0);
  const k=[0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
  const h=[0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19], w=new Uint32Array(64);
  const rotr=(v,n)=>(v>>>n)|(v<<(32-n));
  for(let offset=0;offset<size;offset+=64){
    for(let i=0;i<16;i++)w[i]=view.getUint32(offset+i*4);
    for(let i=16;i<64;i++){
      const a=w[i-15], b=w[i-2];
      w[i]=(w[i-16]+(rotr(a,7)^rotr(a,18)^(a>>>3))+w[i-7]+(rotr(b,17)^rotr(b,19)^(b>>>10)))>>>0;
    }
    let [a,b,c,d,e,f,j,z]=h;
    for(let i=0;i<64;i++){
      const t1=(z+(rotr(e,6)^rotr(e,11)^rotr(e,25))+((e&f)^(~e&j))+k[i]+w[i])>>>0;
      const t2=((rotr(a,2)^rotr(a,13)^rotr(a,22))+((a&b)^(a&c)^(b&c)))>>>0;
      z=j;j=f;f=e;e=(d+t1)>>>0;d=c;c=b;b=a;a=(t1+t2)>>>0;
    }
    [a,b,c,d,e,f,j,z].forEach((v,i)=>h[i]=(h[i]+v)>>>0);
  }
  return h.map(v=>v.toString(16).padStart(8,'0')).join('');
}

// Match Python's normalized numeric fields for stable bundled-event identities.
const pyString = value => JSON.stringify(value).replace(/[\u007f-\uffff]/g,c=>'\\u'+c.charCodeAt(0).toString(16).padStart(4,'0'));
function pyJson(value, compact=false, asFloat=false) {
  const separator=compact?',':', ', colon=compact?':':': ';
  if(Array.isArray(value)) return '['+value.map(v=>pyJson(v,compact)).join(separator)+']';
  if(isObject(value)){
    const event=typeof value.timestamp==='string' && typeof value.service==='string';
    return '{'+Object.keys(value).sort(compare).map(k=>pyString(k)+colon+pyJson(value[k],compact,event&&['value','duration_ms'].includes(k))).join(separator)+'}';
  }
  if(typeof value==='number'){
    if(!Number.isFinite(value))throw new Error('nonfinite number');
    if(asFloat&&Number.isInteger(value)&&Math.abs(value)<1e16)return String(value)+'.0';
    if(Object.is(value,-0))return asFloat?'-0.0':'0';
    return String(value).replace(/e([+-]?)(\d)$/,'e$10$2');
  }
  return typeof value==='string' ? pyString(value) : JSON.stringify(value);
}
function canonical(event) {return pyJson(Object.fromEntries(Object.entries(event).filter(([k])=>!['late','ingested_at'].includes(k))),true);}

export function timestamp(value) {
  if(value===null||value===undefined||typeof value==='boolean')throw new Error('timestamp is required');
  if(typeof value==='number'&&!Number.isFinite(value))throw new Error('timestamp must be finite');
  if(typeof value!=='string'&&typeof value!=='number')throw new Error('timestamp must be ISO string or epoch seconds');
  if(typeof value==='string'&&!/(Z|[+-]\d\d:?\d\d)$/i.test(value))throw new Error('timestamp must contain timezone');
  const date=new Date(typeof value==='number'?value*1000:value);
  if(!Number.isFinite(date.valueOf()))throw new Error('invalid timestamp');
  return date.toISOString();
}
function finite(value,name) {
  if(typeof value==='boolean'||value===null||value===''||Array.isArray(value)||isObject(value))throw new Error(`${name} must be numeric`);
  const n=Number(value);if(!Number.isFinite(n))throw new Error(`${name} must be finite`);return n;
}
export function normalizeEvent(raw) {
  if(!isObject(raw))throw new Error('event must be an object');
  const kind=raw.kind??'log';
  if(!['log','span','metric','deployment'].includes(kind))throw new Error('kind must be log, span, metric or deployment');
  if(typeof raw.service!=='string'||!raw.service.trim()||raw.service.length>200)throw new Error('service is required and limited to 200 characters');
  let severity=String(raw.severity??'info').toLowerCase();if(severity==='warn')severity='warning';
  if(!['debug','info','warning','error','critical'].includes(severity))throw new Error('unsupported severity');
  const attrs=raw.attributes??{};
  if(!isObject(attrs)||Object.keys(attrs).length>100)throw new Error('attributes must be an object with at most 100 fields');
  for(const [k,v] of Object.entries(attrs)){
    if(k.length>200)throw new Error('invalid attribute key');
    if(!(v===null||['string','number','boolean'].includes(typeof v)))throw new Error('normalized attributes must have scalar values');
    if(typeof v==='number'&&!Number.isFinite(v))throw new Error('attributes cannot contain nonfinite numbers');
    if(typeof v==='string'&&v.length>8192)throw new Error('attribute value exceeds 8192 characters');
  }
  const event={timestamp:timestamp(raw.timestamp),service:raw.service.trim(),kind,severity,name:String(raw.name??kind).slice(0,500),message:String(raw.message??'').slice(0,8192),attributes:{...attrs}};
  for(const key of ['trace_id','span_id','parent_span_id','unit'])if(raw[key]!==null&&raw[key]!==undefined)event[key]=String(raw[key]).slice(0,200);
  for(const key of ['duration_ms','value'])if(raw[key]!==null&&raw[key]!==undefined)event[key]=finite(raw[key],key);
  if((event.duration_ms??0)<0)throw new Error('duration_ms cannot be negative');
  if(kind==='metric'&&!Object.hasOwn(event,'value'))throw new Error('metric requires value');
  if(raw.id!==null&&raw.id!==undefined){
    if(typeof raw.id!=='string'||!raw.id.trim()||raw.id.length>250)throw new Error('id must be a nonempty string of at most 250 characters');
    event.id=raw.id;
  }else event.id='ev_'+sha256(canonical(event)).slice(0,24);
  return event;
}
export function normalizePayload(payload) {
  const rows=Array.isArray(payload)?payload:isObject(payload)&&Object.hasOwn(payload,'events')?payload.events:null;
  if(!Array.isArray(rows))throw new Error('expected normalized events array or {events: [...]}');
  if(rows.length>MAX_EVENTS)throw new Error(`event count exceeds ${MAX_EVENTS}`);
  const accepted=[],errors=[],seen=new Map();
  rows.forEach((raw,index)=>{
    try{
      const event=normalizeEvent(raw), serial=canonical(event);
      if(seen.has(event.id)&&seen.get(event.id)!==serial)throw new Error('conflicting duplicate id in payload');
      seen.set(event.id,serial);accepted.push(event);
    }catch(error){errors.push({index,error:error.message});}
  });
  return {events:accepted,errors};
}
/** Call this on file.text(); checks UTF-8 bytes before JSON parsing. */
export function parseImport(text) {
  if(typeof text!=='string')throw new Error('import must be JSON text');
  if(new TextEncoder().encode(text).byteLength>MAX_IMPORT_BYTES)throw new Error('JSON import exceeds the 5 MiB limit');
  const payload=JSON.parse(text);
  const rows=Array.isArray(payload)?payload:payload?.events;
  if(!Array.isArray(rows))throw new Error('Browser import accepts normalized events only: an array or {events: [...]}');
  if(rows.length>MAX_EVENTS)throw new Error(`event count exceeds ${MAX_EVENTS}`);
  return rows;
}

export class EvidenceIndex {
  constructor(events){
    this.byId=new Map(events.map(e=>[e.id,e]));this.byService=new Map();this.byTrace=new Map();this.times=new Map();
    for(const e of events){
      if(!this.byService.has(e.service))this.byService.set(e.service,[]);this.byService.get(e.service).push(e);
      if(e.trace_id){if(!this.byTrace.has(e.trace_id))this.byTrace.set(e.trace_id,[]);this.byTrace.get(e.trace_id).push(e);}
    }
    for(const [service,items] of this.byService){
      items.sort((a,b)=>compare(a.timestamp,b.timestamp)||compare(a.id,b.id));
      this.times.set(service,items.map(e=>epoch(e.timestamp)));
    }
  }
  window(service,start,end){
    const times=this.times.get(service)??[];
    const lower=(value,right)=>{let l=0,h=times.length;while(l<h){const m=(l+h)>>>1;if(times[m]<value||(right&&times[m]===value))l=m+1;else h=m;}return l;};
    return (this.byService.get(service)??[]).slice(lower(start,false),lower(end,true));
  }
  trace(id){return this.byTrace.get(id)??[];}
}

export function serviceGraph(events) {
  const nodes=new Map(),edges=new Map(),spanLookup=new Map(),observed=new Set(),observedErrors=new Set();
  const spanKey=(trace,span)=>JSON.stringify([trace??null,span??null]);
  for(const e of events)if(e.kind==='span'&&e.span_id)spanLookup.set(spanKey(e.trace_id,e.span_id),e);
  const node=id=>{if(!nodes.has(id))nodes.set(id,{id,label:id,event_count:0,error_count:0});return nodes.get(id);};
  for(const e of events){const n=node(e.service);n.event_count++;n.error_count+=Number(ERROR_LEVELS.has(e.severity));}
  for(const e of events){
    if(e.kind!=='span')continue;
    let source=e.service,target=e.attributes['peer.service'];
    const parent=e.parent_span_id?spanLookup.get(spanKey(e.trace_id,e.parent_span_id)):null;
    if(!target&&parent&&parent.service!==e.service){source=parent.service;target=e.service;}
    if(typeof target!=='string'||!target||target===source)continue;
    node(target);const key=JSON.stringify([source,target]);
    if(!edges.has(key))edges.set(key,{source,target,calls:0,error_count:0,max_duration_ms:0,evidence_ids:[]});
    const edge=edges.get(key);
    const callId=JSON.stringify([source,target,e.trace_id??null,parent&&e.service===target&&parent.service===source?parent.span_id:(e.span_id??e.id)]);
    if(!observed.has(callId)){edge.calls++;observed.add(callId);}
    if(ERROR_LEVELS.has(e.severity)&&!observedErrors.has(callId)){edge.error_count++;observedErrors.add(callId);}
    edge.max_duration_ms=Math.max(edge.max_duration_ms,e.duration_ms??0);edge.evidence_ids.push(e.id);
  }
  return {nodes:[...nodes.values()].sort((a,b)=>compare(a.id,b.id)),edges:[...edges.values()].sort((a,b)=>compare(a.source,b.source)||compare(a.target,b.target))};
}
export function upstreamServices(graph,service) {
  const reverse=new Map();for(const edge of graph.edges){if(!reverse.has(edge.target))reverse.set(edge.target,new Set());reverse.get(edge.target).add(edge.source);}
  const seen=new Set([service]),queue=[service];
  for(let i=0;i<queue.length;i++)for(const p of [...(reverse.get(queue[i])??[])].sort(compare))if(!seen.has(p)){seen.add(p);queue.push(p);}
  return [...seen].filter(s=>s!==service).sort(compare);
}

function candidate(cause,service,title,support,contradictions,signal,keywords,checks,missing,ix,graph) {
  support=dedup(support);
  const anchor=Math.min(...support.map(x=>epoch(ix.byId.get(x.event_id).timestamp)));
  const deployments=ix.window(service,anchor-600,anchor+120).filter(e=>e.kind==='deployment'&&epoch(e.timestamp)<=anchor);
  let temporal=.35;
  if(deployments.length){
    const last=deployments.at(-1),elapsed=round(anchor-epoch(last.timestamp));
    temporal=Math.max(.40,1-elapsed/900);
    support.push(evidence(last,`A deployment on ${service} preceded the first supporting signal by ${elapsed} seconds; timing alone does not establish causation.`));
  }
  const affected=upstreamServices(graph,service).filter(s=>ix.window(s,anchor-30,anchor+300).some(e=>ERROR_LEVELS.has(e.severity)));
  const propagation=Math.min(1,.25+.25*affected.length);
  if(!affected.length)missing.push('No observed upstream error propagation in the correlation window.');
  missing.push('No intervention or controlled production experiment confirms causality.');
  const reasons=support.slice(0,3).map(x=>`${x.reason} [${x.event_id}]`).join(' ');
  return {id:`${cause}:${service}`,cause,service,title,score:0,score_label:'heuristic score',explanation:`${title} is a possible explanation for the observed symptoms. ${reasons}`,
    supporting_evidence:support,contradicting_evidence:dedup(contradictions),missing_evidence:uniq(missing),diagnostic_checks:checks,
    factors:{signal:Math.min(1,signal),temporal:round(temporal,4),graph:propagation,keywords:Math.min(1,keywords)},evidence_ids:support.map(x=>x.event_id),related_services:affected};
}
function hypothesesForService(service,ix,graph) {
  const events=ix.byService.get(service),metrics=events.filter(e=>e.kind==='metric'),logs=events.filter(e=>e.kind==='log'),spans=events.filter(e=>e.kind==='span'),results=[];
  const text=e=>(e.name+' '+e.message).toLowerCase();
  const pool=metrics.filter(e=>(e.name==='db.pool.utilization'&&e.value>=.85)||(e.name==='db.pool.pending'&&e.value>=1));
  const poolLogs=logs.filter(e=>['pool exhausted','pool timeout','acquire connection timeout','connection pool exhausted'].some(s=>text(e).includes(s)));
  if(pool.length||poolLogs.length){
    const support=[...pool.map(e=>evidence(e,`${e.name} measured ${g(e.value)}${e.unit?' '+e.unit:''}.`)),...poolLogs.map(e=>evidence(e,`The service logged: ${e.message}`))];
    const first=Math.min(...support.map(e=>epoch(ix.byId.get(e.event_id).timestamp)));
    const contra=metrics.filter(e=>e.name==='db.pool.utilization'&&e.value<.6&&Math.abs(epoch(e.timestamp)-first)<=120).map(e=>evidence(e,`Pool utilization was ${g(e.value)} during the incident window, which weakens a sustained-exhaustion explanation.`));
    results.push(candidate('connection_pool_exhaustion',service,'Connection pool pressure',support,contra,.65+.2*Number(!!pool.length)+.15*Number(!!poolLogs.length),.9*Number(!!poolLogs.length)+.1,
      ['Compare active connections and waiters with the configured pool limit.','Inspect long-running queries and connection release paths.','Compare pool configuration with the preceding deployment.'],
      pool.length&&poolLogs.length?[]:['Both connection-pool metrics and timeout logs would strengthen this finding.'],ix,graph));
  }
  const latencyMetrics=metrics.filter(e=>(e.name.includes('duration')||e.name.includes('latency'))&&e.value*(['s','seconds'].includes(e.unit)?1000:1)>=750);
  const slowSpans=spans.filter(e=>(e.duration_ms??0)>=750&&(e.attributes['span.kind']??'server')==='server');
  if(latencyMetrics.length||slowSpans.length>=2){
    const support=[...latencyMetrics.map(e=>evidence(e,`${e.name} measured ${g(e.value)} ${e.unit??''}.`)),...slowSpans.slice(0,4).map(e=>evidence(e,`Server span ${e.name} took ${g(e.duration_ms)} ms.`))];
    const first=Math.min(...support.map(e=>epoch(ix.byId.get(e.event_id).timestamp)));
    const contra=spans.filter(e=>(e.attributes['span.kind']??'server')==='server'&&(e.duration_ms??Infinity)<100&&Math.abs(epoch(e.timestamp)-first)<=120).slice(0,3).map(e=>evidence(e,`A nearby server span completed in ${g(e.duration_ms)} ms; the slowdown was not universal.`));
    results.push(candidate('downstream_latency',service,'Elevated service latency',support,contra,.55+.15*Number(!!latencyMetrics.length)+.15*Number(!!slowSpans.length),.25,
      ['Inspect the longest child spans to distinguish local work from downstream waits.','Compare latency against a representative baseline and request volume.','Check external dependencies before attributing the delay to this service.'],
      ['The 750 ms threshold is a demo rule, not a service-specific SLO.','Latency may be a symptom of another resource or dependency failure.'],ix,graph));
  }
  const retries=metrics.filter(e=>['http.client.retry.rate','retry.rate'].includes(e.name)&&e.value>=10);
  const retrySpans=spans.filter(e=>typeof e.attributes['retry.attempt']==='number'&&e.attributes['retry.attempt']>=2);
  const retryLogs=logs.filter(e=>text(e).includes('retry')&&['warning','error','critical'].includes(e.severity));
  if(retries.length||retrySpans.length>=3){
    const support=[...retries.map(e=>evidence(e,`Retry rate reached ${g(e.value)} ${e.unit??''}.`)),...retrySpans.slice(0,3).map(e=>evidence(e,`A client span records retry attempt ${e.attributes['retry.attempt']}.`)),...retryLogs.slice(0,2).map(e=>evidence(e,`The service logged: ${e.message}`))];
    const contra=metrics.filter(e=>['http.client.retry.rate','retry.rate'].includes(e.name)&&e.value<2).map(e=>evidence(e,`Recorded retry rate was ${g(e.value)}; amplification may be intermittent.`));
    results.push(candidate('retry_storm',service,'Retry amplification',support,contra,.7+.15*Number(!!retries.length)+.15*Number(!!retrySpans.length),retryLogs.length?.9:.4,
      ['Compare retry attempts with original request rate and downstream error rate.','Review backoff, retry budgets, and timeout interaction.','Replay bounded traffic in an isolated environment to test the amplification hypothesis.'],
      ['Retries may be a consequence of an earlier downstream failure.'],ix,graph));
  }
  const configLogs=logs.filter(e=>['invalid configuration','missing configuration','configuration validation failed','unknown config','invalid endpoint'].some(s=>text(e).includes(s)));
  const configMetrics=metrics.filter(e=>e.name==='config.validation.errors'&&e.value>0);
  if(configLogs.length||configMetrics.length){
    const support=[...configLogs.map(e=>evidence(e,`The service logged: ${e.message}`)),...configMetrics.map(e=>evidence(e,`Configuration validation reported ${g(e.value)} errors.`))];
    const contra=metrics.filter(e=>e.name==='config.validation.errors'&&e.value===0).map(e=>evidence(e,'A successful configuration validation was also observed; compare instance and version labels.'));
    results.push(candidate('configuration_regression',service,'Configuration validation failure',support,contra,.7+.15*Number(!!configLogs.length)+.15*Number(!!configMetrics.length),configLogs.length?1:.3,
      ['Compare validated settings between the failing and healthy instances.','Check required environment variables and endpoint schemes.','Verify a corrected configuration in the test environment before proposing a rollout.'],
      ['A deployment association needs a configuration diff or version-specific evidence.'],ix,graph));
  }
  return results;
}

/** Analyze normalized input; callers may first filter telemetry to model loss. */
export function analyze(rawEvents,{strategy='balanced',start=null,end=null}={}) {
  if(!Object.hasOwn(STRATEGIES,strategy))throw new Error(`strategy must be one of ${Object.keys(STRATEGIES).join(', ')}`);
  if(start)start=timestamp(start);if(end)end=timestamp(end);
  if(start&&end&&start>end)throw new Error('start must be before or equal to end');
  const {events:normalized,errors}=normalizePayload(rawEvents);
  const lateIds=new Set(Array.isArray(rawEvents)?rawEvents.filter(e=>isObject(e)&&e.late).map(e=>e.id):[]);
  const byId=new Map(normalized.map(e=>[e.id,e])),duplicates=normalized.length-byId.size;
  const events=[...byId.values()].filter(e=>(!start||e.timestamp>=start)&&(!end||e.timestamp<=end)).map(e=>({...e,late:lateIds.has(e.id)})).sort((a,b)=>compare(a.timestamp,b.timestamp)||compare(a.id,b.id));
  const ix=new EvidenceIndex(events),graph=serviceGraph(events),weights=STRATEGIES[strategy];
  const hypotheses=[...ix.byService.keys()].sort(compare).flatMap(service=>hypothesesForService(service,ix,graph));
  for(const h of hypotheses){const penalty=Math.min(.2,h.contradicting_evidence.length*.05);h.score=round(Math.max(0,sum(Object.keys(weights).map(k=>h.factors[k]*weights[k]))-penalty)*100,1);}
  hypotheses.sort((a,b)=>b.score-a.score||compare(a.id,b.id));
  const uncertainties=['Scores are uncalibrated heuristics. A high score does not establish a root cause.','Missing telemetry can hide alternative explanations.'];
  if(!events.some(e=>e.kind==='span'))uncertainties.push('No trace spans were supplied; dependency and propagation evidence is unavailable.');
  if(!events.some(e=>e.kind==='metric'))uncertainties.push('No metric observations were supplied; signal checks rely on logs and spans.');
  if(errors.length)uncertainties.push(`${errors.length} invalid/conflicting input records were excluded.`);
  if(duplicates)uncertainties.push(`${duplicates} identical duplicate events were collapsed.`);
  if(lateIds.size)uncertainties.push('Late arrivals were retained and sorted by event time, not arrival time.');
  if(events.some(e=>typeof e.attributes['clock.skew_ms']==='number'&&Math.abs(e.attributes['clock.skew_ms'])>1000))uncertainties.push('Reported clock skew exceeds 1 second; timestamp ordering may be misleading.');
  if(events.some(e=>ERROR_LEVELS.has(e.severity))&&!hypotheses.length)uncertainties.push('Errors are present, but supported diagnostic rules found no specific explanation.');
  const summary=hypotheses.length?`${hypotheses.length} evidence-backed hypotheses across ${ix.byService.size} observed services.`:'No supported diagnostic hypothesis in the selected evidence. This does not prove the system is healthy.';
  const identity=sha256(strategy+pyJson(events)+String(start??'None')+String(end??'None')).slice(0,16);
  const result={analysis_id:'analysis_'+identity,strategy,window:{start:start||(events[0]?.timestamp??null),end:end||(events.at(-1)?.timestamp??null)},summary,
    stats:{events:events.length,services:ix.byService.size,traces:ix.byTrace.size,error_events:events.filter(e=>ERROR_LEVELS.has(e.severity)).length,deployments:events.filter(e=>e.kind==='deployment').length,late_events:events.filter(e=>e.late).length},
    graph,timeline:events,hypotheses,evidence:Object.fromEntries(ix.byId),uncertainties,
    method:{version:'rules-v0.1',weights:{...weights},complexity:'Index O(N log N); service-time query O(log n + k); each upstream traversal O(V + E).',ground_truth_used:false},rejected_events:errors};
  validateAnalysis(result);return result;
}
export function validateAnalysis(analysis) {
  if(!isObject(analysis)||!isObject(analysis.evidence)||!Array.isArray(analysis.hypotheses)||!Object.hasOwn(STRATEGIES,analysis.strategy))throw new Error('invalid analysis object');
  for(const h of analysis.hypotheses){
    const support=h.supporting_evidence??[];if(!support.length)throw new Error('hypothesis has no supporting evidence');
    const refs=[...support,...(h.contradicting_evidence??[])].map(x=>x.event_id).concat(h.evidence_ids??[]);
    if(refs.some(ref=>!Object.hasOwn(analysis.evidence,ref)))throw new Error('analysis references unsupported evidence id');
    if(typeof h.score!=='number'||!Number.isFinite(h.score)||h.score<0||h.score>100)throw new Error('score must be a heuristic between 0 and 100');
  }
  return true;
}
