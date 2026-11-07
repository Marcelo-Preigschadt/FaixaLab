"""Reproduce the shipped local ONNX model (development, not the installer).

Python 3.12; torch==2.5.1 CPU; transformers==4.44.2; onnx==1.17.0;
onnxruntime==1.20.1. Usage: python tools/build_solo_detector.py checkpoint.ckpt
Download/checkpoint revision and original SHA256: solo_presence_metadata.json.
"""
import argparse
import hashlib
import json
from pathlib import Path
import torch
from torch import nn
from onnxruntime.quantization import quantize_dynamic, QuantType
from solo_detector_source.configuration_MERT import MERTConfig
from solo_detector_source.modeling_MERT import MERTModel

ROOT = Path(__file__).resolve().parents[1]


class CheckpointConfig(dict):
    """Data-only replacement for the original checkpoint's mlconfig metadata."""


CheckpointConfig.__module__ = 'mlconfig.config'
CheckpointConfig.__name__ = CheckpointConfig.__qualname__ = 'Config'


class Detector(nn.Module):
    def __init__(self):
        super().__init__()
        config = json.loads((Path(__file__).parent/'solo_detector_source/config.json').read_text())
        self.mert = MERTModel(MERTConfig(**config))
        self.inst_cls_head = nn.Linear(768, 2)

    def forward(self, audio):
        return self.inst_cls_head(self.mert(audio).last_hidden_state.mean(dim=1))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('checkpoint', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT/'faixalab/models/solo_presence.onnx')
    args = parser.parse_args()
    meta = json.loads((ROOT/'faixalab/models/solo_presence_metadata.json').read_text())
    digest = hashlib.sha256()
    with args.checkpoint.open('rb') as source:
        for block in iter(lambda: source.read(1024*1024), b''):
            digest.update(block)
    if digest.hexdigest() != meta['checkpoint_sha256']:
        raise ValueError('Checkpoint SHA256 mismatch')
    torch.set_num_threads(4)
    with torch.serialization.safe_globals([CheckpointConfig]):
        checkpoint = torch.load(args.checkpoint, map_location='cpu', weights_only=True, mmap=True)
    model = Detector().eval()
    model.load_state_dict({k.removeprefix('model.'): v for k, v in checkpoint['state_dict'].items()}, strict=True)
    float_path = args.output.with_name('solo_presence_float.onnx')
    torch.onnx.export(model, torch.zeros((1,120320)), str(float_path),
                      input_names=['audio'], output_names=['logits'], opset_version=17,
                      do_constant_folding=True)
    quantize_dynamic(str(float_path), str(args.output), per_channel=True,
                     weight_type=QuantType.QInt8, op_types_to_quantize=['MatMul','Gemm'])
    print('Verify on representative audio before replacing metadata:',
          hashlib.sha256(args.output.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
