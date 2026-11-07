"""Long synthetic timing regression; optional real-guitar recording smoke test."""
import argparse,json,os,sys,time
from pathlib import Path
import soundfile as sf
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from solo_integration import plucked_melody
from faixalab.solo_tabs import transcribe,TUNING

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--guitar-recording',type=Path)
    args=parser.parse_args()
    data=Path(os.environ.get('FAIXALAB_TEST_DATA_DIR',ROOT.parent/'faixalab_test_data'));data.mkdir(exist_ok=True,parents=True)
    audio,truth=plucked_melody(duration=203.);path=data/'long_solo.wav';sf.write(path,audio,22050,subtype='FLOAT')
    settings={'min_fret':0,'max_fret':24,'voices':1,'scope':'full'}
    began=time.monotonic();result=transcribe(path,settings)
    notes=result['notes'];errors=[]
    for ref in truth:
        choices=[n for n in notes if n['midi']==ref['midi'] and abs(n['start']-ref['start'])<.12]
        if choices:errors.append(min(abs(n['start']-ref['start']) for n in choices))
    row={'duration_seconds':203,'expected_notes':len(truth),'detected_notes':len(notes),'pitch_and_onset_matches':len(errors),
         'matching_tolerance_seconds':.12,'max_onset_error_seconds':max(errors) if errors else None,'seconds':round(time.monotonic()-began,2)}
    (data/'solo_long_result.json').write_text(json.dumps(row,indent=2));print(json.dumps(row),flush=True)
    assert len(errors)/len(truth)>.95,row
    assert all(TUNING[n['string']]+n['fret']==n['midi'] for n in notes if n['string'] is not None)
    if args.guitar_recording:
        audio,sr=sf.read(args.guitar_recording,dtype='float32',always_2d=True)
        path=data/'real_guitar.wav';sf.write(path,audio[sr*6:sr*21],sr,subtype='FLOAT')
        began=time.monotonic();real=transcribe(path,settings)
        assert real['notes']
        assert all(TUNING[n['string']]+n['fret']==n['midi'] for n in real['notes'] if n['string'] is not None)
        row={'detected_notes':len(real['notes']),'unmapped':real['unmapped'],'seconds':round(time.monotonic()-began,2),
             'pitch_accuracy':'not measured without aligned annotations'}
        (data/'solo_real_result.json').write_text(json.dumps(row,indent=2));print(json.dumps(row),flush=True)

if __name__=='__main__':main()
