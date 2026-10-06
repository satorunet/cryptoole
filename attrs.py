"""Attributes (country, languages, cipher system, symbols, people, keywords) and relations between cases.
Used by udb.py build. Automatic values come from the sources; hand-made ones from data/attributes.csv and data/relations.csv.
See ID-SPEC.md, chapters "属性" and "関連"."""
import csv, json, re
from pathlib import Path
H = Path(__file__).resolve().parent

# ---- vocabularies -------------------------------------------------------------------------------------------
# modern country (ISO 3166-1 alpha-2), Japanese, English, and the names/places the sources use for it
COUNTRY = [
    ('VA', 'バチカン（教皇庁）', 'Vatican (Holy See)', r'Vatican|Papa[lc]|Holy See|Secretariat|Nunci'),
    ('IT', 'イタリア', 'Italy', r'Ital|Milan|Milano|\bRom[ae]\b|Toscana|Tuscan|Venice|Venezia|Florence|Firenze|Naples|Napoli|Genoa|Genova|Sardinia|Sicil|Mantova|Mantua|Siena|Modena|Ferrara|Cremona|Turin|Torino|Savoy|Savoie'),
    ('FR', 'フランス', 'France', r'France|Fran[cç]ais|Paris|Alsace|Lorraine|Lotharingia|Langres|Lyon|Bordeaux|Châlons|Nevers'),
    ('ES', 'スペイン', 'Spain', r'Spain|Spanish Monarchy|Hispania|Espa[ñn]a|Madrid|Simancas|Barcelona|Arag[oó]n|Castil'),
    ('PT', 'ポルトガル', 'Portugal', r'Portugal|Lisbon|Lisboa'),
    ('GB', 'イギリス', 'United Kingdom', r'England|Scotland|\bUK\b|\bUk\b|United Kingdom|Britain|London|\bKew\b|\bTNA\b|British Library|\bBL\b|Oxford|Cambridge|Sheffield|Wales|Hatfield'),
    ('IE', 'アイルランド', 'Ireland', r'Ireland|Dublin'),
    ('DE', 'ドイツ', 'Germany', r'German|Saxony|Saxon|Prussia|Prusse|Bavaria|Bayern|Hesse|Hessen|Marburg|Dresden|Berlin|Munich|München|Colonia|Cologne|Köln|Dortmund|Brandenburg|Hstam|BayHStA'),
    ('AT', 'オーストリア', 'Austria', r'Austria|Vienna|Wien|ÖStA|Österreich|Habsburg(?! Netherlands)'),
    ('HU', 'ハンガリー', 'Hungary', r'Hungar|Buda\b|Budapest|Eger\b|Mezőkövesd'),
    ('CZ', 'チェコ', 'Czechia', r'Czech|Bohemia|Prague|Praha'),
    ('PL', 'ポーランド', 'Poland', r'Poland|Polish|Krak[oó]w|Warsaw|Warszawa'),
    ('NL', 'オランダ', 'Netherlands', r'Netherlands(?!.*(Habsburg|Southern))|United Provinces|Holland|Batavian|Hague|Haag|Nimwegen|Amsterdam|Nationaal Archief'),
    ('BE', 'ベルギー', 'Belgium', r'Belgium|Flanders|Flandres|Habsburg Netherlands|Southern Netherlands|Brussels|Bruxelles|Low Countries|Rijksarchief'),
    ('CH', 'スイス', 'Switzerland', r'Switzerland|Swiss|Gen[eè]v|Zürich|Basel'),
    ('SE', 'スウェーデン', 'Sweden', r'Swed|Sverige|Stockholm|Uppsala|Riksarkivet'),
    ('DK', 'デンマーク', 'Denmark', r'Denmark|Danish|Copenhagen|København'),
    ('RU', 'ロシア', 'Russia', r'Russia|St\.? Petersburg|Moscow'),
    ('TR', 'トルコ（オスマン帝国）', 'Türkiye (Ottoman Empire)', r'Ottoman|Constantinople|Istanbul|Turkey'),
    ('GR', 'ギリシャ', 'Greece', r'Greece|Greek|Tessalonica|Thessalonica|Thessaloniki'),
    ('RO', 'ルーマニア', 'Romania', r'Romania|Transylvan|Cluj|Kolozsv'),
    ('US', 'アメリカ合衆国', 'United States', r'\bUSA\b|United States|America(?!s)|Connecticut|Washington'),
    ('BR', 'ブラジル', 'Brazil', r'Brazil|Pernambuco'),
    ('JP', '日本', 'Japan', r'Japan|Japanese'),
    ('CN', '中国', 'China', r'China|Chinese'),
]
LANGS = {'fr': ('フランス語', 'French', r'French|fran[cç]ais'), 'it': ('イタリア語', 'Italian', r'Italian|italiano'), 'es': ('スペイン語', 'Spanish', r'Spanish|español|castellano'),
         'en': ('英語', 'English', r'English'), 'de': ('ドイツ語', 'German', r'German|Deutsch'), 'la': ('ラテン語', 'Latin', r'Latin'),
         'nl': ('オランダ語', 'Dutch', r'Dutch|Nederlands'), 'hu': ('ハンガリー語', 'Hungarian', r'Hungarian|magyar'), 'sv': ('スウェーデン語', 'Swedish', r'Swedish|svenska'),
         'da': ('デンマーク語', 'Danish', r'Danish|dansk'), 'pl': ('ポーランド語', 'Polish', r'Polish|polski'), 'pt': ('ポルトガル語', 'Portuguese', r'Portuguese|português'),
         'ru': ('ロシア語', 'Russian', r'Russian'), 'cs': ('チェコ語', 'Czech', r'Czech'), 'el': ('ギリシア語', 'Greek', r'Greek'), 'ja': ('日本語', 'Japanese', r'Japanese')}
