"""Completed-stage telemetry must preserve the published audio revision."""
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import soundfile as sf
from faixalab import pipeline, storage


class PipelineStateChecks(unittest.TestCase):
    def test_import_persists_guitar_roles_and_uses_saved_vocal_after_refinement(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'projects').mkdir()
            with patch.multiple(storage,ROOT=root,PROJECTS=root/'projects'):
                p=storage.new_project('General import',{'type':'file','file':'upload.mp3'},
                    {'stems':6,'instrument_detail':True,'split_guitars':True,'lyrics':True})
                folder=storage.project_dir(p['id'])
                def stem(name,group):
                    path=folder/group/(name+'.wav');path.parent.mkdir(exist_ok=True)
                    sf.write(path,np.zeros((44100,2),dtype='float32'),44100,subtype='FLOAT')
                    return {'name':name,'file':path.relative_to(folder).as_posix(),'waveform':[]}
                initial=[stem(n,'initial') for n in ('vocals','drums','bass','guitar','piano','other')]
                refined=[initial[1],stem('guitar','refined'),stem('other','refined')]
                roles=[refined[0],stem('guitar_lead','roles'),stem('guitar_rhythm','roles'),refined[-1]]
                def decode(source,target,cancel):
                    sf.write(target,np.zeros((44100,2),dtype='float32'),44100,subtype='FLOAT')
                    return 1.
                def chords(audio,harmonic,**kwargs):
                    self.assertIn(folder/'roles/guitar_rhythm.wav',harmonic)
                    self.assertNotIn(folder/'roles/guitar_lead.wav',harmonic)
                    self.assertNotIn(folder/'refined/guitar.wav',harmonic)
                    return {'chords':[],'bpm':120,'key':'C'}
                def transcribe(path,*args):
                    self.assertEqual(path,folder/'initial/vocals.wav')
                    return [{'start':0,'end':1,'text':'preserved voice'}],{'model':'test'}
                with patch.object(pipeline,'decode_audio',side_effect=decode), \
                     patch.object(pipeline,'separate',return_value=(initial,{'device':'cpu'})), \
                     patch.object(pipeline,'refine_instruments',return_value=(refined,{'device':'cpu'})), \
                     patch.object(pipeline,'split_guitars',return_value=(roles,{'device':'cpu','guitar_split':{}},refined[1])), \
                     patch('faixalab.chords.analyze',side_effect=chords), \
                     patch.object(pipeline,'transcribe',side_effect=transcribe):
                    pipeline.process_project(p['id'],threading.Event())
                final=storage.read_project(p['id'])
                self.assertEqual(final['status'],'ready',final['warnings'])
                self.assertEqual([s['name'] for s in final['stems']],[s['name'] for s in roles])
                self.assertIn('guitar_split',final['engine'])
                self.assertEqual(final['transcription']['audio_source'],'previous_vocals')
                self.assertEqual(final['lyrics'][0]['text'],'preserved voice')
                self.assertTrue(final['performance']['completed'])
                self.assertEqual(set(final['performance']['stages_seconds']),
                    {'audio_decode','initial_separation','instrument_refinement','guitar_roles','chords','lyrics'})


if __name__=='__main__':unittest.main()
