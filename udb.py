"""/crypt/unsolved/ : a Japanese database of unsolved historical ciphers, merged from public lists.

Sources (re-imported on every `import`; Japanese text is kept in its own table and survives):
  cryptiana     S. Tomokiyo, Unsolved Historical Ciphers  (../tomokiyo/unsolved_status.json, made by tomokiyo/build.py)
  cyphersolver  D. Bourdeau, Unsolved Catalogue           (../bourdeau/source-catalogue.json.log, made by bourdeau/build.py)
  cryptocellar  F. Weierud, unbroken German Army messages (fetched live from cryptocellar.org/bgac/)
Only titles, dates, shelfmarks, statuses and links are taken; no article text.

  python3 udb.py import              refresh from the sources
  python3 udb.py pending > p.json    entries still lacking Japanese (src, key, title_en, …)
  python3 udb.py ja p-done.json      load Japanese: [{"src","key","title_ja","note_ja"}]
  python3 udb.py same GRP 'why' src:key src:key …   mark entries in several sources as the same cipher (checked by hand;
                                     the first one is the main row, the others are shown as further sources)
  python3 udb.py build               write index.html, entries.json, udb.py.txt"""
import datetime, email.utils, hashlib, html, json, re, sqlite3, sys, unicodedata, urllib.parse, urllib.request
from pathlib import Path
H = Path(__file__).resolve().parent
C = H.parent
sys.path.insert(0, str(H))   # sidemenu.py lives next to this file
import sidemenu   # shared ☰ drawer pieces and the public address of the search engine
DB = H / 'unsolved.sqlite'
UA = {'User-Agent': 'Mozilla/5.0 (satoru.net crypt index)'}

SCHEMA = '''
CREATE TABLE IF NOT EXISTS entries(
  src TEXT NOT NULL, key TEXT NOT NULL,
  title_en TEXT NOT NULL, grp TEXT NOT NULL DEFAULT '',
  date_text TEXT NOT NULL DEFAULT '', year INTEGER, sortdate TEXT NOT NULL DEFAULT '',
  language TEXT NOT NULL DEFAULT '', shelfmark TEXT NOT NULL DEFAULT '',
  cat TEXT NOT NULL CHECK(cat IN ('open','part','key','solved','na')), status_src TEXT NOT NULL DEFAULT '',
  url TEXT NOT NULL, slug TEXT NOT NULL DEFAULT '',
  first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, gone INTEGER NOT NULL DEFAULT 0,
  solved_on TEXT NOT NULL DEFAULT '', solved_by TEXT NOT NULL DEFAULT '', rtype TEXT NOT NULL DEFAULT 'cipher',
  PRIMARY KEY(src, key));
CREATE TABLE IF NOT EXISTS ja(
  src TEXT NOT NULL, key TEXT NOT NULL, title_ja TEXT NOT NULL, note_ja TEXT NOT NULL DEFAULT '',
  PRIMARY KEY(src, key));
CREATE INDEX IF NOT EXISTS entries_sort ON entries(sortdate);
CREATE TABLE IF NOT EXISTS same(
  grp TEXT NOT NULL, ord INTEGER NOT NULL, src TEXT NOT NULL, key TEXT NOT NULL,
  PRIMARY KEY(src, key));
CREATE TABLE IF NOT EXISTS same_note(grp TEXT PRIMARY KEY, note TEXT NOT NULL, checked TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS same_auto(src TEXT NOT NULL, key TEXT NOT NULL, rid TEXT NOT NULL, PRIMARY KEY(src, key, rid));
'''
SRC = {'cryptiana': ('Cryptiana（友清氏）', 'Cryptiana (Tomokiyo)', 'https://cryptiana.web.fc2.com/code/unsolved.htm'),
       'cyphersolver': ('cyphersolver（Bourdeau）', 'cyphersolver (Bourdeau)', 'https://dbourdeau.github.io/cyphersolver/catalogue.html'),
       'cryptocellar': ('CryptoCellar（Weierud）', 'CryptoCellar (Weierud)', 'https://cryptocellar.org/bgac/'),
       'decode': ('DECODE（DECRYPT）', 'DECODE (DECRYPT)', 'https://de-crypt.org/decrypt-web/RecordsList'),
       'rosson': ('cipher-readings（Rosson）', 'cipher-readings (Rosson)', 'https://github.com/pangoleen/cipher-readings')}
TABL = {'all': ('全て', 'All'), 'open': ('未解読', 'Unsolved'), 'solved': ('解読済', 'Solved'), 'na': ('不明', 'Unknown')}   # tiny labels under the status tabs
CAT = {'open': ('未解決', 'unsolved', '#a3161b'), 'part': ('一部', 'partly', '#b7791f'),
       'key': ('鍵のみ', 'key only', '#3b6fb0'), 'solved': ('解決', 'solved', '#2e7d4f'), 'na': ('状況不明', 'status unknown', '#7a7468')}
TOP = {'open': 'open', 'part': 'open', 'key': 'open', 'solved': 'solved', 'na': 'na'}   # shown as two classes; part/key become a qualifier on 未解決
def badge(cat):
    top = TOP[cat]
    q = f'<span class="q q-{cat}">{T(*CAT[cat][:2])}</span>' if cat != top else ''
    return f'<span class="badge" style="background:{CAT[top][2]}">{T(*CAT[top][:2])}{q}</span>'
# this site's pages, matched on title or shelfmark
OURS = [('vizani1637', r'Vizani|fr\.? ?16158'), ('1592_dinteville', r'Dinteville|fr\.? ?3621'), ('mayenne1586', r'fr\.? ?15572'),
        ('baugy1616', r'Baugy|Clair(?:ambault)?\.? ?369 ff?\. ?2\b'), ('ibarra1592', r'fr\.? ?3641'), ('perez1579', r'es(?:pagnol)?\.? ?132')]
MON = {m: i for i, m in enumerate(['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'], 1)}

def connect():
    db = sqlite3.connect(DB, timeout=120); db.row_factory = sqlite3.Row; db.execute('PRAGMA journal_mode=WAL'); db.executescript(SCHEMA)
    cols = {r[1] for r in db.execute('PRAGMA table_info(entries)')}
    if "'na'" not in db.execute("SELECT sql FROM sqlite_master WHERE name='entries'").fetchone()[0]:   # widen the status CHECK (2026-10-05)
        old = [r[1] for r in db.execute('PRAGMA table_info(entries)')]
        db.executescript('ALTER TABLE entries RENAME TO entries_old;' + SCHEMA)
        new = [r[1] for r in db.execute('PRAGMA table_info(entries)')]
        c = ','.join(x for x in old if x in new)
        db.executescript(f'INSERT INTO entries({c}) SELECT {c} FROM entries_old; DROP TABLE entries_old;')
        cols = set(new)
    for c, dflt in (('solved_on', ''), ('solved_by', ''), ('rtype', 'cipher'),
                    ('src_created', ''), ('src_updated', ''), ('src_scope', ''), ('chash', ''), ('changed_on', '')):   # source dates and change detection (2026-10-06)
        if c not in cols: db.execute(f"ALTER TABLE entries ADD COLUMN {c} TEXT NOT NULL DEFAULT '{dflt}'")
    return db

def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read().decode('utf-8', errors='replace')

def sortdate(text, year=None):
    """'YYYY-MM-DD' (month/day 00 when unknown) from the first date in text, else from year."""
    m = re.search(r'\b(\d{1,2})\s+([A-Z][a-z]{2})[a-z]*\.?\s+(1[0-9]{3})\b', text)
    if m and m.group(2).lower() in MON:
        return f'{m.group(3)}-{MON[m.group(2).lower()]:02d}-{int(m.group(1)):02d}'
    m = re.search(r'\b([A-Z][a-z]{2})[a-z]*\.?\s+(1[0-9]{3})\b', text)
    if m and m.group(1).lower() in MON:
        return f'{m.group(2)}-{MON[m.group(1).lower()]:02d}-00'
    m = re.search(r'\b(1[0-9]{3})(?:s\b)?', text)
    y = (int(m.group(1)) if m else None) or year   # the first year written (a span sorts by its start)
    return f'{y:04d}-00-00' if y else ''

def slug_for(*texts):
    t = ' '.join(texts)
    return next((s for s, rx in OURS if re.search(rx, t, re.I)), '')

# when a Cryptiana entry was solved: the first dated sentence that reports a solution (as Tomokiyo wrote it)
M='January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec'
ACT=r'\b(?:solved|deciphered|decrypted|broken|broke|cracked|notified me of (?:his|her|their) (?:full )?solution|published (?:his|her|their|a|the)? ?(?:full )?(?:solution|decipherment)|provided me with|solution (?:by|was)|was solved|found the key|finding the key|results were published|[Ss]olution of .{0,220}? was published|reads this)\b'
NEG=r'\b(?:undeciphered|unsolved|remains?|appears?|seems?|not been|yet to)\b'
def solved_info(body, by=''):
    sents=re.split(r'(?<!\s[A-Z]\.)(?<=[.!?])\s+',body)   # not after an initial ("Lawren M. Smithline")
    good=[s for s in sents if re.search(ACT,s,re.I) and not re.search(NEG,s,re.I)]
    for s in good:
        for m in re.finditer(r'\b(\d{1,2}) ('+M+r')\.? (\d{4})\b',s):
            if int(m.group(3))>=1990: return f'{m.group(1)} {m.group(2)} {m.group(3)}',s
    y=re.search(r'\((\d{4})\)',by or '')
    if y: return y.group(1),'by'
    for s in good:
        m=re.search(r'\b('+M+r')\.? (\d{4})\b',s)
        if m and int(m.group(2))>=1990: return f'{m.group(1)} {m.group(2)}',s
        m=re.search(r'\b(?:in|In) (\d{4})\b',s) or re.search(r'\((\d{4})\)',s)
        if m and 1800<int(m.group(1))<=2026: return m.group(1),s
    return '',''

_N = r"[A-Z][\w'À-ſ-]*\.?(?:\s+(?:de|van|von|la|du|[A-Z][\w'À-ſ-]*\.?)){1,3}"
NAME_RX = _N + r"(?:(?:,\s*and\s+|,\s*|\s+and\s+)" + _N + r")*"
def solver_in(s, title=''):
    """Who solved, from the sentence that dates the solution."""
    if re.search(r'\bsolved by satorunet\b', s): return 'satorunet'
    if re.search(r'\bI (?:solved|found|reconstructed)\b|\bby the present author\b|\bMy own\b', s): return 'Satoshi Tomokiyo'
    for rx in (r'\b(?:solved|broken|broke|deciphered|solution|decipherment)(?: [a-z]+){0,3} by (' + NAME_RX + r')',
               r'(' + NAME_RX + r')(?:,[^,]{0,40},)? (?:notified me|published|provided me|solved|broke|found that|deciphered)',
               r'\bby (' + NAME_RX + r')'):
        for m in re.finditer(rx, s):
            n = m.group(1).strip().rstrip('.')
            plain = lambda x: unicodedata.normalize('NFKD', x).encode('ascii', 'ignore').decode()
            if re.match(r'(?:The|This|These|In|As|Of|See)\b', n) or plain(n.split()[-1]) in plain(title): continue
            return n
    return ''

def cryptiana_bodies():
    u = (C / 'tomokiyo/source-unsolved.htm.log').read_bytes().decode('shift_jis', errors='replace')
    tx = lambda x: ' '.join(html.unescape(re.sub(r'<[^>]+>', '', x)).split())
    return {tx(re.sub(r'<font[^>]*>.*?</font>', '', m.group(1), flags=re.S | re.I)): tx(m.group(2))
            for m in re.finditer(r'<H3[^>]*>(.*?)</H3>(.*?)(?=<H3|<H2|</BODY|$)', u, re.S | re.I)}

def cryptiana():
    bodies = cryptiana_bodies()
    for x in json.loads((C / 'tomokiyo/unsolved_status.json').read_text(encoding='utf-8')):
        dp = re.search(r'\(([^()]*\d{3,4}[^()]*)\)\s*$', x['title'])   # Cryptiana writes the date in the title: "(1653-1654)", "(c.1590)", "(1665, 1673, 1674)"
        sd = sortdate(dp.group(1) if dp else '') or sortdate(x['title']) or sortdate(x['group'])
        so, sent = solved_info(bodies.get(x['title'], ''), x['by']) if x['cat'] != 'open' else ('', '')
        plain = lambda s: unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
        by = re.sub(r'\s*\(\d{4}\)$', '', x['by'] or '')
        if by and plain(by.split()[-1]) in plain(x['title']): by = ''
        who = by or (solver_in(sent, x['title']) if sent and sent != 'by' else '')
        yield dict(key=x['title'], title_en=x['title'], grp=x['group'], date_text=dp.group(1) if dp else '', year=int(sd[:4]) if sd else None, sortdate=sd,
                   cat=x['cat'], status_src=x['status'] or 'Unsolved', url=x['url'], slug=slug_for(x['title']),
                   solved_on=so, solved_by=who)

# cyphersolver entries link to their own write-up page (docs/<slug>.html), else to their expanded row in the catalogue (#e<id>). Hand-matched where the catalogue text names no page (checked 2026-10-05).
CS_PAGE = {183: 'dinteville1592', 214: 'hellen1752', 223: 'hellen1752', 87: 'percy1559', 137: 'conley1652',
           225: 'dedem1788', 320: 'rohan1636', 161: 'kaa4591', 125: 'r8361'}
def cs_url(x, slugs):
    s = ' '.join(str(x.get(k, '')) for k in ('status', 'outcome', 'score_note', 'verify'))
    refs = re.findall(r'(?:write-up |docs/)([\w-]+)\.html', s) + re.findall(r'targets/([\w.-]+?)/', s)
    pg = CS_PAGE.get(x['id']) or next((z for z in refs if z in slugs), None)
    if pg: return SRC['cyphersolver'][2].rsplit('/', 1)[0] + f'/{pg}.html'
    return f'{SRC["cyphersolver"][2]}#e{x["id"]}'   # the catalogue opens that entry's detail row for #e<id>

def cyphersolver():
    slugs = {q['slug'] for q in json.loads((C / 'bourdeau/source-docs_pages.json.log').read_text(encoding='utf-8'))}
    for x in json.loads((C / 'bourdeau/source-catalogue.json.log').read_text(encoding='utf-8'))['entries']:
        sd = sortdate(x.get('date', ''), x.get('year'))
        yield dict(key=str(x['id']), title_en=x['title'], grp=x.get('region', '') or '', date_text=x.get('date', ''), year=x.get('year'),
                   sortdate=sd, language=x.get('language', ''), shelfmark=x.get('shelfmark', ''), cat='open', status_src=x.get('outcome') or 'open',
                   url=cs_url(x, slugs), slug=slug_for(x['title'], x.get('shelfmark', '')))

def cryptocellar():
    B = 'https://cryptocellar.org/bgac/'
    pages = {'g-army-messages.html': ('Army Enigma', 'German Army Enigma message'), 'g-army-july-1941.html': ('Army Enigma', 'German Army Enigma message'),
             'ultimate-enigma.html': ('Ultimate Enigma Challenge', 'Enigma message (possibly an unknown machine)'),
             'g-army-ts-messages.html': ('Truppenschlüssel', 'German Army Truppenschlüssel message')}
    seen = set()
    for pg, (grp, what) in pages.items():
        t = get(B + pg)
        s = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', re.sub(r'(?s)<(script|style).*?</\1>', '', t))))
        for m in re.finditer(r'message of (\d\d)\.(\d\d)\.(\d{4}), Nr\. ?([\w/ ]+?) ?, \(([A-Z\-]{5})\):(.{0,60})', s):
            d, mo, y, nr, ind, tail = m.groups()
            k = f'{y}-{mo}-{d} {ind} {nr.strip()}'
            if k in seen or re.search(r'\bBroken\b', tail):
                continue
            if grp == 'Army Enigma' and ind in {'BYQMZ', 'FKQLZ', 'XFEDT'}:   # also part of the Ultimate challenge; keep once there
                continue
            seen.add(k)
            yield dict(key=k, title_en=f'{what} {ind}, Nr. {nr.strip()}, {int(d)} {datetime.date(int(y), int(mo), 1):%b} {y}', grp=grp,
                       date_text=f'{d}.{mo}.{y}', year=int(y), sortdate=f'{y}-{mo}-{d}', language='German', cat='open', status_src='unbroken',
                       url=B + pg + '#:~:text=' + urllib.parse.quote(f'({ind})'))


