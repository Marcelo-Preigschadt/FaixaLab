"""Cached compressed streaming and single-file backing tracks for phones."""
from pathlib import Path
import hashlib
import json
import math
import threading
import uuid

from filelock import FileLock

from . import storage
from .media import run_process

ENCODERS=threading.Semaphore(2)


def _encode(inputs, filters, destination, duration=None):
    import imageio_ffmpeg
    destination=Path(destination)
    destination.parent.mkdir(exist_ok=True,parents=True)
    with FileLock(str(destination)+'.lock',timeout=300):
        if destination.is_file():return destination
        temporary=destination.with_name(destination.stem+'.'+uuid.uuid4().hex+'.m4a')
        args=[imageio_ffmpeg.get_ffmpeg_exe(),'-nostdin','-hide_banner','-loglevel','error','-y']
        for source in inputs:args.extend(['-i',str(source)])
        if filters:args.extend(['-filter_complex',filters,'-map','[mix]'])
        else:args.extend(['-map','0:a:0'])
        args.extend(['-vn','-c:a','aac','-b:a','160k','-threads','1','-movflags','+faststart'])
        if duration is not None:args.extend(['-t',str(duration)])
        args.append(str(temporary))
        try:
            with ENCODERS:run_process(args,threading.Event(),lambda line:None)
            if not temporary.is_file() or temporary.stat().st_size<100:raise RuntimeError('Não foi possível preparar o áudio.')
            temporary.replace(destination)
        finally:temporary.unlink(missing_ok=True)
    return destination


def stream(source, root):
    source=Path(source);stat=source.stat()
    key=hashlib.sha256(json.dumps([str(source.resolve()),stat.st_size,stat.st_mtime_ns,'aac-160k-v1']).encode()).hexdigest()[:24]
    return _encode([source],None,Path(root)/'mobile'/('stem_'+key+'.m4a'))


def prepare(project, gains=None, preset='no_vocals_lead'):
    root=storage.project_dir(project['id']).resolve()
    if preset not in {'no_vocals_lead','no_vocals','mixer'}:raise ValueError('Escolha uma mixagem disponível.')
    available={stem['name']:stem for stem in project.get('stems',[])}
    if not available:raise ValueError('Aguarde a separação das faixas.')
    if gains is None:gains={name:0. if name=='vocals' or preset=='no_vocals_lead' and name=='guitar_lead' else 1. for name in available}
    if any(name not in available for name in gains):raise ValueError('Uma faixa da mixagem não existe neste projeto.')
    normalized={name:round(float(gains.get(name,0)),4) for name in available}
    if any(not math.isfinite(value) or value<0 or value>1.5 for value in normalized.values()):
        raise ValueError('Os volumes devem ficar entre 0 e 150%.')
    active=[name for name,value in normalized.items() if value>0]
    if not active:raise ValueError('Ative ao menos uma faixa para a backing track.')
    sources=[];signature=[]
    for name in active:
        source=(root/available[name]['file']).resolve()
        if not source.is_relative_to(root) or not source.is_file():raise ValueError('O áudio de uma faixa não está disponível.')
        stat=source.stat();sources.append(source)
        signature.append([name,normalized[name],stat.st_size,stat.st_mtime_ns])
    key=hashlib.sha256(json.dumps([project.get('audio_revision'),signature,'backing-aac-v1']).encode()).hexdigest()[:24]
    destination=root/'mobile'/('backing_'+key+'.m4a')
    filters=';'.join('[%d:a]volume=%.4f[a%d]'%(i,normalized[name],i) for i,name in enumerate(active))
    filters+=';'+''.join('[a%d]'%i for i in range(len(active)))
    filters+='amix=inputs=%d:duration=longest:dropout_transition=0:normalize=0,alimiter=limit=0.98:level=0:latency=1[mix]'%len(active)
    _encode(sources,filters,destination,project.get('duration'))
    return {'key':key,'gains':normalized,'preset':preset,'file':destination.relative_to(root).as_posix(),
            'url':'/api/projects/%s/backing/%s'%(project['id'],key),'format':'m4a','bitrate':160000}
