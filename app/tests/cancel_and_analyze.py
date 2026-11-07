"""Real worker cancellation and saved-stem analysis after integration_run.py."""
import copy
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DATA = Path(os.environ.get('FAIXALAB_TEST_DATA_DIR', ROOT.parent / 'faixalab_test_data'))
os.environ['FAIXALAB_DATA_DIR'] = str(DATA)


def main():
    from fastapi.testclient import TestClient
    from faixalab.app import app
    identifier = json.loads((DATA / 'integration_result.json').read_text())['project_id']
    started = time.monotonic()
    with TestClient(app) as client:
        url = '/api/projects/' + identifier
        original = client.get(url).json()
        assert original['status'] == 'ready'
        corrected = copy.deepcopy(original['chords'])
        corrected[1]['label'] = 'Am7'
        client.patch(url + '/annotations', json={'chords': corrected}).raise_for_status()
        client.post(url + '/refine', json={'quality': 'quality'}).raise_for_status()
        while time.monotonic() - started < 60:
            p = client.get(url).json()
            if 'trecho ' in p['stage'] and p['progress'] >= 16:
                break
            time.sleep(.2)
        else:
            raise AssertionError('No real separation window started')
        old_stage = p['stage']
        result = client.post(url + '/analyze-chords', json={'stability': 'stable'})
        result.raise_for_status()
        assert result.json()['stopping_separation']
        while time.monotonic() - started < 120:
            p = client.get(url).json()
            if p['status'] not in {'queued','processing'}:
                break
            time.sleep(.2)
        assert p['status'] == 'ready', (p['stage'],p.get('error'),p.get('warnings'))
        assert p['stems'] == original['stems'], 'Saved audio must remain unchanged'
        assert p['audio_revision'] == original['audio_revision']
        assert p['lyrics'] == original['lyrics']
        assert any(c['label']=='Am7' and c.get('edited') for c in p['chords'])
        assert p['chord_analysis']['version']=='0.3.0'
        result = {'real_separation_cancelled':True,'cancelled_stage':old_stage,
                  'saved_stems_unchanged':True,'audio_revision_unchanged':True,
                  'lyrics_unchanged':True,'manual_correction_preserved':True,
                  'chords_recomputed':True,'seconds':round(time.monotonic()-started,2)}
        (DATA / 'cancel_and_analyze_result.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result),flush=True)


if __name__ == '__main__':
    main()
