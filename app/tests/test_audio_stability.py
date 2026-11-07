"""Audio URLs must keep serving their revision throughout refinement."""
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
import numpy as np,soundfile as sf
from fastapi.testclient import TestClient
from faixalab import storage
from faixalab.app import app

class AudioStabilityChecks(unittest.TestCase):
 def test_revision_urls_keep_old_audio_after_refinement_and_guitar_split(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'projects').mkdir()
   with patch.multiple(storage,ROOT=root,PROJECTS=root/'projects'):
    p=storage.new_project('Music',{'type':'file'},{});folder=storage.project_dir(p['id'])
    t=np.arange(22050)/22050
    for rev,freq in [('old',220),('new',440)]:
     (folder/rev).mkdir();sf.write(folder/rev/'guitar.wav',.2*np.sin(2*np.pi*freq*t),22050,subtype='FLOAT')
    storage.update_project(p['id'],status='ready',audio_revision='old',duration=1.,stems=[{'name':'guitar','file':'old/guitar.wav'}])
    with TestClient(app) as client:
     url=f'/api/projects/{p["id"]}/audio/guitar?v=old'
     first=client.get(url);expected=first.content
     storage.update_project(p['id'],stems=[{'name':'guitar','file':'new/guitar.wav'}],audio_revision='new')
     pinned=client.get(url,headers={'Range':'bytes=0-255','If-Range':first.headers['etag']})
     self.assertEqual(pinned.status_code,206)
     self.assertEqual(pinned.content,expected[:256])
     self.assertNotEqual(client.get(f'/api/projects/{p["id"]}/audio/guitar?v=new').content,expected)
     storage.update_project(p['id'],stems=[{'name':'guitar_lead','file':'new/guitar.wav'}],audio_revision='split')
     self.assertEqual(client.get(url).content,expected)
     self.assertEqual(client.get(f'/api/projects/{p["id"]}/audio/guitar?v=missing').status_code,404)

if __name__=='__main__':unittest.main()
