"""Local, independent timbre evidence from a pretrained AudioSet CNN.

Stem names are not evidence of instrument identity. This model classifies the
audio itself; scores are independent sigmoid outputs, not a forced class choice.
"""
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import math
import numpy as np

from .media import Cancelled

ROOT = Path(__file__).parent / 'models'
SR = 32000
GUITAR_LABELS = ('Guitar', 'Electric guitar', 'Acoustic guitar', 'Steel guitar, slide guitar')
REED_LABELS = ('Accordion', 'Harmonica', 'Bagpipes')


@lru_cache(maxsize=1)
def resources():
    import onnxruntime as ort
    meta = json.loads((ROOT/'instrument_id_metadata.json').read_text('utf-8'))
    for name, expected in [('instrument_id.onnx',meta['sha256']), ('instrument_id_frontend.npz',meta['frontend_sha256'])]:
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != expected:
            raise RuntimeError('O reconhecedor de instrumentos está incompleto. Extraia novamente o aplicativo.')
    options=ort.SessionOptions()
    options.intra_op_num_threads=2
    options.inter_op_num_threads=1
    session=ort.InferenceSession(str(ROOT/'instrument_id.onnx'),options,providers=['CPUExecutionProvider'])
    with np.load(ROOT/'instrument_id_frontend.npz') as values:
        mel,window=values['mel'].copy(),values['window'].copy()
    return session,meta,mel,window


def features(audio):
    _,_,mel,window=resources()
    audio=np.asarray(audio,dtype='float32')
    if len(audio)<2:
        audio=np.pad(audio,(0,2-len(audio)))
    emphasized=audio[1:]-.97*audio[:-1]
    padded=np.pad(emphasized,(512,512),mode='reflect' if len(emphasized)>512 else 'constant')
    frames=np.lib.stride_tricks.sliding_window_view(padded,1024)[::320]
    spectrum=np.fft.rfft(frames*window,axis=-1)
    power=(spectrum.real**2+spectrum.imag**2).astype('float32')
    output=(np.log(np.maximum(mel@power.T,0)+1e-5)+4.5)/5.
    return output[None,None].astype('float32')


def score(audio):
    session,_,_,_=resources()
    logits=session.run(['logits'],{'mel':features(audio)})[0][0]
    return 1/(1+np.exp(-np.clip(logits,-60,60)))


def read(path):
    import soundfile as sf
    from scipy.signal import resample_poly
    audio,sr=sf.read(path,dtype='float32',always_2d=True)
    if not np.isfinite(audio).all():
        raise ValueError('Áudio inválido na identificação de instrumentos.')
    audio=audio.mean(1)
    if sr!=SR:
        divisor=math.gcd(sr,SR)
        audio=resample_poly(audio,SR//divisor,sr//divisor)
    return audio.astype('float32')


def analyze_audio(audio, cancel=None, report=None, window=5., hop=2.5, normalize=False):
    _,meta,_,_=resources()
    count=round(window*SR)
    starts=list(range(0,max(1,len(audio)-count+1),round(hop*SR)))
    if len(audio)>count and starts[-1]!=len(audio)-count:
        starts.append(len(audio)-count)
    rows=[]
    for index,start in enumerate(starts):
        if cancel and cancel.is_set():
            raise Cancelled()
        chunk=audio[start:start+count]
        if not len(chunk):
            continue
        rms=float(np.sqrt(np.mean(chunk**2)))
        if rms<2e-5:
            probabilities=np.zeros(len(meta['labels']),dtype='float32')
        else:
            # Verification of separated sources must not depend on their fader
            # level. Limit the gain so numerical leakage is not amplified freely.
            # This changes only the classifier input, never a saved audio sample.
            if normalize:
                chunk=chunk*min(100.,.05/max(rms,1e-9))
            probabilities=score(chunk)
        rows.append({'time':(start+len(chunk)/2)/SR, 'scores':probabilities})
        if report:
            report(index+1,len(starts))
    if not rows:
        rows=[{'time':0.,'scores':np.zeros(len(meta['labels']),dtype='float32')}]
    return np.array([r['time'] for r in rows]),np.stack([r['scores'] for r in rows]),meta['labels']


def analyze(path, cancel=None, report=None):
    return analyze_audio(read(path),cancel,report)


def guitar_evidence(times, scores, labels):
    indices={name:i for i,name in enumerate(labels)}
    guitar=np.max(scores[:,[indices[n] for n in GUITAR_LABELS]],axis=1)
    reed=np.max(scores[:,[indices[n] for n in REED_LABELS]],axis=1)
    competitors=('Piano','Organ','Synthesizer','Violin, fiddle','Cello','Saxophone','Flute','Trumpet',
                 'Bass guitar','Double bass','Bowed string instrument','String section',
                 'Banjo','Mandolin','Ukulele','Harp','Sitar','Zither')
    other=np.max(scores[:,[indices[n] for n in competitors if n in indices]],axis=1)
    # Positive guitar evidence and explicit rejection of a stronger reed/other
    # identity. Uncertain estimates do not authorize a guitar tablature.
    confirmed=(guitar>=.12)&(guitar>=reed*1.25)&(guitar>=other*1.25)
    if len(confirmed)>1:
        adjacent=np.r_[False,confirmed[:-1]]|np.r_[confirmed[1:],False]
        strong=(guitar>=.4)&(reed<.15)&(other<.15)
        confirmed &= adjacent|strong
    return times,confirmed,{'guitar':guitar,'reeds':reed,'other':other}


def summary(times, scores, labels, top=12):
    maxima=np.max(scores,axis=0)
    indices=np.argsort(maxima)[::-1][:top]
    return [{'label':labels[i],'score':round(float(maxima[i]),4)} for i in indices]
