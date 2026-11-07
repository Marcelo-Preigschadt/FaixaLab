"""Shared chord vocabulary for the offline dictionary and manual corrections."""
from functools import lru_cache
from pathlib import Path
import json
import re

PITCHES = {'C':0,'C#':1,'Db':1,'D':2,'D#':3,'Eb':3,'E':4,'Fb':4,'E#':5,
           'F':5,'F#':6,'Gb':6,'G':7,'G#':8,'Ab':8,'A':9,'A#':10,'Bb':10,'B':11,'Cb':11,'B#':0}


@lru_cache(maxsize=1)
def load_dictionary():
    return json.loads((Path(__file__).parent / 'data/chord_dictionary.json').read_text('utf-8'))


def valid_label(label):
    if label == 'N':
        return True
    match = re.fullmatch(r'([A-G](?:#|b)?)(.*?)(?:/([A-G](?:#|b)?))?', label)
    if not match or match[1] not in PITCHES or match[3] is not None and match[3] not in PITCHES:
        return False
    data = load_dictionary()
    quality = data['aliases'].get(match[2], match[2])
    return quality in data['theory']
