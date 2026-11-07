"""Real API refinement job: immutable drums, new stems, saved annotations, ZIP."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import zipfile
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--controls',type=Path,required=True)
    parser.add_argument('--checkpoint',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='FaixaLab-instrument-api-') as temp:
        os.environ['FAIXALAB_DATA_DIR']=temp
        from faixalab import storage,pipeline
        from faixalab.app import app
        from fastapi.testclient import TestClient
        cache=storage.MODELS/'instruments';cache.mkdir()
        os.link(args.checkpoint,cache/'mvsep_mega53_v1.ckpt')
        def read(name):
            a,sr=sf.read(args.controls/name,dtype='float32',always_2d=True)
            return resample_poly(a.mean(1),44100,sr)[:44100*3]
        accordion=read('exp122_accordion_target.wav');guitar=read('exp1159_acoustic_guitar_target.wav')
        n=min(len(accordion),len(guitar));t=np.arange(n)/44100
        mono=.3*accordion[:n]+.3*guitar[:n]
        drums=.015*np.sin(2*np.pi*90*t)*np.exp(-12*(t%.5))
        original=np.stack([mono+drums,mono+drums],axis=1).astype('float32')
        drum=np.stack([drums,drums],axis=1).astype('float32')
        p=storage.new_project('Real mixed instruments',{'type':'file'},{'stems':6,'quality':'balanced','split_guitars':True,'lyrics':True})
        root=storage.project_dir(p['id'])
        for name,a in [('original',original),('drums',drum),('guitar',original-drum)]:
            sf.write(root/(name+'.wav'),a,44100,subtype='FLOAT')
        lyrics=[{'start':0.,'end':1.,'text':'saved annotation'}]
        chord={'start':.2,'end':.8,'label':'C','edited':True,'confidence':1.}
        storage.update_project(p['id'],status='ready',duration=n/44100,audio_revision='before',lyrics=lyrics,chords=[chord],
            stems=[{'name':'drums','label':'Bateria','file':'drums.wav','waveform':[]},
                   {'name':'guitar','label':'Old combined','file':'guitar.wav','waveform':[]}])
        before=(root/'drums.wav').read_bytes();started=time.monotonic();url='/api/projects/'+p['id']
        with TestClient(app) as client:
            client.post(url+'/refine-instruments',json={'selection':['accordion','acoustic_guitar']}).raise_for_status()
            while time.monotonic()-started<180:
                project=client.get(url).json()
                if project['status'] not in {'queued','processing'}:break
                time.sleep(.2)
            assert project['status'] in {'ready','partial'},project
            assert project['audio_revision']!='before'
            names=[s['name'] for s in project['stems']]
            assert {'drums','accordion','acoustic_guitar','other'}<=set(names),names
            assert next(s for s in project['stems'] if s['name']=='drums')['file']=='drums.wav'
            assert (root/'drums.wav').read_bytes()==before
            assert project['lyrics']==lyrics
            assert any(c.get('edited') and c['label']=='C' for c in project['chords'])
            combined=np.zeros_like(original)
            for stem in project['stems']:
                a,sr=sf.read(root/stem['file'],dtype='float32',always_2d=True)
                assert sr==44100 and a.shape==original.shape
                combined+=a
            error=float(np.max(np.abs(combined-original)));assert error<2e-6,error
            response=client.get(url+'/export/zip');response.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                assert z.testzip() is None
                assert {'drums.wav','accordion.wav','acoustic_guitar.wav','other.wav'}<=set(z.namelist())
                assert z.read('drums.wav')==before
            while p['id'] in pipeline.CANCELLATIONS:time.sleep(.01)
        result={'real_pretrained_worker':True,'API_job':True,'status':project['status'],'stems':names,
            'drums_bytes_identical':True,'drums_sha256':hashlib.sha256(before).hexdigest(),
            'original_revision_changed':True,'lyrics_preserved':True,'manual_chord_preserved':True,
            'sum_max_absolute_error':error,'ZIP_stems_verified':True,
            'seconds':round(time.monotonic()-started,2)}
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(result),flush=True)


if __name__=='__main__':main()
