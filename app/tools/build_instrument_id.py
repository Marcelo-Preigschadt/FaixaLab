"""Rebuild the packaged AudioSet CNN; development-only dependencies.

Python 3.12; torch==2.5.1 CPU; torchvision==0.20.1 CPU; torchaudio==2.5.1;
onnx==1.17.0. Usage: python tools/build_instrument_id.py mn10_as_mAP_471.pt
"""
from pathlib import Path
import argparse
import contextlib
import hashlib
import io
import json
import sys
import numpy as np
import torch
import torchaudio

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(Path(__file__).parent/'instrument_id_source'))
from models.mn.model import get_model


class Inference(torch.nn.Module):
    def __init__(self,model):super().__init__();self.model=model
    def forward(self,features):return self.model(features)[0]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('checkpoint',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'faixalab/models')
    args=parser.parse_args()
    meta=json.loads((ROOT/'faixalab/models/instrument_id_metadata.json').read_text('utf-8'))
    if hashlib.sha256(args.checkpoint.read_bytes()).hexdigest()!=meta['checkpoint_sha256']:
        raise ValueError('Checkpoint SHA256 mismatch')
    torch.set_num_threads(4)
    with contextlib.redirect_stdout(io.StringIO()):model=get_model(width_mult=1.,pretrained_name=None).eval()
    model.load_state_dict(torch.load(args.checkpoint,map_location='cpu',weights_only=True),strict=True)
    args.output.mkdir(exist_ok=True,parents=True)
    torch.onnx.export(Inference(model),torch.zeros((1,1,128,501)),str(args.output/'instrument_id.onnx'),
        input_names=['mel'],output_names=['logits'],dynamic_axes={'mel':{3:'frames'}},opset_version=17)
    mel,_=torchaudio.compliance.kaldi.get_mel_banks(128,1024,32000,0.,15000.,100.,-500.,1.)
    mel=torch.nn.functional.pad(mel,(0,1)).numpy()
    window=np.pad(np.hanning(800).astype('float32'),(112,112))
    np.savez_compressed(args.output/'instrument_id_frontend.npz',mel=mel,window=window)
    print('Compare inference outputs before updating metadata.',
          hashlib.sha256((args.output/'instrument_id.onnx').read_bytes()).hexdigest())


if __name__=='__main__':main()
