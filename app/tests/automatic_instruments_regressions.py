"""Recorded-source controls for the general automatic policy (no audio bundled).

Quality metrics are reported, including misses/extra estimates; only numerical
and worker contracts are asserted. This is not an arbitrary-repertoire benchmark.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
import urllib.request

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from faixalab.instrument_runner import refine,validate_identity,SR

# (filename, target RMS, output category). Offsets refer only to test recordings.
CASES=[
 ('accordion_acoustic_equal',0.,[('exp122_accordion_target.wav',.07,'accordion'),('exp1159_acoustic_guitar_target.wav',.07,'acoustic_guitar')]),
 ('quiet_flute_over_cello',0.,[('exp2340_flute_target.wav',.007,'flute'),('exp1758_cello_target.wav',.07,'cello')]),
 ('quiet_sax_over_acoustic',0.,[('exp2448_saxophone_target.wav',.007,'saxophone'),('exp1159_acoustic_guitar_target.wav',.07,'acoustic_guitar')]),
 ('cello_flute_equal',0.,[('exp1758_cello_target.wav',.07,'cello'),('exp2340_flute_target.wav',.07,'flute')]),
 ('accordion_only',0.,[('exp122_accordion_target.wav',.07,'accordion')]),
 ('quiet_flute_minus36dB',5.,[('exp2340_flute_target.wav',.07*10**(-36/20),'flute'),('exp1758_cello_target.wav',.07,'cello')]),
 ('electric_accordion',5.,[('EGSet12_02.wav',.07,'guitar'),('exp122_accordion_target.wav',.07,'accordion')]),
 ('three_sources',5.,[('EGSet12_02.wav',.05,'guitar'),('exp1758_cello_target.wav',.04,'cello'),('exp2448_saxophone_target.wav',.02,'saxophone')]),
 ('silence',0.,[]),
 ('reserve_violin_acoustic',0.,[('exp3431_violin_target.wav',.07,'violin'),('exp1159_acoustic_guitar_target.wav',.07,'acoustic_guitar')]),
 ('reserve_trumpet_acoustic',0.,[('exp2848_trumpet_target.wav',.07,'trumpet'),('exp1159_acoustic_guitar_target.wav',.07,'acoustic_guitar')]),
]


def controls(directory,download=False):
    directory.mkdir(parents=True,exist_ok=True)
    for item in json.loads((ROOT/'tests/fixtures/instrument_control_sources.json').read_text())['sources']:
        path=directory/item['file']
        if not path.exists() and download:
            temporary=path.with_name(path.name+'.download')
            try:
                with urllib.request.urlopen(item['url'],timeout=30) as response,temporary.open('wb') as dest:
                    for block in iter(lambda:response.read(1024*1024),b''):dest.write(block)
                if hashlib.file_digest(temporary.open('rb'),'sha256').hexdigest()!=item['sha256']:
                    raise ValueError('Control checksum mismatch: '+item['file'])
                temporary.replace(path)
            finally:temporary.unlink(missing_ok=True)
        if not path.exists():raise FileNotFoundError(str(path)+'; use --download-controls')
        if hashlib.file_digest(path.open('rb'),'sha256').hexdigest()!=item['sha256']:
            raise ValueError('Control checksum mismatch: '+item['file'])


def audio(directory,name,start=0.,duration=5.):
    a,sr=sf.read(directory/name,dtype='float32',always_2d=True)
    a=resample_poly(a.mean(1),SR,sr)[round(start*SR):round((start+duration)*SR)]
    return a/max(1e-9,float(np.sqrt(np.mean(a*a))))


def sisdr(reference,estimate):
    x=reference.astype('float64');y=estimate.astype('float64')
    x-=x.mean();y-=y.mean()
    target=x*np.dot(x,y)/max(1e-12,np.dot(x,x))
    error=float(np.sum((y-target)**2))
    if error<1e-12:return None  # perfect/scale-equivalent source: no finite baseline
    return float(10*np.log10((np.dot(target,target)+1e-12)/error))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--controls',type=Path,required=True)
    parser.add_argument('--cache',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--download-controls',action='store_true')
    args=parser.parse_args();controls(args.controls,args.download_controls)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    results=[]
    with tempfile.TemporaryDirectory(prefix='FaixaLab-general-tests-') as temporary:
        work=Path(temporary)
        for name,start,parts in CASES:
            refs={category:audio(args.controls,file,start)*gain for file,gain,category in parts}
            mix=sum(refs.values()) if refs else np.zeros(SR,dtype='float32')
            folder=work/name;folder.mkdir()
            stereo=np.stack([mix,mix],1)
            sf.write(folder/'mix.wav',stereo,SR,subtype='FLOAT')
            sf.write(folder/'drums.wav',np.zeros_like(stereo),SR,subtype='FLOAT')
            began=time.monotonic()
            retained,details=refine(folder/'mix.wav',folder/'drums.wav',folder/'out',args.cache)
            metrics=[]
            for category,reference in refs.items():
                baseline=sisdr(reference,mix)
                m={'target':category,'retained':category in retained,'baseline_SI_SDR_dB':baseline}
                if category in retained:
                    estimate=sf.read(folder/'out'/(category+'.wav'),dtype='float32',always_2d=True)[0].mean(1)
                    value=sisdr(reference,estimate)
                    m.update(separated_SI_SDR_dB=value,improvement_dB=value-baseline if value is not None and baseline is not None else None)
                metrics.append(m)
            combined=sum(sf.read(folder/'out'/(category+'.wav'),dtype='float32',always_2d=True)[0] for category in retained+['other'])
            error=float(np.max(np.abs(combined-stereo)))
            assert error<2e-6,error
            assert not list((folder/'out').glob('*.work'))
            assert not list((folder/'out').glob('identity-*'))
            row={'case':name,'retained':retained,'metrics':metrics,'reconstruction_max_error':error,
                 'seconds':time.monotonic()-began,'details':details}
            results.append(row);print(name,retained,flush=True)
            args.output.write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
        short=audio(args.controls,'exp2340_flute_target.wav',start=5.,duration=2.)*.002
        for start in [2.,91.]:
            x=np.zeros(120*SR,dtype='float32');x[round(start*SR):round(start*SR)+len(short)]=short
            path=work/'brief.wav';sf.write(path,np.stack([x,x],1),SR,subtype='FLOAT')
            evidence=validate_identity(path,'flute',.1)
            assert evidence['relative_rms']<.003 and evidence['identity_state']=='confirmed'
            results.append({'case':'brief_flute','start':start,'duration':120.,'validation':evidence})
    args.output.write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
