"""Validate a pinned chords-db guitar.json and build the offline dictionary."""
import json
from pathlib import Path
import re
import sys
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
PC = {'C':0,'C#':1,'Db':1,'D':2,'D#':3,'Eb':3,'E':4,'F':5,'F#':6,'Gb':6,'G':7,'G#':8,'Ab':8,'A':9,'A#':10,'Bb':10,'B':11}
NAMES = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
TUNING = [40,45,50,55,59,64]
# Allowed chord tones and required identity tones. Fifths may be omitted from
# extended voicings; roots and the defining third/seventh/extension are checked.
THEORY = {
 '':([0,4,7],[0,4,7]), 'm':([0,3,7],[0,3,7]), 'dim':([0,3,6],[0,3,6]),
 'dim7':([0,3,6,9],[0,3,6,9]), 'sus2':([0,2,7],[0,2,7]), 'sus4':([0,5,7],[0,5,7]),
 'sus2sus4':([0,2,5,7],[0,2,5,7]), '7sus4':([0,5,7,10],[0,5,10]),
 'aug':([0,4,8],[0,4,8]), '5':([0,7],[0,7]), '6':([0,4,7,9],[0,4,9]),
 '69':([0,2,4,7,9],[0,2,4,9]), '7':([0,4,7,10],[0,4,10]),
 '7b5':([0,4,6,10],[0,4,6,10]), 'aug7':([0,4,8,10],[0,4,8,10]),
 '9':([0,2,4,7,10],[0,2,4,10]), '9b5':([0,2,4,6,10],[0,2,4,6,10]),
 'aug9':([0,2,4,8,10],[0,2,4,8,10]), '7b9':([0,1,4,7,10],[0,1,4,10]),
 '7#9':([0,3,4,7,10],[0,3,4,10]), '11':([0,2,4,5,7,10],[0,5,10]),
 '9#11':([0,2,4,6,7,10],[0,2,4,6,10]), '13':([0,2,4,5,7,9,10],[0,4,9,10]),
 'maj7':([0,4,7,11],[0,4,11]), 'maj7b5':([0,4,6,11],[0,4,6,11]),
 'maj7#5':([0,4,8,11],[0,4,8,11]), 'maj7sus2':([0,2,7,11],[0,2,7,11]),
 'maj9':([0,2,4,7,11],[0,2,4,11]), 'maj11':([0,2,4,5,7,11],[0,4,5,11]),
 'maj13':([0,2,4,5,7,9,11],[0,4,9,11]), 'm6':([0,3,7,9],[0,3,9]),
 'm69':([0,2,3,7,9],[0,2,3,9]), 'm7':([0,3,7,10],[0,3,10]),
 'm7b5':([0,3,6,10],[0,3,6,10]), 'm9':([0,2,3,7,10],[0,2,3,10]),
 'm11':([0,2,3,5,7,10],[0,3,5,10]), 'mMaj7':([0,3,7,11],[0,3,11]),
 'mMaj7b5':([0,3,6,11],[0,3,6,11]), 'mMaj9':([0,2,3,7,11],[0,2,3,11]),
 'mMaj11':([0,2,3,5,7,11],[0,3,5,11]), 'add9':([0,2,4,7],[0,2,4]),
 'madd9':([0,2,3,7],[0,2,3]), 'add11':([0,4,5,7],[0,4,5]),
 'alt':([0,1,3,4,6,8,10],[0,4,10]),
}
ALIASES={'major':'','maj':'','minor':'m','min':'m','sus':'sus4','mmaj7':'mMaj7','mmaj7b5':'mMaj7b5','mmaj9':'mMaj9','mmaj11':'mMaj11','mM7':'mMaj7','7#5':'aug7','9#5':'aug9','6/9':'69','m6/9':'m69','+':'aug','°':'dim','ø':'m7b5','Δ7':'maj7','M7':'maj7','7M':'maj7','m7M':'mMaj7','7(9)':'9','7(13)':'13','7/9':'9','m7(5-)':'m7b5','7(5+)':'aug7','7(b9)':'7b9','7(#9)':'7#9'}

def main():
 raw=json.loads(Path(sys.argv[1]).read_text())
 chords={}; rejected=defaultdict(int); source_positions=0
 for records in raw['chords'].values():
  for record in records:
   root=PC[record['key']]; suffix=record['suffix']; match=re.fullmatch(r'(.*?)(?:/([A-G](?:#|b)?))?',suffix)
   quality=ALIASES.get(match[1],match[1]); explicit_bass=PC.get(match[2])
   if quality not in THEORY:rejected['unsupported_quality']+=len(record['positions']);continue
   allowed,required=THEORY[quality]
   allowed={(root+n)%12 for n in allowed};required={(root+n)%12 for n in required}
   if explicit_bass is not None:allowed.add(explicit_bass)
   for position in record['positions']:
    source_positions+=1
    shape=[f if f<=0 else f+position['baseFret']-1 for f in position['frets']]
    actual=[base+f for base,f in zip(TUNING,shape) if f>=0]
    tones={n%12 for n in actual}
    if not actual or any(f>24 for f in shape):rejected['range']+=1;continue
    if actual!=position.get('midi',actual):rejected['midi_metadata']+=1;continue
    if not tones<=allowed or not required<=tones:rejected['harmonic_identity']+=1;continue
    if quality=='alt' and not tones.intersection({(root+n)%12 for n in [1,3,6,8]}):rejected['alteration_missing']+=1;continue
    bass=min(actual)%12
    if explicit_bass is not None and bass!=explicit_bass:rejected['slash_bass']+=1;continue
    fingers=position['fingers']
    if any(f>0 and not 1<=finger<=4 for f,finger in zip(shape,fingers)):rejected['fingers']+=1;continue
    bad=False
    for finger in range(1,5):
     used=[shape[s] for s,n in enumerate(fingers) if n==finger and shape[s]>0]
     if len(set(used))>1:bad=True
    if bad:rejected['fingers']+=1;continue
    label=NAMES[root]+quality+('/'+NAMES[bass] if bass!=root else '')
    entry=chords.setdefault(label,{'label':label,'root':root,'quality':quality,'bass':bass,'positions':[]})
    if any(p['frets']==shape for p in entry['positions']):continue
    barres=[]
    for fret in position.get('barres',[]):
     actual_fret=fret+position['baseFret']-1
     strings=[i for i,f in enumerate(shape) if f==actual_fret]
     if len(strings)>1 and all(f>=actual_fret for f in shape[strings[0]:strings[-1]+1]):
      barres.append({'fret':actual_fret,'from':strings[0],'to':strings[-1],'finger':fingers[strings[0]]})
    entry['positions'].append({'frets':shape,'fingers':fingers,'barres':barres})
 for entry in chords.values():
  entry['positions'].sort(key=lambda p:(max(p['frets']),sum(f<0 for f in p['frets'])))
 result={'tuning':TUNING,'theory':{q:{'intervals':a,'required':r} for q,(a,r) in THEORY.items()},'aliases':ALIASES,'chords':list(chords.values()),
  'source':{'project':'tombatossals/chords-db','commit':'df06fa7b425cf5fd29485ff6591236b3557e3fac','license':'MIT'},
  'summary':{'chords':len(chords),'positions':sum(len(e['positions']) for e in chords.values()),'families':len(THEORY),'source_positions_checked':source_positions,'rejected':dict(rejected)}}
 (ROOT/'faixalab/data/chord_dictionary.json').write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')))
 print(json.dumps(result['summary']))

if __name__=='__main__':main()
