"""Real ONNX transcription -> tab edit -> MIDI/TXT -> persisted correction."""
from pathlib import Path
import os,sys,json,time,io,zipfile
import numpy as np
import soundfile as sf
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
DATA=Path(os.environ.get('FAIXALAB_TEST_DATA_DIR',ROOT.parent/'faixalab_test_data'))
DATA.mkdir(exist_ok=True,parents=True)
os.environ['FAIXALAB_DATA_DIR']=str(DATA)
from faixalab import storage
from faixalab.app import app
from faixalab.solo_tabs import TUNING,JOBS
from fastapi.testclient import TestClient
import mido


def plucked_melody(sr=22050,duration=5.4):
    pitches=[64,67,69,71,76,74,69,67]
    t=np.arange(round(sr*duration))/sr;y=np.zeros(len(t));truth=[]
    for cycle in np.arange(0,duration-4.8,5.4):
        for index,midi in enumerate(pitches):
            start=cycle+.3+index*.58;end=start+.42
            first,last=round(start*sr),min(len(y),int(np.ceil(end*sr)))
            elapsed=t[first:last]-start;frequency=440*2**((midi-69)/12)
            envelope=(1-np.exp(-elapsed*900))*np.exp(-elapsed*5)
            for harmonic,gain in [(1,1),(2,.4),(3,.2),(4,.1)]:
                y[first:last]+=.23*gain*envelope*np.sin(2*np.pi*frequency*harmonic*elapsed)
            truth.append({'start':start,'end':end,'midi':midi})
    return y.astype('float32'),truth


def wait(client,url):
    begin=time.monotonic()
    while time.monotonic()-begin<120:
        p=client.get(url).json();tab=p.get('tablature') or {}
        if tab.get('status') not in {'queued','processing'} and tab:
            assert tab['status']=='ready',tab
            while p['id'] in JOBS:time.sleep(.01)
            return p
        time.sleep(.1)
    raise AssertionError('Timed out waiting for real transcription')


def main():
    audio,truth=plucked_melody()
    p=storage.new_project('Solo com notas conhecidas',{'type':'file'}, {})
    folder=storage.project_dir(p['id']);sf.write(folder/'lead.wav',audio,22050,subtype='FLOAT')
    storage.update_project(p['id'],status='ready',duration=len(audio)/22050,audio_revision='solo-a',
        stems=[{'name':'guitar_lead','label':'Guitarra solo','file':'lead.wav','waveform':[]}])
    url='/api/projects/'+p['id'];started=time.monotonic()
    with TestClient(app) as client:
        client.post(url+'/solo-tabs',json={'scope':'full'}).raise_for_status()
        p=wait(client,url);notes=p['tablature']['notes']
        assert [n['midi'] for n in notes]==[n['midi'] for n in truth],notes
        errors=[abs(n['start']-ref['start']) for n,ref in zip(notes,truth)]
        assert max(errors)<.08,errors
        assert all(TUNING[n['string']]+n['fret']==n['midi'] for n in notes)
        midi=client.get(url+'/export/solo-midi');midi.raise_for_status()
        parsed=mido.MidiFile(file=io.BytesIO(midi.content))
        assert [m.note for track in parsed.tracks for m in track if m.type=='note_on' and m.velocity]==[n['midi'] for n in truth]
        text=client.get(url+'/export/solo-tab');text.raise_for_status();assert 'E4' in text.text
        first=notes[0]
        edit=client.patch(url+'/solo-tabs',json={'index':0,'start':first['start'],'end':first['end'],'string':5,'fret':0})
        edit.raise_for_status();assert edit.json()['tablature']['notes'][0]['edited']
        client.delete(url+'/solo-tabs/7').raise_for_status()
        client.post(url+'/solo-tabs',json={'min_fret':9,'max_fret':24,'voices':1,'scope':'full'}).raise_for_status()
        p=wait(client,url)
        assert p['tablature']['notes'][0]['fret']==0 and p['tablature']['notes'][0]['edited']
        assert len(p['tablature']['notes'])==7 and len(p['tablature']['excluded_notes'])==1
        export=client.get(url+'/export/zip');export.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(export.content)) as archive:
            assert archive.testzip() is None
            assert {'guitarra_solo.txt','guitarra_solo.mid'}<=set(archive.namelist())
        result={'project_id':p['id'],'test':'real ONNX and API','expected_pitches':[n['midi'] for n in truth],
                'detected_pitches':[n['midi'] for n in notes],'max_onset_error_seconds':round(max(errors),4),
                'physical_positions_verified':True,'MIDI_round_trip':True,'TXT_export':True,'ZIP_export':True,
                'manual_position_preserved_outside_requested_region':True,'deleted_note_preserved_after_reanalysis':True,
                'seconds':round(time.monotonic()-started,2)}
        (DATA/'solo_integration_result.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result),flush=True)

if __name__=='__main__':main()