SYSTEM = {'simple': ('単一換字', 'Simple substitution'), 'homophonic': ('同音異字換字', 'Homophonic substitution'), 'polyphonic': ('多音換字', 'Polyphonic substitution'),
          'nomenclator': ('ノメンクレーター', 'Nomenclator'), 'codebook': ('コード（符号書）', 'Codebook'), 'transposition': ('転置', 'Transposition'),
          'polyalphabetic': ('多表式', 'Polyalphabetic'), 'digraphic': ('二文字換字', 'Digraphic substitution'), 'machine': ('機械式', 'Machine cipher')}
DEC_SYS = {'1': 'simple', '2': 'homophonic', '3': 'transposition', '4': 'polyalphabetic', '5': 'nomenclator', '7': 'polyphonic', '8': 'codebook'}   # '6' = Unknown
SYMBOL = {'numerical': ('数字', 'Numerals'), 'alphabet': ('アルファベット', 'Letters'), 'graphic': ('図形記号', 'Graphic signs'), 'other': ('その他の記号', 'Other signs')}
DEC_SYM = {'1': 'numerical', '3': 'alphabet', '8': 'graphic', '7': 'other'}
REL = {'decipherment-of': ('解読文・写し', 'Decipherment / copy'), 'key-of': ('鍵', 'Key'), 'same-key': ('同じ鍵', 'Same key'),
       'same-correspondence': ('同じ差出人と宛先', 'Same correspondents'), 'sibling': ('同じ時期・同じ束の書簡', 'Sibling letters'),
       'reply-to': ('返信', 'Reply'), 'similar-system': ('似た方式', 'Similar system'), 'cited': ('一緒に言及', 'Cited together'), 'overlap': ('一部が同じ資料', 'Overlapping material')}

def countries(*texts):
    t = ' '.join(x for x in texts if x)
    return [c for c, _, _, rx in COUNTRY if re.search(rx, t)]

def langs(*texts):
    t = ' '.join(x for x in texts if x)
    return [k for k, v in LANGS.items() if re.search(v[2], t, re.I)]

def load_raw(db):
    return {f'decode:{i}': json.loads(j.replace('&amp;lsquot;', '’').replace('&lsquot;', '’')) for i, j in db.execute('SELECT id, json FROM decode_raw')}

def manual_attrs():
    """data/attributes.csv: id,field,value,note  (field: country, city, plaintext_lang, system, person, keyword)"""
    f = H / 'data' / 'attributes.csv'; out = {}
    if f.exists():
        for r in csv.DictReader(f.open(encoding='utf-8')):
            if r.get('id') and r.get('field') and r.get('value'):
                out.setdefault(r['id'].strip(), []).append((r['field'].strip(), r['value'].strip()))
    return out