# DECODE: every record, from decode_fetch.py's tables (list for all, detail where fetched)
DEC_ST = {'1': ('solved', 'Decrypted'), '2': ('open', 'Non-decrypted'), '3': ('part', 'Partially decrypted'), '4': ('na', 'N/A')}
DEC_TY = {'1': 'cipher', '2': 'key', '3': 'manual'}
def decode(db=None):
    db = db or connect()
    raw = {i: json.loads(j) for i, j in db.execute('SELECT id, json FROM decode_raw')} if db.execute("SELECT 1 FROM sqlite_master WHERE name='decode_raw'").fetchone() else {}
    tx = lambda s: ' '.join(html.unescape(re.sub(r'<[^>]+>', ' ', s or '')).replace('&lsquot;', '’').split())   # DECODE writes apostrophes as the non-entity '&lsquot;'
    for i, j in db.execute('SELECT id, json FROM decode_list ORDER BY id'):
        L = json.loads(j); R = raw.get(i, {})
        hb = re.match(r'<b>(.*?)</b>,?(.*?)<br><small>(.*?)</small>', L.get('c_holder') or '', re.S)
        city, holder, name = (tx(hb.group(1)), tx(hb.group(2)), tx(hb.group(3))) if hb else ('', tx(L.get('c_holder')), '')
        ab = re.match(r'<b>(.*?)</b><br/?>(.*)', L.get('c_author') or '', re.S)
        author = tx(R.get('author')) or (tx(ab.group(1)) if ab else '')
        origin = ' '.join(x for x in (tx(R.get('origin_region')), tx(R.get('origin_city'))) if x) or (tx(ab.group(2)) if ab else '')
        if not origin: origin = 'held: ' + ' '.join(x for x in (city, holder) if x)   # no origin given: fall back to where it is kept
        recv, send = tx(R.get('receiver')), tx(R.get('sender'))
        who = author or send
        ty = DEC_TY.get(L.get('record_type') or '', '')
        if who and recv: t = f'{who} to {recv}'
        elif who: t = who
        else: t = name or f'Record {i}'
        if ty == 'key': t = 'Key: ' + t
        sy, sm, sd = R.get('start_year'), R.get('start_month'), R.get('start_day')
        ok = lambda v, lo, hi: str(v).isdigit() and lo <= int(v) <= hi   # DECODE has a few impossible months/days
        if not ok(sy, 1, 2100): sy = None
        if not ok(sm, 1, 12): sm, sd = None, None
        if not ok(sd, 1, 31): sd = None
        ey, em, ed = R.get('end_year'), R.get('end_month'), R.get('end_day')
        if not ok(ey, 1, 2100): ey = None
        if not ok(em, 1, 12): em, ed = None, None
        if not ok(ed, 1, 31): ed = None
        if sm and int(sm) == 1 and (sd is None or int(sd) == 1) and (not ey or (em and int(em) == 12 and (ed is None or int(ed) == 31)) or not em): sm, sd = None, None   # DECODE fills 1 Jan … 31 Dec when only years are known
        if em and int(em) == 12 and (ed is None or int(ed) == 31) and (ey != sy or not sm): em, ed = None, None   # 31 Dec closing a span of years, or a year given as 1 Jan – 31 Dec, is DECODE's fill-in
        one = lambda y, m, d: f'{int(d)} {datetime.date(2000, int(m), 1):%b} {y}' if d and m else (f'{datetime.date(2000, int(m), 1):%b} {y}' if m else str(y))
        if sy:
            dt = one(sy, sm, sd)
            if ey and one(ey, em, ed) != dt and int(ey) >= int(sy): dt += ' – ' + one(ey, em, ed)   # a span, as DECODE gives it (e.g. 1400 – 1599)
        else: dt = tx(L.get('c_cates')).strip(' -')
        lm = re.findall(r'<b>(?:Cleartext|Plaintext):</b>([^<]*)', L.get('c_lang') or '')
        cat, st = DEC_ST.get(L.get('status') or '', ('na', ''))
        yield dict(key=str(i), title_en=t, grp=origin, date_text=dt, year=int(sy) if sy else None, sortdate=sortdate(dt),
                   language=', '.join(x.strip() for x in lm if x.strip()), shelfmark=', '.join(x for x in (city, holder) if x).strip(' ,'),
                   cat=cat, status_src=st or 'N/A', url=f'https://de-crypt.org/decrypt-web/RecordsView/{i}', rtype=ty or 'other',
                   slug=slug_for(t, holder), name=name)

# Paolo Rosson's cipher-readings (GitHub, MIT licence): results table of the README, plus his two sister repositories
def rosson():
    md = get('https://raw.githubusercontent.com/pangoleen/cipher-readings/main/README.md')
    rows = re.findall(r'^\| \[([\w-]+)\]\([\w-]+/?\) \| (.+?) \| (.+?) \| (.+?) \|$', md, re.M)
    m = re.search(r'\[(centurione-1528)\]\(centurione-1528/?\)\. (.+?)\n\n', md, re.S)
    extra = [('centurione-1528', 'The "Venetian?" cipher with superscript digits of 1528 (BnF fr. 3022, no. 20, and the letters signed "Hieronimo Ranzo" in fr. 2988)', 'a code of stems with a small alphabet of single letters for the endings', 'read for the greater part; 86 % reads as connected sense')] if m and not any(r[0] == 'centurione-1528' for r in rows) else []
    for name in ('desportes-1593', 'senecey-1594'):
        try:
            d = json.loads(get(f'https://api.github.com/repos/pangoleen/{name}'))
            extra.append((name, d.get('description') or name, '', 'read'))
        except Exception:
            pass
    plain = lambda s: re.sub(r'\*|\[([^\]]+)\]\([^)]+\)', lambda z: z.group(1) or '', s).strip()
    for folder, doc, new, state in [(a, b, c, d) for a, b, c, d in rows] + extra:
        doc, new, state = plain(doc), plain(new), plain(state)
        sh = re.findall(r'\(([^()]*(?:BnF|British Library|MS|fr\.|Espagnol|Clairambault|Thurloe|Colbert)[^()]*)\)', doc)
        title = re.sub(r'\s*\([^()]*\)\s*$', '', doc).strip() if sh else doc
        cat = 'solved' if (re.search(r'(?i)all cipher passages read|pieces read|first full reading|first time|groups fit', state + ' ' + doc) or state == 'read') and not re.search(r'(?i)in large part|greater part|gaps|\d+ ?%', state) else 'part'
        if folder in ('desportes-1593', 'senecey-1594'): title = re.sub(r',? made with .*$', '', re.sub(r'\s*\([^()]*\)', '', doc)).strip()
        url = (f'https://pangoleen.github.io/cipher-readings/{folder}.html' if folder not in ('desportes-1593', 'senecey-1594') else f'https://github.com/pangoleen/{folder}')
        dt = re.search(r'\b(\d{1,2} [A-Z][a-z]+ \d{4})\b', doc) or re.search(r'\b(1[4-8]\d\d)\b', doc)
        yield dict(key=folder, title_en=title, grp='', date_text=dt.group(1) if dt else '', year=None, sortdate=sortdate(dt.group(1) if dt else folder),
                   language='', shelfmark=sh[-1] if sh else '', cat=cat, status_src=state[:200] or 'read', url=url,
                   solved_on='October 2026', solved_by='Paolo Rosson', slug=slug_for(title, sh[-1] if sh else ''))

def do_import(db):
    now = datetime.date.today().isoformat()
    for src, fn in (('cryptiana', cryptiana), ('cyphersolver', cyphersolver), ('cryptocellar', cryptocellar), ('decode', decode), ('rosson', rosson)):
        try:
            items = list(fn(db) if src == 'decode' else fn())   # decode reads its tables through the same connection
        except Exception as x:
            print(src, 'skipped:', x); continue
        keys = set()
        old = {k: h for k, h in db.execute('SELECT key, chash FROM entries WHERE src=?', (src,))}
        for r in items:
            r = {**dict(grp='', date_text='', year=None, language='', shelfmark='', slug='', solved_on='', solved_by='', rtype='cipher'), **r}
            r.pop('name', None)
            keys.add(r['key'])
            h = hashlib.sha1(json.dumps([r.get(k) for k in ('title_en', 'grp', 'date_text', 'shelfmark', 'language', 'cat', 'status_src', 'solved_on', 'solved_by', 'rtype')]
                                        + ([raw_of(db, r['key'])] if src == 'decode' else []), ensure_ascii=False).encode()).hexdigest()[:16]
            changed = old.get(r['key']) and old[r['key']] != h
            db.execute('''INSERT INTO entries(src,key,title_en,grp,date_text,year,sortdate,language,shelfmark,cat,status_src,url,slug,first_seen,last_seen,gone,solved_on,solved_by,rtype)
                          VALUES(:src,:key,:title_en,:grp,:date_text,:year,:sortdate,:language,:shelfmark,:cat,:status_src,:url,:slug,:now,:now,0,:solved_on,:solved_by,:rtype)
                          ON CONFLICT(src,key) DO UPDATE SET title_en=excluded.title_en,grp=excluded.grp,date_text=excluded.date_text,year=excluded.year,
                          sortdate=excluded.sortdate,language=excluded.language,shelfmark=excluded.shelfmark,cat=excluded.cat,status_src=excluded.status_src,
                          url=excluded.url,slug=excluded.slug,last_seen=excluded.last_seen,gone=0,solved_on=excluded.solved_on,solved_by=excluded.solved_by,rtype=excluded.rtype''', dict(r, src=src, now=now))
            db.execute('UPDATE entries SET chash=?' + (', changed_on=?' if changed else '') + ' WHERE src=? AND key=?', (h, now, src, r['key']) if changed else (h, src, r['key']))
        # gone from the source list: for cryptocellar that means it was broken
        for (k,) in db.execute('SELECT key FROM entries WHERE src=? AND gone=0', (src,)).fetchall():
            if k not in keys:
                db.execute('UPDATE entries SET gone=1 WHERE src=? AND key=?', (src, k))
        print(src, len(items))
    auto_same(db)
    source_dates(db)
    db.execute('CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT)')
    db.execute("INSERT OR REPLACE INTO meta VALUES('last_fetch', ?)", (datetime.datetime.now(JST).isoformat(timespec='minutes'),))   # shown as 最終取得 with the time
    db.commit()

def raw_of(db, key):
    r = db.execute('SELECT json FROM decode_raw WHERE id=?', (int(key),)).fetchone() if key.isdigit() else None
    return {k: v for k, v in json.loads(r[0]).items() if k not in ('c_holder', 'c_author', 'c_lang', 'c_cates')} if r else {}

def source_dates(db):
    """Dates the sources give: src_created (DECODE: the record's creation date), src_updated with src_scope saying what was updated —
    'record' (GitHub history of the record's own folder), 'page' (the write-up page or the article), 'list' (the whole list page; no date per record)."""
    memo = {}
    def gh(repo, path=''):   # latest commit date on GitHub, for a path or the whole repository
        k = ('gh', repo, path)
        if k not in memo:
            try:
                d = json.loads(get(f'https://api.github.com/repos/{repo}/commits?per_page=1' + (f'&path={urllib.parse.quote(path)}' if path else '')))
                memo[k] = d[0]['commit']['committer']['date'][:10] if d else ''
            except Exception: memo[k] = ''
        return memo[k]
    def lm(url):   # Last-Modified of a page
        url = url.split('#')[0]
        if url not in memo:
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=UA, method='HEAD'), timeout=60) as r:
                    v = r.headers.get('Last-Modified')
                memo[url] = email.utils.parsedate_to_datetime(v).date().isoformat() if v else ''
            except Exception: memo[url] = ''
        return memo[url]
    rows = db.execute("SELECT src, key, url FROM entries WHERE gone=0").fetchall()
    cre = {str(i): (json.loads(j).get('creation_date') or '')[:10] for i, j in db.execute('SELECT id, json FROM decode_raw')}
    for src, key, url in rows:
        c, up, sc = '', '', ''
        if src == 'decode': c = cre.get(key, '')
        elif src == 'cyphersolver':
            m = re.match(r'https://dbourdeau\.github\.io/cyphersolver/([\w.-]+\.html)', url or '')
            if m: up, sc = gh('dbourdeau/cyphersolver', 'docs/' + m.group(1)), 'list' if m.group(1) == 'catalogue.html' else 'page'
        elif src == 'rosson':
            m = re.match(r'https://pangoleen\.github\.io/cipher-readings/([\w-]+)\.html', url or '') or None
            if m: up, sc = gh('pangoleen/cipher-readings', m.group(1)), 'record'
            elif re.match(r'https://github\.com/pangoleen/[\w-]+$', url or ''): up, sc = gh(url[19:]), 'record'
        elif src in ('cryptiana', 'cryptocellar') and url:
            up = lm(url); sc = 'list' if re.search(r'unsolved\.htm|g-army-messages', url) else 'page'
        if up or c or src not in ('cyphersolver', 'rosson', 'cryptiana', 'cryptocellar'):   # a failed lookup (e.g. GitHub's hourly limit) keeps the date we had
            db.execute('UPDATE entries SET src_created=?, src_updated=?, src_scope=? WHERE src=? AND key=?', (c, up, sc if up else '', src, key))
    print('source dates', sum(1 for v in memo.values() if v), 'pages/paths dated')

# entries that cite DECODE records (R-numbers, "DECRYPT no.") absorb those records; keys are never linked this way
def auto_same(db):
    ciph = {k for (k,) in db.execute("SELECT key FROM entries WHERE src='decode' AND rtype='cipher'")}
    bodies = cryptiana_bodies()
    cat = {str(x['id']): x for x in json.loads((C / 'bourdeau/source-catalogue.json.log').read_text(encoding='utf-8'))['entries']}
    rx = re.compile(r'(?:DECODE\s*(?:R|no\.?\s*)|DECRYPT\s*(?:R|no\.?\s*)|\bR)(\d{3,5})\b')
    db.execute('DELETE FROM same_auto')
    n = 0
    for src, key, title in db.execute("SELECT src, key, title_en FROM entries WHERE src IN ('cryptiana','cyphersolver')").fetchall():
        if src == 'cryptiana': text = bodies.get(key, '')
        else:
            x = cat.get(key, {}); text = ' '.join((str(x.get('shelfmark', '')), str(x.get('title', '')), re.split(r'(?<=[.;])\s', str(x.get('status', '')))[0]))
        for m in rx.finditer(text):
            if re.search(r'\bkeys?\b[^.;]{0,25}$', text[max(0, m.start() - 30):m.start()], re.I): continue   # "key (DECODE R392)"
            if m.group(1) in ciph:
                db.execute('INSERT OR IGNORE INTO same_auto VALUES(?,?,?)', (src, key, m.group(1))); n += 1
    # same volume and folio in BnF / BL shelfmarks ("BnF fr. 3621 no. 116 f. 130" = "Français 3621, no. 116, f. 130")
    def sig(s):
        s = s or ''
        m = re.search(r'(?:\bfr\.?|Fran[cç]ais|\bFr\.)\s*(\d{3,5})', s) and ('fr', re.search(r'(?:\bfr\.?|Fran[cç]ais|\bFr\.)\s*(\d{3,5})', s).group(1))
        m = m or (re.search(r'Add(?:itional)?\.?\s*(?:MS|Ms\.?)\s*(\d{3,5})', s) and ('add', re.search(r'Add(?:itional)?\.?\s*(?:MS|Ms\.?)\s*(\d{3,5})', s).group(1)))
        m = m or (re.search(r'Clairambault\s*(\d{2,4})|Clair\.\s*(\d{2,4})', s) and ('clair', next(g for g in re.search(r'Clairambault\s*(\d{2,4})|Clair\.\s*(\d{2,4})', s).groups() if g)))
        f = re.findall(r'\bff?\.\s*(\d{1,4})', s)
        return (m[0], m[1], f[0]) if m and f else None
    dec = {}
    for k, sh in db.execute("SELECT key, shelfmark FROM entries WHERE src='decode' AND rtype='cipher'"):
        sg = sig(sh)
        if sg: dec.setdefault(sg, []).append(k)
    for src, key, sh in db.execute("SELECT src, key, shelfmark FROM entries WHERE src='cyphersolver'").fetchall():
        for k in dec.get(sig(sh), []):
            db.execute('INSERT OR IGNORE INTO same_auto VALUES(?,?,?)', (src, key, k)); n += 1
    print('auto links', n)

# ---- page
e = lambda x: html.escape(str(x), quote=True)
T = lambda ja, en: f'<span class="t" lang="ja">{ja}</span><span class="t" lang="en">{en}</span>'

LANG = {'pt': ('ポルトガル語', 'Portuguese'), 'ru': ('ロシア語', 'Russian'), 'da': ('デンマーク語', 'Danish'), 'cs': ('チェコ語', 'Czech'), 'el': ('ギリシア語', 'Greek'), 'fr': ('フランス語', 'French'), 'it': ('イタリア語', 'Italian'), 'es': ('スペイン語', 'Spanish'), 'en': ('英語', 'English'),
        'de': ('ドイツ語', 'German'), 'la': ('ラテン語', 'Latin'), 'nl': ('オランダ語', 'Dutch'), 'sv': ('スウェーデン語', 'Swedish'),
        'pl': ('ポーランド語', 'Polish'), 'hu': ('ハンガリー語', 'Hungarian'), 'ja': ('日本語', 'Japanese'), 'xx': ('不明', 'unknown')}
LRX = {'fr': 'French', 'it': 'Italian', 'es': 'Spanish', 'en': 'English', 'de': 'German', 'la': 'Latin', 'nl': 'Dutch',
       'sv': 'Swedish', 'pl': 'Polish', 'hu': 'Hungarian', 'ja': 'Japanese', 'pt': 'Portuguese', 'ru': 'Russian', 'da': 'Danish', 'cs': 'Czech', 'el': 'Greek'}
REG = {'fr': ('フランス', 'France'), 'it': ('イタリア・教皇庁', 'Italy & Papacy'), 'es': ('スペイン', 'Spain'), 'gb': ('イングランド・英国', 'England & Britain'),
       'de': ('ドイツ・中欧', 'Germany & Central Europe'), 'nl': ('低地諸国', 'Low Countries'), 'sc': ('北欧', 'Scandinavia'),
       'us': ('アメリカ', 'Americas'), 'as': ('アジア', 'Asia'), 'ot': ('その他・複数', 'Other / several')}
# Cryptiana gives no language; its section names give the region, and a language where the section is one (marked as inferred)
CR_GRP = {'Spanish': ('es', 'es'), 'French': ('fr', 'fr'), 'French (up to 1610)': ('fr', 'fr'), 'French (17th Century)': ('fr', 'fr'),
          'French (Napoleonic Age)': ('fr', 'fr'), 'English': ('gb', 'en'), 'English Civil War': ('gb', 'en'), 'Intercepts by Commonwealth': ('gb', 'en'),
          'American': ('us', 'en'), 'German': ('de', ''), 'Enigma': ('de', 'de'), 'Italian (Vatican)': ('it', 'it'), 'Italian/Latin (1520s)': ('it', 'it la'),
          'French, Italian, Spanish': ('ot', ''), 'Telegraphic Age': ('ot', ''), 'Miscellaneous': ('ot', ''), 'Others': ('ot', '')}
CS_REG = {'England': 'gb', 'France': 'fr', 'Italy': 'it', 'Papacy': 'it', 'Low Countries': 'nl', 'Central Europe': 'de', 'Germany': 'de',
          'Scandinavia': 'sc', 'Spain': 'es', 'Other': 'ot'}

