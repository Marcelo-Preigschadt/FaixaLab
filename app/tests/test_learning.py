import io
import os
import tempfile
import unittest
from pathlib import Path
import numpy as np
from fastapi.testclient import TestClient

if not os.environ.get('FAIXALAB_DATA_DIR'):
    os.environ['FAIXALAB_DATA_DIR'] = tempfile.mkdtemp(prefix='faixalab_learning_')

from faixalab.app import app
from faixalab import storage
from faixalab.chord_dictionary import load_dictionary, valid_label
from faixalab.solo_tabs import assign_positions, limit_polyphony, midi_bytes, text_tab, TUNING


class LearningChecks(unittest.TestCase):
    def test_dictionary_uses_matching_pitch_sets_and_actual_slash_bass(self):
        data = load_dictionary()
        checked = 0
        for chord in data['chords']:
            tones = {(chord['root']+n)%12 for n in data['theory'][chord['quality']]['intervals']}
            tones.add(chord['bass'])
            required = {(chord['root']+n)%12 for n in data['theory'][chord['quality']]['required']}
            self.assertTrue(valid_label(chord['label']))
            for position in chord['positions']:
                pitches = [base+f for base,f in zip(TUNING,position['frets']) if f>=0]
                self.assertLessEqual(set(p%12 for p in pitches),tones,chord['label'])
                self.assertLessEqual(required,set(p%12 for p in pitches),chord['label'])
                self.assertEqual(min(pitches)%12,chord['bass'],chord['label'])
                checked += 1
        self.assertEqual(checked,3078)
        for label in ['C6/9','C7M','Cm7M','Cmaj13','G7#9','F#m7b5','Bb/D','Dm11','N']:
            self.assertTrue(valid_label(label),label)
        for label in ['X','Cmystery','<script>','C/unknown','N#']:
            self.assertFalse(valid_label(label),label)

    def test_positions_preserve_pitch_and_do_not_share_a_ringing_string(self):
        notes=[{'start':0.,'end':1.,'midi':64,'confidence':.9},
               {'start':0.,'end':1.,'midi':67,'confidence':.8},
               {'start':1.2,'end':2.,'midi':69,'confidence':.9}]
        mapped=assign_positions(notes)
        self.assertNotEqual(mapped[0]['string'],mapped[1]['string'])
        for note in mapped:
            self.assertEqual(TUNING[note['string']]+note['fret'],note['midi'])
        corrected=[{'start':0.,'end':1.,'midi':64,'string':5,'fret':0,'edited':True}]
        self.assertEqual(assign_positions(corrected,9,24)[0]['fret'],0)

    def test_polyphony_constraint_retains_a_real_sustained_note(self):
        notes=[{'start':0.,'end':2.,'midi':64,'confidence':.9},
               {'start':.5,'end':1.,'midi':76,'confidence':.3}]
        self.assertEqual([n['midi'] for n in limit_polyphony(notes,1)],[64])
        self.assertEqual({n['midi'] for n in limit_polyphony(notes,2)},{64,76})

    def test_midi_round_trip_keeps_pitches_times_and_string_channels(self):
        import mido
        notes=[{'start':.3,'end':.75,'midi':64,'string':4,'confidence':.8},
               {'start':.3,'end':1.,'midi':64,'string':5,'confidence':.8}]
        midi=mido.MidiFile(file=io.BytesIO(midi_bytes(notes)))
        elapsed=0;found=[]
        for message in midi:
            elapsed+=message.time
            if message.type=='note_on' and message.velocity:
                found.append((message.note,message.channel,round(elapsed,3)))
        self.assertEqual(found,[(64,4,.3),(64,5,.3)])

    def test_extended_corrections_and_stale_tab_exports(self):
        p=storage.new_project('Learning test',{'type':'file'}, {})
        storage.update_project(p['id'],status='ready',duration=2.,audio_revision='one',
                chords=[{'start':0.,'end':2.,'label':'C'}],
                tablature={'status':'ready','source_revision':'old','notes':[]})
        with TestClient(app) as client:
            response=client.patch(f'/api/projects/{p["id"]}/annotations',json={'chords':[{'start':0.,'end':2.,'label':'Cmaj13'}]})
            self.assertEqual(response.status_code,200)
            self.assertEqual(client.get(f'/api/projects/{p["id"]}/export/solo-midi').status_code,409)
            self.assertEqual(client.post(f'/api/projects/{p["id"]}/solo-tabs',json={}).status_code,409)
            dictionary=client.get('/api/chord-dictionary').json()
            self.assertEqual(dictionary['summary']['positions'],3078)

    def test_note_deletion_retains_excluded_interval_in_a_legacy_project(self):
        p=storage.new_project('Legacy tab',{'type':'file'}, {})
        storage.update_project(p['id'],status='ready',duration=2.,tablature={'status':'ready','version':'0.6.0','source_revision':'original',
            'notes':[{'start':0.,'end':1.,'midi':64,'note':'E4','string':4,'fret':5},
                     {'start':1.,'end':2.,'midi':67,'note':'G4','string':4,'fret':8}]})
        with TestClient(app) as client:
            response=client.delete(f'/api/projects/{p["id"]}/solo-tabs/1')
            self.assertEqual(response.status_code,200)
            tab=response.json()['tablature']
            self.assertEqual(len(tab['notes']),1)
            self.assertEqual(tab['excluded_notes'],[{'start':1.,'end':2.,'midi':67}])
            self.assertEqual(client.get(f'/api/projects/{p["id"]}/export/solo-midi').status_code,200)

    def test_text_tablature_aligns_double_stops(self):
        text=text_tab({'title':'Double stop','tablature':{'notes':[
            {'start':.3,'end':1.,'midi':64,'note':'E4','string':4,'fret':5},
            {'start':.3,'end':1.,'midi':67,'note':'G4','string':5,'fret':3}]}})
        high=next(line for line in text.splitlines() if line.startswith('e|'))
        second=next(line for line in text.splitlines() if line.startswith('B|'))
        self.assertEqual(high.index('3'),second.index('5'))


if __name__=='__main__':
    unittest.main(verbosity=2)
