from pathlib import Path
import sys,json,importlib.util,time
import numpy as np,soundfile as sf
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from faixalab.chords import analyze
spec=importlib.util.spec_from_file_location('old_chords',ROOT/'tests/baseline_chords_0_1.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
SR=22050
chords={'C':[48,52,55,60,64],'Am':[45,52,57,60,64],'F':[41,48,53,57,60],'G':[43,50,55,59,62],'D':[50,57,62,66],'Em':[40,47,52,55,59],'Cmaj7':[48,52,55,59,64],'Am7':[45,52,55,60,64],'Dm7':[50,57,60,65],'G7':[43,50,53,59,62],'Dsus2':[50,57,62,64],'Dsus4':[50,57,62,67]}
cases=[('pop_C',['C','Am','F','G']),('pop_G',['G','Em','C','D']),('minor_E',['Em','C','G','D']),('sevenths',['Cmaj7','Am7','Dm7','G7']),('suspensions',['Dsus2','D','Dsus4','D']),('silence',['N','G','C','D','N'])]
output=[]
folder=ROOT.parent/'faixalab_test_data/chord_cases';folder.mkdir(exist_ok=True,parents=True)
for name,labels in cases:
 length=3*len(labels);t=np.arange(SR*length)/SR;y=np.zeros_like(t)
 for index,label in enumerate(labels):
  if label=='N':continue
  for onset in np.arange(index*3,(index+1)*3,.5):
   for string,midi in enumerate(chords[label]):
    elapsed=np.maximum(t-onset-string*.008,0)
    envelope=np.where((t>=onset+string*.008)&(elapsed<1.1),np.exp(-elapsed*4),0)
    freq=440*2**((midi-69)/12)
    y+=envelope*(np.sin(2*np.pi*freq*elapsed)+.35*np.sin(4*np.pi*freq*elapsed)+.15*np.sin(6*np.pi*freq*elapsed))*.035
 path=folder/(name+'.wav');sf.write(path,y,SR)
 begin=time.monotonic();before=old.analyze(path)['chords'];after=analyze(path)['chords']
 sample_times=np.arange(.005,length,.01);truth=[labels[min(int(t//3),len(labels)-1)] for t in sample_times]
 def score(events):
  pred=[next((e['label'].split('/')[0] for e in events if e['start']<=t<e['end']),'N') for t in sample_times]
  return round(float(np.mean([a==b for a,b in zip(truth,pred)])),4)
 row={'case':name,'expected':labels,'baseline_accuracy':score(before),'refined_accuracy':score(after),'baseline':before,'refined':after,'seconds':round(time.monotonic()-begin,2)}
 output.append(row);print(json.dumps(row),flush=True)
 (folder.parent/'chord_regression_result.json').write_text(json.dumps(output,indent=2))
