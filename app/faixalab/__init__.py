"""FaixaLab runtime configuration."""
import os
import tempfile
import hashlib
import importlib.metadata
from pathlib import Path
import platform
import sys

__version__ = '0.10.1'

# Reuse compiled DSP only within this release, environment and dependency set.
# Numba additionally checks the CPU model/features before loading native code.
# Never distribute this cache in a ZIP or share it between installations.
_dependencies = []
for _package in ('numba', 'llvmlite', 'numpy', 'scipy', 'librosa'):
    try:
        _dependencies.append((_package, importlib.metadata.version(_package)))
    except importlib.metadata.PackageNotFoundError:
        _dependencies.append((_package, None))
_identity = repr((__version__, sys.implementation.cache_tag, str(Path(sys.prefix).resolve()),
                  str(Path(__file__).resolve().parent), platform.machine(), platform.processor(),
                  _dependencies, os.environ.get('NUMBA_CPU_NAME'), os.environ.get('NUMBA_CPU_FEATURES')))
_fingerprint = hashlib.sha256(_identity.encode()).hexdigest()[:24]
_data_root = Path(os.environ.get('FAIXALAB_DATA_DIR') or
                  Path(os.environ.get('LOCALAPPDATA', Path.home()/'.local/share'))/'FaixaLab')
try:
    _jit_directory = _data_root/'jit-cache'/_fingerprint
    _jit_directory.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('NUMBA_CACHE_DIR', str(_jit_directory))
except OSError:
    _jit_cache = tempfile.TemporaryDirectory(prefix='FaixaLab-jit-', ignore_cleanup_errors=True)
    os.environ['NUMBA_CACHE_DIR'] = _jit_cache.name
