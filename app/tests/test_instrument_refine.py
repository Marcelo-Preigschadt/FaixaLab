"""Catalog/API/worker contracts; accuracy is tested with real recordings separately."""
import json
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

from faixalab import storage,pipeline,instrument_id
from faixalab.app import app
from faixalab.media import Cancelled
from faixalab.instrument_catalog import CATALOG,automatic_candidates,checked_selection
from faixalab.instrument_runner import discover,validate_identity


class InstrumentRefinementChecks(unittest.TestCase):
    def project(self):
        p=storage.new_project('Existing instruments',{'type':'file'}, {'stems':6,'split_guitars':True})
        root=storage.project_dir(p['id'])
        x=np.sin(np.arange(44100)/44100*2*np.pi*220).astype('float32')*.05
        for name in ['original','drums','guitar']:
            sf.write(root/(name+'.wav'),np.stack([x,x],axis=1),44100,subtype='FLOAT')
        p=storage.update_project(p['id'],status='ready',duration=1.,audio_revision='old',lyrics=[{'start':0.,'end':1.,'text':'existing'}],
            stems=[{'name':'drums','label':'Bateria','file':'drums.wav','waveform':[]},
                   {'name':'guitar','label':'Guitarra','file':'guitar.wav','waveform':[]}])
        return p,root

    def test_catalog_excludes_drums_and_ambiguous_parent_child_sums(self):
        self.assertNotIn('drums',CATALOG)
        self.assertIn('accordion',CATALOG)
        self.assertIn('acoustic_guitar',CATALOG)
        self.assertEqual(checked_selection(['accordion','accordion']),['accordion'])
        for selection in [['bowed_strings','violin'],['woodwind','saxophone'],['drums'],['../drums']]:
            with self.assertRaises(ValueError):checked_selection(selection)

    def test_api_queues_refinement_without_replacing_existing_audio(self):
        p,root=self.project();before=(root/'drums.wav').read_bytes()
        with TestClient(app) as client,patch.object(pipeline,'submit') as submit:
            r=client.post('/api/projects/'+p['id']+'/refine-instruments',json={'selection':[]})
            self.assertEqual(r.status_code,202)
            self.assertEqual(r.json()['mode'],'automatic')
            submit.assert_called_once_with(p['id'],retry='instruments')
        saved=storage.read_project(p['id'])
        self.assertEqual(saved['stems'],p['stems'])
        self.assertEqual(saved['audio_revision'],'old')
        self.assertEqual(saved['lyrics'],p['lyrics'])
        self.assertEqual((root/'drums.wav').read_bytes(),before)

    def test_invalid_catalog_selection_does_not_queue_a_job(self):
        p,_=self.project()
        with TestClient(app) as client,patch.object(pipeline,'submit') as submit:
            r=client.post('/api/projects/'+p['id']+'/refine-instruments',json={'selection':['drums']})
            self.assertEqual(r.status_code,422)
            submit.assert_not_called()

    def test_automatic_policy_does_not_gate_extraction_on_legacy_stems(self):
        selected,details=discover(['/missing/incorrectly_named_guitar.wav'])
        self.assertEqual(set(selected),set(automatic_candidates()))
        self.assertTrue({'flute','cello','clarinet','acoustic_guitar','accordion'}<=set(selected))
        self.assertFalse(details['prefiltered_by_existing_stems'])

    def test_each_youtube_import_uses_automatic_pipeline_by_default(self):
        with TestClient(app) as client,patch.object(pipeline,'submit') as submit:
            for url in ['https://youtu.be/BaW_jenozKc','https://www.youtube.com/watch?v=C51rj1HJmpU']:
                response=client.post('/api/import/youtube',json={'url':url})
                self.assertEqual(response.status_code,202,response.text)
                self.assertTrue(response.json()['options']['instrument_detail'])
                self.assertEqual(response.json()['options']['stems'],6)
            self.assertEqual(submit.call_count,2)

    def test_unrecognized_strong_source_is_available_as_uncertain(self):
        p,root=self.project()
        labels=json.loads((instrument_id.ROOT/'instrument_id_metadata.json').read_text())['labels']
        scores=np.zeros((1,len(labels)),dtype='float32')
        scores[:,labels.index('Music')]=.8
        with patch.object(instrument_id,'analyze_audio',return_value=(np.array([.5]),scores,labels)):
            result=validate_identity(root/'guitar.wav','guitar',.05)
        self.assertTrue(result['accepted'])
        self.assertEqual(result['identity_state'],'uncertain')

    def test_empty_class_evidence_does_not_authorize_a_quiet_instrument(self):
        p,root=self.project()
        labels=json.loads((instrument_id.ROOT/'instrument_id_metadata.json').read_text())['labels']
        scores=np.zeros((1,len(labels)),dtype='float32');scores[:,labels.index('Music')]=.8
        with patch.object(instrument_id,'analyze_audio',return_value=(np.array([.5]),scores,labels)):
            result=validate_identity(root/'guitar.wav','sitar',1.)
        self.assertFalse(result['accepted'])

    def test_worker_promotes_new_instruments_with_identical_drums_reference(self):
        p,root=self.project();drum_bytes=(root/'drums.wav').read_bytes();progress=[]
        def worker(args,cancel,line,environment,**kwargs):
            self.assertEqual(Path(args[args.index('--drums')+1]),root/'drums.wav')
            output=Path(args[4])
            for name in ['guitar','acoustic_guitar','accordion','other']:
                sf.write(output/(name+'.wav'),np.zeros((44100,2),dtype='float32'),44100,subtype='FLOAT')
            (output/'engine.json').write_text(json.dumps({'retained':['guitar','acoustic_guitar','accordion'],
                'model':'test-worker-boundary','validation':{'acoustic_guitar':{'identity_state':'uncertain'}},'drums_preserved':True}))
            line('FAIXALAB_INSTRUMENTS '+json.dumps({'fraction':1.,'stage':'done'}))
        with patch.object(pipeline,'run_process',side_effect=worker):
            stems,engine=pipeline.refine_instruments(p,root,p['options'],threading.Event(),lambda *a,**k:progress.append(a))
        drum=next(s for s in stems if s['name']=='drums')
        self.assertEqual(drum,p['stems'][0])
        self.assertEqual((root/drum['file']).read_bytes(),drum_bytes)
        self.assertIn('accordion',[s['name'] for s in stems])
        self.assertIn('acoustic_guitar',[s['name'] for s in stems])
        self.assertTrue(next(s for s in stems if s['name']=='acoustic_guitar')['label'].endswith(' · estimativa'))
        self.assertTrue(engine['instrument_refinement']['drums_preserved'])
        self.assertTrue(progress)

    def test_cancelled_worker_removes_only_new_temporary_output(self):
        p,root=self.project();old=(root/'drums.wav').read_bytes()
        with patch.object(pipeline,'run_process',side_effect=Cancelled()):
            with self.assertRaises(Cancelled):
                pipeline.refine_instruments(p,root,p['options'],threading.Event(),lambda *a,**k:None)
        self.assertEqual((root/'drums.wav').read_bytes(),old)
        self.assertFalse(list((root/'separated/instruments').glob('*')))

    def test_guitar_identity_needs_evidence_over_reeds_and_other_string_instruments(self):
        labels=json.loads((instrument_id.ROOT/'instrument_id_metadata.json').read_text())['labels']
        scores=np.zeros((4,len(labels)),dtype='float32')
        for i,(guitar,accordion,cello,bass) in enumerate([(.7,.03,0,0),(.02,.8,0,0),(.28,0,.4,0),(.35,0,0,.6)]):
            for name,value in [('Guitar',guitar),('Accordion',accordion),('Cello',cello),('Bass guitar',bass)]:
                scores[i,labels.index(name)]=value
        _,confirmed,_=instrument_id.guitar_evidence(np.arange(4),scores,labels)
        self.assertEqual(confirmed.tolist(),[True,False,False,False])


if __name__=='__main__':unittest.main()
