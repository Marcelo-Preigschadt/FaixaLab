"""General lead-guitar presence: learned role evidence + local source prominence.

MERT classifies five-second contexts. Neither detected notes, lack of vocals,
song position nor a project's title are a solo detector. Classification must
agree with a foreground lead estimate; hysteresis follows the local audio to
retain phrase boundaries and rests without opening the entire stem.
"""
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import math
import os
import uuid
import numpy as np

from .media import Cancelled

VERSION = '0.6.0'
SR = 24000
WINDOW = 120000
PAD = 320
STEP = .1
MODEL_DIR = Path(__file__).parent / 'models'


def check_cancel(cancel):
    if cancel and cancel.is_set():
        raise Cancelled()


@lru_cache(maxsize=1)
def load_model():
    import onnxruntime as ort
    path = MODEL_DIR / 'solo_presence.onnx'
    meta = json.loads((MODEL_DIR / 'solo_presence_metadata.json').read_text('utf-8'))
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    if digest.hexdigest() != meta['sha256']:
        raise RuntimeError('O detector de solos está incompleto. Extraia novamente o pacote.')
    settings = ort.SessionOptions()
    settings.intra_op_num_threads = max(1,min(4,int(os.environ.get('FAIXALAB_CPU_THREADS',os.cpu_count() or 1))))
    settings.inter_op_num_threads = 1
    settings.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    return ort.InferenceSession(str(path), settings, providers=['CPUExecutionProvider'])


