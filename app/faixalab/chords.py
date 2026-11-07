"""Inspectable chord inference: harmonic chroma, musical templates and Viterbi."""
import numpy as np
import re

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


def preserve_manual(events, previous):
    """Overlay the user's corrected intervals without discarding new analysis."""
    manual = [c for c in previous if c.get('edited')]
    pieces = []
    for event in events:
        remainder = [event.copy()]
        for fixed in manual:
            next_parts = []
            for part in remainder:
                if fixed['end'] <= part['start'] or fixed['start'] >= part['end']:
                    next_parts.append(part)
                else:
                    if part['start'] < fixed['start']:
                        next_parts.append({**part, 'end': fixed['start']})
                    if part['end'] > fixed['end']:
                        next_parts.append({**part, 'start': fixed['end']})
            remainder = next_parts
        pieces.extend(remainder)
    return sorted(pieces + manual, key=lambda c: (c['start'], c['end']))


def stabilize_events(events, probability, times, labels, minimum):
    """Suppress brief harmonic ornaments, retaining sustained chord changes."""
    events = [dict(e) for e in events]
    for _ in range(len(events)):
        changed = False
        for i, event in enumerate(events):
            if event['label'] == 'N' or event['end'] - event['start'] >= minimum:
                continue
            candidates = [events[j]['label'] for j in [i - 1, i + 1] if 0 <= j < len(events)]
            if not candidates:
                continue
            selected = (times >= event['start']) & (times < event['end'])
            if not selected.any():
                continue
            label = max(candidates, key=lambda c: float(probability[selected, labels.index(c)].mean()))
            if label != event['label']:
                event['label'] = label
                changed = True
        merged = []
        for event in events:
            if merged and event['label'] == merged[-1]['label']:
                merged[-1]['end'] = event['end']
                merged[-1]['confidence'] = min(merged[-1]['confidence'], event['confidence'])
            else:
                merged.append(event.copy())
        events = merged
        if not changed:
            break
    return events


