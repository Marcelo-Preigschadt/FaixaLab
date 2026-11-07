"""Inspectable chord inference: harmonic chroma, musical templates and Viterbi."""
import numpy as np

NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
QUALITIES = {'': [0, 4, 7], 'm': [0, 3, 7], '7': [0, 4, 7, 10],
             'maj7': [0, 4, 7, 11], 'm7': [0, 3, 7, 10]}


def decode_chroma(chroma, times, duration):
    states, templates = [], []
    for root in range(12):
        for suffix, intervals in QUALITIES.items():
            t = np.zeros(12)
            for interval in intervals:
                t[(root + interval) % 12] = 1.0 if interval != 0 else 1.15
            templates.append(t / np.linalg.norm(t))
            states.append(NOTES[root] + suffix)
    templates = np.array(templates)
    x = np.maximum(chroma - .35 * np.median(chroma, axis=0), 0)
    norms = np.linalg.norm(x, axis=0)
    unit = x / np.maximum(norms, 1e-9)
    scores = unit.T @ templates.T
    scores[:, [i for i, label in enumerate(states) if label.endswith('7')]] -= .025
    score = scores[0].copy()
    back = np.empty((len(times), len(states)), dtype=np.int16)
    transition = np.full((len(states), len(states)), -.12)
    np.fill_diagonal(transition, 0)
    for i in range(1, len(times)):
        candidates = score[:, None] + transition
        back[i] = np.argmax(candidates, axis=0)
        score = candidates[back[i], np.arange(len(states))] + scores[i]
    path = [int(np.argmax(score))]
    for i in range(len(times) - 1, 0, -1):
        path.append(int(back[i, path[-1]]))
    path.reverse()
    labels = [states[s] if norms[i] > 1e-5 and scores[i, s] > .45 else 'N' for i, s in enumerate(path)]
    events = []
    start = 0
    for i in range(1, len(labels) + 1):
        if i == len(labels) or labels[i] != labels[start]:
            end = float(times[i]) if i < len(times) else float(duration)
            events.append({'start': round(float(times[start]), 3), 'end': round(end, 3),
                           'label': labels[start], 'confidence': round(float(np.mean([scores[j, path[j]] for j in range(start, i)])), 3)})
            start = i
    # Brief boundary transients inherit a stable neighbour; no extra chord is invented.
    for i in range(1, len(events) - 1):
        e = events[i]
        if e['end'] - e['start'] < .35 and events[i - 1]['label'] == events[i + 1]['label']:
            e['label'] = events[i - 1]['label']
    merged = []
    for e in events:
        if merged and e['label'] == merged[-1]['label']:
            merged[-1]['end'] = e['end']
        else:
            merged.append(e.copy())
    return merged


def analyze(path, harmonic_paths=None):
    import librosa
    sr = 22050
    y, _ = librosa.load(path, sr=sr, mono=True)
    if harmonic_paths:
        harmonic = np.zeros_like(y)
        for p in harmonic_paths:
            track, _ = librosa.load(p, sr=sr, mono=True)
            n = min(len(track), len(harmonic))
            harmonic[:n] += track[:n]
        if np.max(np.abs(harmonic)) < 1e-5:
            harmonic = y
    else:
        harmonic = y
    duration = len(y) / sr
    if len(y) < 2048:
        return {'chords': [], 'key': None, 'bpm': None}
    hop = 4096
    c = librosa.feature.chroma_cqt(y=harmonic, sr=sr, hop_length=hop, bins_per_octave=36)
    times = librosa.frames_to_time(np.arange(c.shape[1]), sr=sr, hop_length=hop)
    events = decode_chroma(c, times, duration)
    energy = np.mean(c, axis=1)
    major = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
    minor = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
    estimates = []
    for root in range(12):
        for mode, profile in [('maior', major), ('menor', minor)]:
            corr = np.corrcoef(energy, np.roll(profile, root))[0, 1] if np.std(energy) > 1e-6 else 0
            estimates.append((float(corr), root, mode))
    confidence, root, mode = max(estimates)
    onset = librosa.onset.onset_strength(y=y, sr=sr)
    tempo = librosa.feature.tempo(onset_envelope=onset, sr=sr)
    bpm = round(float(np.asarray(tempo).flat[0]), 1) if np.any(onset > 1e-5) else None
    key = {'tonic': NOTES[root], 'mode': mode, 'label': NOTES[root] + ' ' + mode, 'confidence': round(confidence, 3)} if np.max(np.abs(y)) > 1e-5 else None
    return {'chords': events, 'key': key, 'bpm': bpm}
