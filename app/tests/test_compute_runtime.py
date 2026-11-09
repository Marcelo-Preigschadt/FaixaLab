import importlib
import os
import subprocess
import threading
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import torch

import install_engine
from faixalab import compute, pipeline
from faixalab.media import Cancelled


class RuntimeChecks(unittest.TestCase):
    def test_lyrics_prefer_current_then_saved_vocal_and_reject_outside_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'current.wav').write_bytes(b'current')
            (root/'previous.wav').write_bytes(b'previous')
            (root/'original.wav').write_bytes(b'mix')
            project={'stems':[{'name':'vocals','file':'current.wav'}],
                     'audio_history':{'older':{'vocals':'previous.wav'}}}
            self.assertEqual(pipeline.transcription_audio(project,root),(root/'current.wav','current_vocals'))
            project['stems']=[]
            self.assertEqual(pipeline.transcription_audio(project,root),(root/'previous.wav','previous_vocals'))
            project['audio_history']['newer']={'vocals':'../../outside.wav'}
            self.assertEqual(pipeline.transcription_audio(project,root),(root/'previous.wav','previous_vocals'))
            (root/'previous.wav').unlink()
            self.assertEqual(pipeline.transcription_audio(project,root),(root/'original.wav','original'))

    def test_thread_budget_uses_allocation_and_honors_explicit_limit(self):
        with patch.object(compute, 'available_cpus', return_value=16), patch.dict(os.environ, {}, clear=True):
            self.assertEqual(compute.thread_budget(), 8)
            os.environ['FAIXALAB_CPU_THREADS'] = '2'
            self.assertEqual(compute.thread_budget(), 2)
            self.assertEqual(compute.worker_environment()['OMP_NUM_THREADS'], '2')
            os.environ['FAIXALAB_CPU_THREADS'] = '30'
            self.assertEqual(compute.thread_budget(), 16)
            self.assertEqual(compute.thread_budget(4), 4)
            os.environ['FAIXALAB_CPU_THREADS'] = 'invalid'
            self.assertEqual(compute.thread_budget(), 8)

    def test_container_quota_overrides_host_cpu_count(self):
        def content(path, *args, **kwargs):
            if str(path) == '/sys/fs/cgroup/cpu.max':
                return '200000 100000'
            raise FileNotFoundError()
        with patch.object(compute.os, 'cpu_count', return_value=64), \
             patch.object(compute.os, 'sched_getaffinity', return_value=set(range(32)), create=True), \
             patch.object(Path, 'read_text', content):
            self.assertEqual(compute.available_cpus(), 2)

    def test_nvidia_detection_uses_driver_report_and_compute_capability(self):
        responses = [subprocess.CompletedProcess([], 0, 'CUDA Version: 12.8', ''),
                     subprocess.CompletedProcess([], 0, 'NVIDIA GeForce RTX 5090, 12.0\n', '')]
        with patch.object(install_engine.shutil, 'which', return_value='nvidia-smi'), \
             patch.object(install_engine.subprocess, 'run', side_effect=responses):
            hardware = install_engine.detect_nvidia()
        self.assertEqual(hardware['cuda'], (12, 8))
        self.assertEqual(hardware['capability'], 12.)
        self.assertEqual(install_engine.choose_plan(hardware)['flavor'], 'cu128')

    def test_cpu_and_cuda_wheels_match_existing_hardware(self):
        self.assertEqual(install_engine.choose_plan(None)['accelerator'], 'cpu')
        for maximum, expected in [((12, 4), 'cu124'), ((12, 1), 'cu121'), ((11, 8), 'cu118'), ((11, 6), 'cpu')]:
            self.assertEqual(install_engine.choose_plan({'cuda':maximum, 'capability':8.6})['flavor'], expected)
        self.assertEqual(install_engine.choose_plan({'cuda':(12, 8), 'capability':3.5})['flavor'], 'cpu')
        self.assertEqual(install_engine.choose_plan({'cuda':(12, 4), 'capability':12.})['flavor'], 'cpu')
        self.assertEqual(install_engine.choose_plan({'cuda':(12, 8), 'capability':12.}, 'cpu')['flavor'], 'cpu')

    def test_failed_cuda_install_or_probe_falls_back_once(self):
        hardware = {'cuda':(12, 4), 'capability':8.6}
        with patch.object(install_engine, 'detect_nvidia', return_value=hardware), \
             patch.object(install_engine, 'install') as install, \
             patch.object(install_engine, 'validate', side_effect=[RuntimeError('driver failed'), {'cuda_available':False}]):
            result = install_engine.prepare('python')
        self.assertEqual(install.call_count, 2)
        self.assertEqual(result['selected']['accelerator'], 'cpu')
        self.assertIn('driver failed', result['fallback_reason'])

    def test_explicit_cuda_never_silently_changes_to_cpu(self):
        with patch.object(install_engine, 'detect_nvidia', return_value=None), \
             patch.object(install_engine, 'install') as install:
            with self.assertRaises(RuntimeError):
                install_engine.prepare('python', accelerator='cuda')
            install.assert_not_called()

    def test_gpu_worker_memory_failure_retries_on_cpu_without_mutating_arguments(self):
        command = ['python', '-m', 'worker', '--device', 'cuda']
        fallback = []
        with patch.object(pipeline, 'run_process', side_effect=[RuntimeError('CUDA out of memory'), None]) as run:
            device, reason = pipeline.run_neural_worker(command, threading.Event(), None, {},
                cwd='.', on_tick=None, on_fallback=lambda:fallback.append(True))
        self.assertEqual(device, 'cpu')
        self.assertEqual(len(fallback), 1)
        self.assertIn('CUDA out of memory', reason)
        self.assertEqual(run.call_args_list[1].args[0][-1], 'cpu')
        self.assertEqual(command[-1], 'cuda')

    def test_worker_does_not_hide_model_errors_or_retry_a_cancellation(self):
        for error, cancel, expected in [(RuntimeError('invalid model shape'), threading.Event(), RuntimeError),
                                        (Cancelled(), threading.Event(), Cancelled)]:
            with patch.object(pipeline, 'run_process', side_effect=error) as run:
                with self.assertRaises(expected):
                    pipeline.run_neural_worker(['p','--device','cuda'],cancel,None,{},cwd='.',on_tick=None,on_fallback=lambda:None)
                self.assertEqual(run.call_count, 1)

    def test_attention_api_accepts_cuda_tagged_inputs_on_pinned_torch(self):
        # Exercise the former CUDA-only API branch using CPU storage. This
        # detects incompatible SDPA keywords; it does not benchmark a real GPU.
        class CudaTaggedCPU(torch.Tensor):
            @property
            def is_cuda(self):
                return True
        x = torch.randn(1, 2, 7, 8)
        tagged = x.as_subclass(CudaTaggedCPU)
        expected = torch.nn.functional.scaled_dot_product_attention(x, x, x)
        for name in ('bs_roformer', 'roformer'):
            module = importlib.import_module('faixalab.vendor.'+name+'.attend')
            attention = module.Attend(flash=True).eval()
            with torch.inference_mode():
                actual = attention(tagged,tagged,tagged).as_subclass(torch.Tensor)
            torch.testing.assert_close(actual, expected, rtol=0, atol=0)


if __name__ == '__main__':
    unittest.main()
