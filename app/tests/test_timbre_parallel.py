"""Context concurrency must preserve classifier inputs, order and cancellation."""
import os,threading,time,unittest
from unittest.mock import patch
import numpy as np
from faixalab import instrument_id as identity
from faixalab.media import Cancelled

class TimbreParallelChecks(unittest.TestCase):
 def setUp(self):
  self.audio=(np.linspace(.02,.2,identity.SR*16)).astype('float32')
  self.resources=patch.object(identity,'resources',return_value=(None,{'labels':['Guitar','Harmonica']},None,None));self.resources.start()
 def tearDown(self):self.resources.stop()
 def test_parallel_results_and_reports_keep_the_original_time_order(self):
  def score(chunk):
   time.sleep(.003 if chunk[0]>.08 else .008)
   return np.array([chunk[0],chunk[-1]],dtype='float32')
  with patch.object(identity,'score',side_effect=score):
   a,x,labels=identity.analyze_audio(self.audio,normalize=True,workers=1)
   reports=[];b,y,other=identity.analyze_audio(self.audio,normalize=True,workers=2,report=lambda i,n:reports.append((i,n)))
  np.testing.assert_array_equal(a,b);np.testing.assert_array_equal(x,y);self.assertEqual(labels,other)
  self.assertEqual([r[0] for r in reports],list(range(1,len(a)+1)))
 def test_cancellation_stops_the_bounded_queue(self):
  event=threading.Event();calls=[]
  def score(chunk):calls.append(1);time.sleep(.01);return np.array([.9,.1],dtype='float32')
  began=time.monotonic()
  with patch.object(identity,'score',side_effect=score):
   with self.assertRaises(Cancelled):identity.analyze_audio(self.audio,event,lambda i,n:event.set(),workers=2)
  self.assertLess(time.monotonic()-began,.5);self.assertLessEqual(len(calls),4)
 def test_two_core_budget_does_not_create_a_second_context_worker(self):
  with patch.dict(os.environ,{'FAIXALAB_CPU_THREADS':'2'}),patch.object(identity,'ThreadPoolExecutor') as pool,patch.object(identity,'score',return_value=np.zeros(2)):
   identity.analyze_audio(self.audio);pool.assert_not_called()
 def test_silent_contexts_do_not_invoke_the_neural_network(self):
  with patch.object(identity,'score') as score:
   _,rows,_=identity.analyze_audio(np.zeros(identity.SR*12,dtype='float32'),workers=2)
   score.assert_not_called();self.assertFalse(rows.any())

if __name__=='__main__':unittest.main()
