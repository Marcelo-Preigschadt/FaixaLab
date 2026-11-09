"""Local neural separation of simultaneous lead and rhythm guitar."""
from pathlib import Path
import argparse
import hashlib
import json
import urllib.request
import uuid

MODEL_URL = ('https://huggingface.co/noblebarkrr/mvsepless_resources/resolve/main/'
             'mel_band_roformer/mbr_lead_rhythm_guitar_listra92.ckpt')
MODEL_SHA256 = 'b3c47bca33609ca1ba0bb2d2076410bfd1eb941b051b72afc1f3e24d12b17eef'
DRY_URL = ('https://huggingface.co/noblebarkrr/mvsepless_resources/resolve/main/'
           'htdemucs/demucs4_lead_rhythm_guitar_drypaint.ckpt')
DRY_SHA256 = '946ffd50d7f2fd87e447d880525283e88bd9061e1b428d4f1d380e764d54d618'


def digest(path):
    checksum = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            checksum.update(block)
    return checksum.hexdigest()


def checkpoint(cache, report=None, method='listra'):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / ('drypaint_lead_rhythm.ckpt' if method == 'drypaint' else 'lead_rhythm_listra92.ckpt')
    url, checksum = (DRY_URL, DRY_SHA256) if method == 'drypaint' else (MODEL_URL, MODEL_SHA256)
    if target.is_file() and digest(target) == checksum:
        return target
    temporary = target.with_suffix('.' + uuid.uuid4().hex + '.part')
    try:
        with urllib.request.urlopen(url, timeout=30) as response, temporary.open('wb') as dest:
            total = int(response.headers.get('Content-Length', 109822623 if method == 'drypaint' else 337073664))
            received = 0
            while block := response.read(1024 * 1024):
                dest.write(block)
                received += len(block)
                if report:
                    report(min(.15, .15 * received / max(total, 1)),
                           'Baixando o modelo de guitarra solo e base — primeiro uso')
        if digest(temporary) != checksum:
            raise RuntimeError('O download do modelo de guitarras está incompleto. Tente novamente.')
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def split(mix, cache, device='cpu', report=None, method='drypaint'):
    import numpy as np
    import torch
    from .vendor.roformer.mel_band_roformer import MelBandRoformer
    if mix.ndim != 2 or mix.shape[1] != 2 or not len(mix) or not np.isfinite(mix).all():
        raise ValueError('A guitarra precisa ser um áudio estéreo válido a 44.100 Hz.')
    if method == 'drypaint':
        return split_drypaint(mix, cache, device, report)
    weights = checkpoint(cache, report)
    config = json.loads((Path(__file__).parent / 'vendor/roformer/lead_rhythm.json').read_text('utf-8'))
    config['multi_stft_resolutions_window_sizes'] = tuple(config['multi_stft_resolutions_window_sizes'])
    from .compute import configure_torch
    configure_torch()
    torch.manual_seed(42)
    model = MelBandRoformer(**config)
    model.load_state_dict(torch.load(weights, map_location='cpu', weights_only=True), strict=True)
    model = model.eval().to(device)
    chunk, step, fade = 132300, 66150, 13230
    length = len(mix)
    audio = torch.from_numpy(mix.T.copy())
    padded = length > 2 * step
    if padded:
        audio = torch.nn.functional.pad(audio, (step, step), mode='reflect')
    result = torch.zeros_like(audio)
    counter = torch.zeros(audio.shape[-1])
    window = torch.ones(chunk)
    window[:fade] = torch.linspace(0, 1, fade)
    window[-fade:] = torch.linspace(1, 0, fade)
    with torch.inference_mode():
        for start in range(0, audio.shape[-1], step):
            part = audio[:, start:start + chunk]
            size = part.shape[-1]
            part = torch.nn.functional.pad(part, (0, chunk - size),
                                           mode='reflect' if size > chunk // 2 else 'constant')
            predicted = model(part[None].to(device))[0, ..., :size].cpu()
            blend = window.clone()
            if start == 0:
                blend[:fade] = 1
            if start + step >= audio.shape[-1]:
                blend[-fade:] = 1
            result[:, start:start + size] += predicted * blend[:size]
            counter[start:start + size] += blend[:size]
            if report:
                report(.15 + .85 * min(1, (start + step) / audio.shape[-1]),
                       'Separando guitarra solo e guitarra base')
        result /= counter.clamp_min(1e-8)
    if padded:
        result = result[:, step:-step]
    lead = result.numpy().T
    if lead.shape != mix.shape or not np.isfinite(lead).all():
        raise RuntimeError('O modelo não retornou guitarras válidas.')
    return lead, mix - lead


def split_drypaint(mix, cache, device='cpu', report=None):
    import numpy as np
    import torch
    from demucs.htdemucs import HTDemucs
    weights = checkpoint(cache, report, 'drypaint')
    config = json.loads((Path(__file__).parent / 'models/guitar_roles_config.json').read_text('utf-8'))
    from .compute import configure_torch
    configure_torch()
    model = HTDemucs(sources=['lead', 'rhythm'], audio_channels=2,
                     samplerate=44100, segment=3, **config)
    model.load_state_dict(torch.load(weights, map_location='cpu', weights_only=True), strict=True)
    model = model.eval().to(device)
    audio = torch.from_numpy(mix.T.copy())
    chunk, step = 132300, 66150
    result = torch.zeros(2, *audio.shape)
    count = torch.zeros(audio.shape[-1])
    # Training-matched 3 s windows, 50% overlap, no external normalization.
    with torch.inference_mode():
        for start in range(0, audio.shape[-1], step):
            part = audio[:, start:start + chunk]
            size = part.shape[-1]
            part = torch.nn.functional.pad(part, (0, chunk - size))
            prediction = model(part[None].to(device))[0, ..., :size].cpu()
            result[..., start:start + size] += prediction
            count[start:start + size] += 1
            if report:
                report(.15 + .85 * min(1, (start + step) / audio.shape[-1]),
                       'Separando guitarra solo e guitarra base')
    result /= count.clamp_min(1e-8)
    # Least-squares mixture consistency uses both learned role estimates.
    lead = (.5 * (result[0] + audio - result[1])).numpy().T
    if lead.shape != mix.shape or not np.isfinite(lead).all():
        raise RuntimeError('O modelo de guitarras retornou áudio inválido.')
    return lead, mix - lead


def main():
    import soundfile as sf
    parser = argparse.ArgumentParser()
    parser.add_argument('source')
    parser.add_argument('output')
    parser.add_argument('--cache', required=True)
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    parser.add_argument('--model', choices=['drypaint', 'listra'], default='drypaint')
    args = parser.parse_args()
    mix, sr = sf.read(args.source, dtype='float32', always_2d=True)
    if sr != 44100:
        raise ValueError('O áudio precisa estar a 44.100 Hz.')
    def report(fraction, stage):
        print('FAIXALAB_GUITARS ' + json.dumps({'fraction': fraction, 'stage': stage}), flush=True)
    lead, rhythm = split(mix, args.cache, args.device, report, args.model)
    output = Path(args.output)
    output.mkdir(exist_ok=True, parents=True)
    for name, data in [('guitar_lead', lead), ('guitar_rhythm', rhythm)]:
        sf.write(output / (name + '.wav'), data, sr, subtype='FLOAT')
    (output / 'engine.json').write_text(json.dumps({'model': 'HTDemucs Lead/Rhythm Dry Paint' if args.model == 'drypaint' else 'Mel-Band RoFormer listra92',
        'sha256': DRY_SHA256 if args.model == 'drypaint' else MODEL_SHA256,
        'stems': ['guitar_lead', 'guitar_rhythm'], 'overlap': .5, 'experimental': True}), 'utf-8')


if __name__ == '__main__':
    main()
