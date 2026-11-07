"""General local separation: infer all candidates, then verify their timbres."""
from pathlib import Path
import argparse
import gc
import hashlib
import json
import math
import os
import tempfile
import time
import urllib.request
import uuid
import numpy as np

from .instrument_catalog import CATALOG, EXCLUSIVE_GROUPS, automatic_candidates, checked_selection
from .media import Cancelled

SR = 44100
MODEL_URL = ('https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/download/'
             'v1.0.21/mvsep_mega_model_bs_roformer_53_stems_v1.ckpt')
MODEL_SHA256 = 'c62820893bbf86d4e734f966bd142d9157cfc8bb8e79e9d8f9ea553f3ff3519f'
MODEL_BYTES = 1368919887
CONFIG_PATH = Path(__file__).parent/'models/mega53_config.json'


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def checkpoint(cache, report=None, cancel=None):
    cache=Path(cache);cache.mkdir(exist_ok=True,parents=True)
    target=cache/'mvsep_mega53_v1.ckpt'
    if target.is_file() and target.stat().st_size==MODEL_BYTES and digest(target)==MODEL_SHA256:
        return target
    temporary=target.with_name(target.name+'.'+uuid.uuid4().hex+'.part')
    try:
        with urllib.request.urlopen(MODEL_URL,timeout=30) as response,temporary.open('wb') as dest:
            received=0
            while block:=response.read(1024*1024):
                if cancel and cancel.is_set():raise Cancelled()
                dest.write(block);received+=len(block)
                if report:
                    report(.08+.12*min(1,received/MODEL_BYTES),
                           'Baixando separador detalhado · %d / %d MB' % (received//1000000,MODEL_BYTES//1000000))
        if temporary.stat().st_size!=MODEL_BYTES or digest(temporary)!=MODEL_SHA256:
            raise RuntimeError('O download do separador ficou incompleto. Tente o refinamento novamente.')
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def load_model(path, selected, device='cpu', *, fast_masks=True):
    import torch
    from .vendor.bs_roformer.bs_roformer import BSRoformer
    config=json.loads(CONFIG_PATH.read_text('utf-8'))
    indices=[config['instruments'].index(CATALOG[name]['head']) for name in selected]
    weights=torch.load(path,map_location='cpu',weights_only=True,mmap=True)
    if 'state_dict' in weights:weights=weights['state_dict']
    remap={original:index for index,original in enumerate(indices)}
    state={}
    for name,value in weights.items():
        if name.startswith('mask_estimators.'):
            parts=name.split('.');head=int(parts[1])
            if head not in remap:continue
            parts[1]=str(remap[head]);name='.'.join(parts)
        state[name]=value
    settings=config['model'].copy();settings['num_stems']=len(indices)
    for name in ('freqs_per_bands','multi_stft_resolutions_window_sizes'):
        if name in settings:settings[name]=tuple(settings[name])
    torch.set_num_threads(max(1,min(4,int(os.environ.get('FAIXALAB_CPU_THREADS',os.cpu_count() or 1)))))
    model=BSRoformer(**settings)
    model.load_state_dict(state,strict=True)
    del state,weights
    model.eval()
    if fast_masks:
        from .fast_masks import enable
        model=enable(model)
    return model.to(device)


def read_stereo(path):
    import soundfile as sf
    from scipy.signal import resample_poly
    data,sr=sf.read(path,dtype='float32',always_2d=True)
    if data.shape[1]==1:data=np.repeat(data,2,axis=1)
    if data.shape[1]!=2 or not len(data) or not np.isfinite(data).all():
        raise ValueError('O refinamento precisa de um áudio estéreo válido.')
    if sr!=SR:
        divisor=math.gcd(sr,SR);data=resample_poly(data,SR//divisor,sr//divisor,axis=0)
    return data.astype('float32')


def discover(paths, report=None, cancel=None):
    # Old stems can already have lost or mixed up an instrument. A classifier
    # on those stems must not decide whether its trained head is run at all.
    # Keep this entry point for existing callers; paths do not filter candidates.
    if cancel and cancel.is_set():raise Cancelled()
    selected=automatic_candidates()
    if report:report(.04,'Avaliando automaticamente %d categorias de instrumentos' % len(selected))
    return selected,{'policy':'separate_then_verify','candidate_count':len(selected),
                     'prefiltered_by_existing_stems':False}


def validate_identity(path, category, mixture_rms, cancel=None):
    from .instrument_id import analyze_audio,read
    import soundfile as sf
    total=0.;samples=0;peak=0.
    with sf.SoundFile(path) as stream:
        for block in stream.blocks(blocksize=SR,dtype='float32',always_2d=True):
            if cancel and cancel.is_set():raise Cancelled()
            energy=float(np.sum(block.astype('float64')**2))
            total+=energy;samples+=block.size
            peak=max(peak,math.sqrt(energy/max(1,block.size)))
    rms=math.sqrt(total/max(1,samples))
    relative=rms/max(mixture_rms,1e-9)
    # A brief solo in a long recording must not disappear under a whole-song
    # RMS cutoff. Presence is checked locally, before loudness-normalized tagging.
    relative_peak=peak/max(mixture_rms,1e-9)
    energy_info={'relative_rms':round(relative,6),'relative_peak_rms':round(relative_peak,6)}
    if peak<2e-5 or relative_peak<.0005:
        return {'accepted':False,'reason':'very_weak',**energy_info,'target_score':0.,'confirmed_contexts':0}
    times,scores,labels=analyze_audio(read(path),cancel,normalize=True)
    lookup={name:i for i,name in enumerate(labels)}
    target_indices=[lookup[tag] for tag in CATALOG[category]['tags'] if tag in lookup]
    target=np.max(scores[:,target_indices],axis=1) if target_indices else np.zeros(len(scores))
    support=[lookup[tag] for tag in CATALOG[category].get('support',[]) if tag in lookup]
    if support:
        target=np.maximum(target,.18*np.max(scores[:,support],axis=1))
    # Evaluate actual instruments, excluding generic Music and Musical instrument.
    target_labels=set(CATALOG[category]['tags'])
    competition=set(tag for item in CATALOG.values() for tag in item['tags'])-target_labels
    # Generic parents describe their children too; they are not contradictory
    # identities. Specific sibling instruments still compete with each other.
    competition-={'Guitar','Strum','Bowed string instrument','String section',
                  'Wind instrument, woodwind instrument','Brass instrument',
                  'Percussion','Mallet percussion','Keyboard (musical)','Bell','Chime'}
    opponents=[lookup[tag] for tag in competition if tag in lookup]
    competing=np.max(scores[:,opponents],axis=1) if opponents else np.zeros(len(scores))
    confirmed=(target>=.12)&(target>=competing*.8)
    if len(confirmed)>1:
        adjacent=np.r_[False,confirmed[:-1]]|np.r_[confirmed[1:],False]
        strong=(target>=.4)&(target>=competing*1.25)
        confirmed &= adjacent|strong
    timbre_confirmed=bool(np.any(confirmed))
    # AudioSet is an independent verifier, not an exhaustive instrument oracle.
    # If every class is weak (e.g. an unusual guitar tone), retain a substantial
    # separator estimate as uncertain rather than silently losing that source.
    # A strong contradictory identity still rejects it. The residual check below
    # also requires uncertain estimates to improve mixture reconstruction.
    contradictory=(competing>=.12)&(competing>np.maximum(target,.01)*3)
    active=np.max(scores,axis=1)>.1
    supported=(target>=.02)&(target>=competing*.5)
    # Preserve dominant unrecognized sources, or quieter estimates with at least
    # weak class support. An almost zero target score cannot qualify every head.
    eligible=active&~contradictory&(supported|(relative_peak>=.5))
    uncertain=bool(not timbre_confirmed and relative_peak>=.1 and np.any(eligible))
    accepted=timbre_confirmed or uncertain
    top=np.argsort(np.max(scores,axis=0))[::-1][:6]
    return {'accepted':accepted,'reason':'separator_candidate' if uncertain else '' if accepted else 'unconfirmed_timbre',
            'identity_state':'confirmed' if timbre_confirmed else 'uncertain' if uncertain else 'unconfirmed',
            **energy_info,'target_score':round(float(target.max()),4),
            'competing_score':round(float(competing.max()),4),
            'confirmed_contexts':int(confirmed.sum()),'normalized_for_identity':True,
            'confirmed_times':[round(float(t),3) for t in times[confirmed]],
            'top':[{'label':labels[i],'score':round(float(scores[:,i].max()),4)} for i in top]}


def resolve_candidates(output, selected, validations, manual=False, cancel=None):
    """Resolve parent/child estimates and near-identical cross-family leakage.

    The separator has overlapping trained heads; summing a family and its child
    creates a second copy of the same audio. Keep children when confirmed and a
    parent as fallback when no child could be identified.
    """
    import soundfile as sf
    retained=[n for n in selected if manual or validations[n]['accepted']]
    decisions=[]
    if manual:return retained,decisions
    for parent,*children in EXCLUSIVE_GROUPS:
        present=[n for n in children if n in retained]
        if parent in retained and present:
            retained.remove(parent)
            decisions.append({'discarded':parent,'reason':'confirmed_children','kept':present})
    # Cosine similarity of actual stereo waveforms, not notes or pitch classes.
    # Independent parts playing the same notes do not normally share a waveform.
    energies={};pairs={}
    for i,left in enumerate(retained):
        with sf.SoundFile(Path(output)/(left+'.wav')) as a:
            energy=0.
            for x in a.blocks(blocksize=SR*10,dtype='float64',always_2d=True):
                if cancel and cancel.is_set():raise Cancelled()
                energy+=float(np.sum(x*x))
            energies[left]=energy
        for right in retained[i+1:]:
            dot=0.
            with sf.SoundFile(Path(output)/(left+'.wav')) as a,sf.SoundFile(Path(output)/(right+'.wav')) as b:
                for x in a.blocks(blocksize=SR*10,dtype='float64',always_2d=True):
                    if cancel and cancel.is_set():raise Cancelled()
                    y=b.read(len(x),dtype='float64',always_2d=True)
                    dot+=float(np.sum(x*y))
            pairs[left,right]=dot
    def strength(name):
        item=validations[name]
        return item.get('target_score',0.)-item.get('competing_score',0.),item.get('confirmed_contexts',0)
    for (left,right),dot in pairs.items():
        if left not in retained or right not in retained:continue
        cosine=dot/max(1e-12,math.sqrt(energies[left]*energies[right]))
        if cosine>=.95:
            kept,discarded=sorted([left,right],key=strength,reverse=True)
            retained.remove(discarded)
            decisions.append({'discarded':discarded,'reason':'duplicate_estimate','kept':[kept],
                              'waveform_cosine':round(cosine,6)})
    return retained,decisions


def verify_quiet_candidates(original, drums, output, retained, validations, cancel=None):
    """Verify weak estimates and conserve useful sources when tagging abstains.

    Confirmed sources enter first. Uncertain candidates enter by decreasing
    energy only if they reduce residual reconstruction error. We never subtract
    every uncertain candidate at once: overlapping guesses could otherwise
    cancel the real source and make all candidates appear unsupported.
    """
    import soundfile as sf
    mixture_rms=float(np.sqrt(np.mean(original**2)))
    confirmed=[n for n in retained if validations[n].get('identity_state')!='uncertain']
    uncertain=sorted((n for n in retained if n not in confirmed),
                     key=lambda n:validations[n].get('relative_rms',0.),reverse=True)
    accepted=list(confirmed);decisions=[]

    def inspect(name, others, classify):
        if cancel and cancel.is_set():raise Cancelled()
        with tempfile.TemporaryDirectory(prefix='identity-',dir=output) as temporary:
            candidate=Path(temporary)/'residual.wav'
            streams={n:sf.SoundFile(Path(output)/(n+'.wav')) for n in others}
            dot=0.;energy=0.
            try:
                with sf.SoundFile(Path(output)/(name+'.wav')) as estimate, \
                     sf.SoundFile(candidate,'w',samplerate=SR,channels=2,subtype='FLOAT') as dest:
                    for offset in range(0,len(original),SR*10):
                        if cancel and cancel.is_set():raise Cancelled()
                        stop=min(len(original),offset+SR*10)
                        block=original[offset:stop]-drums[offset:stop]
                        for stream in streams.values():
                            block-=stream.read(stop-offset,dtype='float32',always_2d=True)
                        prediction=estimate.read(stop-offset,dtype='float64',always_2d=True)
                        dot+=float(np.sum(block*prediction));energy+=float(np.sum(prediction*prediction))
                        dest.write(block)
            finally:
                for stream in streams.values():stream.close()
            evidence=validate_identity(candidate,name,mixture_rms,cancel) if classify else None
        benefit=(2*dot-energy)/max(energy,1e-12)
        validations[name]['reconstruction_support']=round(benefit,6)
        if evidence is not None:validations[name]['residual_verification']=evidence
        return benefit,evidence

    def reject(name):
        validations[name].update(accepted=False,reason='unconfirmed_in_residual')
        decisions.append({'discarded':name,'reason':'unconfirmed_in_residual','kept':[]})

    for name in uncertain:
        benefit,_=inspect(name,accepted,False)
        if benefit>0:accepted.append(name)
        else:reject(name)
    for name in confirmed:
        if validations[name].get('relative_peak_rms',0.)>=10**(-30/20):continue
        _,evidence=inspect(name,[n for n in accepted if n!=name],True)
        if evidence['identity_state']!='confirmed':
            accepted.remove(name);reject(name)
    return [n for n in retained if n in accepted],decisions


def write_remainder(original,drums,output,retained,cancel=None):
    import soundfile as sf
    output=Path(output)
    with sf.SoundFile(output/'other.wav','w',samplerate=SR,channels=2,subtype='FLOAT') as dest:
        streams={name:sf.SoundFile(output/(name+'.wav')) for name in retained}
        try:
            for offset in range(0,len(original),SR*10):
                if cancel and cancel.is_set():raise Cancelled()
                stop=min(len(original),offset+SR*10)
                residual=original[offset:stop]-drums[offset:stop]
                for stream in streams.values():residual-=stream.read(stop-offset,dtype='float32',always_2d=True)
                dest.write(residual)
        finally:
            for stream in streams.values():stream.close()


def refine(audio_path, drums_path, output, cache, selection=None, scan_paths=None,
           device='cpu', report=None, cancel=None, chunk_seconds=6.):
    import soundfile as sf
    import torch
    if report:report(.005,'Conferindo o áudio para a separação por IA')
    original=read_stereo(audio_path);drums=read_stereo(drums_path)
    if len(original)!=len(drums):raise ValueError('A bateria e o áudio original precisam ter a mesma duração.')
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    requested=checked_selection(selection or [])
    selected,detected=(requested,{}) if requested else discover(scan_paths or [audio_path],report,cancel)
    if not selected:raise ValueError('Nenhum instrumento foi selecionado.')
    weights=checkpoint(cache,report,cancel)
    if report:report(.20,'Carregando separador por IA · %d categorias' % len(selected))
    model=load_model(weights,selected,device)
    length=len(original)
    chunk=round(chunk_seconds*SR);overlap=chunk//4;step=chunk-overlap
    starts=list(range(0,max(1,length-chunk+1),step))
    if length>chunk and starts[-1]!=length-chunk:starts.append(length-chunk)
    # Disk-backed overlap accumulators bound resident RAM independently of song
    # length. The learned output heads for unrequested instruments are not built.
    buffers={name:np.memmap(output/(name+'.work'),dtype='float32',mode='w+',shape=(length,2)) for name in selected}
    count=np.zeros(length,dtype='float32')
    window=np.ones(chunk,dtype='float32')
    fade=np.linspace(0,1,overlap,dtype='float32')
    window[:overlap]=fade;window[-overlap:]=fade[::-1]
    try:
        with torch.inference_mode():
            for index,start in enumerate(starts):
                if cancel and cancel.is_set():raise Cancelled()
                part=original[start:start+chunk];size=len(part)
                part=np.pad(part,((0,chunk-size),(0,0)))
                prediction=model(torch.from_numpy(part.T.copy())[None].to(device))[0,...,:size].cpu().numpy()
                if not np.isfinite(prediction).all():raise RuntimeError('O modelo retornou amostras inválidas.')
                blend=window[:size].copy()
                if index==0:blend[:overlap]=1
                if index==len(starts)-1:blend[-overlap:]=1
                for name,signal in zip(selected,prediction):buffers[name][start:start+size]+=signal.T*blend[:,None]
                count[start:start+size]+=blend
                if report:report(.21+.64*(index+1)/len(starts),
                    'Separando %d categorias · trecho %d/%d' % (len(selected),index+1,len(starts)))
        del model
        gc.collect()
        if device=='cuda':torch.cuda.empty_cache()
        count=np.maximum(count,1e-8)
        mixture_rms=float(np.sqrt(np.mean(original**2)))
        validations={}
        for index,name in enumerate(selected):
            if cancel and cancel.is_set():raise Cancelled()
            path=output/(name+'.wav')
            with sf.SoundFile(path,'w',samplerate=SR,channels=2,subtype='FLOAT') as dest:
                for offset in range(0,length,SR*10):
                    stop=min(length,offset+SR*10)
                    dest.write(buffers[name][offset:stop]/count[offset:stop,None])
            validation=validate_identity(path,name,mixture_rms,cancel)
            validations[name]=validation
            if report:report(.85+.10*(index+1)/len(selected),'Conferindo o timbre · '+CATALOG[name]['label'])
        retained,decisions=resolve_candidates(output,selected,validations,bool(requested),cancel)
        if not requested:
            retained,residual_decisions=verify_quiet_candidates(original,drums,output,retained,validations,cancel)
            decisions.extend(residual_decisions)
        for name in selected:
            if name not in retained:(output/(name+'.wav')).unlink()
        if report:report(.96,'Conferindo sobreposições e o áudio restante')
        # Only Other absorbs the reconstruction remainder. Neither guitar nor
        # accordion is filled with unclassified residual audio.
        write_remainder(original,drums,output,retained,cancel)
        details={'model':'MVSep Mega53 v1 · comprehensive candidates + timbre verification',
                 'checkpoint_sha256':MODEL_SHA256,'device':device,'drums_preserved':True,
                 'drums_sha256':digest(drums_path),'selected':selected,'retained':retained,
                 'policy_version':'0.7.0','inference_graph':'batched-masks-0.8.0','mode':'manual' if requested else 'automatic',
                 'discovery':detected,'validation':validations,'resolution':decisions,'chunk_seconds':chunk_seconds,
                 'overlap':.25,'mixture_consistent':True,'remainder':'other',
                 'source_names':{name:CATALOG[name]['head'] for name in selected}}
        (output/'engine.json').write_text(json.dumps(details,ensure_ascii=False,indent=2),'utf-8')
        if report:report(1.,'Separação por IA concluída · %d instrumentos identificados' % (len(retained)+1))
        return retained,details
    finally:
        for buffer in buffers.values():
            buffer.flush()
            buffer._mmap.close()
        buffers.clear()
        for path in output.glob('*.work'):
            try:path.unlink()
            except OSError:pass


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('audio');parser.add_argument('output');parser.add_argument('--drums',required=True)
    parser.add_argument('--cache',required=True);parser.add_argument('--selection',default='[]')
    parser.add_argument('--scan-manifest');parser.add_argument('--device',default='cpu',choices=['cpu','cuda'])
    args=parser.parse_args()
    scans=json.loads(Path(args.scan_manifest).read_text('utf-8')) if args.scan_manifest else None
    def report(fraction,stage):print('FAIXALAB_INSTRUMENTS '+json.dumps({'fraction':fraction,'stage':stage}),flush=True)
    refine(args.audio,args.drums,args.output,args.cache,json.loads(args.selection),scans,args.device,report)


if __name__=='__main__':main()
