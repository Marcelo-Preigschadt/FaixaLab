"""Prepare an isolated browser test with real AAC audio and simulated API updates."""
from pathlib import Path
import argparse,json,shutil,subprocess
import numpy as np,soundfile as sf,imageio_ffmpeg

parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--baseline',type=Path)
args=parser.parse_args();app=Path(__file__).resolve().parents[1];root=args.output.resolve();dist=root/'dist';dist.mkdir(parents=True,exist_ok=True)
for p in (app/'faixalab/web').iterdir():
 if p.is_file():shutil.copyfile(p,dist/p.name)
project=json.loads((app/'tests/fixtures/studio_project.json').read_text())
project.update(title='Teste com áudio sintetizado',duration=90.,status='processing',stage='Refinando instrumentos · teste',progress=50,audio_revision='old',updated_at='2026-11-07T12:00:00Z')
project['chords']=[{'start':i*15.,'end':(i+1)*15.,'label':['Em','C','D'][i%3]} for i in range(6)]
project['lyrics']=[];project['chord_analysis']={'version':'0.3.0'}
(dist/'fixture.json').write_text(json.dumps(project))
shutil.copyfile(app/'faixalab/data/chord_dictionary.json',dist/'dictionary.json')
shutil.copyfile(app/'tests/fixtures/instrument_catalog.json',dist/'instruments.json')
html=(dist/'index.html').read_text().replace('<head>','<head>\n<script src="/qa.js"></script>',1)
html=html.replace('<body class="studio-app"', '<body class="studio-app"',1)
html=html.replace('</body>','''<aside id="qa-panel" style="position:fixed;z-index:1000;top:8px;right:12px;padding:12px 16px;background:#193f39;border:1px solid #52c9a6;border-radius:8px;color:white;font:13px system-ui;max-width:420px"><strong>Teste de reprodução · áudio sintetizado</strong><p id="qa-status">Carregando interface…</p><button id="qa-run" disabled style="padding:10px 16px">Testar reprodução durante refinamento</button><pre id="qa-result" style="white-space:pre-wrap;font-size:11px"></pre></aside></body>''')
(dist/'index.html').write_text(html)
with (dist/'app.js').open('a') as f:f.write('\nwindow.__qa_get=()=>({player,state,poll});\n')
if args.baseline:
 (dist/'baseline.html').write_text(html.replace('src="/app.js"','src="/baseline-app.js"'))
 (dist/'baseline-app.js').write_text((args.baseline/'faixalab/web/app.js').read_text()+'\nwindow.__qa_get=()=>({player,state,poll});\n')
qa=r'''const NativeAudio=window.Audio,networkFetch=window.fetch.bind(window);let fixture;
const fixtureReady=networkFetch('/fixture.json').then(r=>r.json()).then(p=>{fixture=p});
window.Audio=function(url){const u=new URL(url,location.href);if(u.pathname.includes('/audio/'))url='/tone_'+(u.searchParams.get('v')==='new'?'new':'old')+'.m4a';return new NativeAudio(url)};
window.fetch=async function(url,options){const path=new URL(url,location.href).pathname;if(!path.startsWith('/api/'))return networkFetch(url,options);await fixtureReady;let data;
 if(path==='/api/chord-dictionary')return networkFetch('/dictionary.json');
 if(path==='/api/instruments')return networkFetch('/instruments.json');
 if(path==='/api/projects')data=[fixture];else if(path==='/api/projects/'+fixture.id)data=fixture;else return new Response(JSON.stringify({detail:'Rota fora do teste'}),{status:404});
 return new Response(JSON.stringify(data),{headers:{'Content-Type':'application/json'}})};
document.addEventListener('DOMContentLoaded',()=>{let started=0,switched=false,before=0,done=false;
 const status=document.getElementById('qa-status'),button=document.getElementById('qa-run'),result=document.getElementById('qa-result');
 const timer=setInterval(()=>{const q=window.__qa_get?.();if(!q?.player.key)return;
  if(!started){button.disabled=false;status.textContent='Pronto para testar';return;}
  if(done)return;const p=q.player,t=p.current();status.textContent='Reproduzindo: '+t.toFixed(2)+' s · revisão '+q.state.project.audio_revision;
  const finish=(passed,reason)=>{done=true;p.pause();button.disabled=true;status.textContent=passed?'APROVADO · reprodução preservada':'FALHOU · '+reason;result.textContent=JSON.stringify({passed,before_update_seconds:before,after_update_seconds:t,revision_shown:q.state.project.audio_revision,loaded_audio:p.key},null,2);clearInterval(timer);};
  if(!switched&&t>=2){switched=true;before=t;fixture={...fixture,audio_revision:'new',status:'ready',progress:100,stage:'Pronto para tocar',updated_at:'2026-11-07T12:01:00Z'};}
  if(switched&&q.state.project.audio_revision==='new'){
   if(!p.playing&&!(p.wantsPlay??p.playing))finish(false,'áudio interrompido na troca das faixas');
   else if(t>=before+3)finish(true,'');
  }
  if(performance.now()-started>20000&&!done)finish(false,'o áudio não avançou dentro do prazo');
 },100);
 button.onclick=()=>{started=performance.now();button.disabled=true;window.__qa_get().player.play();};
});'''
(dist/'qa.js').write_text(qa)
(root/'.openai').mkdir(exist_ok=True);(root/'.openai/hosting.json').write_text(json.dumps({'static':{'directory':'dist'}}))
sr=22050;t=np.arange(90*sr)/sr
for rev,freq in [('old',220),('new',330)]:
 audio=(.035*np.sin(2*np.pi*freq*t)+.012*np.sin(2*np.pi*freq*1.5*t)).astype('float32')
 wav=root/(rev+'.wav');sf.write(wav,np.column_stack([audio,audio]),sr)
 subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-y','-i',str(wav),'-c:a','aac','-b:a','96k','-movflags','+faststart',str(dist/('tone_'+rev+'.m4a'))],check=True)
 wav.unlink()
print(root,flush=True)
