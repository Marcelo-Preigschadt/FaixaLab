"""Real pretrained inference on recorded sources, with explicit references.

Sources: official AudioSep demo targets, EGSet12. No recordings are distributed.
This measures a small control set, not arbitrary-repertoire accuracy.
"""
import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
import numpy as np
import soundfile as sf
import torch
from scipy.signal import resample_poly

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from faixalab.instrument_id import analyze,guitar_evidence,summary
from faixalab.instrument_runner import load_model,SR
from faixalab.solo_tabs import transcribe


def audio(path):
    x,sr=sf.read(path,dtype='float32',always_2d=True)
    x=x.mean(1)
    if sr!=SR:x=resample_poly(x,SR,sr)
    return x.astype('float32')


def sisdr(reference,estimate):
    x=reference.astype('float64');y=estimate.astype('float64')
    x-=x.mean();y-=y.mean()
    target=x*(np.dot(x,y)/max(1e-12,np.dot(x,x)))
    return float(10*np.log10((np.dot(target,target)+1e-12)/(np.sum((y-target)**2)+1e-12)))


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--controls',type=Path,required=True)
    p.add_argument('--checkpoint',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    results={'identity':[],'separation':[]}
    for path in sorted(args.controls.glob('*.wav')):
        if path.name.endswith('mixture.wav'):continue
        t,s,l=analyze(path);_,confirmed,_=guitar_evidence(t,s,l)
        row={'file':path.name,'guitar_confirmed':bool(confirmed.any()),'top':summary(t,s,l,6)}
        results['identity'].append(row);print('IDENTITY',json.dumps(row),flush=True)
    # Test the actual tablature pipeline with deliberately incorrect stem naming.
    # An accordion recording labelled guitar_lead must not authorize guitar tabs.
    with tempfile.TemporaryDirectory(prefix='FaixaLab-instrument-check-') as temp:
        temp=Path(temp)
        source=args.controls/'exp122_accordion_target.wav'
        x=audio(source);sf.write(temp/'zero.wav',np.zeros_like(x),SR,subtype='FLOAT')
        tab=transcribe(source,{'scope':'solos'},context={'guitar_rhythm':temp/'zero.wav','original':source})
        assert tab['notes']==[] and not tab['sections']
        results['accordion_wrongly_named_guitar']={'automatic_notes':len(tab['notes']),'message':tab['message'],
            'guitar_contexts':tab['presence']['instrument_identity']['guitar_confirmed_contexts']}
    # Equal-RMS source references; no panning shortcut, both channels identical.
    model=load_model(args.checkpoint,['accordion','acoustic_guitar'])
    acc=audio(args.controls/'exp122_accordion_target.wav')[:5*SR]
    guitar=audio(args.controls/'exp1159_acoustic_guitar_target.wav')[:5*SR]
    n=min(len(acc),len(guitar));acc=acc[:n];guitar=guitar[:n]
    acc=.1*acc/max(1e-9,float(np.sqrt(np.mean(acc**2))))
    guitar=.1*guitar/max(1e-9,float(np.sqrt(np.mean(guitar**2))))
    mixture=acc+guitar
    x=torch.from_numpy(np.stack([mixture,mixture]))[None]
    started=time.monotonic()
    with torch.inference_mode():prediction=model(x)[0].numpy().mean(axis=1)
    for name,reference,estimated in zip(['accordion','acoustic_guitar'],[acc,guitar],prediction):
        baseline=sisdr(reference,mixture);value=sisdr(reference,estimated)
        row={'target':name,'seconds':n/SR,'baseline_SI_SDR_dB':round(baseline,3),
             'separated_SI_SDR_dB':round(value,3),'improvement_dB':round(value-baseline,3)}
        results['separation'].append(row);print('SEPARATION',json.dumps(row),flush=True)
    results['forward_seconds']=round(time.monotonic()-started,2)
    results['scope']='Recorded-source controlled mixture; excludes upstream separation and arbitrary-repertoire guarantees.'
    args.output.write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n','utf-8')


if __name__=='__main__':main()
