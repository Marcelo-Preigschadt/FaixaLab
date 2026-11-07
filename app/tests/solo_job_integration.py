"""Real default solo-detection API job, physical timing and MIDI/ZIP exports."""
import argparse
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('recording', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='FaixaLab-solo-job-') as temp:
        os.environ['FAIXALAB_DATA_DIR'] = temp
        from faixalab import storage
        from faixalab.app import app
        from faixalab.solo_presence import read_audio, SR
        from faixalab.solo_tabs import JOBS, TUNING
        from fastapi.testclient import TestClient
        import mido
        piece = read_audio(args.recording)[6*SR:18*SR]
        audio = np.pad(piece, (7*SR, 3*SR))
        p = storage.new_project('Solo após silêncio', {'type':'file'}, {})
        root = storage.project_dir(p['id'])
        for name, signal in [('lead', audio*.92), ('rhythm', audio*.08), ('original', audio)]:
            sf.write(root/(name+'.wav'), signal, SR, subtype='FLOAT')
        storage.update_project(p['id'], status='ready', duration=len(audio)/SR, audio_revision='test-audio',
            stems=[{'name':'guitar_lead','file':'lead.wav','label':'Solo'}, {'name':'guitar_rhythm','file':'rhythm.wav','label':'Base'}])
        url = '/api/projects/'+p['id']
        began = time.monotonic()
        with TestClient(app) as client:
            client.post(url+'/solo-tabs',json={}).raise_for_status()
            while time.monotonic()-began < 120:
                project = client.get(url).json()
                tab = project.get('tablature') or {}
                if tab.get('status') not in {'queued','processing'}:
                    break
                time.sleep(.1)
            assert tab['status'] == 'ready',tab
            assert tab['settings']['scope'] == 'solos'
            assert tab['sections'] and tab['notes']
            assert min(n['start'] for n in tab['notes']) >= 6.9
            assert all(any(s['start'] <= n['start'] < n['end'] <= s['end'] for s in tab['sections']) for n in tab['notes'])
            assert all(TUNING[n['string']]+n['fret']==n['midi'] for n in tab['notes'] if n['string'] is not None)
            response = client.get(url+'/export/solo-midi');response.raise_for_status()
            midi = mido.MidiFile(file=io.BytesIO(response.content))
            elapsed=0; exported=[]
            for message in midi:
                elapsed += message.time
                if message.type=='note_on' and message.velocity:exported.append((elapsed,message.note))
            assert len(exported)==len(tab['notes'])
            for (start,pitch),note in zip(exported,tab['notes']):
                assert abs(start-note['start']) < .002 and pitch==note['midi']
            text=client.get(url+'/export/solo-tab');text.raise_for_status()
            assert 'Trechos de solo detectados' in text.text
            response=client.get(url+'/export/zip');response.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                assert z.testzip() is None
                assert {'guitarra_solo.txt','guitarra_solo.mid','projeto.json'} <= set(z.namelist())
            old_notes = list(tab['notes'])
            client.post(url+'/solo-tabs',json={}).raise_for_status()
            while time.monotonic()-began < 120:
                tab=client.get(url).json()['tablature']
                if tab['status'] not in {'queued','processing'}:break
                time.sleep(.1)
            assert tab['status']=='ready' and tab['notes']==old_notes
            while p['id'] in JOBS:time.sleep(.01)
        result={'default_scope':'solos','real_models':True,'sections':tab['sections'],'notes':len(tab['notes']),
                'minimum_note_start_seconds':min(n['start'] for n in tab['notes']),
                'notes_inside_detected_regions':True,'physical_pitches_match_positions':True,
                'MIDI_original_clock_preserved':True,'TXT':True,'ZIP':True,'cached_reanalysis_deterministic':True,
                'seconds':round(time.monotonic()-began,2)}
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
        print(json.dumps(result),flush=True)


if __name__=='__main__':
    main()
