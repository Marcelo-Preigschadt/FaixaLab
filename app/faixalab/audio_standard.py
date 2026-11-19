"""Shared loudness and lossless delivery for a project's separated tracks."""
import json
import math
from pathlib import Path
import shutil
import uuid

import numpy as np
import soundfile as sf

from .media import Cancelled, ffmpeg_executable, run_process


SAMPLE_RATE = 44100
TARGET_LUFS = -18.0
PEAK_CEILING_DBFS = -1.0
VERSION = 'studio-1'


def standardize(source, folder, stems, cancel):
    """Apply one linear gain to the reference and every stem, retaining raw files."""
    folder = Path(folder).resolve()
    paths = [Path(source).resolve(), *((folder / stem['file']).resolve() for stem in stems)]
    if any(not path.is_relative_to(folder) or not path.is_file() for path in paths):
        raise ValueError('Um dos arquivos de áudio do projeto não está disponível.')

    report = []
    run_process([ffmpeg_executable(), '-hide_banner', '-nostdin', '-i', str(paths[0]),
                 '-vn', '-af', 'loudnorm=I=-18:TP=-1:print_format=json',
                 '-f', 'null', '-'], cancel, report.append)
    text = '\n'.join(report)
    measurement = json.loads(text[text.rfind('{'):text.rfind('}') + 1])
    loudness = float(measurement['input_i'])
    true_peak = float(measurement['input_tp'])
    gain_db = TARGET_LUFS - loudness if math.isfinite(loudness) else 0.0
    if math.isfinite(true_peak):
        gain_db = min(gain_db, PEAK_CEILING_DBFS - true_peak)

    peak = 0.0
    for path in paths:
        with sf.SoundFile(path) as audio:
            if audio.samplerate != SAMPLE_RATE or audio.channels != 2:
                raise ValueError('As faixas precisam estar em estéreo a 44.100 Hz.')
            for block in audio.blocks(blocksize=65536, dtype='float32', always_2d=True):
                if cancel.is_set():
                    raise Cancelled()
                if not np.isfinite(block).all():
                    raise ValueError('Uma faixa contém amostras de áudio inválidas.')
                peak = max(peak, float(np.max(np.abs(block))))
    if peak:
        gain_db = min(gain_db, PEAK_CEILING_DBFS - 20 * math.log10(peak))
    gain = 10 ** (gain_db / 20)

    destination = folder / 'studio' / uuid.uuid4().hex
    destination.mkdir(parents=True)
    outputs = []
    try:
        for index, path in enumerate(paths):
            target = destination / ('reference.wav' if index == 0 else stems[index - 1]['name'] + '.wav')
            with sf.SoundFile(path) as audio, sf.SoundFile(
                    target, 'w', samplerate=SAMPLE_RATE, channels=2, subtype='PCM_24') as output:
                for block in audio.blocks(blocksize=65536, dtype='float32', always_2d=True):
                    if cancel.is_set():
                        raise Cancelled()
                    output.write(block * gain)
            outputs.append(target.relative_to(folder).as_posix())
    except BaseException:
        shutil.rmtree(destination, ignore_errors=True)
        raise

    normalized = [{**stem, 'playback_file': path} for stem, path in zip(stems, outputs[1:])]
    metadata = {'version': VERSION, 'sample_rate': SAMPLE_RATE, 'channels': 2,
                'bits_per_sample': 24, 'target_lufs': TARGET_LUFS,
                'source_lufs': loudness if math.isfinite(loudness) else None,
                'output_lufs': loudness + gain_db if math.isfinite(loudness) else None,
                'gain_db': round(gain_db, 4), 'peak_ceiling_dbfs': PEAK_CEILING_DBFS,
                'reference_file': outputs[0], 'shared_gain': True}
    return normalized, metadata
