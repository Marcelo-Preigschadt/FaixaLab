# Basic Pitch

Spotify AB, Apache-2.0. Fonte: https://github.com/spotify/basic-pitch
Commit: fa5997af0a8210982619003269994a1be25eddf3.

São reutilizadas três funções de note_creation.py: get_infered_onsets, constrain_frequency e output_to_notes_polyphonic. Imports e constantes foram reduzidos às dependências efetivamente usadas. Não houve retreinamento. A inferência ONNX e a marcação temporal com os offsets físicos das janelas ficam em faixalab/solo_tabs.py.