def record_attrs(rec, raw, cs_cat):
    """Attributes of one source record (an `entries` row as a dict)."""
    src, key = rec['src'], rec['key']
    a = {'co': [], 'oc': '', 'ci': '', 'ho': [], 'lp': [], 'lc': [], 'sy': [], 'sb': [], 'pe': [], 'kw': [], 'auto': True}
    if src == 'decode':
        x = raw.get(f'decode:{key}', {})
        a['oc'] = (x.get('origin_region') or '').strip(' .')
        a['ci'] = (x.get('origin_city') or '').strip()
        a['co'] = countries(a['oc'], a['ci'])
        a['ho'] = countries(x.get('current_country') or '', x.get('current_city') or '', x.get('current_holder') or '')
        a['lp'] = langs(x.get('plaintext_lang') or '')
        a['lc'] = langs(x.get('cleartext_lang') or '')
        a['sy'] = [DEC_SYS[c] for c in str(x.get('cipher_types') or '').split(',') if c in DEC_SYS]
        a['sb'] = [DEC_SYM[c] for c in str(x.get('symbol_sets') or '').split(',') if c in DEC_SYM]
        a['pe'] = [p for p in (x.get('author'), x.get('sender'), x.get('receiver')) if p and p.strip() not in ('', '...', '?')]
        a['pg'] = int(x['number_of_pages']) if str(x.get('number_of_pages') or '').strip().isdigit() and int(x['number_of_pages']) > 0 else 0
    elif src == 'cyphersolver':
        x = cs_cat.get(key, {})
        a['oc'] = (x.get('place') or '').split('→')[0].strip()
        a['co'] = countries(a['oc'], x.get('region') or '')
        a['ho'] = countries(x.get('shelfmark') or '')
        a['lp'] = langs(x.get('language') or '')
        a['pe'] = [p.strip(" '‘’") for p in re.split(r'→|->', x.get('correspondents') or '') if p.strip() and not re.match(r'(?i)unknown|\?', p.strip())]
    elif src == 'cryptocellar':
        a['co'] = ['DE']; a['oc'] = 'German Army (Wehrmacht)'; a['lp'] = ['de']
        a['sy'] = ['digraphic'] if 'Truppenschlüssel' in rec['grp'] else ['machine']
        a['sb'] = ['alphabet']
    elif src == 'rosson':
        a['ho'] = countries(rec.get('shelfmark') or '')
        a['co'] = countries(rec['title_en'])
    elif src == 'cryptiana':
        a['ho'] = countries(rec['title_en'])
        a['co'] = countries(rec['title_en'])
    a['lp'] = a['lp'] or langs(rec.get('language') or '')
    return a

def merge_attrs(items):
    """Union of several records' attributes (for a grouped row): order kept, duplicates dropped."""
    out = {'co': [], 'oc': '', 'ci': '', 'ho': [], 'lp': [], 'lc': [], 'sy': [], 'sb': [], 'pe': [], 'kw': []}
    for a in items:
        for k in ('co', 'ho', 'lp', 'lc', 'sy', 'sb', 'pe', 'kw'):
            for v in a.get(k, []):
                if v not in out[k]: out[k].append(v)
        for k in ('oc', 'ci'):
            out[k] = out[k] or a.get(k, '')
    out['pe'] = out['pe'][:12]
    return out

def apply_manual(a, rows):
    key = {'country': 'co', 'city': 'ci', 'plaintext_lang': 'lp', 'system': 'sy', 'person': 'pe', 'keyword': 'kw'}
    for f, v in rows:
        k = key.get(f)
        if not k: continue
        if k == 'ci': a['ci'] = v
        elif v not in a[k]: a[k].append(v)
    return a

# ---- relations ------------------------------------------------------------------------------------------------
def manual_relations():
    """data/relations.csv: a,b,type,source,note — record or row ids (e.g. decode:9451, cyphersolver:183)."""
    f = H / 'data' / 'relations.csv'; out = []
    if f.exists():
        for r in csv.DictReader(f.open(encoding='utf-8')):
            if r.get('a') and r.get('b') and r.get('type') in REL:
                out.append((r['a'].strip(), r['b'].strip(), r['type'], 'manual', (r.get('source') or '').strip(), (r.get('note') or '').strip()))
    return out

def auto_relations(raw, people_of):
    """Relations found in the sources:
    - DECODE notes that cite other DECODE records ('This is a decipherment of … (DECODE no.3827)', 'key …');
    - the same writer and recipient on different rows (people_of: row id -> (writer, recipient))."""
    out = []
    for rid, x in raw.items():
        info = re.sub(r'<[^>]+>', ' ', x.get('additional_information') or '')
        for m in re.finditer(r'(?:DECODE|DECRYPT|record)\s*(?:no\.?|nr\.?|R|#)\s*(\d{2,5})', info, re.I):
            tgt = f'decode:{m.group(1)}'
            if tgt == rid or tgt not in raw: continue
            ctx = info[max(0, m.start() - 120):m.start()].lower()
            ty = 'decipherment-of' if 'decipher' in ctx or 'decrypt' in ctx else 'key-of' if re.search(r'\bkey\b', ctx) else 'cited'
            out.append((rid, tgt, ty, 'auto', 'DECODE', ''))
    pairs = {}
    for row, (w, r) in people_of.items():
        known = lambda s: s and not re.fullmatch(r"(?i)[\s?()'\[\]-]*(unknown|anonymous|anon\.?|n/?a|none|inconnu|unbekannt|sconosciuto|desconocido)?[\s?()'\[\]-]*(sender|recipient|writer|author|receiver)?[\s?()'\[\].-]*", s)
        if known(w) and known(r): pairs.setdefault((w.lower(), r.lower()), []).append(row)
    for rows in pairs.values():
        if 1 < len(rows) <= 40:
            for i, a in enumerate(rows):
                for b in rows[i + 1:]:
                    out.append((a, b, 'same-correspondence', 'auto', '', ''))
    return out
