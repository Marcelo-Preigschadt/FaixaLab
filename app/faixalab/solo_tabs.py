"""Audio-derived lead notes, playable standard-tuning positions and tab jobs."""
from functools import lru_cache
from pathlib import Path
import hashlib
import io
import json
import math
import threading
import uuid
import numpy as np

from . import storage
from .media import Cancelled
from .solo_presence import VERSION

SR, HOP, WINDOW, OVERLAP = 22050, 256, 43844, 30
TUNING = (40, 45, 50, 55, 59, 64)  # E A D G B e, low to high
NAMES = ('C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B')
MODEL_DIR = Path(__file__).parent / 'models'
JOBS = {}
LOCK = threading.RLock()


def current(tab, project):
    return (tab.get('status') == 'ready' and tab.get('version') == VERSION
            and tab.get('source_revision', 'original') == (project.get('audio_revision') or 'original'))


def note_name(midi):
    return NAMES[midi % 12] + str(midi // 12 - 1)


@lru_cache(maxsize=1)
def load_model():
    import onnxruntime as ort
    path = MODEL_DIR / 'solo_notes.onnx'
    meta = json.loads((MODEL_DIR / 'solo_notes_metadata.json').read_text('utf-8'))
    if hashlib.sha256(path.read_bytes()).hexdigest() != meta['sha256']:
        raise RuntimeError('O modelo da tablatura está incompleto. Extraia novamente o pacote.')
    settings = ort.SessionOptions()
    settings.intra_op_num_threads = 2
    settings.inter_op_num_threads = 1
    settings.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    return ort.InferenceSession(str(path), settings, providers=['CPUExecutionProvider'])


def infer_activations(audio, cancel=None, report=None):
    """Overlap in physical sample time, avoiding accumulated window-time drift."""
    session = load_model()
    length = len(audio)
    front = OVERLAP * HOP // 2
    padded = np.pad(audio.astype('float32'), (front, 0))
    stride = WINDOW - OVERLAP * HOP
    offsets = list(range(0, len(padded), stride))
    count = int(np.ceil(length / HOP)) + 1
    sums = {name: np.zeros((count, width), dtype='float32')
            for name, width in [('note', 88), ('onset', 88)]}
    weights = np.zeros(count, dtype='float32')
    input_name = session.get_inputs()[0].name
    for index, offset in enumerate(offsets):
        if cancel and cancel.is_set():
            raise Cancelled()
        chunk = padded[offset:offset + WINDOW]
        chunk = np.pad(chunk, (0, WINDOW - len(chunk)))[None, :, None]
        outputs = session.run(['StatefulPartitionedCall:1', 'StatefulPartitionedCall:2'],
                              {input_name: chunk})
        # The model returns 172 frames for 43844 samples. Reconstruct using
        # actual window offsets rather than treating every window as 172 hops.
        rows = np.arange(OVERLAP // 2, outputs[0].shape[1] - OVERLAP // 2)
        physical = (offset - front) / HOP + rows
        first, last = max(0, math.ceil(physical[0])), min(count - 1, math.floor(physical[-1]))
        targets = np.arange(first, last + 1)
        if len(targets):
            for name, output in zip(('note', 'onset'), outputs):
                for pitch in range(88):
                    sums[name][targets, pitch] += np.interp(targets, physical, output[0, rows, pitch])
            weights[targets] += 1
        if report:
            report('Transcrevendo guitarra solo · trecho %d/%d' % (index + 1, len(offsets)),
                   .08 + .82 * (index + 1) / len(offsets))
    # Fractional boundaries leave at most one uncovered hop; interpolate that
    # boundary between neighbouring predictions, never append a fictitious note.
    known = np.flatnonzero(weights)
    for name, value in sums.items():
        value /= np.maximum(weights[:, None], 1)
        for pitch in range(88):
            value[:, pitch] = np.interp(np.arange(count), known, value[known, pitch])
    return sums


def limit_polyphony(notes, voices=1):
    """Retain the strongest simultaneous note hypotheses and their true attacks."""
    if not notes:
        return []
    boundaries = sorted({n['start'] for n in notes} | {n['end'] for n in notes})
    output, open_notes = [], {}
    ordered = sorted(enumerate(notes), key=lambda item: item[1]['start'])
    active, cursor = {}, 0
    for start, end in zip(boundaries, boundaries[1:]):
        active = {i: n for i, n in active.items() if n['end'] > start + 1e-6}
        while cursor < len(ordered) and ordered[cursor][1]['start'] <= start + 1e-6:
            i, note = ordered[cursor]
            if note['end'] > start:
                active[i] = note
            cursor += 1
        selected = sorted(active, key=lambda i: (active[i]['confidence'], active[i]['midi']), reverse=True)[:voices]
        for i in list(open_notes):
            if i not in selected:
                output.append(open_notes.pop(i))
        for i in selected:
            if i in open_notes:
                open_notes[i]['end'] = end
            else:
                open_notes[i] = {**active[i], 'start': start, 'end': end}
    output.extend(open_notes.values())
    return sorted([n for n in output if n['end'] - n['start'] >= .045], key=lambda n: (n['start'], n['midi']))


def assign_positions(notes, min_fret=0, max_fret=24):
    """Beam search over string/fret choices, continuity and ringing strings."""
    # cost, previous fret/string, active strings, linked chosen positions
    beam = [(0., 5, 4, {}, None)]
    fixed = [n for n in notes if n.get('edited') and n.get('string') is not None]
    for index, note in enumerate(notes):
        choices = [(s, note['midi'] - pitch) for s, pitch in enumerate(TUNING)
                   if min_fret <= note['midi'] - pitch <= max_fret]
        if note.get('edited') and note.get('string') is not None and TUNING[note['string']] + note['fret'] == note['midi']:
            choices = [(note['string'], note['fret'])]
        else:
            choices = [(s,f) for s,f in choices if not any(m['string']==s and m['start']<note['end']-.01 and m['end']>note['start']+.01 for m in fixed)]
        if not choices:
            choices = [(None, None)]
        candidates = []
        for cost, last_fret, last_string, held, link in beam:
            active = {s: v for s, v in held.items() if v[0] > note['start'] + .02}
            for string, fret in choices:
                if string is None:
                    candidates.append((cost + 20, last_fret, last_string, active, (link, index, None, None)))
                    continue
                if string in active:
                    continue
                sounding_frets = [value[1] for value in active.values() if value[1] > 0]
                spread = max(sounding_frets + [fret]) - min(sounding_frets + [fret]) if fret and sounding_frets else 0
                extra = .7 * abs(fret - last_fret) + .35 * abs(string - last_string)
                extra += .03 * fret + .04 * abs(fret - 7) + 3 * max(0, spread - 5)
                positions = {**active, string: (note['end'], fret)}
                candidates.append((cost + extra, fret, string, positions, (link, index, string, fret)))
        if not candidates:
            # Keep the detected pitch even when the requested region cannot
            # accommodate simultaneous notes. It is displayed as unmapped.
            candidates = [(b[0] + 20, b[1], b[2], b[3], (b[4], index, None, None)) for b in beam]
        candidates.sort(key=lambda item: item[0])
        beam, seen = [], set()
        for candidate in candidates:
            signature = (candidate[1], candidate[2], tuple(sorted((s, round(v[0], 2), v[1]) for s, v in candidate[3].items())))
            if signature not in seen:
                beam.append(candidate)
                seen.add(signature)
            if len(beam) >= 24:
                break
    result = [dict(n) for n in notes]
    link = min(beam, key=lambda b: b[0])[4]
    while link:
        previous, index, string, fret = link
        result[index].update(string=string, fret=fret)
        link = previous
    return result


def solo_texture(values, offset, section):
    """Reject a predominantly chordal bed before forcing one/two voices.

    Forcing polyphony=1 first would turn strummed chords into an invented
    melody. Evaluate the original multi-pitch evidence instead. Occasional
    chords and double stops in a melodic solo remain accepted.
    """
    times = offset + np.arange(len(values['note'])) * HOP / SR
    selected = (times >= section['start']) & (times < section['end'])
    pitches = values['note'][selected, 40-21:89-21]
    if not len(pitches):
        return {'accepted': False, 'reason': 'no_pitched_evidence', 'chord_fraction': 0., 'active_frames': 0}
    active = pitches.max(axis=1) >= .25
    polyphony = (pitches >= .25).sum(axis=1)
    fraction = float(np.mean(polyphony[active] >= 3)) if np.any(active) else 0.
    accepted = bool(np.sum(active) * HOP / SR >= .5 and fraction <= .55)
    return {'accepted': accepted, 'reason': '' if accepted else 'polyphonic_accompaniment' if fraction > .55 else 'no_pitched_evidence',
            'chord_fraction': round(fraction, 4), 'active_frames': int(np.sum(active))}


def note_cache_file(cache_path, source, revision, first, last, section, scope):
    if not cache_path:return None
    source=Path(source);stat=source.stat()
    model_hash=json.loads((MODEL_DIR/'solo_notes_metadata.json').read_text('utf-8'))['sha256']
    policy_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    key=hashlib.sha256(json.dumps([str(source.resolve()),stat.st_size,stat.st_mtime_ns,
        revision,model_hash,policy_hash,first,last,section['start'],section['end'],scope]).encode()).hexdigest()
    return Path(cache_path).parent/'solo_notes_cache'/(key+'.json')


def cached_pitch(path):
    if path is None:return None
    try:
        result=json.loads(path.read_text('utf-8'))
        rows=result['frames'];texture=result['texture']
        if not isinstance(rows,list) or any(len(row)!=4 or not all(math.isfinite(float(x)) for x in row) for row in rows):return None
        if texture is not None and not isinstance(texture.get('accepted'),bool):return None
        return rows,texture
    except (OSError,ValueError,KeyError,TypeError,AttributeError):return None


def save_pitch(path, frames, texture, cancel):
    if path is None:return
    if cancel and cancel.is_set():raise Cancelled()
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_text(json.dumps({'frames':frames,'texture':texture}),'utf-8')
        temporary.replace(path)
    finally:temporary.unlink(missing_ok=True)


def transcribe(path, settings, cancel=None, report=None, previous=None, excluded=None,
               context=None, cache_path=None, revision='original'):
    if cancel and cancel.is_set():raise Cancelled()
    import soundfile as sf
    from .vendor.basic_pitch.note_creation import output_to_notes_polyphonic
    from .solo_presence import detect
    settings = {**settings, 'scope': settings.get('scope', 'solos')}
    if settings['scope'] not in {'solos', 'full'}:
        raise ValueError('Escolha Somente solos ou Faixa inteira.')
    presence = None
    if settings['scope'] == 'solos':
        presence = detect(path, context, cancel, report, cache_path, revision)
    if report:
        report('Preparando as notas dos trechos selecionados', .59 if presence else .01)
    info=sf.info(path)
    length=math.ceil(info.frames*SR/info.samplerate)
    duration=length/SR
    # Loading/resampling a whole song is unnecessary when every selected section
    # already has pitch evidence, or when no solo was confirmed.
    audio=None
    sections = presence['sections'] if presence else [{'start': 0., 'end': duration}]
    accepted_sections, rejected_sections = [], []
    notes = []
    for index, section in enumerate(sections):
        if cancel and cancel.is_set():raise Cancelled()
        # Context improves edge predictions. Only events inside the accepted
        # interval survive; sample offsets preserve the original song clock.
        first = max(0, math.floor((section['start'] - .25) * SR))
        last = min(length, math.ceil((section['end'] + .25) * SR))
        def progress(stage, fraction):
            if report:
                base, span = (.60, .32) if presence else (.02, .90)
                report(stage, base + span * (index + fraction) / max(1, len(sections)))
        cache=note_cache_file(cache_path,path,revision,first,last,section,settings['scope'])
        cached=cached_pitch(cache)
        if cached:
            frame_notes,texture=cached
            progress('Notas recuperadas do cache desta faixa',1.)
        else:
            if audio is None:
                import librosa
                audio,_=librosa.load(path,sr=SR,mono=True)
                if not len(audio) or float(np.max(np.abs(audio)))<2e-5:
                    audio=np.zeros(max(1,len(audio)),dtype='float32')
                audio=audio/max(1.,float(np.max(np.abs(audio)))/.95)
            values=infer_activations(audio[first:last],cancel,progress)
            texture=solo_texture(values,first/SR,section) if presence else None
            frame_notes=[]
            if texture is None or texture['accepted']:
                frame_notes=output_to_notes_polyphonic(values['note'], values['onset'],
                    onset_thresh=.4, frame_thresh=.25, min_note_len=4, infer_onsets=True,
                    min_freq=80., max_freq=1350., melodia_trick=True, energy_tol=4)
                frame_notes=[[float(start),float(end),int(pitch),float(confidence)] for start,end,pitch,confidence in frame_notes]
            save_pitch(cache,frame_notes,texture,cancel)
        if presence:
            if not texture['accepted']:
                rejected_sections.append({**section, 'texture': texture})
                continue
            section = {**section, 'texture': texture}
        accepted_sections.append(section)
        for start, end, pitch, confidence in frame_notes:
            a = max(section['start'], first / SR + start * HOP / SR)
            b = min(section['end'], first / SR + end * HOP / SR)
            if 40 <= pitch <= 88 and b - a >= .045:
                notes.append({'start': round(a, 4), 'end': round(b, 4), 'midi': int(pitch),
                              'note': note_name(int(pitch)), 'confidence': round(float(confidence), 3)})
    notes = limit_polyphony(notes, settings.get('voices', 1))
    notes = [n for n in notes if not any(
        (settings.get('voices',1)==1 or n['midi']==deleted['midi']) and
        min(n['end'],deleted['end'])-max(n['start'],deleted['start']) >
        .5*min(n['end']-n['start'],deleted['end']-deleted['start'])
        for deleted in (excluded or []))]
    manual = [n for n in (previous or []) if n.get('edited')]
    if manual:
        notes = [n for n in notes if not any(n['start'] < m['end'] and n['end'] > m['start'] and
                 (n['midi'] == m['midi'] or settings.get('voices', 1) == 1) for m in manual)] + manual
        notes.sort(key=lambda n: (n['start'], n['midi']))
    if cancel and cancel.is_set():
        raise Cancelled()
    if report:
        report('Escolhendo cordas e casas para o solo', .94)
    notes = assign_positions(notes, settings.get('min_fret', 0), settings.get('max_fret', 24))
    if presence:
        presence = {**presence, 'candidate_sections': sections, 'sections': accepted_sections,
                    'rejected_sections': rejected_sections,
                    'solo_seconds': round(sum(s['end'] - s['start'] for s in accepted_sections), 4)}
        sections = accepted_sections
    outside = sum(not any(n['start'] < s['end'] and n['end'] > s['start'] for s in sections) for n in manual)
    message = ''
    if presence and not sections:
        message = 'Nenhum trecho de solo foi confirmado. A faixa inteira continua disponível para audição.'
        identity=presence.get('instrument_identity') or {}
        if identity and not identity.get('guitar_confirmed_contexts'):
            message='A fonte não foi confirmada como guitarra ou violão. Nenhuma tablatura automática foi criada; refine os instrumentos para isolar a guitarra.'
    elif not notes:
        message = 'Nenhuma nota suficientemente definida foi detectada nos trechos selecionados.'
    if presence and outside:
        message += ' %d correções manuais fora dos solos foram preservadas.' % outside
    return {'notes': notes, 'duration': round(duration, 4),
            'engine': 'MERT solo presence + Basic Pitch ONNX + playable-position search' if presence else 'Basic Pitch ONNX + playable-position search',
            'version': VERSION, 'presence': presence, 'sections': sections if presence else [],
            'tuning': list(TUNING), 'settings': settings,
            'unmapped': sum(n['string'] is None for n in notes),
            'message': message.strip()}


def request(identifier, settings):
    from .pipeline import POOL
    with LOCK:
        p = storage.read_project(identifier)
        if identifier in JOBS:
            return False
        source = next((s for s in p.get('stems', []) if s['name'] == 'guitar_lead'), None)
        if not source:
            raise ValueError('Separe guitarra solo e base antes de gerar a tablatura.')
        if p['status'] in {'queued', 'processing'}:
            raise ValueError('Aguarde a separação terminar para transcrever a faixa atual.')
        token, event = uuid.uuid4().hex, threading.Event()
        previous = p.get('tablature') or {}
        revision = p.get('audio_revision') or 'original'
        tab = {**previous, 'job_id': token, 'status': 'queued', 'progress': 0,
               'stage': 'Na fila para transcrever guitarra solo', 'error': None,
               'source_revision': revision, 'source_file': source['file'], 'settings': settings}
        keep = settings.get('preserve_edits',True)
        if not keep:
            tab['excluded_notes'] = []
        storage.update_project(identifier, tablature=tab)
        JOBS[identifier] = event
        POOL.submit(_run, identifier, token, event, source['file'], revision, settings,
                    previous.get('notes', []) if keep else [],previous.get('excluded_notes',[]) if keep else [])
        return True


def _run(identifier, token, event, source_file, revision, settings, previous, excluded):
    def update(**changes):
        with storage.LOCK:
            p = storage.read_project(identifier)
            tab = p.get('tablature') or {}
            if tab.get('job_id') != token or (p.get('audio_revision') or 'original') != revision:
                raise Cancelled()
            storage.update_project(identifier, tablature={**tab, **changes})
    try:
        if event.is_set():
            raise Cancelled()
        result = transcribe(storage.project_dir(identifier) / source_file, settings, event,
             lambda stage, value: update(status='processing', stage=stage, progress=round(value * 100, 1)),
             previous, excluded, context=_context(identifier),
             cache_path=storage.project_dir(identifier) / 'solo_presence_cache.json', revision=revision)
        if event.is_set():
            raise Cancelled()
        update(**result, status='ready', stage='Tablatura pronta', progress=100, error=None)
    except Cancelled:
        with storage.LOCK:
            p = storage.read_project(identifier)
            tab = p.get('tablature') or {}
            if tab.get('job_id') == token:
                storage.update_project(identifier, tablature={**tab, 'status': 'cancelled', 'stage': 'Transcrição interrompida'})
    except Exception as exc:
        update(status='failed', stage='Não foi possível transcrever o solo', error=str(exc)[-1000:])
    finally:
        with LOCK:
            if JOBS.get(identifier) is event:
                JOBS.pop(identifier, None)


def _context(identifier):
    p = storage.read_project(identifier)
    root = storage.project_dir(identifier)
    paths = {'original': root / 'original.wav'}
    for stem in p.get('stems', []):
        path = (root / stem['file']).resolve()
        if path.is_relative_to(root):
            paths[stem['name']] = path
    return paths


def cancel(identifier=None):
    with LOCK:
        for key, event in JOBS.items():
            if identifier is None or key == identifier:
                event.set()


def midi_bytes(notes):
    import mido
    midi = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage('set_tempo', tempo=500000, time=0))
    for channel in range(6):
        track.append(mido.Message('program_change', program=29, channel=channel, time=0))
    events = []
    for note in notes:
        events.extend([(round(note['start'] * 960), 1, note), (round(note['end'] * 960), 0, note)])
    last = 0
    for tick, on, note in sorted(events, key=lambda e: (e[0], e[1], e[2]['midi'])):
        track.append(mido.Message('note_on' if on else 'note_off', note=note['midi'],
                                  channel=note.get('string') if note.get('string') is not None else 0,
                                  velocity=max(35, min(110, round(note.get('confidence', .7) * 127))) if on else 0,
                                  time=max(0, tick - last)))
        last = tick
    stream = io.BytesIO()
    midi.save(file=stream)
    return stream.getvalue()


def text_tab(project):
    tab = project.get('tablature') or {}
    notes = tab.get('notes') or []
    lines = [project['title'], 'Guitarra solo | Afinacao E A D G B e | Posicoes sugeridas', '']
    if tab.get('settings', {}).get('scope', 'solos') == 'solos':
        lines += ['Trechos de solo detectados:']
        lines += ['%.2fs - %.2fs' % (s['start'], s['end']) for s in tab.get('sections', [])]
        if not tab.get('sections'):
            lines.append('Nenhum trecho de solo confirmado.')
        lines.append('')
    groups=[]
    for note in notes:
        if groups and abs(note['start']-groups[-1][0]['start'])<=.025 and not any(n.get('string')==note.get('string') for n in groups[-1]):
            groups[-1].append(note)
        else:
            groups.append([note])
    for offset in range(0, len(groups), 18):
        chunk = groups[offset:offset + 18]
        lines.append('%.2fs - %.2fs' % (chunk[0][0]['start'],max(n['end'] for group in chunk for n in group)))
        for string in range(5, -1, -1):
            cells=[]
            for group in chunk:
                note=next((n for n in group if n.get('string')==string),None)
                cells.append(('-%s-' % note['fret']).ljust(4,'-') if note else '----')
            lines.append(('EADGBe'[string]) + '|' + ''.join(cells) + '|')
        lines.append('')
    lines += ['Notas e tempos exatos (segundos):', 'Inicio\tFim\tNota\tCorda (1=e)\tCasa']
    for n in notes:
        lines.append('%.4f\t%.4f\t%s\t%s\t%s' % (n['start'], n['end'], n['note'],
                    6 - n['string'] if n.get('string') is not None else '?', n['fret'] if n.get('fret') is not None else '?'))
    return '\n'.join(lines) + '\n'
