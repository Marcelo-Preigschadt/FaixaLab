"""Real-model foreground regression on external recordings; no audio bundled.

Usage: python tests/solo_presence_regressions.py --recordings DIR --export DIR
DIR recordings contains egset12/*.wav and guitarset/*_mic.wav, obtained from
their official Zenodo releases. Controlled role leakage is explicitly labelled;
these controls do not measure the accuracy of the preceding Demucs separator.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from faixalab.solo_presence import SR, detect, read_audio
from faixalab.solo_tabs import transcribe


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--recordings', type=Path, required=True)
    parser.add_argument('--export', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--held-out', action='store_true')
    args = parser.parse_args()
    results = []
    cases = [
        ('bossa_comp_leak', 'guitarset/00_BN1-129-Eb_comp_mic.wav', 'negative', .08),
        ('jazz_comp_leak', 'guitarset/00_Jazz1-200-B_comp_mic.wav', 'negative', .08),
        ('bossa_comp_misassigned', 'guitarset/00_BN1-147-Gb_comp_mic.wav', 'negative', .92),
        ('jazz_comp_misassigned', 'guitarset/00_Jazz1-130-D_comp_mic.wav', 'negative', .92),
        ('electric_melody', 'egset12/01.wav', 'positive', .92),
        ('acoustic_bossa_solo', 'guitarset/00_BN1-129-Eb_solo_mic.wav', 'positive', .92),
        ('acoustic_jazz_solo', 'guitarset/00_Jazz1-130-D_solo_mic.wav', 'positive', .92),
    ]
    if args.held_out:
        cases = [
            ('heldout_rock_comp', 'guitarset/05_Rock3-117-Bb_comp_mic.wav', 'negative', .92),
            ('heldout_jazz_comp', 'guitarset/05_Jazz3-150-C_comp_mic.wav', 'negative', .92),
            ('heldout_funk_solo', 'guitarset/03_Funk1-97-C_solo_mic.wav', 'positive', .92),
            ('heldout_rock_solo', 'guitarset/00_Rock2-142-D_solo_mic.wav', 'positive', .92),
        ]
    with tempfile.TemporaryDirectory(prefix='FaixaLab-presence-') as temp:
        temp = Path(temp)
        for name, source, label, share in cases:
            path = args.recordings / source
            audio = read_audio(path)[6*SR:18*SR]
            context = {}
            for stem, data in [('guitar_lead', audio * share), ('guitar_rhythm', audio * (1-share)), ('original', audio)]:
                target = temp / (stem + '.wav')
                sf.write(target, data, SR, subtype='FLOAT')
                context[stem] = target
            started = time.monotonic()
            tab = transcribe(context['guitar_lead'], {'scope':'solos','voices':1}, context=context)
            r = tab['presence']
            row = {'case': name, 'source': source, 'source_range_seconds': [6,18],
                   'expected': label, 'controlled_lead_gain': share,
                   'sections': r['sections'], 'detected_seconds': r['solo_seconds'],
                   'seconds': round(time.monotonic()-started,2),
                   'detected_any': bool(r['sections'])}
            results.append(row)
            print(json.dumps(row), flush=True)
        if args.export and not args.held_out:
            # Known true guitar phrase with an independently active vocal stem.
            directory = args.export
            lead = read_audio(directory/'guitar_lead.wav')[6*SR:18*SR]
            rhythm = read_audio(directory/'guitar_rhythm.wav')[6*SR:18*SR]
            vocal = read_audio(directory/'vocals.wav')[20*SR:32*SR] * .35
            context = {}
            for stem, data in [('guitar_lead',lead),('guitar_rhythm',rhythm),('original',lead+rhythm+vocal)]:
                target = temp/(stem+'.wav');sf.write(target,data,SR,subtype='FLOAT');context[stem]=target
            tab = transcribe(context['guitar_lead'], {'scope':'solos','voices':1}, context=context)
            r = tab['presence']
            row = {'case':'guitar_phrase_with_continuous_vocals','expected':'positive',
                   'detected_any':bool(r['sections']),'sections':r['sections'],'detected_seconds':r['solo_seconds'],
                   'vocal_RMS':float(np.sqrt(np.mean(vocal**2)))}
            results.append(row);print(json.dumps(row),flush=True)
    summary = {'algorithm_version':'0.5.0','cases':results,
               'negative_cases':sum(r['expected']=='negative' for r in results),
               'negative_cases_with_false_detection':sum(r['expected']=='negative' and r['detected_any'] for r in results),
               'positive_cases':sum(r['expected']=='positive' for r in results),
               'positive_cases_with_detection':sum(r['expected']=='positive' and r['detected_any'] for r in results),
               'limitations':'Small controlled role-assignment study; no end-to-end separation benchmark or guaranteed accuracy on arbitrary repertoire.'}
    args.output.parent.mkdir(exist_ok=True,parents=True)
    args.output.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf-8')
    print('SUMMARY',json.dumps({k:v for k,v in summary.items() if k!='cases'}),flush=True)


if __name__ == '__main__':
    main()
