"""Non-overlapping output choices for the public Mega53 checkpoint.

Parent/child outputs (guitar + electric/acoustic, keys + piano, vocal +
lead/backing, drums + kick/snare) must not all enter the same default mix.
"""
CATALOG = {
    'vocals': {'label':'Voz', 'head':'vocal', 'tags':['Singing','Speech','Vocal music','Male singing','Female singing','A capella']},
    'bass': {'label':'Baixo', 'head':'bass', 'tags':['Bass guitar','Double bass']},
    'guitar': {'label':'Guitarra elétrica', 'head':'electric-guitar', 'tags':['Electric guitar','Steel guitar, slide guitar'], 'support':['Guitar']},
    'acoustic_guitar': {'label':'Violão', 'head':'acoustic-guitar', 'tags':['Acoustic guitar'], 'support':['Guitar','Strum']},
    'accordion': {'label':'Gaita / acordeon', 'head':'accordion', 'tags':['Accordion']},
    'harmonica': {'label':'Gaita de boca', 'head':'harmonica', 'tags':['Harmonica']},
    'piano': {'label':'Piano', 'head':'piano', 'tags':['Piano','Electric piano']},
    'organ': {'label':'Órgão', 'head':'organ', 'tags':['Organ','Electronic organ','Hammond organ']},
    'synth': {'label':'Sintetizador', 'head':'synth', 'tags':['Synthesizer','Sampler']},
    'bowed_strings': {'label':'Cordas de arco', 'head':'bowed_strings', 'tags':['Bowed string instrument','Violin, fiddle','Cello','String section']},
    'brass': {'label':'Metais', 'head':'brass', 'tags':['Brass instrument','Trumpet','Trombone','French horn']},
    'woodwind': {'label':'Sopros', 'head':'woodwind', 'tags':['Wind instrument, woodwind instrument','Saxophone','Flute','Clarinet','Oboe','Bassoon']},
    'banjo': {'label':'Banjo', 'head':'banjo', 'tags':['Banjo']},
    'mandolin': {'label':'Bandolim', 'head':'mandolin', 'tags':['Mandolin']},
    'ukulele': {'label':'Ukulele', 'head':'ukulele', 'tags':['Ukulele']},
    'harp': {'label':'Harpa', 'head':'harp', 'tags':['Harp']},
    'percussion': {'label':'Percussão adicional', 'head':'percussion', 'tags':['Percussion','Tambourine','Maraca','Shaker','Tabla','Conga']},
    'bells': {'label':'Sinos / campanas', 'head':'bells', 'tags':['Bell','Church bell','Glockenspiel','Chime','Wind chime']},
    'electric_piano': {'label':'Piano digital', 'head':'digital-piano', 'tags':['Electric piano','Keyboard (musical)']},
    'saxophone': {'label':'Saxofone', 'head':'saxophone', 'tags':['Saxophone']},
    'flute': {'label':'Flauta', 'head':'flute', 'tags':['Flute']},
    'violin': {'label':'Violino', 'head':'violin', 'tags':['Violin, fiddle']},
    'cello': {'label':'Violoncelo', 'head':'cello', 'tags':['Cello']},
    'trumpet': {'label':'Trompete', 'head':'trumpet', 'tags':['Trumpet']},
    'clarinet': {'label':'Clarinete', 'head':'clarinet', 'tags':['Clarinet']},
    'trombone': {'label':'Trombone', 'head':'trombone', 'tags':['Trombone']},
    'french_horn': {'label':'Trompa', 'head':'french-horn', 'tags':['French horn']},
    'harpsichord': {'label':'Cravo', 'head':'harpsichord', 'tags':['Harpsichord']},
    'sitar': {'label':'Sitar', 'head':'sitar', 'tags':['Sitar']},
    'marimba': {'label':'Marimba / xilofone', 'head':'marimba', 'tags':['Marimba, xylophone']},
    'tambourine': {'label':'Pandeiro / pandeirola', 'head':'tambourine', 'tags':['Tambourine']},
    'timpani': {'label':'Tímpanos', 'head':'timpani', 'tags':['Timpani']},
    'wind_chimes': {'label':'Carrilhão de vento', 'head':'wind-chimes', 'tags':['Wind chime']},
}

EXCLUSIVE_GROUPS = (('piano','electric_piano'), ('bowed_strings','violin','cello'),
                    ('woodwind','saxophone','flute','clarinet'),
                    ('brass','trumpet','trombone','french_horn'),
                    ('percussion','marimba','tambourine','timpani'),
                    ('bells','wind_chimes'))


def automatic_candidates():
    """Every supported head is evaluated, independently of title or old stems.

    Parents are candidates for an uncertain family, never extra tracks to add
    on top of its confirmed children. Resolution happens after inference.
    """
    return list(CATALOG)


def checked_selection(selection):
    if not isinstance(selection,list) or any(not isinstance(x,str) or x not in CATALOG for x in selection):
        raise ValueError('Selecione instrumentos disponíveis no catálogo.')
    selected=list(dict.fromkeys(selection))
    if len(selected)>18:
        raise ValueError('Escolha até 18 categorias por refinamento.')
    for group in EXCLUSIVE_GROUPS:
        if group[0] in selected and any(child in selected for child in group[1:]):
            raise ValueError('Escolha a família ou os instrumentos individuais, para evitar faixas sobrepostas.')
    return selected


def public_catalog():
    return {'instruments':[{'name':name,'label':item['label']} for name,item in CATALOG.items()],
            'exclusive_groups':EXCLUSIVE_GROUPS,
            'automatic_candidates':automatic_candidates(),
            'automatic_policy':'separate_then_verify',
            'download_bytes':1368919887,'processing':'local'}
