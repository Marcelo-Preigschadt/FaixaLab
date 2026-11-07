'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const path=require('node:path');
const source=fs.readFileSync(process.env.FAIXALAB_PLAYER_SOURCE||path.join(__dirname,'../faixalab/web/app.js'),'utf8');
const definition=source.slice(source.indexOf('function audioKey('),source.indexOf('const player = new StemPlayer();'));
function harness(){
 const elements=new Map();let now=1000;
 const element=id=>{if(!elements.has(id))elements.set(id,{textContent:'',disabled:false,checked:false,hidden:true,setAttribute(){},classList:{toggle(){}}});return elements.get(id)};
 class Audio extends EventTarget{
  constructor(url){super();this.src=url;this.duration=300;this._time=0;this.seeks=0;this.playbackRate=1;this.volume=1;this.paused=true;this.readyState=4;this.seeking=false;this.playCalls=0;this.loads=0;this.buffered={length:1,start:()=>0,end:()=>300};}
  get currentTime(){return this._time}set currentTime(v){this._time=v;this.seeks++}
  play(){this.playCalls++;this.paused=false;return this.pending?new Promise(resolve=>{this.release=resolve}):Promise.resolve()}
  pause(){this.paused=true}load(){this.loads++}removeAttribute(name){if(name==='src')this.src=''}
 }
 class AudioContext{constructor(){this.destination={};this.state='running'}createDynamicsCompressor(){return {threshold:{},knee:{},ratio:{},connect(){}}}createMediaElementSource(){return {connect(){},disconnect(){}}}createGain(){return {gain:{},connect(){},disconnect(){}}}resume(){this.state='running';return Promise.resolve()}close(){this.state='closed';return Promise.resolve()}}
 const context={Audio,AudioContext,Event,console,performance:{now:()=>now},location:{hostname:'127.0.0.1'},window:{location:{hostname:'127.0.0.1'},matchMedia:()=>({matches:false})},setInterval:()=>1,clearInterval(){},setTimeout:(f,ms)=>{const t=setTimeout(f,ms);t.unref();return t},clearTimeout,URL,document:{},$:element,toast:()=>{},updateMediaSession(){},updateMediaPosition(){}};
 vm.createContext(context);vm.runInContext(definition+'\nthis.Player=StemPlayer;',context);
 return {player:new context.Player(),advance:n=>{now+=n},elements};
}
function project(revision='old',count=4){return {id:'a'.repeat(32),audio_revision:revision,duration:300,stems:Array.from({length:count},(_,i)=>({name:['vocals','drums','guitar','other'][i]||'stem_'+i,label:'Track '+i,file:revision+'/'+i+'.wav'}))}}
const tests=[];const test=(name,run)=>tests.push({name,run});
test('refinement_does_not_interrupt_playback_or_reset_time',async()=>{
 const {player:p}=harness();p.load(project());await p.play();p.tracks.forEach(t=>t.audio._time=87);
 const audio=p.tracks[0].audio;p.load(project('refined'));
 assert.equal(p.playing,true);assert.equal(p.current(),87);assert.equal(p.tracks[0].audio,audio);assert.equal(audio.paused,false);
 p.pause();await p.play();assert.equal(p.current(),87);assert(p.key.includes('refined'));p.dispose();
});
test('synchronization_does_not_seek_again_during_buffering_or_seeking',async()=>{
 const {player:p}=harness();p.load(project());await p.play();const a=p.tracks[0].audio,b=p.tracks[1].audio;
 a._time=25;b._time=23;b.seeking=true;const before=b.seeks;p.synchronize();assert.equal(b.seeks,before);
 b.seeking=false;b.readyState=2;p.synchronize();assert.equal(b.seeks,before);p.dispose();
});
test('pause_wins_over_a_late_play_promise',async()=>{
 const {player:p}=harness();p.load(project());p.tracks.forEach(t=>t.audio.pending=true);
 const start=p.play();await new Promise(r=>setImmediate(r));p.pause();p.tracks.forEach(t=>t.audio.release?.());await start;
 assert.equal(p.playing,false);assert(p.tracks.every(t=>t.audio.paused));p.dispose();
});
test('solo_decodes_only_the_audible_stem',async()=>{
 const {player:p}=harness();p.load(project('old',12));p.tracks[3].solo=true;await p.play();
 assert.equal(p.tracks.filter(t=>!t.audio.paused).length,1);assert.equal(p.tracks[3].audio.paused,false);p.dispose();
});
test('desktop_loopback_plays_wav_without_transcoding',async()=>{
 const {player:p}=harness();p.load(project());assert(p.tracks.every(t=>new URL(t.audio.src,'http://local').searchParams.get('format')==='wav'));p.dispose();
});
test('codec_error_recovers_at_the_same_position',async()=>{
 const {player:p}=harness();p.load(project());await p.play();p.tracks.forEach(t=>t.audio._time=54);
 const a=p.clock();await p.recover(a,true);
 assert.equal(p.playing,true);assert.equal(p.current(),54);assert.equal(a.loads,1);assert(new URL(a.src,'http://local').searchParams.get('format')==='m4a');p.dispose();
});
test('watchdog_retries_without_entering_an_infinite_restart_loop',async()=>{
 const {player:p,advance}=harness();p.load(project());await p.play();p.tracks.forEach(t=>t.audio._time=38);p.synchronize();
 for(let i=0;i<3;i++){advance(5000);p.synchronize();await new Promise(r=>setImmediate(r));}
 assert.equal(p.wantsPlay,false);assert(p.message.includes('interrompido'));assert.equal(p.current(),38);p.dispose();
});
test('refinement_preserves_mixer_levels_and_a_new_song_starts_from_zero',async()=>{
 const {player:p}=harness();p.load(project());p.tracks[1].gain=.6;p.tracks[0].mute=true;
 await p.play();p.tracks.forEach(t=>t.audio._time=41);p.load(project('new'));await p.applyPending();
 assert.equal(p.current(),41);assert.equal(p.playing,true);assert.equal(p.tracks[1].gain,.6);assert.equal(p.tracks[0].mute,true);
 const other=project();other.id='b'.repeat(32);p.load(other);assert.equal(p.current(),0);assert.equal(p.playing,false);assert.equal(p.tracks[0].mute,false);p.dispose();
});
test('suspended_audio_context_resumes_at_the_same_song_position',async()=>{
 const {player:p}=harness();p.load(project());await p.play();p.tracks.forEach(t=>t.audio._time=29);p.context.state='suspended';p.synchronize();await new Promise(r=>setImmediate(r));
 assert.equal(p.context.state,'running');assert.equal(p.playing,true);assert.equal(p.current(),29);p.dispose();
});
(async()=>{const results=[];for(const t of tests){try{await t.run();results.push({name:t.name,passed:true})}catch(e){results.push({name:t.name,passed:false,error:e.message})}}console.log(JSON.stringify({passed:results.filter(r=>r.passed).length,total:results.length,results},null,2));if(results.some(r=>!r.passed))process.exitCode=1})().catch(e=>{console.error(e);process.exitCode=1});
