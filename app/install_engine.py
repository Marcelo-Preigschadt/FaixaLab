"""Install a pinned CPU/CUDA runtime for hardware already on this machine.

No cloud instances, drivers, CUDA toolkit or paid services are provisioned.
Uses only the standard library so it can run before app dependencies exist.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


CPU = {'accelerator': 'cpu', 'torch': '2.5.1', 'flavor': 'cpu'}


def detect_nvidia():
    executable = shutil.which('nvidia-smi')
    if not executable and os.name == 'nt':
        candidate = Path(os.environ.get('ProgramFiles', 'C:/Program Files'))/'NVIDIA Corporation/NVSMI/nvidia-smi.exe'
        if candidate.is_file():
            executable = str(candidate)
    if not executable:
        return None
    kwargs = {'capture_output': True, 'text': True, 'encoding': 'utf-8',
              'errors': 'replace', 'timeout': 10}
    if os.name == 'nt':
        kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
    try:
        result = subprocess.run([executable], **kwargs)
        version = re.search(r'CUDA Version:\s*(\d+)\.(\d+)', result.stdout)
        if result.returncode or not version:
            return None
        query = subprocess.run([executable, '--query-gpu=name,compute_cap',
                                '--format=csv,noheader'], **kwargs)
        name, capability = 'NVIDIA', None
        if query.returncode == 0 and query.stdout.strip():
            first = query.stdout.splitlines()[0].rsplit(',', 1)
            name = first[0].strip()
            if len(first) == 2:
                try:
                    capability = float(first[1].strip())
                except ValueError:
                    pass
        return {'name': name, 'cuda': tuple(map(int, version.groups())),
                'capability': capability}
    except (OSError, subprocess.TimeoutExpired):
        return None


def choose_plan(hardware, accelerator='auto'):
    if accelerator == 'cpu' or not hardware:
        return dict(CPU)
    maximum = tuple(hardware['cuda'])
    capability = hardware.get('capability')
    if capability is not None and capability < 5.:
        return dict(CPU)
    if capability is not None and capability >= 10.:
        if maximum >= (12, 8):
            return {'accelerator': 'cuda', 'torch': '2.7.1', 'flavor': 'cu128'}
        return dict(CPU)
    for minimum, flavor in (((12, 4), 'cu124'), ((12, 1), 'cu121'), ((11, 8), 'cu118')):
        if maximum >= minimum:
            return {'accelerator': 'cuda', 'torch': '2.5.1', 'flavor': flavor}
    return dict(CPU)


PROBE = '''import json, torch
import torch.nn.functional as F
info = {'torch': torch.__version__, 'cuda_available': torch.cuda.is_available()}
if info['cuda_available']:
    # Test real kernels, not just whether a driver/device is discoverable.
    x = torch.randn(1, 2, 16, 32, device='cuda')
    y = F.scaled_dot_product_attention(x, x, x)
    z = torch.randn(64, 64, device='cuda')
    assert bool(torch.isfinite(y).all() & torch.isfinite(z @ z).all())
    torch.cuda.synchronize()
    info['device'] = torch.cuda.get_device_name(0)
print(json.dumps(info))
'''


def validate(python, plan):
    result = subprocess.run([str(python), '-c', PROBE], capture_output=True,
                            text=True, encoding='utf-8', errors='replace', timeout=90)
    if result.returncode:
        raise RuntimeError(result.stderr[-1500:] or 'Falha ao validar o motor de áudio.')
    info = json.loads(result.stdout.strip().splitlines()[-1])
    if plan['accelerator'] == 'cuda' and not info['cuda_available']:
        raise RuntimeError('O motor CUDA não conseguiu acessar a GPU.')
    return info


def install(python, plan, uv=None):
    command = [uv] if uv else [str(python), '-m', 'uv']
    version = plan['torch'] + '+' + plan['flavor']
    subprocess.run(command + ['pip', 'install', '--python', str(python),
                             'torch==' + version, 'torchaudio==' + version,
                             '--index-url', 'https://download.pytorch.org/whl/' + plan['flavor']], check=True)


def prepare(python, *, uv=None, accelerator='auto', report=None):
    hardware = None if accelerator == 'cpu' else detect_nvidia()
    plan = choose_plan(hardware, accelerator)
    if accelerator == 'cuda' and plan['accelerator'] != 'cuda':
        raise RuntimeError('Não foi encontrada uma GPU NVIDIA/driver compatível com os motores disponíveis.')
    print('Preparando motor de áudio: ' + plan['accelerator'].upper(), flush=True)
    fallback = None
    try:
        install(python, plan, uv)
        verified = validate(python, plan)
    except (subprocess.SubprocessError, OSError, RuntimeError, ValueError) as error:
        if plan['accelerator'] != 'cuda' or accelerator == 'cuda':
            raise
        fallback = str(error)[-1500:]
        print('A GPU não ficou disponível. Preparando o motor CPU para continuar.', flush=True)
        plan = dict(CPU)
        install(python, plan, uv)
        verified = validate(python, plan)
    result = {'selected': plan, 'hardware': hardware, 'verified': verified, 'fallback_reason': fallback}
    if report:
        report = Path(report)
        report.parent.mkdir(parents=True, exist_ok=True)
        temporary = report.with_suffix('.tmp')
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf-8')
        temporary.replace(report)
    print('Motor validado: ' + plan['accelerator'].upper(), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--python', type=Path, default=Path(sys.executable))
    parser.add_argument('--uv')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--accelerator', choices=('auto', 'cpu', 'cuda'),
                        default=os.environ.get('FAIXALAB_ACCELERATOR', 'auto'))
    args = parser.parse_args()
    prepare(args.python, uv=args.uv, accelerator=args.accelerator, report=args.report)


if __name__ == '__main__':
    main()
