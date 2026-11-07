import os
import tempfile
import unittest
from pathlib import Path
import numpy as np
import sys
import threading
import time
from unittest.mock import patch

os.environ['FAIXALAB_DATA_DIR'] = tempfile.mkdtemp(prefix='faixalab_checks_')
from faixalab.media import youtube_id
from faixalab.chords import decode_chroma, preserve_manual, stabilize_events
from faixalab.neural_chords import decode
from faixalab.media import run_process, Cancelled
from faixalab.app import app, chord_text, transpose_chord
from faixalab import storage
from fastapi.testclient import TestClient


class FunctionalChecks(unittest.TestCase):
    def test_duration_decoding_ignores_rapid_candidates_but_retains_sustained_change(self):
        times = np.arange(100) * .1
        probability = np.full((100, 4), .003)
        probability[:60, 0] = .94
        probability[60:, 1] = .94
        for start in [9, 22, 39, 52]:
            probability[start:start+2] = [.08, .01, .9, .01]
        events = decode(probability, times, ['C', 'G', 'Em', 'N'], 10., minimum_seconds=.8)
        self.assertEqual([e['label'] for e in events], ['C','G'])
        self.assertAlmostEqual(events[0]['end'], 6., places=2)

    def test_subprocess_reports_real_elapsed_and_propagates_reader_errors(self):
        ticks, lines = [], []
        run_process([sys.executable,'-u','-c',"import time; print('working', flush=True); time.sleep(1.3)"],
                    threading.Event(), lines.append, on_tick=ticks.append)
        self.assertTrue(any('working' in line for line in lines))
        self.assertTrue(any(t['elapsed_seconds']>=1 for t in ticks))
        def fail(_):
            raise ValueError('progress callback failed')
        began = time.monotonic()
        with self.assertRaisesRegex(ValueError, 'progress callback failed'):
            run_process([sys.executable,'-u','-c',"import time; print('working', flush=True); time.sleep(10)"],
                        threading.Event(), fail)
        self.assertLess(time.monotonic()-began, 3.)

    def test_requesting_chords_cancels_active_job_and_queues_after_termination(self):
        from faixalab import pipeline
        p = storage.new_project('Existing audio',{'type':'file'},{'stems':6})
        storage.update_project(p['id'], status='processing', stems=[{'name':'guitar','file':'guitar.wav'}])
        (storage.project_dir(p['id'])/'original.wav').write_bytes(b'test')
        event=threading.Event()
        pipeline.CANCELLATIONS[p['id']]=event
        try:
            with TestClient(app) as client:
                response=client.post(f'/api/projects/{p["id"]}/analyze-chords',json={'stability':'stable'})
                self.assertEqual(response.status_code,202)
                self.assertTrue(response.json()['stopping_separation'])
                self.assertTrue(event.is_set())
                self.assertEqual(pipeline.PENDING_RETRIES[p['id']]['chord_stability'],'stable')
            # A cancelled process exits through finally before the new job is submitted.
            with patch.object(pipeline,'submit') as enqueue:
                pipeline.process_project(p['id'],event,retry='chords')
                enqueue.assert_called_once_with(p['id'],retry='chords')
                self.assertEqual(storage.read_project(p['id'])['status'],'queued')
        finally:
            pipeline.CANCELLATIONS.pop(p['id'],None)
            pipeline.PENDING_RETRIES.pop(p['id'],None)

    def test_stable_harmony_rejects_brief_melodic_chord_label(self):
        events=[{'start':0.,'end':2.,'label':'C','confidence':.9},
                {'start':2.,'end':2.15,'label':'Em','confidence':.6},
                {'start':2.15,'end':4.,'label':'C','confidence':.9},
                {'start':4.,'end':6.,'label':'G','confidence':.9}]
        probability=np.tile([.9,.05,.05],(60,1))
        result=stabilize_events(events,probability,np.arange(60)*.1,['C','Em','G'],.5)
        self.assertEqual([e['label'] for e in result],['C','G'])
        self.assertEqual(result[0]['end'],4.)
    def test_neural_timeline_suppresses_single_frame_spike_and_ends_at_audio(self):
        p = np.full((40, 3), .005)
        p[:20, 0] = .99
        p[20:, 1] = .99
        p[10] = [.01, .98, .01]
        events = decode(p, np.arange(40)*.1, ['C', 'G7', 'N'], 4)
        self.assertEqual([e['label'] for e in events], ['C', 'G7'])
        self.assertEqual(events[0]['start'], 0)
        self.assertEqual(events[0]['end'], events[1]['start'])
        self.assertEqual(events[-1]['end'], 4)

    def test_refined_chords_keep_only_manually_corrected_intervals(self):
        fresh = [{'start': 0., 'end': 2., 'label': 'C'}, {'start': 2., 'end': 4., 'label': 'F'}]
        old = [{'start': 0., 'end': 1., 'label': 'Am'}, {'start': 1., 'end': 3., 'label': 'G7', 'edited': True}]
        refined = preserve_manual(fresh, old)
        self.assertEqual([(c['start'], c['end'], c['label']) for c in refined], [(0.,1.,'C'),(1.,3.,'G7'),(3.,4.,'F')])

    def test_annotation_edit_retains_other_confidences_and_word_timing(self):
        p = storage.new_project('Correções', {'type':'file'}, {})
        original = [{'start':0.,'end':2.,'label':'C','confidence':.9}, {'start':2.,'end':4.,'label':'G','confidence':.8}]
        storage.update_project(p['id'], duration=4., chords=original)
        with TestClient(app) as client:
            changed = [{**c, 'label':'G7' if i else c['label']} for i,c in enumerate(original)]
            response=client.patch(f'/api/projects/{p["id"]}/annotations',json={'chords':changed})
            self.assertEqual(response.status_code,200)
            chords=response.json()['chords']
            self.assertFalse(chords[0]['edited'])
            self.assertEqual(chords[0]['confidence'],.9)
            self.assertTrue(chords[1]['edited'])

    def test_youtube_single_video_and_host_boundaries(self):
        for url in ['https://youtu.be/BaW_jenozKc?t=3', 'https://www.youtube.com/watch?v=BaW_jenozKc&list=ignored', 'https://music.youtube.com/watch?v=BaW_jenozKc']:
            self.assertEqual(youtube_id(url), 'BaW_jenozKc')
        for url in ['http://youtube.com/watch?v=BaW_jenozKc', 'https://youtube.com.evil.test/watch?v=BaW_jenozKc', 'https://127.0.0.1/private', 'https://www.youtube.com/playlist?list=123', 'https://user:pass@youtube.com/watch?v=BaW_jenozKc']:
            with self.assertRaises(ValueError):
                youtube_id(url)

    def test_chord_progression_and_silence(self):
        chroma = np.zeros((12, 80))
        for i, notes in enumerate([[0, 4, 7], [9, 0, 4], [5, 9, 0], [7, 11, 2]]):
            chroma[notes, i*20:(i+1)*20] = 1
        events = decode_chroma(chroma, np.arange(80) * .1, 8)
        self.assertEqual([x['label'] for x in events], ['C', 'Am', 'F', 'G'])
        self.assertTrue(all(x['label'] == 'N' for x in decode_chroma(np.zeros((12, 20)), np.arange(20)*.1, 2)))

    def test_cifra_export_handles_edited_empty_line_and_transposition(self):
        p = {'title': 'Teste', 'key': {'label': 'C maior'}, 'lyrics': [{'start': 0, 'end': 1, 'text': ''}, {'start': 1, 'end': 3, 'text': 'Minha canção'}], 'chords': [{'start': 1, 'end': 3, 'label': 'C'}]}
        self.assertIn('D', chord_text(p, 2))
        self.assertIn('[D]Minha', chord_text(p, 2, True))
        self.assertEqual(transpose_chord('Bb/D', 2), 'C/E')

    def test_mutation_origin_and_annotation_validation(self):
        p = storage.new_project('Teste', {'type': 'file'}, {})
        storage.update_project(p['id'], duration=5)
        with TestClient(app) as client:
            blocked = client.post('/api/import/youtube', headers={'Origin': 'https://outside.example'}, json={'url': 'https://youtu.be/BaW_jenozKc'})
            self.assertEqual(blocked.status_code, 403)
            rejected = client.patch(f'/api/projects/{p["id"]}/annotations', json={'chords': [{'start': -1, 'end': 2, 'label': 'C'}]})
            self.assertEqual(rejected.status_code, 422)
            invalid = client.get('/api/projects/not-a-project/audio/original')
            self.assertEqual(invalid.status_code, 404)


if __name__ == '__main__':
    unittest.main(verbosity=2)