DEC_REG = [('fr', r'France|Paris|Lyon|Bordeaux'), ('it', r'Ital|Vatican|Papal|Rome|Roma|Venice|Venezia|Florence|Firenze|Naples|Napoli|Milan|Genoa|Sicily|Sardinia|Turin|Torino|Modena|Mantua|Siena'),
           ('es', r'Spain|Hispania|Portugal|Madrid|Simancas|Barcelona|Lisbon'),
           ('gb', r'England|Britain|United Kingdom|\\bUK\\b|Scotland|Ireland|Wales|London|Sheffield|Oxford|Cambridge|Kew'), ('nl', r'Netherlands|United Provinces|Belgium|Flanders|Holland|Hague|Haag|Nimwegen|Amsterdam|Brussels'),
           ('sc', r'Sweden|Denmark|Norway|Finland|Iceland|Stockholm|Copenhagen|Uppsala'), ('us', r'United States|USA|America|Canada|Mexico|Washington'),
           ('de', r'German|Austria|Hungary|Bohemia|Czech|Poland|Switzerland|Prussia|Bavaria|Saxony|Slovak|Croatia|Transylvania|Romania|Vienna|Wien|Dresden|Berlin|Munich|München|Dortmund|Buda|Mezőkövesd|Prague|Krak'),
           ('as', r'Japan|China|Korea|India|Ottoman|Turkey|Persia|Constantinople|Istanbul')]
def dec_reg(s):
    return next((k for k, rx in DEC_REG if re.search(rx, s or '', re.I)), 'ot')

