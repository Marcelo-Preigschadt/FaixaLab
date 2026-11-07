"""Inference equivalence, cache invalidation and real mobile audio contracts."""
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient
from faixalab import storage, solo_presence, solo_tabs
from faixalab.app import app


class SpeedAndMobileChecks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        (self.root/'projects').mkdir()
        self.root_patch=patch.multiple(storage,ROOT=self.root,PROJECTS=self.root/'projects')
        self.root_patch.start()
    def tearDown(self):
        self.root_patch.stop()
        self.temp.cleanup()

    def test_context_mask_preserves_positive_sections_at_different_positions(self):
        sr=solo_presence.SR
        t=np.arange(20*sr)/sr
        rhythm=(.07*np.sin(2*np.pi*220*t)).astype('float32')
        for start in (2,7,13):
            lead=np.zeros_like(rhythm)
            inside=(t>=start)&(t<start+3)
            lead[inside]=.3*np.sin(2*np.pi*440*t[inside])
            mix=lead+rhythm
            centers=np.arange(20,dtype='float32')
            scores=np.full((20,2),.95,dtype='float32')
            candidates=solo_presence.context_candidates(lead,rhythm,mix)
            complete=solo_presence.decode_sections(centers,scores,lead,rhythm,mix)
            masked=solo_presence.decode_sections(centers,scores*candidates[:,None],lead,rhythm,mix)
            self.assertEqual(len(complete),1)
            self.assertEqual(complete,masked)
            self.assertLess(candidates.sum(),len(candidates))

    def test_fused_masks_preserve_all_heads_and_subset_order(self):
        import torch
        from torch import nn
        from faixalab.fast_masks import FusedMaskBank
        torch.manual_seed(12)
        class Head(nn.Module):
            def __init__(self):
                super().__init__()
                self.to_freqs=nn.ModuleList([nn.Sequential(nn.Sequential(nn.Linear(4,8),nn.Tanh(),nn.Linear(8,2*n)),nn.GLU(-1)) for n in (3,5,2)])
            def forward(self,x):return torch.cat([net(x[:,:,i]) for i,net in enumerate(self.to_freqs)],-1)
        heads=nn.ModuleList([Head() for _ in range(3)])
        x=torch.randn(2,7,3,4)
        bank=FusedMaskBank(heads)
        with torch.inference_mode():
            expected=torch.stack([head(x) for head in heads],dim=1)
            torch.testing.assert_close(bank(x),expected,rtol=1e-6,atol=1e-6)
            torch.testing.assert_close(bank(x,[2,0]),expected[:,[2,0]],rtol=1e-6,atol=1e-6)

    def test_pitch_cache_reuses_inference_and_invalidates_audio_revision(self):
        path=self.root/'guitar.wav'
        sf.write(path,.2*np.sin(2*np.pi*440*np.arange(22050)/22050),22050)
        frames=[[3,15,64,.9],[17,33,67,.85]]
        from faixalab.vendor.basic_pitch import note_creation
        with patch.object(solo_tabs,'infer_activations',return_value={'note':np.ones((40,88)),'onset':np.ones((40,88))}) as infer,patch.object(note_creation,'output_to_notes_polyphonic',return_value=frames):
            a=solo_tabs.transcribe(path,{'scope':'full','max_fret':24},cache_path=self.root/'presence.json')
            b=solo_tabs.transcribe(path,{'scope':'full','max_fret':23},cache_path=self.root/'presence.json')
            self.assertGreater(len(a['notes']),0)
            self.assertEqual([(n['midi'],n['start'],n['end']) for n in a['notes']],[(n['midi'],n['start'],n['end']) for n in b['notes']])
            self.assertEqual(infer.call_count,1)
            solo_tabs.transcribe(path,{'scope':'full'},cache_path=self.root/'presence.json',revision='new-audio')
            self.assertEqual(infer.call_count,2)

    def test_youtube_and_file_duplicates_reuse_jobs(self):
        from faixalab import pipeline
        with TestClient(app) as client,patch.object(pipeline,'submit') as submit:
            a=client.post('/api/import/youtube',json={'url':'https://www.youtube.com/watch?v=BaW_jenozKc'}).json()
            b=client.post('/api/import/youtube',json={'url':'https://youtu.be/BaW_jenozKc?t=12'}).json()
            self.assertEqual(a['id'],b['id']);self.assertTrue(b['reused'])
            one=client.post('/api/import/file',files={'file':('first.wav',b'unique-wave-test','audio/wav')}).json()
            two=client.post('/api/import/file',files={'file':('renamed.wav',b'unique-wave-test','audio/wav')}).json()
            self.assertEqual(one['id'],two['id']);self.assertTrue(two['reused'])
            self.assertEqual(submit.call_count,2)

    def test_backing_removes_vocals_lead_retains_rhythm_and_supports_ranges(self):
        from faixalab import backing
        import imageio_ffmpeg,subprocess
        p=storage.new_project('Mobile',{'type':'file'}, {})
        root=storage.project_dir(p['id']);sr=22050;t=np.arange(sr*2)/sr
        for name,freq in [('vocals',440),('guitar_lead',660),('guitar_rhythm',220)]:
            sf.write(root/(name+'.wav'),.15*np.sin(2*np.pi*freq*t),sr,subtype='FLOAT')
        p=storage.update_project(p['id'],status='ready',duration=2.,stems=[{'name':n,'file':n+'.wav'} for n in ('vocals','guitar_lead','guitar_rhythm')])
        with TestClient(app) as client:
            first=client.post('/api/projects/'+p['id']+'/backing',json={})
            self.assertEqual(first.status_code,200,first.text)
            result=first.json();audio=root/result['file'];stamp=audio.stat().st_mtime_ns
            second=client.post('/api/projects/'+p['id']+'/backing',json={}).json()
            self.assertEqual(result['key'],second['key']);self.assertEqual(stamp,audio.stat().st_mtime_ns)
            partial=client.get(result['url'],headers={'Range':'bytes=0-31'})
            self.assertEqual(partial.status_code,206);self.assertEqual(len(partial.content),32)
            self.assertEqual(partial.headers['content-type'],'audio/mp4')
            self.assertEqual(client.post('/api/projects/'+p['id']+'/backing',json={'preset':'mixer','gains':{}}).status_code,422)
            streamed=client.get('/api/projects/'+p['id']+'/audio/guitar_rhythm?format=m4a',headers={'Range':'bytes=0-31'})
            self.assertEqual(streamed.status_code,206)
        decoded=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-i',str(audio),'-f','f32le','-ac','1','-ar',str(sr),'-'],capture_output=True,check=True)
        samples=np.frombuffer(decoded.stdout,dtype='<f4')[:sr*2]
        spectrum=np.abs(np.fft.rfft(samples*np.hanning(len(samples))))
        def peak(freq):
            k=round(freq*len(samples)/sr);return spectrum[max(0,k-2):k+3].max()
        self.assertGreater(peak(220),10)
        self.assertLess(peak(440),peak(220)*.03);self.assertLess(peak(660),peak(220)*.03)

    def test_codespaces_origin_and_mobile_assets(self):
        with patch.dict(os.environ,{'CODESPACE_NAME':'test-space','PORT':'7860','GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN':'app.github.dev'}),TestClient(app) as client:
            for path in ('/mobile.css','/manifest.webmanifest','/icon.svg','/service-worker.js','/app.js','/studio.css'):
                self.assertEqual(client.get(path).status_code,200,path)
            with patch('faixalab.pipeline.submit'):
                result=client.post('/api/import/youtube',headers={'Origin':'https://test-space-7860.app.github.dev'},json={'url':'https://youtu.be/BaW_jenozKc'})
                self.assertEqual(result.status_code,202,result.text)
                blocked=client.post('/api/import/youtube',headers={'Origin':'https://outside.example'},json={'url':'https://youtu.be/BaW_jenozKc'})
                self.assertEqual(blocked.status_code,403)

if __name__=='__main__':unittest.main()
