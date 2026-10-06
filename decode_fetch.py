"""Fetch DECODE (de-crypt.org) records through its public JSON API into unsolved.sqlite.

  python3 decode_fetch.py list            the whole record list (one request) -> table decode_list
  python3 decode_fetch.py detail [--all] [--shard=k/n]  per-record detail -> table decode_raw (only records not fetched yet,
                                          or all with --all); one request at a time, polite delay

API: /decrypt-web/api/list/records?recperpage=N&start=1 and /decrypt-web/api/view/records/<id>.
Only metadata is stored (no images)."""
import json, sqlite3, sys, time, urllib.request
from pathlib import Path
H = Path(__file__).resolve().parent
DB = H / 'unsolved.sqlite'
API = 'https://de-crypt.org/decrypt-web/api/'
UA = {'User-Agent': 'Mozilla/5.0 (satoru.net crypt index)'}
DELAY = 0.3

def get(url, timeout=120):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))

def connect():
    db = sqlite3.connect(DB, timeout=120)
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('''CREATE TABLE IF NOT EXISTS decode_list(id INTEGER PRIMARY KEY, json TEXT NOT NULL, seen TEXT NOT NULL);
                        CREATE TABLE IF NOT EXISTS decode_raw(id INTEGER PRIMARY KEY, json TEXT NOT NULL, fetched TEXT NOT NULL);''')
    return db

def do_list(db):
    d = get(API + 'list/records?recperpage=20000&start=1', timeout=600)
    now = time.strftime('%Y-%m-%d')
    for r in d['records']:
        db.execute('INSERT OR REPLACE INTO decode_list VALUES(?,?,?)', (int(r['id']), json.dumps(r, ensure_ascii=False), now))
    db.commit()
    print('list', d['totalRecordCount'], len(d['records']))

def do_detail(db, everything=False):
    ids = [i for (i,) in db.execute('SELECT id FROM decode_list ORDER BY id')]
    have = set() if everything else {i for (i,) in db.execute('SELECT id FROM decode_raw')}
    todo = [i for i in ids if i not in have]
    sh = next((x.split('=')[1] for x in sys.argv if x.startswith('--shard=')), None)   # --shard=k/n: only ids with id % n == k
    if sh:
        k, nn = map(int, sh.split('/')); todo = [i for i in todo if i % nn == k]
    print('detail todo', len(todo), flush=True)
    for n, i in enumerate(todo, 1):
        for attempt in range(3):
            try:
                d = get(f'{API}view/records/{i}')
                if d.get('success'):
                    db.execute('INSERT OR REPLACE INTO decode_raw VALUES(?,?,?)', (i, json.dumps(d['records'], ensure_ascii=False), time.strftime('%Y-%m-%d')))
                break
            except Exception as x:
                time.sleep(5 * (attempt + 1))
        db.commit()
        if n % 100 == 0:
            print('detail', n, '/', len(todo), flush=True)
        time.sleep(DELAY)
    db.commit()
    print('detail done', len(todo))

if __name__ == '__main__':
    db = connect()
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'list': do_list(db)
    elif cmd == 'detail': do_detail(db, '--all' in sys.argv)
    else: print(__doc__)