def analyze(path, harmonic_paths=None, bass_path=None, cancel=None, progress=None,
            stability='stable', harmonic_weights=None):
    import librosa
    sr = 22050
    y, _ = librosa.load(path, sr=sr, mono=True)
    if harmonic_paths:
        harmonic = np.zeros_like(y)
        weights = harmonic_weights if harmonic_weights is not None else [1.] * len(harmonic_paths)
        if len(weights) != len(harmonic_paths):
            raise ValueError('Pesos do acompanhamento incompatíveis com as faixas.')
        for p, weight in zip(harmonic_paths, weights):
            track, _ = librosa.load(p, sr=sr, mono=True)
            n = min(len(track), len(harmonic))
            harmonic[:n] += float(weight) * track[:n]
    else:
        harmonic = y
    duration = len(y) / sr
    if len(y) < 2048:
        return {'chords': [], 'key': None, 'bpm': None}
    hop = 2048
    bass, _ = librosa.load(bass_path, sr=sr, mono=True) if bass_path else (harmonic, sr)
    pitch_audio = harmonic.copy()
    if bass_path:
        n = min(len(bass), len(pitch_audio))
        pitch_audio[:n] += .2 * bass[:n]
    c = librosa.feature.chroma_cqt(y=pitch_audio, sr=sr, hop_length=hop, bins_per_octave=36)
    bass_cqt = np.abs(librosa.cqt(y=bass, sr=sr, hop_length=hop,
                                 fmin=librosa.note_to_hz('C1'), n_bins=36, tuning=0))
    bass_chroma = bass_cqt[:12] + .5 * bass_cqt[12:24] + .25 * bass_cqt[24:36]
    bass_times = librosa.frames_to_time(np.arange(bass_chroma.shape[1]), sr=sr, hop_length=hop)
    times = librosa.frames_to_time(np.arange(c.shape[1]), sr=sr, hop_length=hop)
    from .neural_chords import probabilities, decode
    # Keep the full-song context learned by BTC. Spectral evidence from the
    # isolated accompaniment sharpens actual note changes and suppresses leakage.
    # The singer and lead-guitar melodies must never drive chord changes.
    probability, neural_times, labels = probabilities(pitch_audio, cancel, progress,
                                                     basic_weight=.35 if stability == 'stable' else .15)
    intervals = [[0, 3, 7], [0, 4, 7], [0, 3, 6], [0, 4, 8], [0, 3, 7, 9],
                 [0, 4, 7, 9], [0, 3, 7, 10], [0, 3, 7, 11], [0, 4, 7, 11],
                 [0, 4, 7, 10], [0, 3, 6, 9], [0, 3, 6, 10], [0, 2, 7], [0, 5, 7]]
    templates = []
    penalties = []
    for root in range(12):
        for notes in intervals:
            template = np.zeros(12)
            template[(root + np.asarray(notes)) % 12] = 1
            templates.append(template / np.linalg.norm(template))
            penalties.append(.035 if len(notes) > 3 else 0)
    whitened = np.maximum(c - .25 * np.median(c, axis=0), 0)
    whitened /= np.maximum(np.linalg.norm(whitened, axis=0), 1e-8)
    spectral = whitened.T @ np.asarray(templates).T - penalties
    spectral = np.column_stack([spectral, np.full(len(spectral), .3)])
    # CQT calls can differ by one padded frame; align by physical time.
    spectral = np.column_stack([np.interp(neural_times, times, spectral[:, i])
                                for i in range(spectral.shape[1])])
    logits = .5 * np.log(np.maximum(probability, 1e-8)) + .5 * 15 * spectral
    root_profile = bass_chroma / np.maximum(np.max(bass_chroma, axis=0), 1e-6)
    root_profile = np.column_stack([np.interp(neural_times, bass_times, row) for row in root_profile])
    logits[:, :168] += .45 * np.repeat(root_profile, 14, axis=1)
    if stability == 'stable':
        # Strong evidence is required for extra notes; a passing bass/melody
        # must not promote every triad to a sixth, seventh or suspension.
        complexity = [0, 0, .35, .35, .9, .9, .45, .9, .45, .35, .9, .6, .55, .55]
        logits[:, :168] -= np.tile(complexity, 12)
    combined = np.exp(logits - logits.max(axis=1, keepdims=True))
    combined /= combined.sum(axis=1, keepdims=True)
    onset = librosa.onset.onset_strength(y=y, sr=sr)
    tempo = librosa.feature.tempo(onset_envelope=onset, sr=sr)
    bpm = round(float(np.asarray(tempo).flat[0]), 1) if np.any(onset > 1e-5) else None
    if stability == 'stable':
        from scipy.ndimage import uniform_filter1d
        width = max(3, min(9, int(.7 * 60 / (bpm or 120) / (hop / sr)) | 1))
        combined = uniform_filter1d(combined, size=width, axis=0, mode='nearest')
    rms = librosa.feature.rms(y=harmonic, frame_length=4096, hop_length=hop)[0]
    rms_times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)
    minimum = min(1.2, max(.6, 2 * 60 / (bpm or 120))) if stability == 'stable' else 0
    events = decode(combined, neural_times, labels, duration, energy=(rms_times, rms),
                    minimum_seconds=minimum)
    if stability == 'stable':
        events = stabilize_events(events, combined, neural_times, labels, minimum)
    # Move only nearby transitions onto a real attack in the accompaniment.
    # Sustained changes without an attack keep their analysis timestamps.
    onset_envelope = librosa.onset.onset_strength(y=harmonic, sr=sr, hop_length=512)
    attacks = librosa.onset.onset_detect(onset_envelope=onset_envelope, sr=sr,
                                        hop_length=512, units='time')
    label_index = {label: i for i, label in enumerate(labels)}
    for i in range(1, len(events)):
        old, new = label_index[events[i - 1]['label']], label_index[events[i]['label']]
        choices = []
        for candidate in attacks[np.abs(attacks - events[i]['start']) <= .14]:
            margin = minimum if stability == 'stable' else .18
            if not events[i - 1]['start'] + margin < candidate < events[i]['end'] - margin:
                continue
            before = (neural_times >= candidate - .28) & (neural_times < candidate - .02)
            after = (neural_times > candidate + .02) & (neural_times <= candidate + .28)
            if not before.any() or not after.any():
                continue
            contrast = float(np.mean(spectral[before, old] - spectral[before, new]) +
                             np.mean(spectral[after, new] - spectral[after, old]))
            if contrast > .08:
                choices.append((contrast - .1 * abs(candidate - events[i]['start']), float(candidate)))
        if choices:
            candidate = max(choices)[1]
            events[i - 1]['end'] = events[i]['start'] = round(candidate, 3)
    if bass_path and stability == 'detailed':
        for event in events:
            match = re.fullmatch(r'([A-G]#?)(.*)', event['label'])
            if not match or event['end'] - event['start'] < .4:
                continue
            selected = (bass_times >= event['start'] + .08) & (bass_times < event['end'] - .05)
            if not selected.any():
                continue
            strength = np.median(bass_chroma[:, selected], axis=1)
            order = np.argsort(strength)
            note, runner_up = int(order[-1]), int(order[-2])
            root = NOTES.index(match[1])
            suffixes = ['m', '', 'dim', 'aug', 'm6', '6', 'm7', 'mMaj7', 'maj7', '7', 'dim7', 'm7b5', 'sus2', 'sus4']
            quality = suffixes.index(match[2])
            supported = (note - root) % 12 in intervals[quality]
            if (supported and note != root and strength[note] > .05 and
                    strength[note] / max(float(strength.sum()), 1e-8) > .5 and
                    strength[note] > 2 * strength[runner_up]):
                event['label'] += '/' + NOTES[note]
    energy = np.mean(c, axis=1)
    major = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
    minor = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
    estimates = []
    for root in range(12):
        for mode, profile in [('maior', major), ('menor', minor)]:
            corr = np.corrcoef(energy, np.roll(profile, root))[0, 1] if np.std(energy) > 1e-6 else 0
            estimates.append((float(corr), root, mode))
    confidence, root, mode = max(estimates)
    key = {'tonic': NOTES[root], 'mode': mode, 'label': NOTES[root] + ' ' + mode, 'confidence': round(confidence, 3)} if np.max(np.abs(y)) > 1e-5 else None
    return {'chords': events, 'key': key, 'bpm': bpm,
            'chord_analysis': {'engine': 'BTC + CQT + semi-Markov' if stability == 'stable' else 'BTC + CQT', 'version': '0.3.0',
                               'hop_seconds': round(hop / sr, 6),
                               'classes': 169, 'context_overlap': .5,
                               'source': 'instrumental_accompaniment' if harmonic_paths else 'input_audio',
                               'stability': stability,
                               'minimum_chord_seconds': round(minimum, 3),
                               'harmonic_weights': list(weights) if harmonic_paths else [],
                               'automatic_inversions': stability == 'detailed'}}
