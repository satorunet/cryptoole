# Copyright (c) 2026 satoru.net. MIT License (see LICENSE): https://github.com/satorunet/cryptoole
# SPDX-License-Identifier: MIT
"""Render og.png (1200x630) for the Twitter/OGP card of the Cryptoole top page, with headless Chromium (Python playwright).
Run after udb.py build when the counts change:  python3 ogimage.py"""
import asyncio, json
from pathlib import Path
from playwright.async_api import async_playwright
H = Path(__file__).resolve().parent

def html():
    D = json.loads((H / 'idx.json').read_text(encoding='utf-8'))
    top = {'open': 'open', 'part': 'open', 'key': 'open', 'solved': 'solved', 'na': 'na'}
    n = {'open': 0, 'solved': 0, 'na': 0}   # count records, not rows: a series row counts each member (pc = [solved, unsolved, unknown])
    for x in D:
        if x.get('pc'):
            for k, v in zip(('solved', 'open', 'na'), x['pc']): n[k] += v
        else: n[top[x['c']]] += 1
    recs = sum(n.values())
    sv = lambda d: f'<svg viewBox="0 0 24 24" width="34" height="34" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">{d}</svg>'
    ic = {'all': sv('<path d="M12 3 3 8l9 5 9-5-9-5z"/><path d="m3 13 9 5 9-5"/>'),   # same icons as the status tabs (udb.SICON)
          'open': sv('<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>'),
          'solved': sv('<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 7.5-2"/>'),
          'na': sv('<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14"/><path d="M12 17.5h.01"/>')}
    emb = 'data:image/svg+xml;base64,' + __import__('base64').b64encode((H / 'emblem.svg').read_bytes()).decode()
    return (f'''<!doctype html><html><head><meta charset="utf-8"><style>
body{{margin:0;width:1200px;height:630px;background:#f7f4ee;font-family:"Noto Serif JP",Georgia,serif;color:#1f1d1a;display:flex;flex-direction:column;justify-content:center;padding:0 90px;box-sizing:border-box}}
img.em{{width:118px;height:118px;vertical-align:-14px;margin-right:22px}}.logo{{font:700 132px/1 Georgia,"Noto Serif",serif;letter-spacing:-2px}}.tag{{font:500 38px/1.35 "Noto Sans JP",system-ui,sans-serif;color:#4a453e;margin:18px 0 36px}}.tag span{{display:block;font:500 25px/1.4 "Noto Sans",system-ui,sans-serif;color:#6b655c;margin-top:4px}}
.seg{{display:grid;grid-template-columns:repeat(4,1fr);width:1020px;border:2px solid #ddd5c7;border-radius:22px;overflow:hidden;background:#fffdf8}}.c{{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;padding:20px 8px 18px;border-right:2px solid #ddd5c7}}.c:last-child{{border-right:0}}.c.on{{background:#f3e7d9;box-shadow:inset 0 -6px 0 #8a3b12}}.c b{{display:flex;align-items:center;gap:12px;font:700 46px/1 Georgia,serif;color:#1f1d1a}}.c svg{{flex:none}}.c i{{font:700 22px/1.2 'Noto Sans JP',system-ui,sans-serif;font-style:normal;letter-spacing:.06em}}.c i span{{font-weight:500;font-size:19px;margin-left:8px;opacity:.85}}.src{{margin-top:34px;font:500 24px 'Noto Sans JP',system-ui,sans-serif;color:#6b655c}}
</style></head><body>
<div class="logo"><img src="EMB" class="em">Crypt<span style="color:#3554b5">o</span><span style="color:#d4472a">o</span><span style="color:#e0a000">l</span><span style="color:#2e7d55">e</span></div>
<div class="tag">未解決暗号のオープン検索エンジン<span>open search engine for unsolved historical ciphers</span></div>
<div class="seg"><div class="c on"><b>{ic['all']}{recs:,}</b><i style="color:#6b655c">全て<span>All</span></i></div><div class="c"><b style="color:#a3161b">{ic['open']}<span style="color:#1f1d1a">{n['open']:,}</span></b><i style="color:#a3161b">未解読<span>Unsolved</span></i></div><div class="c"><b style="color:#2e7d4f">{ic['solved']}<span style="color:#1f1d1a">{n['solved']:,}</span></b><i style="color:#2e7d4f">解読済<span>Solved</span></i></div><div class="c"><b style="color:#7a7468">{ic['na']}<span style="color:#1f1d1a">{n['na']:,}</span></b><i style="color:#7a7468">不明<span>Unknown</span></i></div></div>
<div class="src">Cryptiana · cyphersolver · CryptoCellar · DECODE · cipher-readings</div></body></html>''').replace('EMB', emb)

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={'width': 1200, 'height': 630})
        await pg.set_content(html(), wait_until='networkidle')
        await pg.screenshot(path=str(H / 'og.png'))
        await b.close()

if __name__ == '__main__':
    asyncio.run(main()); print('og.png written')