def facets(r):
    """(language codes, inferred?, region code, century) for one entry."""
    inferred = False
    if r['src'] == 'cryptiana':
        reg, lg = CR_GRP.get(r['grp'], ('ot', ''))
        if re.search(r'Japanese', r['title_en']): reg, lg = 'as', 'ja'
        langs, inferred = lg.split(), bool(lg)
    else:
        langs = [k for k, w in LRX.items() if re.search(w, r['language'])]
        reg = {'cyphersolver': CS_REG.get(r['grp'], 'ot'), 'cryptocellar': 'de', 'decode': dec_reg(r['grp'])}.get(r['src'], 'ot')
    y = int(r['sortdate'][:4]) if r['sortdate'] else None
    return (langs or ['xx']), inferred, reg, (y // 100 + 1 if y else 0)

# small source marks: a coloured pill with a three-letter abbreviation of the researcher (our own marks, not the sites' logos)
MARK = {'cryptiana': ('Tmk', '#8a4b9c'), 'cyphersolver': ('Bdu', '#1f6f8b'), 'cryptocellar': ('Wrd', '#7a5a1e'), 'decode': ('Dcd', '#3d6b3a'), 'rosson': ('Rsn', '#6b4f8a')}   # Tomokiyo, Bourdeau, Weierud
def mark(src, link=True, icon=True):
    """Source mark: the three-letter code; links to the source list."""
    m, c = MARK[src]
    ja, en, url = SRC[src]
    fav = f'<img src="fav/{FAV[src]}" width="14" height="14" alt="" loading="lazy">' if src in FAV and icon else ''
    tag = (f'<a class="mk" href="{e(url)}" title="{e(ja)} / {e(en)}" aria-label="{e(en)}">' if link else '<span class="mk" aria-hidden="true">')
    return (f'{tag}{fav if link else ""}<svg viewBox="0 0 30 16" width="30" height="16" aria-hidden="true">'
            f'<rect width="30" height="16" rx="8" fill="{c}"/><text x="15" y="11.6" text-anchor="middle" font-size="10" font-weight="700" font-family="system-ui,sans-serif" fill="#fff">{m}</text></svg>' + ('</a>' if link else '</span>'))
FAV = {}   # favicons not shown (user, 2026-10-05); marks are the three-letter codes only
NAME = {'cryptiana': 'Cryptiana', 'cyphersolver': 'cyphersolver', 'cryptocellar': 'CryptoCellar', 'decode': 'DECODE', 'rosson': 'cipher-readings'}
SITE_URL = {'cryptiana': 'https://cryptiana.web.fc2.com/code/crypto.htm', 'cyphersolver': 'https://dbourdeau.github.io/cyphersolver/', 'cryptocellar': 'https://cryptocellar.org/', 'decode': 'https://de-crypt.org/', 'rosson': 'https://pangoleen.github.io/cipher-readings/'}

def notitle_year(s, en=False):
    """Drop dates from a title (the date column shows them)."""
    if en:
        s = re.sub(r'\s*\((?:c\.|ca\.|circa)?\s*\d{3,4}(?:s)?(?:[\s,\-–/?]|or|and|c\.|\d)*\)', '', s)
        s = re.sub(r',\s*\d{1,2} [A-Z][a-z]{2} \d{4}$', '', s)            # CryptoCellar: "…, Nr. 3, 22 Jun 1941"
        s = re.sub(r',\s*(?:\d{1,2}(?:[–-]\d{1,2})?\s+)?[A-Z][a-z]+\.?\s+\d{4}(?=\s*(?:\(|$|,))', '', s)   # ", 25 June 1571" / ", Sept 1645"
        s = re.sub(r'\s*\(\d{1,2} [A-Z][a-z]+ \d{4}\)', '', s)                                  # (15 March 1577)
        s = re.sub(r',\s*\d{1,2} and \d{1,2} [A-Z][a-z]{2,} \d{4}$', '', s)                     # , 14 and 15 Jan 1808
        s = re.sub(r' of \d{1,2} [A-Z][a-z]+ \d{4}$', '', s)                                     # reply of 4 May 1446
        s = re.sub(r',\s*\d{4}(?:[–-]\d{2,4})?$', '', s)                                        # , 1652 / , 1635–36
        s = re.sub(r' \d{4}(?=:)', '', s)                                                        # leaf 1559:
    else:
        s = re.sub(r'（\d{4}年\d{1,2}月\d{1,2}日、', '（', s)                # CryptoCellar: keep "Nr."
        s = re.sub(r'（[\d〜～・、年頃代ごろまたは\s?？-]*\d{3,4}[\d〜～・、年頃代ごろまたは\s?？-]*）', '', s)
        D = r'\d{4}(?:〜\d{2,4})?年(?:\d{1,2}月(?:\d{1,2}(?:・\d{1,2})?日)?)?'
        s = re.sub(r'（' + D + r'）', '', s)                                  # （1577年3月15日）
        s = re.sub(r'、' + D + r'付の', '、', s)                              # 、1446年5月4日付の返書
        s = re.sub(r'、' + D + r'(?=（|$)', '', s)                            # 、1763年4月15日 / 、1645年9月（…）
        s = re.sub(r'(?<=[^\d、])' + r'\d{4}年(?=：)', '', s)                 # Throckmorton文書1559年：
    return s.strip()

def fmt_when(s, en=False):
    """'19 September 2026' / 'September 2026' / '2023' -> Japanese or short English."""
    m = re.match(r'(\d{1,2}) ([A-Za-z]+)\.? (\d{4})$', s) or re.match(r'()([A-Za-z]+)\.? (\d{4})$', s)
    if m:
        d, mo, y = m.groups(); k = mo[:3].lower(); mi = MON.get(k)
        if mi:
            if en: return (f'{int(d)} ' if d else '') + f'{datetime.date(2000, mi, 1):%b} {y}'
            return f'{y}年{mi}月' + (f'{int(d)}日' if d else '')
    return s if en else (s + '年' if re.fullmatch(r'\d{4}', s) else s)

MENU = [('./', 'Cryptoole（未解決暗号のオープン検索）', 'Cryptoole (open search for unsolved ciphers)'), ('stats.html', '未解読暗号の解読状況統計', 'Decipherment statistics'),
        ('/crypt/timeline/', '各サイトの更新情報（時系列）', 'Updates from each site (timeline)'),
        ('spec.html', '未解決暗号の統一フォーマット（仕様案）', 'Unified format for unsolved ciphers (draft)'),
        ('https://github.com/satorunet/cryptoole', 'ソースコード（GitHub）', 'Source code (GitHub)'), ('/crypt/', 'crypt トップ', 'crypt home')]
SORTS = [('date', ('暗号の年代', 'Cipher date')), ('solved', ('解決日', 'Solved date')), ('added', ('追加日', 'Date added')),
         ('size', ('シリーズの件数', 'Series size')), ('pages', ('総頁数', 'Total pages'))]   # each with its own default direction (DIRDEF in the page script)
def solved_key(s):
    """'19 September 2026' -> '2026-09-19', 'March 2021' -> '2021-03-00', '2023' -> '2023-00-00'."""
    m = re.match(r'(?:(\d{1,2}) )?([A-Za-z]+)\.? (\d{4})$', s)
    if m and MON.get(m.group(2)[:3].lower()):
        return f'{m.group(3)}-{MON[m.group(2)[:3].lower()]:02d}-{int(m.group(1) or 0):02d}'
    m = re.fullmatch(r'(\d{4})', s)
    return f'{m.group(1)}-00-00' if m else ''

def ja_title(s):
    s = re.sub(r'^Key: ', '鍵：', s)
    m = re.match(r'(鍵：)?(.+?) to (.+)$', s)
    return f'{m.group(1) or ""}{m.group(2)} から {m.group(3)} へ' if m else s

def honor(names):
    """Japanese: 'A and B' -> 'A・B'; 氏 only for names written in Japanese (Latin-script names stay bare, user 2026-10-05)."""
    if not names: return ''
    ps = [x.strip() for x in re.split(r',\s*and\s+|\s+and\s+|,\s*', names) if x.strip()]
    return '・'.join(f'{x}氏' if re.search(r'[\u3040-\u30ff\u4e00-\u9fff]', x) else x for x in ps)

JST = datetime.timezone(datetime.timedelta(hours=9), 'JST')
def fmt_when_iso(d, en=False):
    """'2026-10-05' -> '2026年10月5日' / '5 Oct 2026'; '2026-10-06T12:40+09:00' -> '2026年10月6日 12:40（日本時間）' / '6 Oct 2026, 12:40 JST'."""
    if 'T' in (d or ''):
        try:
            x = datetime.datetime.fromisoformat(d).astimezone(JST)
            return f'{x.day} {x:%b} {x.year}, {x:%H:%M} JST' if en else f'{x.year}年{x.month}月{x.day}日 {x:%H:%M}'
        except Exception:
            return d
    try:
        x = datetime.date.fromisoformat(d)
        return f'{x.day} {x:%b} {x.year}' if en else f'{x.year}年{x.month}月{x.day}日'
    except Exception:
        return d

def fmt_text(dt, en=False):
    """The date as the source writes it, kept exact: spans (12–27 Dec 1558, 1628–1658), lists (2 Mar and 2 May 1577; 1706; 1709),
    decades (1520s), circa ([c. 1586]) and Old Style double years (1572/3). None when the text is not a date we can read."""
    t = re.sub(r'\([^()]*\)', ' ', dt or '')            # cataloguers' remarks: "(docket)", "(BnF range 1520-29)"
    t = re.sub(r"'[^']*'", ' ', t)                        # quoted original wording: 'ce xxvj juin'
    t = t.replace('[', ' ').replace(']', ' ')
    circa = bool(re.search(r'(?i)\b(?:c\.|ca\.|circa)\s*(?=\d)', t)); t = re.sub(r'(?i)\b(?:c\.|ca\.|circa)\s*(?=\d)', '', t)
    t = ' '.join(t.split()).strip(' ,;')
    if not t: return None
    part = re.compile(r'^(?:(\d{1,2})(?!\d)\s*)?(?:([A-Za-z]{3,})\.?\s*)?(?:(\d{3,4})(?:/(\d{1,2}))?(s)?)?(\?)?$')
    segs, more = [], False
    for seg in [s.strip() for s in re.split(r'[;,]', t) if s.strip()]:
        bits = re.split(r'\s*(–|—|-|\band\b|\bor\b)\s*', seg)
        ps, ok = [], True
        for k, b in enumerate(bits[::2]):
            m = part.match(b)
            if not m or not any(m.groups()) or (m.group(2) and m.group(2)[:3].lower() not in MON): ok = False; break
            ps.append([m.group(1), MON[m.group(2)[:3].lower()] if m.group(2) else None, m.group(3), m.group(4), m.group(5), bits[2 * k - 1] if k else '', m.group(6)])
        if not ok or not ps:
            if segs: more = True; continue
            return None
        for k in range(len(ps) - 2, -1, -1):             # "12–27 Dec 1558": the first part takes month and year from the next
            if not ps[k][2]:
                ps[k][2], ps[k][3] = ps[k + 1][2], ps[k + 1][3]
                if ps[k][0] and not ps[k][1]: ps[k][1] = ps[k + 1][1]
        if not all(p[2] for p in ps): return None
        segs.append(ps)
    if not segs: return None
    def one(p, prev):
        d, mo, y, y2, dec = p[:5]
        yy = y + (f'/{y2}' if y2 else '')
        if en: return ' '.join(x for x in (str(int(d)) if d else '', f'{datetime.date(2000, mo, 1):%b}' if mo else '', yy + ('s' if dec else '')) if x) + ('?' if p[6] else '')
        same_y = prev and prev[2] == y and not dec
        s = '' if same_y and (mo or d) else f'{int(yy) if yy.isdigit() else yy}年' + ('代' if dec else '')
        if mo: s += '' if same_y and prev[1] == mo and d else f'{mo}月'
        if d: s += f'{int(d)}日'
        return s + ('?' if p[6] else '')
    out = []
    for ps in segs:
        s = ''
        for k, p in enumerate(ps):
            if k: s += {'and': ' and ', 'or': ' or '}.get(p[5], ' – ') if en else {'and': '・', 'or': ' または '}.get(p[5], ' 〜 ')
            s += one(p, ps[k - 1] if k else None)
        out.append(s)
    s = (('; ' if ';' in t else ', ') if en else '・').join(out) + ((' etc.' if en else ' ほか') if more else '')
    if not circa: return s
    return 'c. ' + s if en else (s[:-1] + '頃?' if s.endswith('?') else s + '頃')

def fmt_date(r, en=False):
    if r['date_text']:
        s = fmt_text(r['date_text'], en)
        if s: return s
    dt = r['date_text'] or ''
    if ' – ' in dt:   # a span: "1400 – 1599", "7 Feb 1719 – 19 Jan 1745", "14 May – 4 Aug 1593"
        a, b = dt.split(' – ', 1)
        sb = sortdate(b)
        sa = sortdate(a if re.search(r'\d{3,4}', a) else f'{a} {sb[:4]}') if sb else ''
        if sa and sb:
            f = lambda s: fmt_date({**r, 'date_text': '', 'sortdate': s}, en)
            return f(sa) + (' – ' if en else ' 〜 ') + f(sb)
    sd = r['sortdate']
    if not sd: return '—'
    y, m, d = sd.split('-')
    decade = re.search(r'\d0s', r['grp'] + r['title_en']) and not r['date_text']
    if m == '00': return (f'{int(y)}s' if decade else f'{int(y)}') if en else (f'{int(y)}年' + ('代' if decade else ''))
    if en: return (f'{int(d)} ' if d != '00' else '') + f'{datetime.date(2000, int(m), 1):%b} {int(y)}'
    return f'{int(y)}年{int(m)}月' + (f'{int(d)}日' if d != '00' else '')

def facet_rows(rs):
    """[(group, (label_ja, label_en), [(value, (ja, en), count)])] for the drop-downs."""
    F = [facets(r) for r in rs]
    lc = {k: sum(1 for f in F if k in f[0]) for k in LANG}
    rc = {k: sum(1 for f in F if f[2] == k) for k in REG}
    cc = {}
    for f in F: cc[f[3]] = cc.get(f[3], 0) + 1
    n = lambda col, v: sum(1 for r in rs if (v in r['srcs'] if col == 'src' else r[col] == v))
    TY = {'cipher': ('暗号文', 'Ciphertext'), 'key': ('鍵', 'Key'), 'manual': ('手引き', 'Manual'), 'other': ('その他', 'Other')}
    return [('cat', ('状況', 'Status'), [(k, CAT[k][:2], sum(1 for r in rs if TOP[r['cat']] == k)) for k in ('open', 'solved', 'na')]),
            ('type', ('種類', 'Type'), [(k, v, n('rtype', k)) for k, v in TY.items()]),
            ('src', ('出典', 'Source'), [(k, v[:2], n('src', k)) for k, v in SRC.items()]),
            ('lang', ('言語', 'Language'), [(k, LANG[k], lc[k]) for k in sorted(LANG, key=lambda k: (k == 'xx', -lc[k]))]),
            ('reg', ('地域', 'Region'), [(k, REG[k], rc[k]) for k in sorted(REG, key=lambda k: (k == 'ot', -rc[k]))]),
            ('cen', ('世紀', 'Century'), [(str(c), (f'{c}世紀', f'{c}th c.') if c else ('年代不明', 'undated'), cc[c]) for c in sorted(cc, key=lambda c: (c == 0, c))])] + extra_rows()

def extra_rows():
    import attrs
    cn = {c: (ja, en) for c, ja, en, _ in attrs.COUNTRY}; cn['xx'] = ('不明', 'unknown')
    sy = dict(attrs.SYSTEM); sy['xx'] = ('不明', 'unknown')
    k, y = FACET_EXTRA.get('ctry', {}), FACET_EXTRA.get('sys', {})
    return [('ctry', ('国（出自）', 'Country of origin'), [(c, cn[c], k[c]) for c in sorted(k, key=lambda c: (c == 'xx', -k[c])) if c in cn]),
            ('sys', ('方式', 'System'), [(c, sy[c], y[c]) for c in sorted(y, key=lambda c: (c == 'xx', -y[c])) if c in sy])]

# status tab icons: all = stack, unsolved = closed lock, solved = open lock, unknown = question mark
_SV = lambda d: f'<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{d}</svg>'
SICON = {'all': _SV('<path d="M12 3 3 8l9 5 9-5-9-5z"/><path d="m3 13 9 5 9-5"/>'),
         'open': _SV('<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>'),
         'solved': _SV('<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 7.5-2"/>'),
         'na': _SV('<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14"/><path d="M12 17.5h.01"/>')}

def selects(rs):
    o = lambda v, ja, en, sel='': f'<option value="{v}" data-ja="{e(ja)}" data-en="{e(en)}"{sel}>{e(ja)}</option>'
    out = []
    rows = facet_rows(rs)
    cat = next(r for r in rows if r[0] == 'cat')
    seg = ('<div class="seg cats" role="group" aria-label="状況 / Status">'
           + f'<a href="./" data-cat="all" aria-pressed="true" title="すべて / All"><span class="ti">{SICON["all"]}<b>{len(rs)}</b></span><span class="tl">{T(*TABL["all"])}</span></a>'
           + ''.join(f'<a href="?status={k}" data-cat="{k}" aria-pressed="false" title="{ja} / {en}" style="--ic:{CAT[k][2]}"><span class="ti">{SICON[k]}<b>{c}</b></span><span class="tl">{T(*TABL[k])}</span></a>' for k, (ja, en), c in cat[2] if c)
           + '</div>')
    for g, (lj, le), items in rows:
        if g == 'cat': continue
        out.append(f'<label class="fs"><span>{T(lj, le)}</span><select data-g="{g}">' + o('all', 'すべて', 'All')
                   + ''.join(o(k, f'{ja}（{c}）', f'{en} ({c})') for k, (ja, en), c in items if c) + '</select></label>')
    # one-tap order toggle: the icon shows the current order (oldest at top = arrow down the years)
    sortb = ('<div class="sortw"><button type="button" class="fs-sort" id="sort" aria-haspopup="menu" aria-expanded="false" title="並び順 / Order">'
               '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
               '<path d="M7 4v16M3 16l4 4 4-4M17 20V4M13 8l4-4 4 4"/></svg><span id="sortlab"></span></button>'
               '<div class="sortm" id="sortm" role="menu" hidden>'
               + ''.join(f'<button type="button" role="menuitemradio" data-sort="{k}" aria-checked="false" data-ja="{e(ja)}" data-en="{e(en)}">{T(e(ja), e(en))}</button>' for k, (ja, en) in SORTS)
               + '</div></div>'
               '<button type="button" class="fs-dir" id="sortdir" title="並び順の向き / Direction" aria-label="並び順の向きを切り替える / Reverse the order">'
               '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M6 13l6 6 6-6"/></svg></button>')
    
    out.append(f'<button type="button" class="fs-reset" id="reset">{T("条件をクリア", "Clear")}</button>')
    # advanced search opens as a floating window (<dialog>)
    advb = ('<button type="button" class="advb" id="advbtn" aria-haspopup="dialog" title="詳細検索 / Advanced search" aria-label="詳細検索 / Advanced search">'
            '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="currentColor"><circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/></svg><span id="advn"></span></button>')
    return ('<div class="bar1">' + seg + '<span class="brk"></span>' + sortb + advb + '</div><p class="hitn" id="hitn" aria-live="polite" hidden></p>'
            + '<nav class="fnav" id="fnav" aria-label="ページ内の移動 / Jump"><button type="button" data-go="top" title="一番上へ / To top" aria-label="一番上へ / To top" hidden><svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M6 15l6-6 6 6"/></svg></button><button type="button" data-go="bottom" title="一番下へ / To bottom" aria-label="一番下へ / To bottom" hidden><svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg></button></nav>'
            + f'<dialog class="adv" id="adv" aria-label="詳細検索 / Advanced search"><div class="advh"><b>{T("詳細検索", "Advanced search")}</b>'
            + f'<button type="button" class="advx" id="advclose" aria-label="閉じる / Close">×</button></div>'
            + '<div class="filters">' + ''.join(out) + '</div>'
            + f'<div class="advf"><span id="advcount"></span><button type="button" class="advok" id="advok">{T("結果を見る", "Show results")}</button></div></dialog>')


PRIO = ['open', 'part', 'key', 'solved', 'na']   # a group shows its "least solved" member's status
def decode_names(db):
    """DECODE record id -> its record name (e.g. 'ASFi_SIIVol1_12', 'Codice_Amadi_1269_pt01')."""
    out = {}
    for i, j in db.execute('SELECT id, json FROM decode_list'):
        m = re.search(r'<small>(.*?)</small>', json.loads(j).get('c_holder') or '')
        if m: out[f'decode:{i}'] = html.unescape(m.group(1)).replace('&lsquot;', '’').strip()
    return out

PART = re.compile(r'(?i)^(.+?)(?:[ _\-]+(?:pt|part|teil|parte|f|fol)?[ _.\-]*\d{1,4}[rv]?)$')   # "<volume>_12", "<volume>_pt01", "<ms> 001r"
def SKEY(s):
    """Series key: the record name with numbers removed, separators unified, dangling labels and known spelling variants folded."""
    k = re.sub(r'[ _.,\-]+', '_', re.sub(r'\d+', '', s)).strip('_').lower()
    k = re.sub(r'(?:_(?:fasc|kt|nr|n|no|vol|reg|scat|leg|d|v|r|f|fol|pt|part))+$', '', k)
    k = re.sub(r'(^|_)(?:fr|francais)(?=_|$)', r'\1français', k)        # "BnF fr" = "BnF Français"
    k = re.sub(r'^bl_add_ms', 'add_ms', k)                               # "BL Add MS" = "Add MS"
    return k
FOLIO = re.compile(r'(?i)[,;]?\s*(?:ff?\.|fol\.?|fols\.?|folio|pp?\.|page|no\.|n°)\s*\d+\s*[rv]?(?:\s*[-–]\s*\d+\s*[rv]?)?|\s+\d{1,4}\s*[rv]\b')
def group_decode(D, names, shelf):
    """Group DECODE-only rows into series. Two records belong together (same record type) when
      a) their record names share a series stem once item and volume numbers are dropped
         ('<stem>_12', '<stem>_pt01', '<ms> 001r', '<stem>_9_172'), or one record's name is that stem itself, or
      b) their shelfmarks are the same once folio/page/item numbers are removed, and name a volume or manuscript.
    Links are chained (union-find), so a manuscript split across name variants ends up in one row.
    Rows that join nothing are then grouped by identical title. The first member carries the others in field m."""
    free, out = [], []
    for x in D:
        (free if x['S'] == ['decode'] and not x.get('m') else out).append(x)
    par = {x['i']: x['i'] for x in free}
    def find(a):
        while par[a] != a: par[a] = par[par[a]]; a = par[a]
        return a
    def union(a, b): par[find(a)] = find(b)
    key_first, label = {}, {}
    def link(k, x, lab):
        if k in key_first: union(x['i'], key_first[k])
        else: key_first[k] = x['i']; label[k] = lab
    names_ok = {}
    for x in free:                                   # a) numbered names
        m = PART.match(names.get(x['i'], ''))
        if m:
            stem = m.group(1); m2 = re.match(r'^(.+?)[ _\-]+\d{1,3}$', stem); stem = m2.group(1) if m2 else stem
            k = (x['y'], 'n:' + SKEY(stem)); link(k, x, stem); names_ok[x['i']] = k
    for x in free:                                   # head record named like its series
        k = (x['y'], 'n:' + SKEY(names.get(x['i'], '')))
        if x['i'] not in names_ok and k[1] != 'n:' and k in key_first: union(x['i'], key_first[k]); names_ok[x['i']] = k
    for x in free:                                   # b) shelfmarks without folio numbers
        st = re.sub(r'[\s,;.:]+$', '', FOLIO.sub('', shelf.get(x['i'], '') or '')).strip()
        if st and (re.search(r'\d', st) or re.search(r'(?i)\bms\b|codex|cod\.', st)):
            link((x['y'], 's:' + st.lower()), x, st)
    comp = {}
    for x in free: comp.setdefault(find(x['i']), []).append(x)
    rest = []
    for root, ms in comp.items():
        if len(ms) == 1: rest += ms; continue
        ids = {x['i'] for x in ms}
        ks = [k for k, f in key_first.items() if find(f) == root]
        nk = [k for k in ks if k[1].startswith('n:')]
        if nk:   # label from the name series covering most members; numbers dropped
            best = max(nk, key=lambda k: sum(1 for x in ms if names_ok.get(x['i']) == k))
            raw = re.sub(r'\d+', '', label[best])
        else:
            raw = label[ks[0]]
        lab = re.sub(r'\s*[-_/]+\s*', ' ', raw)
        lab = re.sub(r'\s+', ' ', lab).strip(' ,.-')
        lab = re.sub(r'(?:[\s,]+(?:n|nr|no|fasc|scat|reg|vol|Vol|d|v|r|Signatura|leg|ms|kt))+$', '', lab).strip(' ,.-') or lab
        out.append(merge(ms, lab, 'vol', names))
    by = {}
    for x in rest:
        tt = re.sub(r'^Key: ', '', x['te']).strip()
        if tt in ('', '...', '…') or re.match(r'(?i)(record \d+|unknown\b)', tt): out.append(x)
        else: by.setdefault((x['y'], x['te']), []).append(x)
    for ms in by.values():
        out.append(merge(ms, None, 'title') if len(ms) > 1 else ms[0])
    return out

def merge(ms, label, kind, names=None):
    nat = lambda s: [int(z) if z.isdigit() else z.lower() for z in re.split(r'(\d+)', re.sub(r'[ _]+', '_', s))]
    if names:   # a collection: list its records in shelf order (record names "…_9_172" sorted naturally)
        ms.sort(key=lambda x: (nat(names.get(x['i'], '')), x['i']))
    else:
        ms.sort(key=lambda x: (x['k'] or '9999', x['i']))
    main = dict(ms[0])
    main['k'] = min((x['k'] for x in ms if x['k']), default='')   # the row sorts by its earliest record
    main['m'] = [[x['u'], x['dj'], x['de'], x['mj'], x['me'], x['c'], x['i'], x['tj'], x['te'], (names or {}).get(x['i'], '')] for x in ms[1:]]
    if names: main['nm'] = names.get(ms[0]['i'], '')
    main['mk'] = kind
    main['c'] = min((x['c'] for x in ms), key=PRIO.index)
    main['L'] = sorted({l for x in ms for l in x['L'] if l != 'xx'}) or ['xx']
    main['s'] = max((x['s'] for x in ms), default='')
    if label:   # a volume: name the row after it
        key = main['y'] == 'key'
        main['tj'] = label
        main['te'] = label
        main['tj0'], main['te0'] = ms[0]['tj'], ms[0]['te']   # the first record's own title (for its chip)
        main['mj'] = re.sub(r'\s*(?:part|pt)\.?\s*\d+.*?(?= · |$)', '', main['mj']); main['me'] = re.sub(r'\s*(?:part|pt)\.?\s*\d+.*?(?= · |$)', '', main['me'])
    return main

def assign_ids(db, D):
    """Unified IDs (ID-SPEC §1, §2, §6): CR000123 for a record, CS00042 for a series. Kept in uid_ref / uid_series; an ID once given never changes.
    A record is one source record, or several source records of the same cipher (mk='same'); a series is a grouped row (volume or same title)."""
    db.execute('CREATE TABLE IF NOT EXISTS uid_ref(ref TEXT PRIMARY KEY, cid INTEGER NOT NULL, created TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS uid_series(skey TEXT PRIMARY KEY, sid INTEGER NOT NULL, created TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS uid_alias(old_cid INTEGER PRIMARY KEY, new_cid INTEGER NOT NULL, reason TEXT, date TEXT)')
    today = datetime.date.today().isoformat()
    have = dict(db.execute('SELECT ref, cid FROM uid_ref'))
    nk = lambda r: (list(SRC).index(r.split(':')[0]) if r.split(':')[0] in SRC else 9, [int(z) if z.isdigit() else z for z in re.split(r'(\d+)', r)])
    sets = []
    for x in D:
        if x.get('mk') == 'same': sets.append([x['i']] + [m[6] for m in x['m']])
        else: sets += [[x['i']]] + [[m[6]] for m in x.get('m', [])]
    sets.sort(key=lambda s: min(nk(r) for r in s))
    nxt = (db.execute('SELECT MAX(cid) FROM uid_ref').fetchone()[0] or 0) + 1
    cid_of = {}
    for s in sets:
        old = sorted({have[r] for r in s if r in have})
        if old: c = old[0]
        else: c, nxt = nxt, nxt + 1
        for o in old[1:]:   # two records found to be one cipher: keep the older ID, the other becomes an alias (§2.2)
            db.execute('INSERT OR IGNORE INTO uid_alias VALUES(?,?,?,?)', (o, c, 'same cipher', today))
        for r in s:
            if r not in have: db.execute('INSERT INTO uid_ref VALUES(?,?,?)', (r, c, today)); have[r] = c
            cid_of[r] = c
    shave = dict(db.execute('SELECT skey, sid FROM uid_series'))
    snxt = (db.execute('SELECT MAX(sid) FROM uid_series').fetchone()[0] or 0) + 1
    for x in sorted((x for x in D if x.get('m') and x.get('mk') != 'same'), key=lambda x: nk(x['i'])):
        k = 'row:' + x['i']
        if k not in shave:
            db.execute('INSERT INTO uid_series VALUES(?,?,?)', (k, snxt, today)); shave[k] = snxt; snxt += 1
        x['cs'] = f'CS{shave[k]:05d}'
    for x in D:
        x['cr'] = f'CR{cid_of[x["i"]]:06d}'
        for m in x.get('m', []):
            while len(m) < 10: m.append('')
            m[10:] = [f'CR{cid_of[m[6]]:06d}']
    db.commit()

PER = {}   # source key -> that record's own attributes (filled by add_attrs)
LANG_CC = {'fr': 'FR', 'it': 'IT', 'es': 'ES', 'en': 'GB', 'de': 'DE', 'nl': 'NL', 'hu': 'HU', 'sv': 'SE', 'da': 'DK', 'pl': 'PL', 'pt': 'PT', 'ru': 'RU', 'cs': 'CZ', 'el': 'GR', 'ja': 'JP'}   # Latin: no country
def pub_prefix(ref, rec, raw):
    """Country + year part of the public record ID (ID-SPEC §1): FR1591, IT15XX, XXXXXX. Fixed when the ID is given."""
    a = PER.get(ref, {})
    cc = (a.get('co') or [''])[0] or next((LANG_CC[l] for l in a.get('lp', []) if l in LANG_CC), '') or 'XX'
    r = rec.get(ref, {})
    if ref.startswith('decode:'):
        x = raw.get(ref, {}); ys = [str(v) for v in (x.get('start_year'), x.get('end_year')) if str(v or '').isdigit() and 1 <= int(v) <= 2100]
    else:
        ys = re.findall(r'(?<!\d)(1\d{3}|20\d\d)(?!\d)', r.get('date_text') or '') or ([str(r['year'])] if r.get('year') else re.findall(r'^(\d{4})', r.get('sortdate') or ''))
    ys = sorted({y.zfill(4) for y in ys})
    if not ys: yr = 'XXXX'
    elif len(ys) == 1: yr = ys[0]
    else:   # a span: the decade if both ends share it (1590–1592 -> 159X), else the century it starts in (1501–1601, 1601–1800 -> 15XX, 16XX)
        yr = ys[0][:3] + 'X' if ys[0][:3] == ys[-1][:3] else ys[0][:2] + 'XX'
    return cc + yr

def assign_pub(db, D):
    """Public record ID = <country><year>-<n>, e.g. FR1591-3. Given once per record (CR number) and never changed (uid_pub).
    The sources' own numbers (DECODE R1876, cyphersolver no. 20) are kept as information beside it, not used in it."""
    db.execute('CREATE TABLE IF NOT EXISTS uid_pub(cid INTEGER PRIMARY KEY, pid TEXT UNIQUE NOT NULL, prefix TEXT NOT NULL, n INTEGER NOT NULL, created TEXT)')
    rec = {f"{r['src']}:{r['key']}": dict(r) for r in db.execute('SELECT * FROM entries')}
    import attrs
    raw = attrs.load_raw(db)
    have = {c: p for c, p in db.execute('SELECT cid, pid FROM uid_pub')}
    top = {}
    for p, n in db.execute('SELECT prefix, MAX(n) FROM uid_pub GROUP BY prefix'): top[p] = n
    refs = {}   # CR number -> its source keys
    for r, c in db.execute('SELECT ref, cid FROM uid_ref'): refs.setdefault(c, []).append(r)
    live = {int(x['cr'][2:]) for x in D} | {int(m[10][2:]) for x in D for m in x.get('m', [])}
    new = []
    for c in live - set(have):
        rs = sorted(refs[c], key=lambda r: (not PER.get(r, {}).get('co'), r))
        pre = pub_prefix(rs[0], rec, raw)
        dk = min(((rec.get(r, {}).get('sortdate') or '') or '9999') for r in rs)
        new.append((pre, dk, c))
    today = datetime.date.today().isoformat()
    for pre, dk, c in sorted(new):
        top[pre] = n = top.get(pre, 0) + 1; have[c] = f'{pre}-{n}'
        db.execute('INSERT INTO uid_pub VALUES(?,?,?,?,?)', (c, have[c], pre, n, today))
    db.commit()
    pages = lambda r: PER.get(r, {}).get('pg') or 0
    for x in D:
        x['pid'] = have[int(x['cr'][2:])]
        x['pg'] = pages(x['i']) or max([pages(m[6]) for m in x.get('m', []) if x.get('mk') == 'same'] or [0])
        for m in x.get('m', []):
            m[11:] = [have[int(m[10][2:])], pages(m[6])]

def write_stats(db, D, CSS, head, BAR, LANGJS, T):
    """stats.html: one entry per record (a same-cipher row counts once, a series row counts each member)."""
    import statspage, attrs
    E = {f"{r['src']}:{r['key']}": dict(r) for r in db.execute('SELECT src, key, sortdate, year FROM entries')}
    recs = []
    for x in D:
        ms = [] if x.get('mk') == 'same' else x.get('m', [])
        for i, st in [(x['i'], x['c'] if x.get('mk') == 'same' else (x.get('c0') or x['c']))] + [(m[6], m[5]) for m in ms]:
            e = E.get(i, {}); sd = e.get('sortdate') or ''
            main = i == x['i']
            recs.append(dict(row=x['i'], src=i.split(':')[0], top=TOP[st], year=int(sd[:4]) if sd[:4].isdigit() and int(sd[:4]) else e.get('year'),
                             cc=(PER.get(i, {}).get('co') or ['xx'])[0], solvers=statspage.split_names(x.get('sb', '')) if main else [],
                             solved=solved_key(x['so'][1]) if main and x.get('so') else '', tj=x['tj'], te=x['te']))
    statspage.write(CSS, head, BAR, LANGJS, T, MENU, recs, SRC, MARK, attrs.COUNTRY)

FACET_EXTRA = {}
def add_attrs(db, D):
    """Country, languages, system, symbols, people, keywords (A) and relations (rel) for each row; K/Y are the filter keys."""
    import attrs
    raw = attrs.load_raw(db)
    cs = {str(x['id']): x for x in json.loads((C / 'bourdeau/source-catalogue.json.log').read_text(encoding='utf-8'))['entries']}
    rec = {f"{r['src']}:{r['key']}": dict(r) for r in db.execute('SELECT * FROM entries')}
    man = attrs.manual_attrs()
    rowof, people = {}, {}
    for x in D:
        ids = [x['i']] + [m[6] for m in x.get('m', [])]
        for i in ids: rowof[i] = x['i']
        for i in ids:
            if i in rec: PER[i] = attrs.apply_manual(attrs.record_attrs(rec[i], raw, cs), man.get(i, []))
        A = attrs.merge_attrs([attrs.record_attrs(rec[i], raw, cs) for i in ids if i in rec])
        for i in ids: A = attrs.apply_manual(A, man.get(i, []))
        x['A'] = A; x['K'] = A['co'] or ['xx']; x['Y'] = A['sy'] or ['xx']
        main = rec.get(x['i'], {})
        if x['i'].startswith('decode:'):
            r0 = raw.get(x['i'], {}); people[x['i']] = ((r0.get('author') or r0.get('sender') or '').strip(), (r0.get('receiver') or '').strip())
        elif x['i'].startswith('cyphersolver:'):
            p = [q.strip() for q in re.split(r'→|->', cs.get(x['i'].split(':')[1], {}).get('correspondents') or '')]
            if len(p) == 2: people[x['i']] = (p[0], p[1])
    title = {x['i']: (x['tj'], x['te']) for x in D}
    rels = {}
    for a, b, ty, basis, src, note in attrs.auto_relations(raw, people) + attrs.manual_relations():
        ra, rb = rowof.get(a), rowof.get(b)
        if not ra or not rb or ra == rb: continue
        for s, t, back in ((ra, rb, False), (rb, ra, True)):
            lst = rels.setdefault(s, {})
            k = (ty, t)
            if k not in lst or (basis == 'manual'): lst[k] = [ty, t, title[t][0], title[t][1], basis, src, note, 1 if back else 0]
    for x in D:
        r = list(rels.get(x['i'], {}).values())
        r.sort(key=lambda z: (z[4] != 'manual', z[0], z[2]))
        if r: x['rel'] = r[:60]
    import collections
    FACET_EXTRA['ctry'] = collections.Counter(c for x in D for c in x['K'])
    FACET_EXTRA['sys'] = collections.Counter(c for x in D for c in x['Y'])

def write_static(D):
    """idx.json for the search page (searched in the browser) and c/<id>.json for every row (its detail page)."""
    sd = H / 'c'; sd.mkdir(exist_ok=True)
    for f in sd.glob('*.json'): f.unlink()
    idx = []
    for x in D:
        y = {k: v for k, v in x.items() if k not in ('m', 'tj0', 'te0', 'A', 'rel', 'sd')}
        y['ms'] = ' '.join([x['pid'], x['cr'], x.get('cs', ''), x['i'].replace('decode:', 'R') if x['i'].startswith('decode:') else ''] + [m[6].replace('decode:', 'R') + ' ' + m[9] + ' ' + m[10] + ' ' + m[11] for m in x.get('m', [])] + x.get('A', {}).get('pe', []) + ([x['sb']] if x.get('sb') else [])).strip()   # people are searchable too (the case page links names here)   # unified IDs, member R-numbers and names stay searchable
        if x.get('m'): y['mn'] = len(x['m'])
        pg = x.get('pg', 0) if x.get('mk') == 'same' else x.get('pg', 0) + sum(m[12] for m in x.get('m', []) if len(m) > 12)   # total pages of the row
        if pg: y['pg'] = pg
        else: y.pop('pg', None)
        if x.get('m') and x.get('mk') != 'same':   # status counts of the series: solved, unsolved (incl. partly / key only), unknown
            t = [TOP[x.get('c0') or x['c']]] + [TOP[m[5]] for m in x['m']]
            y['pc'] = [t.count('solved'), t.count('open'), t.count('na')]
        (sd / (re.sub(r'[^A-Za-z0-9]+', '-', x['i']) + '.json')).write_text(json.dumps(x, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        idx.append(y)
    (H / 'idx.json').write_text(json.dumps(idx, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

def write_serve(D):
    """serve.sqlite: one read-only table queried by api.cgi (rows come back a page at a time)."""
    tmp = H / 'serve.sqlite.tmp'
    if tmp.exists(): tmp.unlink()
    s = sqlite3.connect(tmp)
    s.execute("CREATE TABLE rows(id TEXT PRIMARY KEY, k TEXT, s TEXT, a TEXT, c TEXT, srcs TEXT, langs TEXT, r TEXT, cen TEXT, y TEXT, t TEXT, j TEXT)")
    s.execute("CREATE TABLE uid(uid TEXT PRIMARY KEY, row TEXT)")   # CR/CS -> row, for api.cgi?cid= / ?sid=
    s.executemany("INSERT OR IGNORE INTO uid VALUES(?,?)", [(z, x["i"]) for x in D for z in [x["pid"], x["cr"], x.get("cs")] + [v for m in x.get("m", []) for v in m[10:12]] if z])
    for x in D:
        tt = ' '.join([x['tj'], x['te'], x['mj'], x['me'], x.get('n', ''), x['i'], x.get('g', ''), x['pid'], x['cr'], x.get('cs', '')]
                      + [' '.join(o[2:]) for o in x.get('o', [])] + [' '.join(m[1:5] + m[6:9] + m[10:12]) for m in x.get('m', [])]).lower()
        s.execute('INSERT INTO rows VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                  (x['i'], x['k'], x['s'], x['a'], x['c'], ' ' + ' '.join(x['S']) + ' ', ' ' + ' '.join(x['L']) + ' ', x['R'], str(x['C']), x['y'], tt,
                   json.dumps(x, ensure_ascii=False, separators=(',', ':'))))
    for col in ('k', 's', 'a', 'c', 'y', 'r', 'cen'):
        s.execute(f'CREATE INDEX i_{col} ON rows({col})')
    s.commit(); s.execute('VACUUM'); s.close()
    tmp.replace(H / 'serve.sqlite')

def build(db):
    CSS = re.search(r'<style>(.*?)</style>', (C / 'bourdeau/index.html').read_text(encoding='utf-8'), re.S).group(1)
    CSS += ('.ul{list-style:none;margin:0;padding:0}.ul li{display:block;padding:9px 0;border-bottom:1px solid var(--line)}.ul .dt{font-weight:600;color:var(--ink);font-variant-numeric:tabular-nums}'
            '.ul .d{font:600 13.5px/1.4 system-ui,sans-serif;font-variant-numeric:tabular-nums}.ul .ja{font-weight:600}.ul .en{color:var(--muted);font-size:13px}'
            '.ul .m{font-size:12.5px;color:var(--muted);margin-top:2px}.ul .nt{font-size:13.5px;margin-top:3px}'
            '.badge{display:inline-block;color:#fff;font:600 11px system-ui,sans-serif;border-radius:999px;padding:1px 8px;margin-right:6px;vertical-align:1px}'
            '.badge .q{display:inline-block;margin:-1px -8px -1px 6px;padding:1px 8px 1px 6px;border-radius:0 999px 999px 0;background:rgba(255,255,255,.3);font-weight:500}.badge .q-key{background:#4f7fbd}'
            '.sname{display:inline-flex;align-items:center;gap:4px;white-space:nowrap}.sname img{border-radius:3px}.sname .mk{margin-right:0}'
            '.menub{flex:none;margin-left:4px;display:inline-flex;align-items:center;justify-content:center;width:36px;height:34px;border:1px solid var(--line);background:var(--paper);color:var(--ink);border-radius:999px;cursor:pointer}.menub:hover{border-color:var(--accent);color:var(--accent)}'
            '.side{position:fixed;inset:0 0 0 auto;margin:0;max-width:none;max-height:none;height:100vh;height:100dvh;width:min(400px,88vw);border:0;border-left:1px solid var(--line);border-radius:16px 0 0 16px;background:var(--paper);color:var(--ink);padding:0;overflow-y:auto;box-shadow:-12px 0 40px rgba(0,0,0,.22)}'
            '.side[open]{animation:sidein .22s cubic-bezier(.2,.8,.2,1)}@keyframes sidein{from{transform:translateX(100%)}to{transform:none}}'
            '@media (prefers-reduced-motion:reduce){.side[open]{animation:none}}'
            '.side::backdrop{background:rgba(0,0,0,.3);backdrop-filter:blur(2px)}'
            '.side .advh{position:sticky;top:0;z-index:1;background:var(--paper);padding:14px 18px 10px;border-bottom:1px solid var(--line);margin:0}'
            '.side .advh b{font:700 16px/1.3 Georgia,"Noto Serif JP",serif}'
            '.side section{padding:4px 18px 10px}.side h2{font:700 13px system-ui,sans-serif;letter-spacing:.04em;color:var(--muted);margin:14px 0 6px;border:0;padding:0}'
            '.side .acc{border-bottom:1px solid var(--line)}.side .acc summary{cursor:pointer;padding:10px 2px;list-style:none;display:flex;justify-content:space-between;align-items:center}.side .acc summary::-webkit-details-marker{display:none}.side .acc summary::after{content:"▾";color:var(--muted);transition:transform .15s}.side .acc[open] summary::after{transform:rotate(180deg)}.side .accb{padding:0 2px 12px}'
            '.side .navl{list-style:none;padding:0;margin:0}.side .navl li{margin:0;border-bottom:1px solid var(--line)}.side .navl a{display:block;padding:10px 2px;text-decoration:none;color:var(--ink)}.side .navl a:hover{color:var(--accent)}.side .seg.theme{margin:4px 0 6px}.seg.theme button{padding:7px 14px}'
            '.side .srcl li{display:flex;align-items:center;gap:6px}.side .srcl .mk{flex:none}.side .srcl a{flex:1;min-width:0;text-align:left}.cntp{flex:none;min-width:2.2em;text-align:center;font:600 11.5px/18px system-ui,sans-serif;font-variant-numeric:tabular-nums;color:var(--ink);background:var(--accent-soft);border:1px solid var(--line);border-radius:999px;padding:0 7px}'
            '.side ul{margin:0;padding-left:1.1em;font-size:14px;line-height:1.65}.side ul.srcl{list-style:none;padding:0;margin:0 0 8px}.side .srcl li{margin:6px 0}.side li{margin:4px 0}.side .upd{display:grid;grid-template-columns:auto 1fr;gap:2px 12px;margin:10px 0 0;padding:8px 10px;border:1px solid var(--line);border-radius:8px;font-size:13.5px}.side .upd dt{color:var(--muted);font-weight:600}.side .upd dd{margin:0;font-variant-numeric:tabular-nums}.side .lead{font-size:14px;line-height:1.7;margin:0 0 8px}.side .note{font-size:13.5px;line-height:1.7;margin:0}'
            '.also{font-size:13.5px;margin-top:4px;padding-top:4px;border-top:1px dashed var(--line)}.also .m{font-size:12px}'
            '.lead .t[lang=ja]{word-break:keep-all;word-break:auto-phrase;overflow-wrap:anywhere;line-break:strict}'
            '#ul mark{background:#ffe066;color:#1f1d1a;font-weight:700;border-radius:3px;padding:0 2px;box-shadow:0 0 0 1px #e0b400}'
            '@media (prefers-color-scheme:dark){:root:not([data-theme="light"]) #ul mark{background:#f2c94c;color:#16140f}}:root[data-theme="dark"] #ul mark{background:#f2c94c;color:#16140f}'
            '.brandh .logo{color:inherit;text-decoration:none}.brandh .logo:hover{opacity:.85}.brandh{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 12px}.brandh small{font:500 14px system-ui,sans-serif;color:var(--muted)}'
            '.ser{margin:6px 0 2px;padding:30px 0 0 10px;margin-top:-22px;border-left:2px solid var(--line);max-height:26em;overflow-y:auto}.serp{font:600 12.5px system-ui,sans-serif;color:var(--muted);margin-bottom:4px}.serr{display:flex;gap:10px;align-items:baseline;padding:2px 0}.serr b{flex:none;min-width:2.2em;font:600 12.5px system-ui,sans-serif;color:var(--ink);text-align:right}.serr span{display:flex;flex-wrap:wrap;gap:3px 4px}.sn{font:12.5px ui-monospace,Menlo,Consolas,monospace;text-decoration:none;padding:0 5px;border-radius:5px;border:1px solid var(--line);background:var(--paper)}.sn:hover{border-color:var(--accent)}.sn{position:relative;display:inline-flex;align-items:center;gap:3px}.sn svg{color:var(--sc)}.sn.s-open{border-color:#a3161b66}.sn.s-solved{border-color:#2e7d4f88}.sn::after{content:attr(data-tip);white-space:pre;position:absolute;z-index:40;left:50%;bottom:calc(100% + 6px);transform:translateX(-50%);background:var(--ink);color:var(--bg);font:12px/1.45 system-ui,sans-serif;padding:5px 8px;border-radius:6px;box-shadow:0 4px 14px rgba(0,0,0,.25);opacity:0;pointer-events:none;transition:opacity .12s}.sn:hover::after,.sn:focus-visible::after,.sn.tip::after{opacity:1}'
            '.ty{display:inline-flex;vertical-align:-2px;margin-right:4px;color:var(--muted)}.serl{display:inline-flex;align-items:center;justify-content:center;vertical-align:-3px;width:26px;height:22px;margin:4px 6px 0 0;border:1px solid var(--line);border-radius:999px;text-decoration:none}.serl:hover{border-color:var(--accent)}.grpn{font-size:12.5px;color:var(--muted)}.grpd>summary.vh{display:block;position:absolute}.ul a.grpt::after{content:" ▾";font-size:.7em;color:var(--muted)}.ul a.grpt[aria-expanded="true"]::after{content:" ▴"}.serl:hover{text-decoration:underline}'
            '.pbw{display:inline-flex;align-items:center;gap:6px;vertical-align:middle;margin-left:6px}.pbw .pbar{display:inline-flex;width:64px;height:6px;border-radius:999px;overflow:hidden;background:var(--line)}.pbw .pbar i{display:block;height:100%}.pbw .pct{font:11.5px system-ui,sans-serif;color:var(--muted)}'
            '.grpd .rn{font-size:12px;color:var(--ink);margin-right:4px}.grpd{margin-top:4px;font-size:13.5px}.grpd summary{cursor:pointer;color:var(--accent)}.grpd ul{list-style:none;margin:4px 0 0;padding:0 0 0 10px;border-left:2px solid var(--line);max-height:22em;overflow-y:auto}.grpd li{padding:3px 0;color:var(--muted)}.grpd li a{margin-right:6px}.grpd .badge{font-size:10px}'
            '.mk{display:inline-flex;align-items:center;gap:3px;vertical-align:-3px;margin-right:6px;text-decoration:none}.mk:hover{opacity:.75}.mk img{border-radius:3px}'
            '.filters{display:flex;flex-wrap:wrap;gap:8px 12px;margin:8px 0 12px;align-items:flex-end}.fs{display:flex;flex-direction:column;gap:2px;font:600 12px system-ui,sans-serif;color:var(--muted)}'
            '.fs select{font:inherit;font-size:14px;font-weight:400;color:var(--ink);background:var(--paper);border:1px solid var(--line);border-radius:8px;padding:5px 8px;min-width:9em;max-width:100%}'
            '.advb{position:relative;display:inline-flex;align-items:center;justify-content:center;width:34px;height:34px;padding:0;border:1px solid var(--line);background:var(--paper);color:var(--ink);border-radius:8px;cursor:pointer}.advb:hover{background:var(--accent-soft)}#advn:empty{display:none}.advb #advn{position:absolute;top:-6px;right:-6px;min-width:16px;height:16px;padding:0 4px;border-radius:999px;background:var(--accent);color:#fff!important;font:700 10px/16px system-ui,sans-serif;text-align:center}'
            '.adv{border:1px solid var(--line);border-radius:12px;background:var(--paper);color:var(--ink);padding:14px 16px;width:min(560px,calc(100vw - 32px));box-shadow:0 12px 40px rgba(0,0,0,.25)}'
            '.adv::backdrop{background:rgba(0,0,0,.35)}.advh{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}'
            '.advx{font-size:22px;line-height:1;border:0;background:none;color:var(--muted);cursor:pointer;padding:2px 6px}'
            '.adv .filters{margin:6px 0}.adv .fs{flex:1 1 45%}.adv .fs select{width:100%}'
            '.advf{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:8px;font-size:13px;color:var(--muted)}'
            '.advok{font:inherit;font-size:14px;border:0;background:var(--accent);color:#fff;border-radius:8px;padding:7px 14px;cursor:pointer}'
            '.bar1{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:10px 0 4px}#advn{font-size:12px;color:var(--muted)}'
            '.seg{display:flex;flex-wrap:wrap;gap:0;margin:0;border:1px solid var(--line);border-radius:10px;overflow:hidden;width:fit-content;max-width:100%}'
            '.seg a,.seg button{text-decoration:none;font:inherit;font-size:13.5px;border:0;border-right:1px solid var(--line);background:var(--paper);color:var(--ink);padding:7px 12px;cursor:pointer;display:inline-flex;align-items:center;gap:6px}'
            '.seg a:last-child,.seg button:last-child{border-right:0}.seg a i,.seg button i{width:9px;height:9px;border-radius:50%;display:inline-block}.seg a b,.seg button b{font-weight:600;color:var(--muted)}'
            '.vh{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}.seg [data-cat] svg{color:var(--ic,currentColor)}'
            '.seg.cats a.zero{opacity:.45}.seg.cats{display:grid;grid-template-columns:repeat(4,1fr);width:100%;max-width:none}.bar1 .brk{flex-basis:100%;height:0}'
            '.seg.cats a[data-cat]{flex-direction:column;justify-content:center;align-items:center;gap:2px;padding:6px 4px 5px;line-height:1.1}'
            '.seg [data-cat] .ti{display:inline-flex;align-items:center;gap:6px}.seg [data-cat] .tl{font-size:10.5px;letter-spacing:.06em;font-weight:600;color:var(--ic,var(--muted))}'
            '.seg [data-cat][aria-pressed="false"] .tl{opacity:.8}'
            '.seg [aria-pressed="false"]{color:var(--muted)}.seg [aria-pressed="false"]:hover{background:var(--accent-soft);color:var(--ink)}'
            '.seg [aria-pressed="true"]{background:var(--accent-soft);color:var(--ink);font-weight:600;box-shadow:inset 0 -2px 0 var(--accent)}.seg [aria-pressed="true"] b{color:var(--ink)}'
            '.conds{display:flex;flex-wrap:nowrap;gap:6px;margin:6px 0 2px;overflow-x:auto;scrollbar-width:thin;-webkit-overflow-scrolling:touch;padding-bottom:2px}.conds:empty{display:none}.cond{flex:none;white-space:nowrap}'
            '.cond{display:inline-flex;align-items:center;gap:4px;font-size:13px;background:var(--accent-soft);border:1px solid var(--accent);color:var(--ink);border-radius:999px;padding:2px 4px 2px 10px}'
            '.cond b{font-weight:600;color:var(--accent)}.cond button{border:0;background:none;color:var(--muted);cursor:pointer;font-size:15px;line-height:1;padding:2px 6px;border-radius:999px}.cond button:hover{color:var(--accent)}'
            '.advb.on{background:var(--accent-soft);border-color:var(--accent)}.fs select.on{border-color:var(--accent);box-shadow:inset 0 0 0 1px var(--accent);background:var(--accent-soft)}.fs-sort.on{border-color:var(--accent);color:var(--accent)}'
            '.sortw{position:relative}.fs-sort{display:inline-flex;align-items:center;gap:6px;height:34px;padding:0 10px;border:1px solid var(--line);background:var(--paper);color:var(--ink);border-radius:8px;cursor:pointer;font:inherit;font-size:13px}.fs-sort:hover{border-color:var(--accent);color:var(--accent)}'
            '.sortm{position:absolute;z-index:30;top:calc(100% + 4px);left:0;min-width:15em;background:var(--paper);border:1px solid var(--line);border-radius:10px;box-shadow:0 10px 30px rgba(0,0,0,.18);padding:4px;display:flex;flex-direction:column}'
            '.fs-dir{display:inline-flex;align-items:center;justify-content:center;width:34px;height:34px;padding:0;border:1px solid var(--line);background:var(--paper);color:var(--ink);border-radius:8px;cursor:pointer}.fs-dir:hover{background:var(--accent-soft)}.fs-dir svg{transition:transform .25s}.fs-dir.up svg{transform:rotate(180deg)}'
            '.sortm button{font:inherit;font-size:14px;text-align:left;border:0;background:none;color:var(--ink);padding:8px 10px 8px 26px;border-radius:7px;cursor:pointer;position:relative}'
            '.sortm button:hover{background:var(--accent-soft)}.sortm button[aria-checked="true"]::before{content:"✓";position:absolute;left:9px;color:var(--accent)}'
            '.fnav{position:fixed;right:12px;top:55%;transform:translateY(-50%);z-index:20;display:flex;flex-direction:column;gap:10px}.fnav button{width:48px;height:48px;border-radius:50%;border:1px solid var(--line);background:color-mix(in srgb,var(--paper) 92%,transparent);color:var(--ink);box-shadow:0 2px 8px rgba(0,0,0,.15);display:flex;align-items:center;justify-content:center;cursor:pointer;-webkit-backdrop-filter:blur(4px);backdrop-filter:blur(4px)}.fnav button:hover,.fnav button:focus-visible,.fnav button:active{opacity:1;background:var(--accent-soft);color:var(--accent)}.fnav button{opacity:.55;transform:scale(1);transition:opacity .4s ease,transform .4s ease,visibility 0s linear 0s}.fnav button[hidden]{display:flex!important;visibility:hidden;opacity:0;transform:scale(.8);pointer-events:none;transition:opacity .4s ease,transform .4s ease,visibility 0s linear .4s}@media (prefers-reduced-motion:reduce){.fnav button,.fnav button[hidden]{transition:none}}'
            '.ul .hd{display:flex;flex-direction:column;align-items:flex-start;gap:3px}.ul .hd .badge{flex:none;margin:0}.ul .hd .tt{display:block;width:100%;min-width:0}.ul .hd .hr{display:flex;align-items:center;width:100%}.ul .hr .mks{display:flex;gap:3px;margin-left:auto}.ul .mks .mk{margin:0}'
            '.qbox{flex:1 1 auto;min-width:0;position:relative;display:flex;flex-wrap:wrap;align-items:center;gap:4px 6px;padding:4px 42px 4px 6px;border:1px solid var(--line);border-radius:8px;background:var(--paper)}.qbox:focus-within{border-color:var(--accent);box-shadow:0 0 0 2px var(--accent-soft)}.qbox input{flex:1 1 9em;min-width:6em;border:0!important;outline:0;background:transparent!important;padding:6px!important;box-shadow:none!important}.qbox .conds{display:flex;flex-wrap:wrap;gap:4px;margin:0;padding:0;overflow:visible}.qbox .conds:empty{display:none}.qbox .cond{font-size:12.5px;padding:1px 2px 1px 8px}'
            '.hitn{display:flex;align-items:baseline;gap:6px;margin:4px 0 8px;padding:8px 12px;border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:8px;background:var(--paper);font-size:13.5px;color:var(--muted)}.hitn svg{align-self:center;color:var(--accent);flex:none}.hitn .hl{font-weight:600;color:var(--ink)}.hitn b{font:700 20px/1 Georgia,serif;color:var(--accent);margin-left:4px}.hitn .hu{color:var(--ink)}.hitn .ht{margin-left:auto;font-size:12.5px}.nohit{text-align:center;padding:28px 12px;border:1px dashed var(--line);border-radius:12px;margin:12px 0;color:var(--muted)}.nohit p{margin:4px 0}.nohit p:first-child{font-size:16px;color:var(--ink);font-weight:600}.nohit .nh2{font-size:13.5px}.nohit .fs-reset{margin-top:10px}'
            '.qw input{padding-right:2.4em!important}.qw input::-webkit-search-cancel-button{display:none}.qx{position:absolute;right:6px;top:50%;transform:translateY(-50%);width:28px;height:28px;border:0;border-radius:999px;background:var(--line);color:var(--ink);font-size:18px;line-height:1;cursor:pointer}.qx:hover{background:var(--accent);color:#fff}'
            '.morew{text-align:center;margin:14px 0}.more{font:inherit;font-size:14px;border:1px solid var(--line);background:var(--paper);color:var(--accent);border-radius:999px;padding:8px 22px;cursor:pointer}'
            '.fs-reset{font:inherit;font-size:13px;border:1px solid var(--line);background:var(--bg);color:var(--muted);border-radius:8px;padding:6px 10px;cursor:pointer}.gone{opacity:.55}'
            '@media (max-width:560px){.ul li{grid-template-columns:1fr}}')
    rs = db.execute('SELECT e.*, j.title_ja, j.note_ja FROM entries e LEFT JOIN ja j USING(src,key) ORDER BY sortdate=\'\', sortdate, src, key').fetchall()
    # merge entries that are the same cipher in several sources (table `same`, checked by hand)
    rs = [dict(r) for r in rs]
    by = {(r['src'], r['key']): r for r in rs}
    mem = {}
    for g, s, k in db.execute('SELECT grp, src, key FROM same ORDER BY grp, ord'):
        if (s, k) in by: mem.setdefault(g, []).append(by[(s, k)])
    skip = set()
    for r in rs: r['others'], r['srcs'] = [], [r['src']]
    for g, ms in mem.items():
        main = ms[0]
        for o in ms[1:]:
            main['others'].append(o)
            if o['src'] not in main['srcs']: main['srcs'].append(o['src']); skip.add((o['src'], o['key']))
            main['slug'] = main['slug'] or o['slug']
    for s, k, rid in db.execute('SELECT src, key, rid FROM same_auto'):
        m, o = by.get((s, k)), by.get(('decode', rid))
        if not m or not o: continue
        if (s, k) in skip:   # the citing entry was merged into another row: attach there
            m = next((r for r in rs if any(x is m for x in r['others'])), None)
            if not m: continue
        if o not in m['others']:
            m['others'].append(o)
            if 'decode' not in m['srcs']: m['srcs'].append('decode')
        skip.add(('decode', rid))
    rs = [r for r in rs if (r['src'], r['key']) not in skip]
    def mkx(r):
        tj = r['title_ja'] or (ja_title(r['title_en']) if r['src'] == 'decode' else r['title_en'])
        langs, inf, reg, cen = facets(r)
        ltxt = '・'.join(LANG[l][0] for l in langs if l != 'xx') + ('（分類から推定）' if inf else '')
        ltxt_en = ', '.join(LANG[l][1] for l in langs if l != 'xx') + (' (inferred from the section)' if inf else '')
        grp = r['grp'] if r['src'] not in ('cyphersolver', 'decode') else ''
        meta = ' · '.join(x for x in (r['shelfmark'], ltxt, REG[reg][0]) if x)   # Japanese: the shelfmark is the only English kept (a shared key)
        meta_en = ' · '.join(x for x in (r['shelfmark'], ltxt_en, REG[reg][1], grp) if x)
        if r['cat'] not in ('open', 'na') and (r['solved_on'] or r['solved_by']):
            lab = {'solved': ('解決', 'Solved'), 'part': ('一部解決', 'Partly solved'), 'key': ('鍵の特定', 'Key found')}[r['cat']]
            sj = f'{lab[0]}：' + '・'.join(x for x in (fmt_when(r['solved_on']), honor(r['solved_by'])) if x)
            se = f'{lab[1]}: ' + ', '.join(x for x in (fmt_when(r['solved_on'], True), r['solved_by']) if x)
            meta = sj + (' · ' + meta if meta else '')
            meta_en = se + (' · ' + meta_en if meta_en else '')
        if r['gone']:
            meta += f' · 一覧から外れた（{r["last_seen"]}）'; meta_en += f' · no longer listed ({r["last_seen"]})'
        x = dict(i=f'{r["src"]}:{r["key"]}', k=r['sortdate'] or '', s=solved_key(r['solved_on']) if r['cat'] not in ('open', 'na') else '', a=r['first_seen'],
                 c=r['cat'], S=r['srcs'], L=langs, R=reg, C=cen, y=r['rtype'], dj=fmt_date(r), de=fmt_date(r, True),
                 tj=notitle_year(tj), te=notitle_year(r['title_en'], True), u=r['url'], mj=meta, me=meta_en)
        if r['note_ja']: x['n'] = r['note_ja']
        if r['slug']: x['g'] = r['slug']
        if r['gone']: x['x'] = 1
        if r['solved_by'] and r['cat'] in ('solved', 'part'):
            x['sb'] = r['solved_by']
            k = solved_key(r['solved_on'] or '')
            if k:
                y_, m_, d_ = k.split('-')
                x['so'] = [f'{int(y_)}年' + (f'{int(m_)}月' if m_ != '00' else '') + (f'{int(d_)}日' if d_ != '00' else ''), r['solved_on']]
        if r['src_created'] or r['src_updated'] or r['changed_on']: x['sd'] = [[r['src'], r['src_created'], r['src_updated'], r['src_scope'], r['changed_on']]]
        return x
    NAMES = decode_names(db)
    D = []
    for r in rs:
        x = mkx(r)
        if r['others']:   # the same cipher in other sources: bundled like a series (one row, members listed in m)
            ox = [mkx(o) for o in r['others']]
            x['m'] = [[o['u'], o['dj'], o['de'], o['mj'], o['me'], o['c'], o['i'], o['tj'], o['te'], NAMES.get(o['i'], '')] for o in ox]
            x['mk'] = 'same'
            x['sd'] = x.get('sd', []) + [z for o in ox for z in o.get('sd', [])]
            BEST = ['solved', 'part', 'key', 'open', 'na']   # the same cipher read elsewhere counts as read
            best = min([x] + ox, key=lambda z: BEST.index(z['c']))
            if BEST.index(best['c']) < BEST.index(x['c']):
                x['c0'] = x['c']   # the main source's own status, shown on its record line
                for k in ('sb', 'so'):
                    if best.get(k): x[k] = best[k]
                x['c'] = best['c']; x['s'] = best['s'] or x['s']
                x['mj'] = best['mj'].split(' · ')[0] + ' · ' + x['mj'] if best['mj'].startswith(('解決', '一部解決')) else x['mj']
                x['me'] = best['me'].split(' · ')[0] + ' · ' + x['me'] if best['me'].startswith(('Solved', 'Partly')) else x['me']
        D.append(x)
    D = group_decode(D, NAMES, {f'{r["src"]}:{r["key"]}': r['shelfmark'] for r in rs})
    # the record type is shown as an icon, not as a "鍵：/Key:" prefix in the title
    untype = lambda s, ja: (lambda u: ('（不明）' if ja else '(unknown)') if u in ('', '...', '…') else u)(re.sub(r'^(鍵：|Key: )', '', s or '').strip())
    for x in D:
        x['tj'], x['te'] = untype(x['tj'], True), untype(x['te'], False)
        for k in ('tj0', 'te0'):
            if x.get(k): x[k] = untype(x[k], k == 'tj0')
        for m in x.get('m', []):
            m[7], m[8] = untype(m[7], True), untype(m[8], False)
    assign_ids(db, D)
    add_attrs(db, D)
    assign_pub(db, D)
    write_serve(D)
    write_static(D)
    # counts on the page follow the grouped rows
    keep = {x['i']: x for x in D}
    rs = [r for r in rs if f"{r['src']}:{r['key']}" in keep]
    for r in rs: r['cat'] = keep[f"{r['src']}:{r['key']}"]['c']
    n = len(rs)
    cnt = lambda col, v: sum(1 for r in rs if (v in r['srcs'] if col == 'src' else r[col] == v))
    T_plain = lambda n: f'{n:,} 件 / {n:,} entries'
    chips = selects(rs)
    # each source links to the search filtered by it, with the number of rows it appears in; most rows first
    srcs = '<ul class="srcl">' + ''.join(f'<li>{mark(k, link=False, icon=False)}<a href="./?source={k}" title="{e(v[0])} / {e(v[1])}">{T(*v[:2])}</a><span class="cntp" title="{T_plain(cnt("src", k))}">{cnt("src", k):,}</span></li>' for k, v in sorted(SRC.items(), key=lambda kv: -cnt('src', kv[0]))) + '</ul>'
    upd = max((r['last_seen'] for r in rs), default='')
    m = db.execute("SELECT v FROM meta WHERE k='last_fetch'").fetchone() if db.execute("SELECT 1 FROM sqlite_master WHERE name='meta'").fetchone() else None
    if m: upd = m[0]   # the time of the last fetch, not just the day
    def sname(k):
        return f'<a href="{e(SITE_URL[k])}">{e(NAME[k])}</a>'
    SN = '・'.join(sname(k) for k in SRC)
    SN_EN = ', '.join(sname(k) for k in list(SRC)[:-1]) + ' and ' + sname(list(SRC)[-1])
    body = (f'<h1 class="vh">Cryptoole — {T("未解決暗号のオープン検索エンジン", "an open search engine for unsolved historical ciphers")}</h1>'
            f'<div class="tools qw"><div class="qbox"><div class="conds" id="conds" aria-live="polite"></div><input id="q" type="search" placeholder="検索（題名・所蔵番号・言語）" data-ph-ja="検索（題名・所蔵番号・言語）" data-ph-en="Search (title, shelfmark, language)" aria-label="検索 / Search" autocomplete="off"><button type="button" id="qx" class="qx" aria-label="検索語を消す / Clear search" title="検索語を消す / Clear" hidden>×</button></div></div>{chips}'
            f'<ul class="ul" id="ul" aria-busy="true"></ul><div class="nohit" id="nohit" hidden><p>{T("該当する暗号は見つかりませんでした。", "No ciphers match.")}</p><p class="nh2">{T("検索語を減らすか、条件を外してみてください。", "Try fewer words or remove a condition.")}</p><button type="button" class="fs-reset" id="nhclear">{T("条件をクリア", "Clear all")}</button></div><div class="morew"><button type="button" class="more" id="more" hidden>{T("さらに表示", "Show more")}</button></div>'
            # side menu (drawer) with the explanation and the sources
            f'<dialog class="side" id="side" aria-label="メニュー / Menu"><div class="advh"><b>{T("メニュー", "Menu")}</b><button type="button" class="advx" id="sideclose" aria-label="閉じる / Close">×</button></div>'
            f'<section><h2>{T("情報", "Info")}</h2>'
            f'<details class="acc"><summary>{T("このデータベースについて", "About this database")}</summary><div class="accb">'
            f'<p class="lead">{T(f"{SN} の<wbr>暗号の<wbr>一覧を<wbr>一元的に<wbr>管理。<wbr>状況・<wbr>種類・<wbr>言語・<wbr>地域・<wbr>年代で<wbr>横断して<wbr>絞り込める", f"The {SN_EN} lists of unsolved ciphers managed in one place, filterable across sources by status, language, region and date")}</p>'
            '<ul>'
            f'<li>{T("出典を取り直すたびに、各項目の状況を更新する。一覧から外れた項目も消さずに記録する。", "Each refresh updates every entry’s status; entries that drop off a list are kept and marked.")}</li>'
            f'<li>{T("状況は「未解決」「解決」「不明」の3つ。一部だけ読めたものは「未解決｜一部」、鍵だけ分かっているものは「未解決｜鍵のみ」と付記する。DECODE で状況が記されていない記録（鍵の多く）は「不明」。", "Three classes: unsolved, solved and unknown. Partly read entries show “unsolved | partly”, those with only the key known “unsolved | key only”; DECODE records without a status (most keys) are “unknown”.")}</li>'
            f'<li>{T("DECODE の全記録（暗号文・鍵・手引き）を含む。種類は詳細検索で絞り込める。Cryptiana や cyphersolver の項目が DECODE の記録番号や同じ所蔵番号・葉を挙げている場合は、1行にまとめる。", "All DECODE records (ciphertexts, keys, manuals) are included; filter by type under Advanced search. Where a Cryptiana or cyphersolver entry cites a DECODE record number or the same shelfmark and folio, they share one row.")}</li>'
            f'<li>{T("出典・言語・地域・世紀は「詳細検索」で横断して絞り込める。並び順はアイコンから、暗号の年代・解決日・追加日を選べる。", "Filter across sources by source, language, region and century under “Advanced search”; the order button offers cipher date, solve date and date added.")}</li>'
            '</ul></div></details>'
            f'<details class="acc" open id="sources"><summary>{T("出典と取得について", "Sources and data")}</summary><div class="accb">'
            + srcs +
            f'<dl class="upd"><dt>{T("最終取得", "Last fetched")}</dt><dd>{T(fmt_when_iso(upd), fmt_when_iso(upd, True))}</dd></dl>'
            '</div></details>'
            '<ul class="navl">' + ''.join(f'<li><a href="{h}"{' class="gh"' if 'github.com' in h else ''}>{T(ja, en)}</a></li>' for h, ja, en in MENU[1:]) + '</ul></section>'
            + sidemenu.LANGSEC +
            f'<section><h2>{T("テーマ", "Theme")}</h2><div class="seg theme" role="group" aria-label="テーマ / Theme">'
            '<button type="button" data-theme-set="auto" aria-pressed="true" title="自動 / Auto" aria-label="自動 / Auto"><svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor"/></svg></button>'
            '<button type="button" data-theme-set="light" aria-pressed="false" title="ライト / Light" aria-label="ライト / Light"><svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg></button>'
            '<button type="button" data-theme-set="dark" aria-pressed="false" title="ダーク / Dark" aria-label="ダーク / Dark"><svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/></svg></button></div></section>'
            '</dialog>'
            f'<footer>satorunet · <a href="/crypt/">crypt</a> · <a href="/crypt/timeline/">{T("更新の時系列", "Timeline of updates")}</a> · <a href="api.html">API</a> · <a class="gh" href="https://github.com/satorunet/cryptoole">GitHub</a></footer>')
    SIJ = json.dumps({k: SICON[TOP.get(k, k)].replace('width="18" height="18"', 'width="11" height="11"') for k in list(CAT) + ['all']}, ensure_ascii=False)
    CJ = json.dumps({k: [v[0], v[1], v[2]] for k, v in CAT.items()}, ensure_ascii=False)
    MJ = json.dumps({k: [m, c, SRC[k][2], SRC[k][0], SRC[k][1]] for k, (m, c) in MARK.items()}, ensure_ascii=False)
    js = ("var q=document.getElementById('q'),ul=document.getElementById('ul'),more=document.getElementById('more'),"
          "PAGE=100,f={cat:'all',src:'all',type:'all',lang:'all',reg:'all',cen:'all',ctry:'all',sys:'all'},ADV=['src','type','lang','reg','cen','ctry','sys'],DEF='solved',DIRDEF={date:'asc',solved:'desc',added:'desc',size:'desc',pages:'desc'},mode=DEF,dir=DIRDEF[DEF],P={cat:'status',src:'source',type:'type',lang:'language',reg:'region',cen:'century',ctry:'country',sys:'system'};"
          "var CAT=" + CJ + ",TOP={open:'open',part:'open',key:'open',solved:'solved',na:'na'},MK=" + MJ + ",SI=" + SIJ + ";"
          "function esc(s){return String(s==null?'':s).replace(/[&<>\"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c];});}"
          "function T(a,b){return '<span class=\"t\" lang=\"ja\">'+a+'</span><span class=\"t\" lang=\"en\">'+b+'</span>';}"
          "function mark(s){var m=MK[s];return '<span class=\"mk\" title=\"'+esc(m[3])+' / '+esc(m[4])+'\" aria-label=\"'+esc(m[4])+'\"><svg viewBox=\"0 0 30 16\" width=\"30\" height=\"16\" aria-hidden=\"true\"><rect width=\"30\" height=\"16\" rx=\"8\" fill=\"'+m[1]+'\"/><text x=\"15\" y=\"11.6\" text-anchor=\"middle\" font-size=\"10\" font-weight=\"700\" font-family=\"system-ui,sans-serif\" fill=\"#fff\">'+m[0]+'</text></svg></span>';}"
          "function badge(c){var t=TOP[c],q=c!==t?'<span class=\"q q-'+c+'\">'+T(CAT[c][0],CAT[c][1])+'</span>':'';return '<span class=\"badge\" style=\"background:'+CAT[t][2]+'\">'+T(CAT[t][0],CAT[t][1])+q+'</span>';}"
          "var TY={key:'<span class=\"ty\" title=\"鍵 / Key\" aria-label=\"鍵 / Key\"><svg viewBox=\"0 0 24 24\" width=\"15\" height=\"15\" aria-hidden=\"true\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><circle cx=\"7.5\" cy=\"15.5\" r=\"4.5\"/><path d=\"m10.7 12.3 9.3-9.3M17 6l3 3M14.5 8.5l2 2\"/></svg></span>',manual:'<span class=\"ty\" title=\"手引き / Manual\" aria-label=\"手引き / Manual\"><svg viewBox=\"0 0 24 24\" width=\"15\" height=\"15\" aria-hidden=\"true\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M4 5a2 2 0 0 1 2-2h12v16H6a2 2 0 0 0-2 2z\"/><path d=\"M4 19V5\"/></svg></span>'};"
          "function row(x){var dd=x.dj&&x.dj!=='—';return '<li class=\"'+(x.x?'gone':'')+'\"><div><div class=\"hd\"><div class=\"hr\">'+badge(x.c)+'<span class=\"mks\">'+x.S.map(mark).join('')+'</span></div><span class=\"tt\">'"
          "+'<a class=\"ja\" href=\"case.html?id='+encodeURIComponent(x.i)+'\">'+T(esc(x.tj),esc(x.te))+'</a>'+(x.g?' <a class=\"slug\" href=\"https://satoru.net/crypt/'+esc(x.g)+'/\">'+esc(x.g)+'</a>':'')+'</span></div>'"
          "+(x.n?'<div class=\"nt t\" lang=\"ja\">'+esc(x.n)+'</div>':'')+'<div class=\"m\">'+(dd?'<span class=\"dt\">'+T(esc(x.dj),esc(x.de))+'</span>'+(x.mj?' · ':''):'')+T(esc(x.mj),esc(x.me))+(x.pg?' · <span class=\"pgc\">'+(x.mn&&x.mk!=='same'?T('計 '+x.pg.toLocaleString()+'頁','total '+x.pg.toLocaleString()+' pp.'):T(x.pg.toLocaleString()+'頁',x.pg.toLocaleString()+' pp.'))+'</span>':'')+'</div>'"
          "+(x.o||[]).map(function(o){return '<div class=\"also\">'+mark(o[0])+'<a href=\"'+esc(o[1])+'\">'+T(esc(o[2]),esc(o[3]))+'</a></div>';}).join('')"
          "+(x.mn?''"
          "+'<details class=\"grpd\" data-id=\"'+esc(x.i)+'\"><summary>'+(x.mk==='vol'?T('同じ巻・シリーズの記録 ほか '+x.mn+' 件','+ '+x.mn+' more records in this series'):x.mk==='same'?T('関連する記録 ほか '+x.mn+' 件','+ '+x.mn+' related records'):T('同じ題名の記録 ほか '+x.mn+' 件','+ '+x.mn+' more records with this title'))+(x.pc?pbar(x.pc):'')+'</summary><div class=\"qv\">…</div></details>':'')+'</div></li>';}"
          "function sfile(id){return 'c/'+id.replace(/[^A-Za-z0-9]+/g,'-')+'.json';}"
          "function pbar(c){if(!c[0]&&!c[1])return '';var n=c[0]+c[1]+c[2],K=['solved','open','na'],pc=function(v){var r=v*100/n;return r>0&&r<1?'<1%':r>99&&r<100?'>99%':Math.round(r)+'%';};return ' <span class=\"pbw\">'+(c.filter(function(v){return v;}).length>1?'<span class=\"pbar\" aria-hidden=\"true\">'+K.map(function(k,i){return c[i]?'<i style=\"width:'+(c[i]*100/n)+'%;background:'+CAT[k][2]+'\"></i>':'';}).join('')+'</span>':'')+'<span class=\"pct\">'+[[c[0],T('解決 ','solved ')],[c[1],T('未解決 ','unsolved ')],[c[2],T('不明 ','unknown ')]].filter(function(z){return z[0];}).map(function(z){return z[1]+pc(z[0]);}).join(' · ')+'</span></span>';}"
          "function quick(x){return x.mk==='vol'&&x.nm?series(x):'<ul>'+x.m.map(function(m){var sc=m[6].split(':')[0];return '<li>'+badge(m[5])+(MK[sc]?mark(sc):'')+'<a href=\"'+esc(m[0])+'\">'+esc(sc==='decode'?m[6].replace('decode:','R'):(m[7]||m[6]))+'</a> '+T(esc(m[1]),esc(m[2]))+(m[3]&&m[3]!==x.mj?' · '+T(esc(m[3]),esc(m[4])):'')+'</li>';}).join('')+'</ul>';}"
          "ul.addEventListener('toggle',function(ev){var d=ev.target;if(!d.classList||!d.classList.contains('grpd')||!d.open||d.dataset.ok)return;d.dataset.ok=1;"
          "fetch(sfile(d.dataset.id)).then(function(r){return r.json();}).then(function(x){var qv=d.querySelector('.qv');qv.innerHTML=quick(x);qv.querySelectorAll('a').forEach(function(a){a.href='case.html?id='+encodeURIComponent(x.i);a.removeAttribute('target');});}).catch(function(){d.querySelector('.qv').textContent='—';delete d.dataset.ok;});},true);"
          "var tipOn=null;ul.addEventListener('click',function(ev){var a=ev.target.closest('.sn');if(!a)return;if(matchMedia('(hover: none)').matches&&tipOn!==a){ev.preventDefault();if(tipOn)tipOn.classList.remove('tip');a.classList.add('tip');tipOn=a;}});"
          "document.addEventListener('click',function(ev){if(tipOn&&!ev.target.closest('.sn')){tipOn.classList.remove('tip');tipOn=null;}});"
          "function norm(s){return String(s||'').replace(/[ _]+/g,'_');}"
          "function series(x){var all=[[x.u,x.dj,x.de,x.mj,x.me,x.c,x.i,x.tj0||x.tj,x.te0||x.te,x.nm]].concat(x.m),ns=all.map(function(m){return norm(m[9]);}),pre=ns[0];"
          "ns.forEach(function(n){var k=0;while(k<pre.length&&k<n.length&&pre[k]===n[k])k++;pre=pre.slice(0,k);});pre=pre.replace(/[^_]*$/,'');"
          "var rows=[],cur=null;all.forEach(function(m,j){var rest=ns[j].slice(pre.length),p=rest.split('_'),it=p.pop(),vol=p.join(' ');if(!cur||cur.v!==vol){cur={v:vol,a:[]};rows.push(cur);}"
          "var st=CAT[m[5]],tip=(TOP[m[5]]!==m[5]?CAT[TOP[m[5]]][0]+'｜':'')+st[0]+' / '+(TOP[m[5]]!==m[5]?CAT[TOP[m[5]]][1]+' | ':'')+st[1]+'\\n'+m[6].replace('decode:','R')+(m[2]?' · '+m[2]:'')+(m[8]?'\\n'+m[8]:'');"
          "cur.a.push('<a class=\"sn s-'+TOP[m[5]]+'\" style=\"--sc:'+CAT[TOP[m[5]]][2]+'\" href=\"'+esc(m[0])+'\" data-tip=\"'+esc(tip)+'\" aria-label=\"'+esc(tip.replace(/\\n/g,' · '))+'\">'+SI[m[5]]+esc(it||m[6].replace('decode:','R'))+'</a>');});"
          "return '<div class=\"ser\"><div class=\"serp\">'+esc(pre.replace(/_+$/,'').replace(/_/g,' '))+'</div>'+rows.map(function(r){return '<div class=\"serr\">'+(r.v?'<b>'+esc(r.v)+'</b>':'')+'<span>'+r.a.join('')+'</span></div>';}).join('')+'</div>';}"
          "function advn(){var n=0;ADV.forEach(function(g){if(f[g]!=='all')n++;});var el=document.getElementById('advn');if(el)el.textContent=n?String(n):'';}"
          "function hl(root){var ws=q.value.trim().toLowerCase().split(/\\s+/).filter(Boolean);if(!ws.length)return;"
          "var re=new RegExp('('+ws.map(function(w){return w.replace(/[.*+?^${}()|[\\]\\\\]/g,'\\\\$&');}).join('|')+')','gi');"
          "var tw=document.createTreeWalker(root,NodeFilter.SHOW_TEXT,{acceptNode:function(n){return n.parentNode.closest('svg,mark')?NodeFilter.FILTER_REJECT:NodeFilter.FILTER_ACCEPT;}}),ns=[],n;"
          "while((n=tw.nextNode())){re.lastIndex=0;if(re.test(n.nodeValue))ns.push(n);}re.lastIndex=0;"
          "ns.forEach(function(n){var fr=document.createDocumentFragment(),parts=n.nodeValue.split(re);parts.forEach(function(s,i){if(!s)return;if(i%2){var m=document.createElement('mark');m.textContent=s;fr.appendChild(m);}else fr.appendChild(document.createTextNode(s));});n.parentNode.replaceChild(fr,n);});}"
          "var D=null,hits=[],total=0;"
          "function has(k,v){var s=f[k];if(s==='all')return true;var a=String(s).split(',');if(Array.isArray(v)){for(var z=0;z<v.length;z++)if(a.indexOf(v[z])>=0)return true;return false;}return a.indexOf(String(v))>=0;}"
          "function ok(x,w,nc){if((!nc&&!has('cat',TOP[x.c]))||!has('src',x.S)||!has('type',x.y)||!has('lang',x.L)||!has('reg',x.R)||!has('cen',x.C)||!has('ctry',x.K||['xx'])||!has('sys',x.Y||['xx']))return false;"

          "for(var i=0;i<w.length;i++)if(x._t.indexOf(w[i])<0)return false;return true;}"
          "function run(keep){advn();if(window.save)save();if(window.conds)conds();if(!D)return;var off=keep?ul.children.length:0;"
          "if(!keep){var w=q.value.trim().toLowerCase().split(/\\s+/).filter(Boolean).slice(0,8);"
          "var fld={date:'k',solved:'s',added:'a'}[mode]||'k',up=dir==='asc',sg=up?-1:1;"
          "hits=D.filter(function(x){return ok(x,w);});var cc={all:0,open:0,solved:0,na:0};D.forEach(function(x){if(ok(x,w,1)){cc.all++;cc[TOP[x.c]]++;}});document.querySelectorAll('.seg [data-cat]').forEach(function(t){var e=t.querySelector('.ti b');if(e)e.textContent=(cc[t.dataset.cat]||0).toLocaleString();t.classList.toggle('zero',!cc[t.dataset.cat]);});if(mode==='pages')hits.sort(function(a,b){if(!a.pg!==!b.pg)return a.pg?-1:1;return sg*((b.pg||0)-(a.pg||0))||(a.k<b.k?-1:(a.k>b.k?1:0));});else if(mode==='size')hits.sort(function(a,b){return sg*((b.mn||0)-(a.mn||0))||(a.k<b.k?-1:(a.k>b.k?1:0));});else hits.sort(function(a,b){var x=a[fld]||'',y=b[fld]||'';if(x===y)return a.k<b.k?-1:(a.k>b.k?1:(a.i<b.i?-1:1));if(!x)return 1;if(!y)return -1;return up?(x<y?-1:1):(x<y?1:-1);});total=hits.length;}"
          "var page=hits.slice(off,off+(off?PAGE*2:PAGE)),h=page.map(row).join('');if(keep)ul.insertAdjacentHTML('beforeend',h);else ul.innerHTML=h;for(var z=off;z<ul.children.length;z++)hl(ul.children[z]);"
          "ul.removeAttribute('aria-busy');more.hidden=ul.children.length>=total;document.getElementById('nohit').hidden=total>0;var hn=document.getElementById('hitn'),act=q.value.trim()||f.cat!=='all'||ADV.some(function(g){return f[g]!=='all';});hn.hidden=!act||!total;if(act)hn.innerHTML='<svg viewBox=\"0 0 24 24\" width=\"16\" height=\"16\" aria-hidden=\"true\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2.2\" stroke-linecap=\"round\"><circle cx=\"10.5\" cy=\"10.5\" r=\"6.5\"/><path d=\"m15.5 15.5 5 5\"/></svg>'"
          "+'<span class=\"hl\">'+T('検索結果','Results')+'</span><b>'+total.toLocaleString()+'</b><span class=\"hu\">'+T('件',total===1?'match':'matches')+'</span>'"
          "+'<span class=\"ht\">'+T('全 '+D.length.toLocaleString()+' 件中','of '+D.length.toLocaleString())+'</span>';"
          "var ac=document.getElementById('advcount');if(ac)ac.textContent=total+' / '+D.length;}"
          "fetch('idx.json').then(function(r){return r.json();}).then(function(d){D=d;D.forEach(function(x){x._t=(x.tj+' '+x.te+' '+x.mj+' '+x.me+' '+(x.n||'')+' '+x.i+' '+(x.g||'')+' '+(x.ms||'')).toLowerCase();delete x.ms;});run();})"
          ".catch(function(){ul.removeAttribute('aria-busy');ul.innerHTML='<li>'+T('読み込めませんでした。','Could not load the index.')+'</li>';});"
          "more.addEventListener('click',function(){run(true);});"
          "var fn=document.getElementById('fnav'),fu=fn.querySelector('[data-go=top]'),fd=fn.querySelector('[data-go=bottom]'),ft=0;"
          "function fnv(){var y=scrollY,h=document.documentElement.scrollHeight-innerHeight;fu.hidden=y<400;fd.hidden=h<800||y>h-80;}"
          "addEventListener('scroll',function(){if(!ft)ft=requestAnimationFrame(function(){ft=0;fnv();});},{passive:true});addEventListener('resize',fnv);"
          "fu.addEventListener('click',function(){scrollTo({top:0,behavior:'smooth'});});fd.addEventListener('click',function(){scrollTo({top:document.documentElement.scrollHeight,behavior:'smooth'});});"
          "new MutationObserver(fnv).observe(ul,{childList:true});"
          "var qx=document.getElementById('qx');function qxs(){qx.hidden=!q.value;}"
          "var tq;q.addEventListener('input',function(){qxs();clearTimeout(tq);tq=setTimeout(function(){run();},120);});"
          "qx.addEventListener('click',function(){window.cse(1320,520,.06,'square',.03);q.value='';qxs();run();q.focus();});"
          "q.addEventListener('keydown',function(ev){if(ev.key==='Escape'&&q.value){ev.preventDefault();q.value='';qxs();run();}});setTimeout(qxs,0);"
          "var sel=document.querySelectorAll('select[data-g]'),so=document.getElementById('sort');"
          "function lab(){var l=document.documentElement.dataset.ui==='en'?'en':'ja';document.querySelectorAll('option[data-ja]').forEach(function(o){o.textContent=o.dataset[l];});document.querySelectorAll('[data-ph-ja]').forEach(function(e){e.placeholder=e.dataset[l==='en'?'phEn':'phJa'];e.setAttribute('aria-label',e.placeholder);});}"
          "sel.forEach(function(s){s.addEventListener('change',function(){f[s.dataset.g]=s.value;run();});});"
          "var sg=document.querySelectorAll('.seg [data-cat]');function seg(v){f.cat=v;sg.forEach(function(x){x.setAttribute('aria-pressed',String(x.dataset.cat===v));});}"
          "sg.forEach(function(b){b.addEventListener('click',function(ev){if(ev.metaKey||ev.ctrlKey||ev.shiftKey||ev.button)return;ev.preventDefault();window.cse(880,880,.03,'square',.018);seg(b.dataset.cat);run();});});"
          "window.save=null;"
          "function save(){var u=new URLSearchParams(location.search);['q','sort'].concat(Object.keys(P).map(function(k){return P[k];})).forEach(function(k){u.delete(k);});"
          "var v=q.value.trim();if(v)u.set('q',v);Object.keys(P).forEach(function(k){if(k==='cat'){if(f.cat!=='all')u.set('status',f.cat);}else if(f[k]!=='all')u.set(P[k],f[k]);});u.delete('dir');if(mode!==DEF)u.set('sort',mode);if(dir!==DIRDEF[mode])u.set('dir',dir);"
          "var s=u.toString().replace(/%2C/gi,',');try{history.replaceState(null,'',location.pathname+(s?'?'+s:'')+location.hash);}catch(e){}}window.save=save;"
          "(function(){var u=new URLSearchParams(location.search);if(u.get('q'))q.value=u.get('q');var sv=u.get('sort'),dv=u.get('dir');var OLD={'desc':['date','desc'],'date-desc':['date','desc'],'solved-asc':['solved','asc']};if(OLD[sv]){dv=dv||OLD[sv][1];sv=OLD[sv][0];}if(sv&&DIRDEF[sv])mode=sv;dir=(dv==='asc'||dv==='desc')?dv:DIRDEF[mode];"
          "Object.keys(P).forEach(function(k){var v=u.get(P[k]);if(!v)return;if(v==='*')v='all';if(k==='cat'){if(v.indexOf(',')>=0)f.cat=v;else if(document.querySelector('.seg [data-cat=\"'+v+'\"]'))seg(v);return;}if(v.indexOf(',')>=0){f[k]=v;return;}"
          "var s=document.querySelector('select[data-g=\"'+k+'\"]');if(s&&s.querySelector('option[value=\"'+v+'\"]')){s.value=v;f[k]=v;}});seg(f.cat);})();"
          "var LBL={q:['検索','Search'],cat:['状況','Status'],src:['出典','Source'],type:['種類','Type'],ctry:['国','Country'],sys:['方式','System'],lang:['言語','Language'],reg:['地域','Region'],cen:['世紀','Century'],sort:['並び順','Order']};"
          "function txt(el){var l=document.documentElement.dataset.ui==='en'?'en':'ja';var o=el&&el.querySelector('.t[lang=\"'+l+'\"]');return o?o.textContent:(el?el.textContent:'');}"
          "window.conds=function(){var l=document.documentElement.dataset.ui==='en'?1:0,box=document.getElementById('conds'),h=[];"
          "function chip(k,v){h.push('<span class=\"cond\"><span>'+LBL[k][l]+'：<b></b></span><button type=\"button\" data-x=\"'+k+'\" aria-label=\"×\">×</button></span>');vals.push(v);}var vals=[];"
          "var qv=q.value.trim();"
          "function lbl(sel,v){return String(v).split(',').map(function(z){var e=document.querySelector(sel.replace('#',z));return e?(e.tagName==='OPTION'?e.textContent.replace(/[（(]\\d+[）)]$/,''):txt(e).replace(/\\s*\\d+$/,'')):z;}).join('・');}"
          "if(f.cat!=='all')chip('cat',lbl('.seg [data-cat=\"#\"]',f.cat));"
          "ADV.forEach(function(g){var s=document.querySelector('select[data-g=\"'+g+'\"]');s.classList.toggle('on',f[g]!=='all');if(f[g]!=='all')chip(g,lbl('select[data-g=\"'+g+'\"] option[value=\"#\"]',f[g]));});"
          "if(mode!==DEF||dir!==DIRDEF[mode])chip('sort',slab(l?'en':'ja'));"
          "document.getElementById('advbtn').classList.toggle('on',ADV.some(function(g){return f[g]!=='all';}));"
          "box.innerHTML=h.join('');box.querySelectorAll('.cond b').forEach(function(b,i){b.textContent=vals[i];});"
          "box.querySelectorAll('[data-x]').forEach(function(x){x.addEventListener('click',function(){var k=x.dataset.x;window.cse(1320,520,.06,'square',.03);"
          "if(k==='q'){q.value='';qxs();}else if(k==='cat')seg('all');else if(k==='sort'){mode=DEF;dir=DIRDEF[DEF];sl();}else{var s=document.querySelector('select[data-g=\"'+k+'\"]');s.value='all';f[k]='all';}run();});});};"
          "var sm=document.getElementById('sortm'),sb=document.querySelectorAll('.sortm [data-sort]');"
          "function dlab(l){var n=mode==='size'||mode==='pages';return dir==='asc'?(n?(l==='en'?'fewest first':'少ない順'):(l==='en'?'oldest first':'古い順')):(n?(l==='en'?'most first':'多い順'):(l==='en'?'newest first':'新しい順'));}function slab(l){var b=document.querySelector('.sortm [data-sort=\"'+mode+'\"]');return (b?b.dataset[l]:mode)+(l==='en'?': ':'：')+dlab(l);}function sl(){var l=document.documentElement.dataset.ui==='en'?'en':'ja';sb.forEach(function(b){b.setAttribute('aria-checked',String(b.dataset.sort===mode));});var t=slab(l);document.getElementById('sortlab').textContent=t;so.title=t;var sd=document.getElementById('sortdir');sd.classList.toggle('up',dir==='asc');sd.title=(l==='en'?'Reverse: now ':'向きを切り替え（今は')+dlab(l)+(l==='en'?'':'）');so.classList.toggle('on',mode!==DEF||dir!==DIRDEF[mode]);}"
          "function sm_(o){sm.hidden=!o;so.setAttribute('aria-expanded',String(o));}"
          "so.addEventListener('click',function(ev){ev.stopPropagation();sm_(sm.hidden);});"
          "sb.forEach(function(b){b.addEventListener('click',function(){mode=b.dataset.sort;dir=DIRDEF[mode];sm_(false);sl();run();});});"
          "document.addEventListener('click',function(ev){if(!sm.hidden&&!sm.contains(ev.target))sm_(false);});function se(up){window.cse(up?2093:1319,up?2093:1319,.03,'square',.05);}document.getElementById('sortdir').addEventListener('click',function(){dir=dir==='asc'?'desc':'asc';se(dir==='asc');sl();run();});document.addEventListener('keydown',function(ev){if(ev.key==='Escape')sm_(false);});"
          "var tb=document.querySelectorAll('[data-theme-set]');function th(v,save){var r=document.documentElement;if(v==='auto')delete r.dataset.theme;else r.dataset.theme=v;tb.forEach(function(b){b.setAttribute('aria-pressed',String(b.dataset.themeSet===v));});if(save){try{localStorage.setItem('crypt-theme',v);}catch(e){}}}"
          "th(document.documentElement.dataset.theme||'auto',false);tb.forEach(function(b){b.addEventListener('click',function(){th(b.dataset.themeSet,true);});});"
          "var sd=document.getElementById('side');document.getElementById('menubtn').addEventListener('click',function(){window.cse(1568,1568,.035,'square',.05);if(sd.showModal)sd.showModal();else sd.setAttribute('open','');});"
          "function sc(){if(sd.close)sd.close();else sd.removeAttribute('open');}document.getElementById('sideclose').addEventListener('click',sc);"
          "sd.addEventListener('click',function(ev){if(ev.target!==sd)return;var r=sd.getBoundingClientRect();if(ev.clientX<r.left||ev.clientX>r.right||ev.clientY<r.top||ev.clientY>r.bottom)sc();});"
          "var dlg=document.getElementById('adv');document.getElementById('advbtn').addEventListener('click',function(){if(dlg.showModal)dlg.showModal();else dlg.setAttribute('open','');});"
          "function cl(){if(dlg.close)dlg.close();else dlg.removeAttribute('open');}document.getElementById('advclose').addEventListener('click',cl);document.getElementById('advok').addEventListener('click',cl);"
          "dlg.addEventListener('click',function(ev){if(ev.target!==dlg)return;var r=dlg.getBoundingClientRect();if(ev.clientX<r.left||ev.clientX>r.right||ev.clientY<r.top||ev.clientY>r.bottom)cl();});"
          "document.getElementById('nhclear').addEventListener('click',function(){document.getElementById('reset').click();});document.getElementById('reset').addEventListener('click',function(){sel.forEach(function(s){s.value='all';f[s.dataset.g]='all';});seg('all');q.value='';qxs();run();});"
          "document.querySelectorAll('[data-set]').forEach(function(b){b.addEventListener('click',function(){lab();sl();conds();});});lab();sl();run();")
    exp = re.search(r'(?s)^(.*?<script>.*?</script>)', (C / 'timeline/index.html').read_text(encoding='utf-8')).group(1)  # same head as the timeline page
    head = re.sub(r"<script>try\{var th=localStorage.*?</script>", '', exp.split('<title>')[0])
    BAR = re.search(r'<header class="bar">.*?</header>', (C / 'timeline/index.html').read_text(encoding='utf-8'), re.S).group(0)
    LANGJS = re.search(r"var root=document\.documentElement.*?\}\);\}\);", (C / 'timeline/index.html').read_text(encoding='utf-8'), re.S).group(0)
    MENUB = (f'<button type="button" class="menub" id="menubtn" aria-haspopup="dialog" aria-label="メニュー / Menu" title="このデータベースについて / About"><svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 7h16M4 12h16M4 17h16"/></svg></button>')
    BAR = sidemenu.cbar(BAR, T)
    head += "<script>try{var th=localStorage.getItem('crypt-theme');if(th==='light'||th==='dark')document.documentElement.dataset.theme=th;else if(th!=='auto')document.documentElement.dataset.theme='light';}catch(e){}</script>"
    page = (f'{head}{sidemenu.ICON}<title>Cryptoole — 未解決暗号のオープン検索エンジン / open search for unsolved ciphers</title><meta name="author" content="satorunet">'
            f'<meta name="description" content="Cryptiana・cyphersolver・CryptoCellar・DECODE・cipher-readings の未解決暗号を一元的に検索。状況・種類・言語・地域・年代で横断して絞り込める。"><link rel="canonical" href="{sidemenu.SEARCH_URL}">'
            f'<meta property="og:type" content="website"><meta property="og:site_name" content="Cryptoole"><meta property="og:url" content="{sidemenu.SEARCH_URL}">'
            f'<meta property="og:title" content="Cryptoole — 未解決暗号のオープン検索エンジン"><meta property="og:description" content="Cryptiana・cyphersolver・CryptoCellar・DECODE・cipher-readings の未解決暗号を一元的に検索。状況・種類・言語・地域・年代で横断して絞り込める。">'
            f'<meta property="og:image" content="{sidemenu.SEARCH_URL}og.png?v={int((H / 'og.png').stat().st_mtime) if (H / 'og.png').exists() else 0}"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630"><meta property="og:image:alt" content="Cryptoole — 未解決暗号のオープン検索エンジン">'
            f'<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="Cryptoole — 未解決暗号のオープン検索エンジン"><meta name="twitter:description" content="未解決の歴史的暗号を一元的に検索できるエンジン。"><meta name="twitter:image" content="{sidemenu.SEARCH_URL}og.png?v={int((H / 'og.png').stat().st_mtime) if (H / 'og.png').exists() else 0}">\n'
            f'<style>{CSS}{sidemenu.LOGO_CSS}{sidemenu.GH_CSS}{sidemenu.SPIN_CSS}</style></head><body><main>\n{BAR}\n{body}\n</main>\n<script>(function(){{{LANGJS}{sidemenu.SE_JS}{js}}})();</script></body></html>\n')
    page = page.replace('href="/crypt/', 'href="https://satoru.net/crypt/')   # served from cryptoole.satoru.net: links back to satoru.net are absolute
    (H / 'index.html').write_text(page, encoding='utf-8')
    (H / 'udb.py.txt').write_text(Path(__file__).read_text(encoding='utf-8'), encoding='utf-8')
    import apidoc   # the public API specification page, from the same code tables
    import seriespage   # series.html: one grouped series, linked from the list
    import specpage     # spec.html: the unified-format specification (from ID-SPEC.md)
    specpage.write(CSS, head, BAR, LANGJS, T, MENU)
    seriespage.write(CSS, head, BAR, LANGJS, js, CJ, MJ, SIJ, T, MENU)
    write_stats(db, D, CSS, head, BAR, LANGJS, T)
    F = [facets(r) for r in rs]
    counts = {'src': {k: cnt('src', k) for k in SRC}, 'lang': {k: sum(1 for f in F if k in f[0]) for k in LANG}, 'reg': {k: sum(1 for f in F if f[2] == k) for k in REG}}
    apidoc.write(CSS, head, LANGJS, SRC, LANG, REG, counts, n, fmt_when_iso(upd, True))
    print('built', n, {k: cnt('cat', k) for k in CAT}, {k: cnt('src', k) for k in SRC})

def main():
    db = connect()
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'import':
        do_import(db)
    elif cmd == 'pending':
        rs = db.execute('SELECT e.src,e.key,e.title_en,e.grp,e.date_text,e.shelfmark,e.status_src FROM entries e LEFT JOIN ja j USING(src,key) WHERE j.title_ja IS NULL').fetchall()
        print(json.dumps([dict(r) for r in rs], ensure_ascii=False, indent=1))
    elif cmd == 'ja':
        for x in json.loads(Path(sys.argv[2]).read_text(encoding='utf-8')):
            db.execute('INSERT INTO ja VALUES(?,?,?,?) ON CONFLICT(src,key) DO UPDATE SET title_ja=excluded.title_ja,note_ja=excluded.note_ja',
                       (x['src'], x['key'], x['title_ja'], x.get('note_ja', '')))
        db.commit(); print('ok')
    elif cmd == 'same':
        g, note, mems = sys.argv[2], sys.argv[3], sys.argv[4:]
        db.execute('DELETE FROM same WHERE grp=?', (g,))
        for i, m in enumerate(mems):
            s, k = m.split(':', 1)
            if not db.execute('SELECT 1 FROM entries WHERE src=? AND key=?', (s, k)).fetchone(): sys.exit(f'no entry {m}')
            db.execute('INSERT OR REPLACE INTO same VALUES(?,?,?,?)', (g, i, s, k))
        db.execute('INSERT OR REPLACE INTO same_note VALUES(?,?,?)', (g, note, datetime.date.today().isoformat()))
        db.commit(); print('ok', g, len(mems))
    elif cmd == 'build':
        build(db)
    else:
        print(__doc__)

if __name__ == '__main__':
    main()