def read_audio(path):
    import soundfile as sf
    from scipy.signal import resample_poly
    data, sr = sf.read(path, dtype='float32', always_2d=True)
    if not np.isfinite(data).all():
        raise ValueError('A faixa contém amostras de áudio inválidas.')
    data = data.mean(axis=1)
    if sr != SR:
        divisor = math.gcd(sr, SR)
        data = resample_poly(data, SR // divisor, sr // divisor)
    return data.astype('float32')


def align(data, length):
    return np.pad(data[:length], (0, max(0, length - len(data))))


def power_envelope(audio):
    """100 ms grid; centred 500 ms energy, in absolute mixture gain."""
    from scipy.ndimage import uniform_filter1d
    hop = round(SR * STEP)
    count = max(1, math.ceil(len(audio) / hop))
    padded = np.pad(audio, (0, count * hop - len(audio)))
    energy = np.mean(padded.reshape(count, hop) ** 2, axis=1)
    energy = uniform_filter1d(energy, size=5, mode='constant')
    return energy.astype('float32')


def classify(mixture, lead, cancel=None, report=None, candidates=None):
    """Two views; raw mixture is the original classifier's training domain.

    The isolated view supports (or vetoes) the mixture prediction. It cannot
    create a solo by itself: an isolated rhythm guitar can sound like a solo
    recording even though its role in the arrangement is accompaniment.
    """
    centers = np.arange(0, len(lead) / SR, 1., dtype='float32')
    if candidates is None:candidates=np.ones(len(centers),dtype=bool)
    if len(candidates)!=len(centers):raise ValueError('Invalid solo context mask')
    session = load_model() if np.any(candidates) else None
    probabilities = np.zeros((len(centers), 2), dtype='float32')
    for index, center in enumerate(centers):
        check_cancel(cancel)
        if not candidates[index]:continue
        start = round((float(center) - 2.5) * SR)
        end = start + WINDOW
        for view, audio in enumerate((mixture, lead)):
            chunk = audio[max(0, start):min(len(audio), end)]
            chunk = np.pad(chunk, (max(0, -start), max(0, end - len(audio)) + PAD))
            logits = session.run(['logits'], {'audio': chunk[None].astype('float32')})[0][0]
            delta = float(np.clip(logits[0] - logits[1], -60, 60))
            probabilities[index, view] = 1 / (1 + math.exp(delta))
        if report:
            report('Localizando solos · contexto %d/%d' % (index + 1, len(centers)),
                   .04 + .54 * (index + 1) / max(1, len(centers)))
    return centers, probabilities


def source_evidence(lead, rhythm, mixture, identity=None):
    """The unconditional audio requirements shared by gating and decoding."""
    lead_power=power_envelope(lead)
    rhythm_power=power_envelope(rhythm)
    mix_power=power_envelope(mixture)
    times=(np.arange(len(lead_power))+.5)*STEP
    role=lead_power/np.maximum(lead_power+rhythm_power,1e-12)
    relative=lead_power/np.maximum(mix_power,1e-12)
    floor=max(4e-10,float(np.percentile(lead_power,95))*1e-4)
    active=lead_power>floor
    is_guitar=np.ones(len(times),dtype=bool)
    if identity is not None:
        identity_times,confirmed=identity
        is_guitar=np.interp(times,identity_times,confirmed.astype('float32'))>=.6
    return times,active,role,relative,is_guitar


def context_candidates(lead, rhythm, mixture, identity=None):
    """Skip only contexts unable to affect any valid source-supported frame.

    The decoder spreads three adjacent 1 s contexts, then interpolates. A
    probability can therefore affect frames at most 2 s from its centre. The
    extra 100 ms margin includes floating-point/grid boundaries. Both semantic
    views still run for every context which can affect an accepted frame.
    """
    times,active,role,relative,is_guitar=source_evidence(lead,rhythm,mixture,identity)
    possible=active&(role>=.55)&(relative>=.008)&is_guitar
    prefix=np.r_[0,np.cumsum(possible)]
    centers=np.arange(0,len(lead)/SR,1.,dtype='float32')
    first=np.searchsorted(times,centers-2.1,side='left')
    last=np.searchsorted(times,centers+2.1,side='right')
    return prefix[last]>prefix[first]


def _runs(mask):
    changes = np.diff(np.pad(mask.astype('int8'), (1, 1)))
    return list(zip(np.flatnonzero(changes == 1), np.flatnonzero(changes == -1)))


def decode_sections(centers, probabilities, lead, rhythm, mixture, identity=None):
    """Fixed global operating point; no track-specific thresholds or timestamps."""
    from scipy.ndimage import maximum_filter1d
    times,active,role,relative,is_guitar=source_evidence(lead,rhythm,mixture,identity)
    # Allow one adjacent analysis context to confirm a sustained phrase. Its
    # actual edges still require local lead energy, not the five-second window.
    spread = maximum_filter1d(probabilities, size=3, axis=0, mode='nearest')
    mixed_score = np.interp(times, centers, spread[:, 0])
    lead_score = np.interp(times, centers, spread[:, 1])
    support = active & (role >= .55) & (relative >= .008)
    support &= (lead_score >= .35) | (mixed_score >= .7)
    anchors = active & (role >= .78) & (relative >= .015)
    anchors &= (lead_score >= .7) & (mixed_score >= .5)
    if identity is not None:
        support &= is_guitar
        anchors &= is_guitar
    # Fill bounded phrase rests up to approximately one inference stride;
    # never extend across an unbounded beginning
    # or ending, and never substitute the complete song if no anchor exists.
    for first, last in _runs(~support):
        if first > 0 and last < len(support) and (last - first) * STEP <= 1.2:
            support[first:last] = True
    if identity is not None:
        # Do not bridge a phrase through an explicitly non-guitar instrument.
        support &= is_guitar
    sections = []
    duration = len(lead) / SR
    for first, last in _runs(support):
        if (last - first) * STEP < 2. or np.sum(anchors[first:last]) * STEP < .6:
            continue
        start, end = max(0., first * STEP), min(duration, last * STEP)
        sections.append({
            'start': round(start, 4), 'end': round(end, 4),
            # This is evidence, not a calibrated probability of correctness.
            'evidence': round(float(np.max(np.minimum(mixed_score[first:last], lead_score[first:last]))), 3),
            'lead_share': round(float(np.median(role[first:last])), 3),
        })
    return sections


def _signature(paths, revision):
    files = []
    for name, path in sorted(paths.items()):
        path = Path(path)
        if path.is_file():
            stat = path.stat()
            files.append([name, str(path.resolve()), stat.st_size, stat.st_mtime_ns])
    policy_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    model_hash = json.loads((MODEL_DIR / 'solo_presence_metadata.json').read_text('utf-8'))['sha256']
    identity_hash=json.loads((MODEL_DIR/'instrument_id_metadata.json').read_text('utf-8'))['sha256']
    identity_policy=hashlib.sha256((Path(__file__).parent/'instrument_id.py').read_bytes()).hexdigest()
    return hashlib.sha256(json.dumps([VERSION, policy_hash, model_hash, identity_hash, identity_policy, revision, files]).encode()).hexdigest()


def detect(lead_path, context, cancel=None, report=None, cache_path=None, revision='original'):
    paths = {name: Path(path) for name, path in (context or {}).items() if Path(path).is_file()}
    paths['guitar_lead'] = Path(lead_path)
    if 'guitar_rhythm' not in paths:
        raise ValueError('A detecção de solos precisa das faixas solo e base do projeto. Para transcrever uma faixa isolada, escolha Faixa inteira.')
    signature = _signature(paths, revision)
    if cache_path:
        try:
            cached = json.loads(Path(cache_path).read_text('utf-8'))
            if cached.get('signature') == signature:
                check_cancel(cancel)
                if report:
                    report('Trechos de solo recuperados da análise desta faixa', .58)
                return cached['result']
        except (OSError, ValueError, KeyError):
            pass
    check_cancel(cancel)
    if report:
        report('Preparando detecção de guitarra em primeiro plano', .01)
    lead = read_audio(lead_path)
    rhythm = align(read_audio(paths['guitar_rhythm']), len(lead))
    if not len(lead):
        raise ValueError('A faixa de guitarra está vazia.')
    if 'original' in paths:
        mixture = align(read_audio(paths['original']), len(lead))
    else:
        # Project exports contain stems rather than original.wav. Their sum
        # reconstructs the mixture because separation is mixture-consistent.
        mixture = lead + rhythm
        others = [name for name in paths if name not in {'original','guitar_lead','guitar_rhythm'}]
        if not others:
            raise ValueError('A detecção de solos precisa do áudio original ou das demais faixas do projeto.')
        for name in others:
            check_cancel(cancel)
            mixture += align(read_audio(paths[name]), len(lead))
    from .instrument_id import analyze as identify, guitar_evidence, summary as identity_summary
    if report:report('Conferindo se a fonte é guitarra ou violão',.03)
    identity_times,identity_scores,identity_labels=identify(lead_path,cancel)
    identity_times,confirmed,parts=guitar_evidence(identity_times,identity_scores,identity_labels)
    timbre={'model':'EfficientAT MN10 AudioSet ONNX','top':identity_summary(identity_times,identity_scores,identity_labels,10),
            'guitar_confirmed_contexts':int(confirmed.sum()),'contexts':len(confirmed),
            'scores':[{'time':round(float(t),3),'guitar':round(float(g),4),'reeds':round(float(r),4),'other':round(float(o),4),'confirmed':bool(c)}
                      for t,g,r,o,c in zip(identity_times,parts['guitar'],parts['reeds'],parts['other'],confirmed)]}
    if np.max(np.abs(lead)) < 2e-5 or not np.any(confirmed):
        centers, probabilities = np.array([0.]), np.zeros((1, 2), dtype='float32')
        candidates=np.zeros(1,dtype=bool)
        sections = []
    else:
        candidates=context_candidates(lead,rhythm,mixture,(identity_times,confirmed))
        centers, probabilities = classify(mixture, lead, cancel, report,candidates)
        check_cancel(cancel)
        sections = decode_sections(centers, probabilities, lead, rhythm, mixture,(identity_times,confirmed))
    result = {
        'version': VERSION, 'engine': 'MERT guitar-role contexts + source-prominence hysteresis',
        'sections': sections, 'duration': round(len(lead) / SR, 4),
        'analyzed_seconds': round(len(lead) / SR, 4),
        'solo_seconds': round(sum(s['end'] - s['start'] for s in sections), 4),
        'context_seconds': 5, 'stride_seconds': 1,
        'contexts_evaluated':int(candidates.sum()),'contexts_total':len(candidates),
        'instrument_identity':timbre,
        'scores': [{'time': float(t), 'mix': round(float(p[0]), 5), 'lead': round(float(p[1]), 5)}
                   for t, p in zip(centers, probabilities)],
    }
    if cache_path:
        check_cancel(cancel)
        path = Path(cache_path)
        temporary = path.with_suffix('.' + uuid.uuid4().hex + '.tmp')
        try:
            temporary.write_text(json.dumps({'signature': signature, 'result': result}), 'utf-8')
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    return result
