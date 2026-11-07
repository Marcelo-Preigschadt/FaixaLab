"""Integration evidence: recorded-source MP3, real models, automatic default.

The YouTube network download is not part of this test. --models-cache points
to a directory containing instruments/ and torch/; missing weights download.
"""
from pathlib import Path
import sys,os,json,time,tempfile,subprocess,zipfile,io,argparse
import numpy as np,soundfile as sf
from scipy.signal import resample_poly
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
parser=argparse.ArgumentParser(description='Real MP3 import through the automatic pipeline; no model mocks.')
parser.add_argument('--controls',type=Path,required=True)
parser.add_argument('--models-cache',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
with tempfile.TemporaryDirectory(prefix='FaixaLab-auto-import-') as temporary:
    os.environ['FAIXALAB_DATA_DIR']=temporary
    from faixalab import storage,pipeline
    from faixalab.app import app
    from fastapi.testclient import TestClient
    import imageio_ffmpeg
    storage.MODELS=args.models_cache.resolve()
    storage.MODELS.mkdir(parents=True,exist_ok=True)
    def read(name):
        x,s=sf.read(args.controls/name,dtype='float32',always_2d=True)
        x=resample_poly(x.mean(1),44100,s)[:44100*4]
        return x*.07/max(1e-9,float(np.sqrt(np.mean(x*x))))
    x=read('exp122_accordion_target.wav')+read('exp1159_acoustic_guitar_target.wav')
    wav=Path(temporary)/'known_mixture.wav';mp3=Path(temporary)/'known_mixture.mp3'
    sf.write(wav,np.stack([x,x],1),44100,subtype='FLOAT')
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-loglevel','error','-i',str(wav),'-b:a','192k',str(mp3)],check=True)
    began=time.monotonic();stages=[]
    with TestClient(app) as client:
        r=client.post('/api/import/file',files={'file':('sources.mp3',mp3.read_bytes(),'audio/mpeg')},
                      data={'options':json.dumps({'lyrics':False,'quality':'fast','split_guitars':False})})
        r.raise_for_status();p=r.json();assert p['options']['instrument_detail'] is True
        url='/api/projects/'+p['id']
        while time.monotonic()-began<420:
            p=client.get(url).json()
            if not stages or stages[-1]['stage']!=p['stage']:stages.append({'stage':p['stage'],'progress':p['progress']})
            if p['status'] not in {'queued','processing'}:break
            time.sleep(.25)
        assert p['status'] in {'ready','partial'},p
        names=[s['name'] for s in p['stems']]
        assert {'accordion','acoustic_guitar','drums','other'}<=set(names),names
        details=p['engine']['instrument_refinement'];assert len(details['selected'])==33
        assert details['discovery']['prefiltered_by_existing_stems'] is False
        assert details['policy_version']=='0.7.0' and details['mode']=='automatic'
        folder=storage.project_dir(p['id']);original=sf.read(folder/'original.wav',dtype='float32',always_2d=True)[0]
        combined=sum(sf.read(folder/s['file'],dtype='float32',always_2d=True)[0] for s in p['stems'])
        error=float(np.max(np.abs(original-combined)));assert error<2e-6,error
        r=client.get(url+'/export/zip');r.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            assert z.testzip() is None
            assert {'drums.wav','accordion.wav','acoustic_guitar.wav','other.wav'}<=set(z.namelist())
        result={'MP3_import_real':True,'downloaded_Demucs_and_real_neural_workers':True,'default_instrument_detail':True,
            'automatic_categories':len(details['selected']),'mode':details['mode'],'status':p['status'],'warnings':p['warnings'],
            'stems':names,'sum_max_absolute_error':error,'ZIP_stems_verified':True,'stages':stages,
            'seconds':round(time.monotonic()-began,2),'youtube_network_download_tested':False,
            'youtube_route_contract_tested_separately':True}
        print(json.dumps(result,ensure_ascii=False),flush=True)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        while p['id'] in pipeline.CANCELLATIONS:time.sleep(.01)
