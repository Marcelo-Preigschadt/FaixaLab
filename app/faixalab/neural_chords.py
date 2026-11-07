"""Pretrained BTC chord probabilities with overlapping, sample-timed context.

Architecture/checkpoints: Jonggwon Park, BTC-ISMIR19 (MIT), pinned in models/.
Only tensor/primitive checkpoints are shipped; runtime uses weights_only=True.
"""
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import numpy as np

SR = 22050
HOP = 2048
CONTEXT = 108
ROOTS = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
SUFFIXES = ['m', '', 'dim', 'aug', 'm6', '6', 'm7', 'mMaj7', 'maj7', '7',
            'dim7', 'm7b5', 'sus2', 'sus4']
LABELS = [root + suffix for root in ROOTS for suffix in SUFFIXES] + ['N', 'N']
MODEL_DIR = Path(__file__).parent / 'models'


@lru_cache(maxsize=2)
def load_model(classes):
    import torch
    from .vendor.btc.btc_model import BTC_model
    metadata = json.loads((MODEL_DIR / 'btc_metadata.json').read_text('utf-8'))
    entry = next(item for item in metadata['models'] if item['classes'] == classes)
    path = MODEL_DIR / entry['file']
    if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
        raise RuntimeError('O modelo de acordes está incompleto. Extraia novamente o pacote do FaixaLab.')
    checkpoint = torch.load(path, map_location='cpu', weights_only=True)
    model = BTC_model({**metadata['architecture'], 'num_chords': classes})
    model.load_state_dict(checkpoint['model'], strict=True)
    model.eval()
    return model, float(checkpoint['mean']), float(checkpoint['std'])


