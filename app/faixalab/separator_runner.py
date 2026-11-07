"""Demucs workers: tuned ensemble, harmonic refinement, shared-gain WAVs."""
import argparse
import gc
import json
from pathlib import Path
import random
import torch
import soundfile as sf
from demucs.pretrained import get_model
from demucs.apply import apply_model, BagOfModels


class ProgressPool:
    """Demucs' serial, lazy executor, with progress after each actual window.

    apply_model submits all overlap-add windows before requesting their results.
    Keeping this contract preserves its padding, shifts and reconstruction.
    """
    def __init__(self, report):
        self.report, self.total, self.completed = report, 0, 0

    def submit(self, function, *args, **kwargs):
        self.total += 1
        owner = self

        class Result:
            def result(self):
                owner.report(owner.completed / owner.total,
                             f'trecho {owner.completed + 1}/{owner.total}')
                value = function(*args, **kwargs)
                owner.completed += 1
                owner.report(owner.completed / owner.total,
                             f'{owner.completed}/{owner.total} trechos concluídos')
                return value

        return Result()


def infer(audio, name, device, shifts, overlap, report=None):
    model = get_model(name).eval()
    reference = audio.mean(0)
    mean, scale = reference.mean(), reference.std().clamp_min(1e-8)
    normalized = ((audio - mean) / scale)[None]
    with torch.inference_mode():
        members = list(zip(model.models, model.weights)) if isinstance(model, BagOfModels) else [(model, [1] * len(model.sources))]
        prediction = torch.zeros(len(model.sources), *audio.shape)
        weights = torch.zeros(len(model.sources))
        for index, (member, gains) in enumerate(members):
            def chunk_progress(fraction, text):
                if report:
                    title = f'Refinando instrumentos — etapa {index + 1}/{len(members)}' if len(members) > 1 else 'Separando instrumentos'
                    report((index + fraction) / len(members),
                           f'{title} · {text}')
            pool = ProgressPool(chunk_progress)
            out = apply_model(member, normalized, device=device, shifts=shifts,
                              split=True, overlap=overlap, segment=7,
                              progress=False, num_workers=0, pool=pool)[0].cpu()
            gains = torch.tensor(gains)
            prediction += out * gains[:, None, None]
            weights += gains
            member.to('cpu')
        prediction /= weights[:, None, None]
        prediction = prediction * scale + mean
    sources = {source: prediction[i] for i, source in enumerate(model.sources)}
    del model
    gc.collect()
    if device == 'cuda':
        torch.cuda.empty_cache()
    return sources


def separate(audio, stems=6, quality='quality', device='cpu', report=None):
    random.seed(2026)
    torch.manual_seed(2026)
    shifts = 0 if quality == 'fast' else 1
    overlap = .25 if quality == 'fast' else .5
    if quality == 'quality':
        primary = infer(audio, 'htdemucs_ft', device, shifts, overlap,
                        lambda fraction, text: report(fraction * (.8 if stems == 6 else 1), text) if report else None)
        if stems == 6:
            if report:
                report(.8, 'Isolando guitarra e piano do acompanhamento limpo')
            harmonic = audio - primary['vocals'] - primary['drums'] - primary['bass']
            extra = infer(harmonic, 'htdemucs_6s', device, shifts, overlap,
                          lambda fraction, text: report(.8 + .2 * fraction, text) if report else None)
            primary['guitar'], primary['piano'] = extra['guitar'], extra['piano']
        model_name = 'htdemucs_ft + htdemucs_6s' if stems == 6 else 'htdemucs_ft'
    else:
        name = 'htdemucs_6s' if stems == 6 else 'htdemucs'
        primary = infer(audio, name, device, shifts, overlap, report)
        model_name = name
    # Preserve each original sample and relative gain. Put the reconstruction
    # residual in Other, rather than injecting it into isolated target sources.
    primary['other'] = audio - sum(value for key, value in primary.items() if key != 'other')
    return primary, {'model': model_name, 'quality': quality, 'overlap': overlap,
                     'shifts': shifts, 'mixture_consistent': True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('audio')
    parser.add_argument('output')
    parser.add_argument('--stems', type=int, choices=[4, 6], default=6)
    parser.add_argument('--quality', choices=['fast', 'balanced', 'quality'], default='quality')
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    args = parser.parse_args()
    torch.set_num_threads(min(4, torch.get_num_threads()))
    data, sr = sf.read(args.audio, dtype='float32', always_2d=True)
    if sr != 44100 or data.shape[1] != 2:
        raise ValueError('O áudio precisa estar em estéreo, a 44.100 Hz.')
    def report(fraction, stage):
        print('FAIXALAB_PROGRESS ' + json.dumps({'fraction': fraction, 'stage': stage}), flush=True)
    sources, metadata = separate(torch.from_numpy(data.T.copy()), args.stems, args.quality, args.device, report)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    for name, stem in sources.items():
        sf.write(out / (name + '.wav'), stem.numpy().T, sr, subtype='FLOAT')
    (out / 'engine.json').write_text(json.dumps(metadata, indent=2), 'utf-8')
    print('FAIXALAB_SEPARATION_COMPLETE', flush=True)


if __name__ == '__main__':
    main()
