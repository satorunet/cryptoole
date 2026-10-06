#!/usr/bin/python3
# Copyright (c) 2026 satoru.net. MIT License (see LICENSE): https://github.com/satorunet/cryptoole
# SPDX-License-Identifier: MIT
# 未解決暗号データベースの検索 API（serve.sqlite を読むだけ。udb.py build が作る）
# 例: api.cgi?status=open&source=decode&language=fr&q=dinteville&sort=date&offset=0&limit=100
# 仕様: api.html（誰でも自由に使える。キー不要、CORS 許可）
import json, os, sqlite3, sys, urllib.parse
from pathlib import Path

DB = Path(__file__).resolve().parent / 'serve.sqlite'
SORT = {'date': ("k = ''", 'k ASC'), 'date-desc': ("k = ''", 'k DESC'), 'solved': ("s = ''", 's DESC'),
        'solved-asc': ("s = ''", 's ASC'), 'added': ("a = ''", 'a DESC')}
TOP = {'open': ('open', 'part', 'key'), 'solved': ('solved',), 'na': ('na',)}
TOPOF = {'open': 'open', 'part': 'open', 'key': 'open', 'solved': 'solved', 'na': 'na'}
DETAIL = {'open': None, 'part': 'partly', 'key': 'key_only', 'solved': None, 'na': None}

def readable(x):
    """Public field names (the page itself asks for compact=1 and gets the short keys)."""
    sid_of = lambda r: (lambda s, k: {'source': s, 'id': 'R' + k if s == 'decode' else '#' + k if s == 'cyphersolver' else k})(*r.split(':', 1))
    return {'id': x['i'], 'cid': x.get('pid'), 'sid': x.get('cs'), 'source_dates': [{'source': d[0], 'created': d[1] or None, 'updated': d[2] or None, 'updated_scope': d[3] or None, 'change_seen': d[4] or None} for d in x.get('sd', [])], 'source_ids': [sid_of(r) for r in [x['i']] + [m[6] for m in x.get('m', []) if x.get('mk') == 'same']], 'status': TOPOF[x['c']], 'status_detail': DETAIL[x['c']], 'type': x['y'], 'sources': x['S'],
            'title_ja': x['tj'], 'title_en': x['te'], 'url': x['u'], 'date_ja': x['dj'], 'date_en': x['de'],
            'date_sort': x['k'] or None, 'solved_sort': x['s'] or None, 'added': x['a'], 'languages': [l for l in x['L'] if l != 'xx'],
            'region': x['R'], 'century': x['C'] or None, 'details_ja': x['mj'], 'details_en': x['me'], 'note_ja': x.get('n'),
            'satoru_page': ('https://satoru.net/crypt/' + x['g'] + '/') if x.get('g') else None, 'no_longer_listed': bool(x.get('x')),
            'same_cipher': [{'source': m[6].split(':')[0], 'id': m[6], 'url': m[0], 'title_ja': m[7], 'title_en': m[8]} for m in x.get('m', []) if x.get('mk') == 'same'],
            'group_members': [{'id': m[6], 'cid': m[11] if len(m) > 11 else None, 'url': m[0], 'status': TOPOF[m[5]], 'date_en': m[2], 'details_en': m[4]} for m in x.get('m', []) if x.get('mk') != 'same']}

def out(obj, status='200 OK'):
    body = json.dumps(obj, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    sys.stdout.write(f'Status: {status}\r\nContent-Type: application/json; charset=utf-8\r\nAccess-Control-Allow-Origin: *\r\n'
                     f'Cache-Control: public, max-age=300\r\nContent-Length: {len(body)}\r\n\r\n')
    sys.stdout.flush(); sys.stdout.buffer.write(body)

def main():
    p = {k: v[-1] for k, v in urllib.parse.parse_qs(os.environ.get('QUERY_STRING', '')).items()}
    if p.get('cid') or p.get('sid'):   # unified ID: api.cgi?cid=CR000123 / ?sid=CS00042 -> the row that holds it
        db = sqlite3.connect(f'file:{DB}?mode=ro&immutable=1', uri=True)
        r = db.execute('SELECT row FROM uid WHERE uid = ?', ((p.get('cid') or p.get('sid')).strip().upper(),)).fetchone()
        if not r: return out({'error': 'not found'}, '404 Not Found')
        p['id'] = r[0]
    if p.get('id'):   # one row by id (series pages): api.cgi?id=decode:3753
        db = sqlite3.connect(f'file:{DB}?mode=ro&immutable=1', uri=True)
        r = db.execute('SELECT j FROM rows WHERE id = ?', (p['id'],)).fetchone()
        if not r: return out({'error': 'not found'}, '404 Not Found')
        x = json.loads(r[0])
        return out({'total': 1, 'items': [x if p.get('compact') == '1' else readable(x)]})
    where, args = [], []
    st = p.get('status', 'all')
    if st in TOP:
        where.append(f'c IN ({",".join("?" * len(TOP[st]))})'); args += TOP[st]
    for key, col in (('source', 'srcs'), ('language', 'langs')):        # space-delimited lists
        v = p.get(key, 'all')
        if v != 'all': where.append(f'{col} LIKE ?'); args.append(f'% {v} %')
    for key, col in (('type', 'y'), ('region', 'r'), ('century', 'cen')):
        v = p.get(key, 'all')
        if v != 'all': where.append(f'{col} = ?'); args.append(v)
    for w in (p.get('q') or '').lower().split()[:8]:
        where.append("t LIKE ? ESCAPE '\\'"); args.append('%' + w.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%')
    empty, order = SORT.get(p.get('sort', 'date'), SORT['date'])
    try: offset = max(0, int(p.get('offset', 0)))
    except ValueError: offset = 0
    try: limit = min(200, max(1, int(p.get('limit', 100))))
    except ValueError: limit = 100
    db = sqlite3.connect(f'file:{DB}?mode=ro&immutable=1', uri=True)
    db.row_factory = sqlite3.Row
    w = (' WHERE ' + ' AND '.join(where)) if where else ''
    total = db.execute(f'SELECT count(*) FROM rows{w}', args).fetchone()[0]
    rs = db.execute(f'SELECT j FROM rows{w} ORDER BY {empty}, {order}, k, id LIMIT ? OFFSET ?', args + [limit, offset]).fetchall()
    out({'total': total, 'all': db.execute('SELECT count(*) FROM rows').fetchone()[0], 'offset': offset,
         'items': [json.loads(r['j']) if p.get('compact') == '1' else readable(json.loads(r['j'])) for r in rs]})

try:
    main()
except Exception as x:
    out({'error': str(x)}, '500 Internal Server Error')
