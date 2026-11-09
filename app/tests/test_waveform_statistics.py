import copy
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import soundfile as sf
from faixalab import waveform_statistics as stats
from faixalab.instrument_runner import resolve_candidates, verify_quiet_candidates
from faixalab.media import Cancelled


class WaveformChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.rng = np.random.default_rng(43)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, audio):
        sf.write(self.root/(name+'.wav'), audio, 44100, subtype='FLOAT')

    def test_statistics_use_all_samples_and_both_channels_across_blocks(self):
        audio = {n:self.rng.normal(0,.1,(7001,2)).astype('float32') for n in ('a','b','c')}
        for n,x in audio.items():self.write(n,x)
        result = stats.collect(self.root,list(audio),block_frames=997)
        for a,x in audio.items():
            self.assertAlmostEqual(result.energy(a),float(np.sum(x.astype('float64')**2)),places=10)
            for b,y in audio.items():
                self.assertAlmostEqual(result.dot(a,b),float(np.sum(x.astype('float64')*y)),places=10)

    def test_duplicate_estimates_are_removed_but_independent_stereo_parts_survive(self):
        x = self.rng.normal(0,.1,(9000,2)).astype('float32')
        y = self.rng.normal(0,.1,(9000,2)).astype('float32')
        for name,value in [('guitar',x),('piano',x*.8),('flute',y)]:self.write(name,value)
        evidence = {n:{'accepted':True,'target_score':score,'confirmed_contexts':3} for n,score in [('guitar',.9),('piano',.5),('flute',.7)]}
        retained, decisions = resolve_candidates(self.root,list(evidence),evidence)
        self.assertEqual(retained,['guitar','flute'])
        self.assertEqual(decisions[0]['reason'],'duplicate_estimate')

    def test_near_duplicate_threshold_uses_legacy_arithmetic(self):
        x = self.rng.normal(0,.1,(4000,2)).astype('float32')
        self.write('guitar',x);self.write('piano',x)
        with patch.object(stats,'exact_pair',return_value=.94999999999) as exact:
            supplied=stats.WaveformStatistics(['guitar','piano'],np.array([[1.,.95],[.95,1.]]))
            evidence={n:{'accepted':True} for n in ('guitar','piano')}
            retained,_=resolve_candidates(self.root,list(evidence),evidence,statistics=supplied)
        exact.assert_called_once()
        self.assertEqual(retained,['guitar','piano'])

    def test_reconstruction_support_keeps_a_missing_source_and_rejects_an_unrelated_one(self):
        x = self.rng.normal(0,.04,(9000,2)).astype('float32')
        y = self.rng.normal(0,.04,(9000,2)).astype('float32')
        z = self.rng.normal(0,.04,(9000,2)).astype('float32')
        names=['guitar','piano','flute']
        for name,value in zip(names,[x,y,z]):self.write(name,value)
        original=x+y;drums=np.zeros_like(original)
        evidence={n:{'accepted':True,'identity_state':'uncertain','relative_rms':gain} for n,gain in zip(names,[1.,.8,.6])}
        evidence['guitar'].update(identity_state='confirmed',relative_peak_rms=.5)
        legacy=copy.deepcopy(evidence)
        expected,expected_decisions=verify_quiet_candidates(original,drums,self.root,names,legacy)
        collected=stats.collect(self.root,names,reference=(original,drums),block_frames=997)
        actual,decisions=verify_quiet_candidates(original,drums,self.root,names,evidence,statistics=collected)
        self.assertEqual(actual,expected)
        self.assertEqual(actual,['guitar','piano'])
        self.assertEqual(decisions,expected_decisions)

    def test_support_on_zero_boundary_uses_exact_residual(self):
        x = self.rng.normal(0,.04,(9000,2)).astype('float32')
        self.write('piano',x)
        original=x*.5;drums=np.zeros_like(x)
        evidence={'piano':{'accepted':True,'identity_state':'uncertain','relative_rms':1.}}
        collected=stats.collect(self.root,['piano'],reference=(original,drums))
        support,bound=collected.reconstruction_support('piano',[])
        self.assertLessEqual(abs(support),bound)
        actual,_=verify_quiet_candidates(original,drums,self.root,['piano'],evidence,statistics=collected)
        self.assertEqual(actual,[])
        self.assertEqual(evidence['piano']['reconstruction_support'],0.)

    def test_mismatched_audio_and_cancellation_do_not_produce_statistics(self):
        self.write('a',np.zeros((3000,2),dtype='float32'))
        self.write('b',np.zeros((2999,2),dtype='float32'))
        with self.assertRaises(ValueError):stats.collect(self.root,['a','b'])
        cancel=threading.Event();cancel.set()
        with self.assertRaises(Cancelled):stats.collect(self.root,['a'],cancel=cancel)


if __name__=='__main__':unittest.main()
