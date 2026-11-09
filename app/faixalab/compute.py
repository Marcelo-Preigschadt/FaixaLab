"""Bound inference parallelism by the actual machine or container allocation."""
import math
import os
from pathlib import Path


def available_cpus():
    count = os.cpu_count() or 1
    if hasattr(os, 'sched_getaffinity'):
        try:
            count = min(count, len(os.sched_getaffinity(0)))
        except OSError:
            pass
    # os.cpu_count() can expose the host rather than the Codespace/container.
    for quota_path, period_path in (
        ('/sys/fs/cgroup/cpu.max', None),
        ('/sys/fs/cgroup/cpu/cpu.cfs_quota_us', '/sys/fs/cgroup/cpu/cpu.cfs_period_us'),
    ):
        try:
            if period_path:
                quota = int(Path(quota_path).read_text())
                period = int(Path(period_path).read_text())
            else:
                quota, period = Path(quota_path).read_text().split()
                if quota == 'max':
                    continue
                quota, period = int(quota), int(period)
            if quota > 0 and period > 0:
                count = min(count, max(1, math.ceil(quota / period)))
        except (OSError, ValueError):
            pass
    return max(1, count)


def thread_budget(limit=None):
    available = available_cpus()
    try:
        requested = int(os.environ.get('FAIXALAB_CPU_THREADS', ''))
    except ValueError:
        requested = min(8, available)
    if requested < 1:
        requested = min(8, available)
    return max(1, min(requested, available, limit or 32))


def configure_torch():
    import torch
    budget = thread_budget()
    torch.set_num_threads(budget)
    return budget


def worker_environment():
    environment = os.environ.copy()
    budget = str(thread_budget())
    environment.update(PYTHONUTF8='1', FAIXALAB_CPU_THREADS=budget,
                       OMP_NUM_THREADS=budget, MKL_NUM_THREADS=budget,
                       OPENBLAS_NUM_THREADS='1')
    return environment
