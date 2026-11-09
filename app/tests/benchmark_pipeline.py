"""Time the real automatic pipeline on an existing, reproducible audio file.

Run each version in a separate process, with the same dependency environment,
cached model weights and input. Downloads and queue wait are not timed. Model
loading, separation, all candidates, verification, chords and lyrics are timed.
The supplied audio is not redistributed and no model is mocked.
"""
import argparse
import functools
import json
import os
from pathlib import Path
import shutil
import sys
import threading
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--models-cache', type=Path, required=True)
    parser.add_argument('--audio', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    os.environ['FAIXALAB_DATA_DIR'] = str(args.data.resolve())
    sys.path.insert(0, str(args.source_root.resolve()))
    from faixalab import storage, pipeline, chords, __version__
    from faixalab.app import Options
    storage.MODELS = args.models_cache.resolve()
    recorded = {}
    transitions = []
    original_update = storage.update_project
    def checked_update(identifier, **changes):
        result = original_update(identifier, **changes)
        if 'stems' in changes:
            names = [s['name'] for s in changes['stems']]
            assert [s['name'] for s in storage.read_project(identifier)['stems']] == names
            transitions.append(names)
            print(json.dumps({'saved_stems': names}), flush=True)
        return result
    storage.update_project = checked_update
    def watch(module, name, stage):
        function = getattr(module, name)
        @functools.wraps(function)
        def run(*a, **kw):
            began = time.perf_counter()
            try:
                result = function(*a, **kw)
                if stage in {'initial_separation', 'instrument_refinement', 'guitar_roles'}:
                    print(json.dumps({'returned_stage':stage,'stems':[s['name'] for s in result[0]]}),flush=True)
                return result
            finally:
                recorded[stage] = time.perf_counter()-began
                print(json.dumps({'stage':stage, 'seconds':recorded[stage]}), flush=True)
        setattr(module, name, run)
    for name,stage in [('decode_audio','decode'),('separate','initial_separation'),
                       ('refine_instruments','instrument_refinement'),
                       ('split_guitars','guitar_roles'),('transcribe','lyrics')]:
        watch(pipeline,name,stage)
    watch(chords,'analyze','chords')
    options = Options().model_dump()
    p = storage.new_project('Reproducible performance control',
                            {'type':'file','file':'upload'+args.audio.suffix}, options)
    folder = storage.project_dir(p['id'])
    shutil.copyfile(args.audio, folder/p['source']['file'])
    began = time.perf_counter()
    pipeline.process_project(p['id'],threading.Event())
    elapsed = time.perf_counter()-began
    p = storage.read_project(p['id'])
    assert p['status'] in {'ready','partial'}, p
    assert len(p['engine']['instrument_refinement']['selected']) == 33
    if 'guitar_roles' in recorded and not any(w['stage']=='guitars' for w in p['warnings']):
        assert {'guitar_lead','guitar_rhythm'} <= {s['name'] for s in p['stems']}, p['stems']
    result = {'version':__version__, 'seconds':elapsed, 'stages_seconds':recorded,
              'options':options, 'project_folder':str(folder), 'status':p['status'],
              'warnings':p['warnings'], 'stems':[s['name'] for s in p['stems']],
              'duration':p['duration'], 'chords':p['chords'], 'lyrics':p['lyrics'],
              'stem_transitions':transitions,
              'instrument_timings':p['engine']['instrument_refinement'].get('timings_seconds'),
              'cpu_threads':p['engine']['instrument_refinement'].get('cpu_threads'),
              'youtube_download_included':False, 'model_downloads_included':False,
              'tablature_included':False}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in {'chords','lyrics'}},ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
