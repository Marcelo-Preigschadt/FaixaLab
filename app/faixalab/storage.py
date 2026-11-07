from pathlib import Path
from datetime import datetime, timezone
import json
import os
import re
import threading
import uuid
import hashlib

DEFAULT_ROOT = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local/share')) / 'FaixaLab'
ROOT = Path(os.environ.get('FAIXALAB_DATA_DIR', DEFAULT_ROOT)).resolve()
PROJECTS = ROOT / 'projects'
MODELS = ROOT / 'models'
for directory in [PROJECTS, MODELS]:
    directory.mkdir(parents=True, exist_ok=True)
LOCK = threading.RLock()


def now():
    return datetime.now(timezone.utc).isoformat()


def project_dir(identifier):
    if not re.fullmatch(r'[a-f0-9]{32}', identifier):
        raise ValueError('Projeto inválido.')
    return PROJECTS / identifier


def read_project(identifier):
    with LOCK:
        return json.loads((project_dir(identifier) / 'project.json').read_text('utf-8'))


def update_project(identifier, **changes):
    with LOCK:
        p = project_dir(identifier) / 'project.json'
        data = json.loads(p.read_text('utf-8')) if p.exists() else {'id': identifier, 'created_at': now()}
        # Streaming URLs name an immutable audio revision. Keep only file
        # references, never duplicate waveforms/annotations on progress writes.
        if 'stems' in changes or 'audio_revision' in changes:
            previous = data.get('stems') or []
            updated = changes.get('stems', previous)
            before = [(stem.get('name'), stem.get('file')) for stem in previous]
            after = [(stem.get('name'), stem.get('file')) for stem in updated]
            if previous and before != after and changes.get('audio_revision', data.get('audio_revision')) == data.get('audio_revision'):
                changes['audio_revision'] = uuid.uuid4().hex
            old_revision = data.get('audio_revision') or 'original'
            new_revision = changes.get('audio_revision', data.get('audio_revision')) or 'original'
            if previous and (before != after or old_revision != new_revision):
                history = dict(data.get('audio_history') or {})
                history[old_revision] = {stem['name']: stem['file'] for stem in previous}
                data['audio_history'] = history
        data.update(changes, updated_at=now())
        tmp = p.with_suffix('.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), 'utf-8')
        os.replace(tmp, p)
        return data


def new_project(title, source, options):
    identifier = uuid.uuid4().hex
    project_dir(identifier).mkdir()
    return update_project(identifier, title=title[:200], source=source, options=options,
                          status='queued', stage='Na fila', progress=0, warnings=[], stems=[],
                          chords=[], lyrics=[], error=None)


def _import_key(source_key,options):
    return hashlib.sha256(json.dumps(['imports-v1',source_key,options],sort_keys=True).encode()).hexdigest()


def cached_import(source_key,options):
    """Caller holds LOCK through lookup/create/register to deduplicate requests."""
    try:
        index=json.loads((ROOT/'import_cache.json').read_text('utf-8'))
        if not isinstance(index,dict):return None
        identifier=index.get(_import_key(source_key,options))
        if not identifier:return None
        p=read_project(identifier)
        if p.get('status') not in {'queued','processing','ready','partial'}:return None
        if p.get('instrument_settings',{}).get('selection'):return None
        return p
    except (OSError,ValueError,TypeError):return None


def remember_import(source_key,options,identifier):
    path=ROOT/'import_cache.json'
    try:index=json.loads(path.read_text('utf-8'))
    except (OSError,ValueError):index={}
    if not isinstance(index,dict):index={}
    index[_import_key(source_key,options)]=identifier
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(index),'utf-8')
    temporary.replace(path)


def list_projects():
    with LOCK:
        projects = []
        for path in PROJECTS.glob('*/project.json'):
            try:
                p = json.loads(path.read_text('utf-8'))
                projects.append({k: p.get(k) for k in ['id', 'title', 'status', 'stage', 'progress', 'duration', 'key', 'bpm', 'created_at', 'updated_at']})
            except (OSError, ValueError):
                continue
        return sorted(projects, key=lambda p: p.get('created_at', ''), reverse=True)
