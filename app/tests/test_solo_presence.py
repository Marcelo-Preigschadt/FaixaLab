"""Boundary, no-solo, cache, cancellation and legacy-result contracts."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import soundfile as sf

from faixalab import solo_presence, solo_tabs, storage
from faixalab.app import app
from faixalab.media import Cancelled
from fastapi.testclient import TestClient


class SoloPresenceChecks(unittest.TestCase):
    def signals(self, start=7., end=14., duration=25.):
        t = np.arange(round(duration * solo_presence.SR)) / solo_presence.SR
        rhythm = (.08 * np.sin(2 * np.pi * 220 * t)).astype('float32')
        lead = (.005 * np.sin(2 * np.pi * 330 * t)).astype('float32')
        inside = (t >= start) & (t < end)
        lead[inside] = .23 * np.sin(2 * np.pi * 440 * t[inside])
        mixture = lead + rhythm + .12 * np.sin(2 * np.pi * 117 * t)
        centers = np.arange(duration)
        scores = np.full((len(centers), 2), .99, dtype='float32')
        return centers, scores, lead, rhythm, mixture.astype('float32')

    def test_foreground_edges_come_from_audio_and_translate_with_the_audio(self):
        for start in (3., 8., 17.):
            args = self.signals(start, start + 4)
            result = solo_presence.decode_sections(*args)
            self.assertEqual(len(result), 1)
            self.assertLess(abs(result[0]['start'] - start), .5)
            self.assertLess(abs(result[0]['end'] - start - 4), .5)

    def test_classifier_alone_cannot_turn_quiet_accompaniment_leakage_into_solo(self):
        t, p, _, rhythm, mix = self.signals()
        result = solo_presence.decode_sections(t, p, rhythm * .08, rhythm, mix)
        self.assertEqual(result, [])

    def test_silence_and_uncertain_detection_do_not_fall_back_to_whole_song(self):
        t, p, lead, rhythm, mix = self.signals()
        self.assertEqual(solo_presence.decode_sections(t, p, lead * 0, rhythm, mix), [])
        self.assertEqual(solo_presence.decode_sections(t, p * 0, lead, rhythm, mix), [])

    def test_vocal_energy_does_not_apply_an_absolute_vocal_presence_veto(self):
        t, p, lead, rhythm, mix = self.signals()
        # Competing non-guitar energy is present throughout, including the solo.
        self.assertTrue(solo_presence.decode_sections(t, p, lead, rhythm, mix))

    def test_presence_cache_reuses_inference_and_invalidates_changed_audio(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            t, p, lead, rhythm, mixture = self.signals(duration=20.)
            for name, a in [('lead', lead), ('rhythm', rhythm), ('original', mixture)]:
                sf.write(root / (name + '.wav'), a, solo_presence.SR, subtype='FLOAT')
            context = {'guitar_rhythm': root / 'rhythm.wav', 'original': root / 'original.wav'}
            from faixalab import instrument_id
            labels=json.loads((instrument_id.ROOT/'instrument_id_metadata.json').read_text())['labels']
            identity=np.zeros((2,len(labels)),dtype='float32');identity[:,labels.index('Guitar')]=.9
            with patch.object(instrument_id,'analyze',return_value=(np.array([2.5,17.5]),identity,labels)), \
                 patch.object(solo_presence, 'classify', return_value=(t, p)) as infer:
                first = solo_presence.detect(root / 'lead.wav', context, cache_path=root / 'cache.json')
                second = solo_presence.detect(root / 'lead.wav', context, cache_path=root / 'cache.json')
                self.assertEqual(first, second)
                self.assertEqual(infer.call_count, 1)
                sf.write(root / 'rhythm.wav', rhythm * .9, solo_presence.SR, subtype='FLOAT')
                solo_presence.detect(root / 'lead.wav', context, cache_path=root / 'cache.json')
                self.assertEqual(infer.call_count, 2)

    def test_cancel_before_loading_and_inference(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'audio.wav'
            sf.write(path, np.zeros(2400), solo_presence.SR)
            cancel = threading.Event()
            cancel.set()
            with patch.object(solo_presence, 'load_model') as load:
                with self.assertRaises(Cancelled):
                    solo_presence.detect(path, {'guitar_rhythm': path, 'original': path}, cancel)
                load.assert_not_called()

    def test_rejected_regions_have_no_automatic_notes_and_preserve_explicit_edits(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'lead.wav'
            sf.write(path, np.zeros(22050), 22050)
            manual = {'start': .2, 'end': .4, 'midi': 64, 'note': 'E4', 'string': 5, 'fret': 0,
                      'confidence': .9, 'edited': True}
            detected = {'sections': [], 'version': solo_presence.VERSION, 'solo_seconds': 0}
            with patch.object(solo_presence, 'detect', return_value=detected), patch.object(solo_tabs, 'infer_activations') as pitch:
                result = solo_tabs.transcribe(path, {'scope': 'solos'})
                self.assertEqual(result['notes'], [])
                self.assertIn('Nenhum trecho', result['message'])
                kept = solo_tabs.transcribe(path, {'scope': 'solos'}, previous=[manual])
                self.assertEqual(kept['notes'][0]['fret'], 0)
                self.assertIn('correções manuais', kept['message'])
                pitch.assert_not_called()

    def test_old_analysis_is_rejected_for_editing_and_export(self):
        project = storage.new_project('Legacy tab', {'type': 'file'}, {})
        project = storage.update_project(project['id'], status='ready', duration=2.,
                    audio_revision='same-audio', tablature={'status': 'ready', 'version': '0.4.0',
                    'source_revision': 'same-audio', 'notes': []})
        self.assertFalse(solo_tabs.current(project['tablature'], project))
        url = '/api/projects/' + project['id']
        with TestClient(app) as client:
            for kind in ('solo-tab', 'solo-midi'):
                self.assertEqual(client.get(url + '/export/' + kind).status_code, 409)
            self.assertEqual(client.delete(url + '/solo-tabs/0').status_code, 409)
            self.assertEqual(client.post(url + '/solo-tabs', json={'scope': 'invalid'}).status_code, 422)


if __name__ == '__main__':
    unittest.main()
