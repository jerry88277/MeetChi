import { chromium } from 'playwright';
const FE=process.env.FE_URL||'https://meetchi-frontend-315688033208.asia-southeast1.run.app';
// Credentials via env — do NOT hardcode secrets. Run:
//   FE_URL=... UAT_EMAIL=uat01@test.meetchi UAT_PASS=**** CPU=4 node frontend-perf-harness.mjs
const EMAIL=process.env.UAT_EMAIL||'', PASS=process.env.UAT_PASS||'';
if(!EMAIL||!PASS){ console.error('Set UAT_EMAIL and UAT_PASS env vars'); process.exit(1); }
const CPU_SLOWDOWN = Number(process.env.CPU||4);
const b=await chromium.launch({headless:true,args:['--disable-dev-shm-usage']});
const ctx=await b.newContext({viewport:{width:1440,height:900}});
const p=await ctx.newPage();
const client=await ctx.newCDPSession(p);
// per-route JS byte tracking
let jsBytes={}, curRoute='login';
p.on('response',async r=>{ const u=r.url(); if(u.endsWith('.js')||u.includes('/_next/static/chunks/')){ try{const buf=await r.body(); jsBytes[curRoute]=(jsBytes[curRoute]||0)+buf.length;}catch{} }});
async function killTour(){ for(const s of ['button[aria-label="關閉"]','text=略過導覽','svg.lucide-x']){const l=p.locator(s).first(); if(await l.count()){await l.click({force:true}).catch(()=>{});await p.waitForTimeout(300);}} await p.keyboard.press('Escape').catch(()=>{}); }
async function navTiming(){ return await p.evaluate(()=>{ const n=performance.getEntriesByType('navigation')[0]||{}; return {dcl:Math.round(n.domContentLoadedEventEnd||0),load:Math.round(n.loadEventEnd||0)};}); }
async function domCount(){ return await p.evaluate(()=>document.querySelectorAll('*').length); }
// Event Timing based input latency measurement
async function measureInputLatency(sel, text){
  await p.locator(sel).first().click();
  await p.evaluate(()=>{ window.__ev=[]; window.__lt=[];
    new PerformanceObserver(l=>{for(const e of l.getEntries()){ window.__ev.push({name:e.name, dur:Math.round(e.duration), delay:Math.round(e.processingStart-e.startTime), proc:Math.round(e.processingEnd-e.processingStart)});}}).observe({type:'event',durationThreshold:0,buffered:true});
    new PerformanceObserver(l=>{for(const e of l.getEntries()) window.__lt.push(Math.round(e.duration));}).observe({type:'longtask',buffered:true});
  });
  const t0=Date.now();
  await p.keyboard.type(text,{delay:120});
  const wall=Date.now()-t0;
  await p.waitForTimeout(500);
  return await p.evaluate((w)=>{ const ev=window.__ev||[]; const inp=ev.filter(e=>e.name==='keydown'||e.name==='input'||e.name==='keypress');
    const durs=inp.map(e=>e.dur).sort((a,b)=>a-b);
    const procs=inp.map(e=>e.proc);
    const max=durs.length?durs[durs.length-1]:0;
    const p75=durs.length?durs[Math.floor(durs.length*0.75)]:0;
    const avgProc=procs.length?Math.round(procs.reduce((a,c)=>a+c,0)/procs.length):0;
    const lt=window.__lt||[];
    return {events:inp.length, maxDur:max, p75Dur:p75, avgProc, longTasks:lt.length, longTaskMax:lt.length?Math.max(...lt):0, wall:w};
  }, wall);
}
try{
  await p.goto(FE+'/login?uat=1',{waitUntil:'networkidle',timeout:45000});
  await p.waitForTimeout(1000);
  await p.locator('input[type="email"]').first().fill(EMAIL);
  await p.locator('input[type="password"]').first().fill(PASS);
  await p.locator('button[type="submit"]').first().click();
  await p.waitForTimeout(6000);
  await p.evaluate(()=>{localStorage.setItem('meetchi_tour_completed_v1','1');localStorage.setItem('meetchi_tour_dismissed_v1','1');});
  // Enable CPU throttle to emulate VDI
  await client.send('Emulation.setCPUThrottlingRate',{rate:CPU_SLOWDOWN});
  console.log('=== CPU throttle x'+CPU_SLOWDOWN+' (emulating VDI/weak client) ===');
  const routes={dashboard:'/dashboard', rag:'/dashboard?view=rag', templates:'/dashboard?view=templates', settings:'/dashboard?view=settings', admin:'/dashboard?view=admin'};
  const rep={};
  for(const [name,path] of Object.entries(routes)){
    curRoute=name; jsBytes[name]=0;
    await p.goto(FE+path,{waitUntil:'networkidle',timeout:45000});
    await p.waitForTimeout(2500); await killTour();
    rep[name]={js_kb:Math.round((jsBytes[name]||0)/1024), ...(await navTiming()), dom:await domCount()};
  }
  console.log('\n--- Per-module load ---');
  for(const [k,v] of Object.entries(rep)) console.log(k.padEnd(11), 'JS='+v.js_kb+'KB', 'DCL='+v.dcl+'ms', 'load='+v.load+'ms', 'DOMnodes='+v.dom);
  // Input latency: feedback modal vs dashboard search baseline
  await p.goto(FE+'/dashboard',{waitUntil:'networkidle',timeout:45000}); await p.waitForTimeout(2000); await killTour();
  console.log('\n--- Input latency (typing 25 chars, CPU x'+CPU_SLOWDOWN+') ---');
  // baseline: dashboard search input
  const base=await measureInputLatency('input[type="text"], input[placeholder]','搜尋測試輸入延遲一二三四五');
  console.log('dashboard-search  ', JSON.stringify(base));
  // open feedback modal
  await p.locator('text=回報問題').first().click({force:true}); await p.waitForTimeout(1500);
  // the summary textarea (問題描述)
  const fb=await measureInputLatency('textarea','測試回報模組輸入延遲一二三四五六七八九十');
  console.log('feedback-summary  ', JSON.stringify(fb));
}catch(e){console.log('ERR:',e.message);}
await b.close();
