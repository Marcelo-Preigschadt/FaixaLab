"""Open FaixaLab Online with its installed audio importer ready."""

import ctypes
import os

from activate import main as activate_importer
from faixalab.local_import import SITE


def open_faixalab():
    try:
        importer_ready = activate_importer() == 0
    except OSError:
        importer_ready = False
    if not importer_ready:
        ctypes.windll.user32.MessageBoxW(
            None,
            "O importador do YouTube não iniciou. Abra o FaixaLab pelo atalho "
            "para tentar novamente.",
            "FaixaLab Online",
            0x30,
        )
    os.startfile(SITE + '/FaixaLab/')


if __name__ == '__main__':
    open_faixalab()
