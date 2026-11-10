'use strict';
// Real Chromium media elements, Web Audio graph and float32 stereo WAVs.
const assert=require('node:assert/strict'),fs=require('node:fs'),http=require('node:http');
const path=require('node:path'),{execFileSync}=require('node:child_process');
const {chromium}=require('playwright');
const sourcePath=path.join(__dirname,'../faixalab/web/app.js');
const current=fs.readFileSync(sourcePath,'utf8');
const baseline=execFileSync('git',['show','8b6ddfc52df4f8656d53cb3346e6385b96dcf9ff:app/faixalab/web/app.js'],{cwd:path.join(__dirname,'../..'),encoding:'utf8'});
const definition=s=>s.slice(s.indexOf('function audioKey('),s.indexOf('const player = new StemPlayer();'));
const sr=44100,seconds=10,pcm=Buffer.alloc(sr*seconds*8),wav=Buffer.alloc(44+pcm.length);
for(let i=0;i<sr*seconds;i++){const sample=.04*Math.sin(2*Math.PI*220*i/sr);pcm.writeFloatLE(sample,i*8);pcm.writeFloatLE(sample,i*8+4);}
wav.write('RIFF');wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);wav.writeUInt32LE(16,16);wav.writeUInt16LE(3,20);wav.writeUInt16LE(2,22);wav.writeUInt32LE(sr,24);wav.writeUInt32LE(sr*8,28);wav.writeUInt16LE(8,32);wav.writeUInt16LE(32,34);wav.write('data',36);wav.writeUInt32LE(pcm.length,40);pcm.copy(wav,44);
const requests=new Map(),began=new Map(),timers=new Set();
const server=http.createServer((req,res)=>{
 const url=new URL(req.url,'http://localhost');
 if(url.pathname.startsWith('/api/')){
  const id=url.pathname.split('/')[3];requests.set(id,(requests.get(id)||0)+1);
  const match=/bytes=(\d+)-(\d*)/.exec(req.headers.range||'');
  const start=match?Number(match[1]):0,end=match&&match[2]?Math.min(Number(match[2]),wav.length-1):wav.length-1;
  const body=wav.subarray(start,end+1);
  res.writeHead(match?206:200,{'Content-Type':'audio/wav','Content-Length':body.length,'Accept-Ranges':'bytes',...(match?{'Content-Range':`bytes ${start}-${end}/${wav.length}`}:{})});
  if(!id.startsWith('slow')){res.end(body);return;}
  if(!began.has(id))began.set(id,Date.now());
  const delay=Math.max(0,8200-(Date.now()-began.get(id))),head=Math.min(body.length,256*1024);
  res.write(body.subarray(0,head));
  const timer=setTimeout(()=>{timers.delete(timer);if(!res.destroyed)res.end(body.subarray(head));},delay);timers.add(timer);
  res.on('close',()=>{clearTimeout(timer);timers.delete(timer);});return;
 }
 const id=url.pathname.slice(1)||'fast',code=id.endsWith('old')?baseline:current;
 res.setHeader('Content-Type','text/html; charset=utf-8');
 res.end(`<!doctype html><button id="play">Play</button><p id="status"></p><script>
 const $=s=>document.querySelector(s);function updateMediaSession(){}function updateMediaPosition(){}function toast(s){$('#status').textContent=s;}
 ${definition(code)}
 window.player=new StemPlayer();window.loads=0;const originalLoad=HTMLMediaElement.prototype.load;HTMLMediaElement.prototype.load=function(){window.loads++;return originalLoad.call(this)};
 player.load({id:${JSON.stringify(id)},audio_revision:'qa',duration:${seconds},stems:Array.from({length:4},(_,i)=>({name:'stem'+i,file:i+'.wav'}))});
 window.states=[];player.onState=()=>states.push({at:performance.now(),playing:player.playing,buffering:player.buffering,position:player.current(),message:player.message});
 $('#play').onclick=()=>player.play();
 </script>`);
});
(async()=>{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--disable-background-timer-throttling']});
 const results=[];
 try{
  for(const id of ['fast','slow-old','slow-fixed']){
   const context=await browser.newContext();const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.goto(`http://127.0.0.1:${server.address().port}/${id}`);await page.click('#play');
   let completed=true;
   try{await page.waitForFunction(()=>player.playing&&player.current()>3,{},{timeout:16000});}catch{completed=false;}
   const result=await page.evaluate(async()=>{
    let rms=0;
    if(player.context&&player.tracks[0].gainNode){
     const analyser=player.context.createAnalyser(),silent=player.context.createGain();silent.gain.value=0;player.tracks[0].gainNode.connect(analyser);analyser.connect(silent);silent.connect(player.context.destination);
     await new Promise(resolve=>setTimeout(resolve,100));const samples=new Float32Array(analyser.fftSize);analyser.getFloatTimeDomainData(samples);rms=Math.sqrt(samples.reduce((s,v)=>s+v*v,0)/samples.length);analyser.disconnect();silent.disconnect();
    }
    return {position:player.current(),playing:player.playing,context:player.context?.state,loads,rms,buffering_events:states.filter(s=>s.buffering).length,message:player.message};
   });
   results.push({case:id,completed,...result,requests:requests.get(id)||0,errors});await context.close();
  }
  console.log(JSON.stringify(results,null,2));
  for(const result of results.filter(r=>r.case!=='slow-old')){assert(result.completed,result.case+' did not resume');assert(result.rms>.001,result.case+' has no Web Audio signal');assert.equal(result.loads,0,result.case+' reloaded the audio');assert.deepEqual(result.errors,[]);}
 }finally{await browser.close();for(const timer of timers)clearTimeout(timer);server.closeAllConnections();server.close();}
})().catch(e=>{console.error(e);process.exitCode=1;for(const timer of timers)clearTimeout(timer);server.closeAllConnections();server.close();});
