"""FaixaLab runtime configuration."""
import os
import tempfile

__version__ = '0.8.0'

# Native librosa/Numba stencils must not reuse stale machine-code caches from
# another installation/process. Model downloads remain in persistent storage.
_jit_cache = tempfile.TemporaryDirectory(prefix='FaixaLab-jit-', ignore_cleanup_errors=True)
os.environ['NUMBA_CACHE_DIR'] = _jit_cache.name
