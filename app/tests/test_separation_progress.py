"""The progress executor must preserve Demucs inference sample for sample."""
import random
import unittest
import torch
from demucs.apply import apply_model
from faixalab.separator_runner import ProgressPool


class TwoSourceModel(torch.nn.Module):
    samplerate = 100
    segment = 7
    sources = ['one', 'two']

    def forward(self, value):
        return torch.stack([value * .7, value * .3], dim=1)


class ProgressChecks(unittest.TestCase):
    def test_203_seconds_all_windows_report_and_reconstruct_exactly(self):
        audio = torch.randn(1, 2, 20300)
        for shifts in [0, 1]:
            events = []
            model = TwoSourceModel()
            random.seed(2026)
            expected = apply_model(model, audio, shifts=shifts, overlap=.5, segment=7)
            random.seed(2026)
            actual = apply_model(model, audio, shifts=shifts, overlap=.5, segment=7,
                                 pool=ProgressPool(lambda f, s: events.append((f, s))))
            torch.testing.assert_close(actual, expected, rtol=0, atol=0)
            completed = [f for f, s in events if 'concluídos' in s]
            self.assertGreater(len(completed), 50)
            self.assertEqual(completed[-1], 1)
            self.assertTrue(all(a < b for a, b in zip(completed, completed[1:])))


if __name__ == '__main__':
    unittest.main(verbosity=2)
