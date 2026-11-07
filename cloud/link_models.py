"""Link verified release models into the editable source checkout."""
from pathlib import Path
import os
ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'.app/FaixaLab/faixalab/models'
target=ROOT/'app/faixalab/models'
target.mkdir(parents=True,exist_ok=True)
linked=0
for model in sorted(source.iterdir()):
    if model.suffix not in {'.onnx','.pt','.npz'} or not model.is_file():continue
    destination=target/model.name
    if destination.exists():continue
    destination.unlink(missing_ok=True)
    destination.symlink_to(os.path.relpath(model,destination.parent))
    linked+=1
if not (target/'solo_presence.onnx').is_file():raise RuntimeError('O pacote não contém os modelos esperados.')
print(str(linked)+' modelos ligados ao código-fonte em app/.')