def probabilities(audio, cancel=None, progress=None, basic_weight=.15):
    import librosa
    import torch
    from .media import Cancelled
    torch.set_num_threads(min(4, torch.get_num_threads()))
    # Match training's logarithmic CQT, while keeping the actual hop/sample rate.
    cqt = librosa.cqt(y=audio, sr=SR, hop_length=HOP, n_bins=144,
                      bins_per_octave=24, tuning=0)
    features = np.log(np.abs(cqt).T + 1e-6).astype('float32')
    count = len(features)
    starts = list(range(0, max(1, count - CONTEXT + 1), CONTEXT // 2))
    if count > CONTEXT and starts[-1] != count - CONTEXT:
        starts.append(count - CONTEXT)
    edge = np.maximum(.15, np.hanning(CONTEXT + 2)[1:-1]).astype('float32')
    outputs = []
    for model_index, classes in enumerate((170, 25)):
        model, mean, scale = load_model(classes)
        values = np.zeros((count, classes), dtype='float32')
        weights = np.zeros(count, dtype='float32')
        with torch.inference_mode():
            for batch_start in range(0, len(starts), 8):
                if cancel and cancel.is_set():
                    raise Cancelled()
                selected = starts[batch_start:batch_start + 8]
                windows = []
                for start in selected:
                    window = (features[start:start + CONTEXT] - mean) / scale
                    windows.append(np.pad(window, ((0, CONTEXT - len(window)), (0, 0))))
                x = torch.from_numpy(np.stack(windows))
                hidden, _ = model.self_attn_layers(x)
                predicted = model.output_layer.output_projection(hidden).softmax(-1).numpy()
                for start, probability in zip(selected, predicted):
                    n = min(CONTEXT, count - start)
                    values[start:start + n] += probability[:n] * edge[:n, None]
                    weights[start:start + n] += edge[:n]
                if progress:
                    progress('Reconhecendo os acordes no contexto da música',
                             78 + 6 * (model_index + (batch_start + len(selected)) / len(starts)))
        outputs.append(values / np.maximum(weights[:, None], 1e-8))
    rich, basic = outputs
    # The separately trained major/minor head steadies roots and thirds without
    # removing sevenths or suspensions supported by the rich recognizer.
    family = np.empty_like(rich)
    minor = {'m', 'm6', 'm7', 'mMaj7', 'dim', 'dim7', 'm7b5'}
    for root in range(12):
        for quality, suffix in enumerate(SUFFIXES):
            family[:, root * 14 + quality] = basic[:, root * 2 + int(suffix in minor)]
    family[:, 168:] = basic[:, 24, None]
    merged = np.maximum(rich, 1e-8) ** (1 - basic_weight) * np.maximum(family, 1e-8) ** basic_weight
    merged /= merged.sum(axis=1, keepdims=True)
    merged[:, 169] += merged[:, 168]  # X (undefined harmony) joins N.
    merged = np.delete(merged, 168, axis=1)
    return merged, np.arange(count) * HOP / SR, LABELS[:168] + ['N']


def duration_path(emission, minimum_frames, switch_penalty=2.8):
    """Semi-Markov MAP path; every harmonic segment must mature before a switch.

    N has one-frame minimum. There is no quantization of actual chord attacks.
    O(frames * states) time and memory, independent of the duration threshold.
    """
    frames, states = emission.shape
    minimum = max(1, min(int(minimum_frames), frames))
    lengths = np.full(states, minimum, dtype=int)
    lengths[-1] = 1
    prefix = np.vstack([np.zeros(states), np.cumsum(emission, axis=0)])
    value = np.full((frames, states), -np.inf)
    previous = np.full((frames, states), -1, dtype=np.int16)
    steps = np.ones((frames, states), dtype=np.int16)
    indexes = np.arange(states)
    for frame in range(frames):
        if frame:
            value[frame] = value[frame - 1] + emission[frame]
            previous[frame] = indexes
        for length in np.unique(lengths):
            selected = indexes[lengths == length]
            origin = frame - length
            if origin < -1:
                continue
            block = prefix[frame + 1, selected] - prefix[frame + 1 - length, selected]
            if origin == -1:
                candidate = block
                parents = np.full(len(selected), -1)
            else:
                ranking = np.argsort(value[origin])[-2:]
                parents = np.where(selected == ranking[-1], ranking[-2], ranking[-1])
                candidate = value[origin, parents] + block - switch_penalty
            better = candidate > value[frame, selected]
            chosen = selected[better]
            value[frame, chosen] = candidate[better]
            previous[frame, chosen] = parents[better]
            steps[frame, chosen] = length
    path = np.empty(frames, dtype=np.int16)
    frame, state = frames - 1, int(np.argmax(value[-1]))
    while frame >= 0:
        length = int(steps[frame, state])
        path[frame - length + 1:frame + 1] = state
        state, frame = int(previous[frame, state]), frame - length
    return path


def decode(probability, times, labels, duration, energy=None, minimum_seconds=0):
    from scipy.ndimage import median_filter
    p = probability.copy()
    if energy is not None:
        level = np.interp(times, energy[0], energy[1])
        silence = level < max(2e-5, float(np.max(level)) * .015)
        p[silence] = 1e-8
        p[silence, -1] = 1
    p = median_filter(p, size=(3, 1), mode='nearest')
    emission = np.log(np.maximum(p, 1e-8))
    frames, states = emission.shape
    if minimum_seconds and frames > 1:
        hop = float(np.median(np.diff(times)))
        path = duration_path(emission, int(np.ceil(minimum_seconds / hop)))
    else:
        back = np.zeros((frames, states), dtype=np.int16)
        value = emission[0].copy()
        for frame in range(1, frames):
            best = int(np.argmax(value))
            switch = value[best] - 2.2
            stay = value >= switch
            back[frame] = np.where(stay, np.arange(states), best)
            value = np.where(stay, value, switch) + emission[frame]
        path = np.empty(frames, dtype=np.int16)
        path[-1] = np.argmax(value)
        for frame in range(frames - 1, 0, -1):
            path[frame - 1] = back[frame, path[frame]]
    events = []
    start = 0
    for frame in range(1, frames + 1):
        if frame == frames or path[frame] != path[start]:
            end = min(duration, float(times[frame])) if frame < frames else duration
            if end > float(times[start]):
                events.append({'start': round(float(times[start]), 3), 'end': round(end, 3),
                               'label': labels[path[start]],
                               'confidence': round(float(np.mean(probability[start:frame, path[start]])), 3)})
            start = frame
    return events
