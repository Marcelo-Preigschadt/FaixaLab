"""Full-waveform correlations with one bounded-memory pass over each stem."""
from contextlib import ExitStack
from pathlib import Path
import math
import numpy as np
import soundfile as sf
from .media import Cancelled


class WaveformStatistics:
    def __init__(self, names, gram, reference=False):
        self.names = tuple(names)
        self.offset = int(reference)
        self.indices = {name: i + self.offset for i, name in enumerate(names)}
        self.gram = gram

    def energy(self, name):
        i = self.indices[name]
        return float(self.gram[i, i])

    def dot(self, left, right):
        return float(self.gram[self.indices[left], self.indices[right]])

    def reconstruction_support(self, name, others):
        """Return support and a conservative bound for float32 subtraction error.

        The legacy residual subtracts sources sequentially in float32. The
        correlation identity is evaluated in float64; candidates close enough
        to zero to change the decision must use that original residual instead.
        """
        if not self.offset:
            raise ValueError('A reference waveform is required.')
        i = self.indices[name]
        energy = self.energy(name)
        dot = float(self.gram[i, 0]) - sum(self.dot(name, n) for n in others)
        denominator = max(energy, 1e-12)
        benefit = (2 * dot - energy) / denominator
        eps = len(others) * np.finfo(np.float32).eps
        gamma = eps / max(1e-9, 1 - eps)
        scale = math.sqrt(max(0., float(self.gram[0, 0])))
        scale += sum(math.sqrt(max(0., self.energy(n))) for n in others)
        bound = 2 * gamma * scale * math.sqrt(max(0., energy)) / denominator
        return benefit, bound + 1e-8


def collect(output, names, *, reference=None, cancel=None, block_frames=88200):
    """Read every sample/channel, without downsampling or an RMS shortcut."""
    names = list(names)
    size = len(names) + int(reference is not None)
    gram = np.zeros((size, size), dtype='float64')
    if not names:
        return WaveformStatistics(names, gram, reference is not None)
    with ExitStack() as stack:
        streams = [stack.enter_context(sf.SoundFile(Path(output)/(name+'.wav'))) for name in names]
        frames, sr, channels = len(streams[0]), streams[0].samplerate, streams[0].channels
        if any((len(s), s.samplerate, s.channels) != (frames, sr, channels) for s in streams):
            raise ValueError('As faixas precisam ter duração, canais e amostragem iguais.')
        if reference is not None and any(np.shape(x) != (frames, channels) for x in reference):
            raise ValueError('A referência precisa ter os mesmos canais e duração das faixas.')
        for start in range(0, frames, block_frames):
            if cancel and cancel.is_set():
                raise Cancelled()
            count = min(block_frames, frames - start)
            matrix = np.empty((size, count * channels), dtype='float64')
            offset = int(reference is not None)
            if reference is not None:
                # Match the original subtraction's float32 rounding first.
                matrix[0] = (reference[0][start:start+count] - reference[1][start:start+count]).reshape(-1)
            for i, stream in enumerate(streams, offset):
                matrix[i] = stream.read(count, dtype='float64', always_2d=True).reshape(-1)
            gram += matrix @ matrix.T
    return WaveformStatistics(names, gram, reference is not None)


def exact_pair(output, left, right, cancel=None, block_frames=441000):
    """Legacy arithmetic for correlations on a decision boundary."""
    energies = [0., 0.]
    dot = 0.
    with sf.SoundFile(Path(output)/(left+'.wav')) as a, sf.SoundFile(Path(output)/(right+'.wav')) as b:
        for x in a.blocks(blocksize=block_frames, dtype='float64', always_2d=True):
            if cancel and cancel.is_set():
                raise Cancelled()
            y = b.read(len(x), dtype='float64', always_2d=True)
            energies[0] += float(np.sum(x*x))
            energies[1] += float(np.sum(y*y))
            dot += float(np.sum(x*y))
    return dot / max(1e-12, math.sqrt(energies[0]*energies[1]))
