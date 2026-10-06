"""Write /crypt/unsolved/api.html: the public specification of api.cgi.
Called from udb.py build (so the code tables below always match the data)."""
import html, re, sys
from pathlib import Path
H = Path(__file__).resolve().parent
C = H.parent
sys.path.insert(0, str(H))   # sidemenu.py lives next to this file
import sidemenu

e = lambda x: html.escape(str(x), quote=True)
T = lambda ja, en: f'<span class="t" lang="ja">{ja}</span><span class="t" lang="en">{en}</span>'
BASE = sidemenu.SEARCH_URL + 'api.cgi'

def table(head, rows):
    return ('<div class="grid"><table><thead><tr>' + ''.join(f'<th>{h}</th>' for h in head) + '</tr></thead><tbody>'
            + ''.join('<tr>' + ''.join(f'<td>{c}</td>' for c in r) + '</tr>' for r in rows) + '</tbody></table></div>')

def write(CSS, head, LANGJS, SRC, LANG, REG, counts, total, updated):
    code = lambda s: f'<code>{e(s)}</code>'
    ex = lambda q: f'<a href="api.cgi?{e(q)}"><code>api.cgi?{e(q)}</code></a>'
    params = [
        (code('q'), T('検索語。空白で区切ると全語を含むもの（AND）。題名・所蔵番号・説明・ID を大文字小文字の区別なく部分一致で探す。最大8語。',
                      'Search words; space-separated words must all match (AND). Case-insensitive substring match over titles, shelfmarks, details and IDs. Up to 8 words.'), '—'),
        (code('status'), T('状況。', 'Status.') + ' ' + ', '.join(code(x) for x in ('open', 'solved', 'na')), code('all')),
        (code('source'), T('出典（その出典を含む行）。', 'Source (rows that include it).') + ' ' + ', '.join(code(k) for k in SRC), code('all')),
        (code('type'), T('種類。', 'Record type.') + ' ' + ', '.join(code(x) for x in ('cipher', 'key', 'manual', 'other')), code('all')),
        (code('language'), T('言語コード（下表）。', 'Language code (table below).'), code('all')),
        (code('region'), T('地域コード（下表）。', 'Region code (table below).'), code('all')),
        (code('century'), T('世紀（例 16）。年代不明は 0。', 'Century (e.g. 16); 0 = undated.'), code('all')),
        (code('sort'), ', '.join(code(x) for x in ('date', 'date-desc', 'solved', 'solved-asc', 'added'))
         + T('（暗号の年代 古い順／新しい順、解決日 新しい順／古い順、追加日 新しい順）', ' (cipher date asc/desc, solve date desc/asc, date added desc)'), code('date')),
        (code('offset'), T('何件目から返すか（0 始まり）。', 'Zero-based start position.'), code('0')),
        (code('limit'), T('返す件数。1〜200。', 'Number of items, 1–200.'), code('100')),
        (code('cid') + ' / ' + code('sid'), T('統一ID（記録 FR1591-3・シリーズ CS00042）で引く。その記録・シリーズを含む1行を返す。', 'Look up by Cryptoole ID (record FR1591-3, series CS00042); returns the one row that holds it.'), '—'),
        (code('id'), T('行の ID（例 decode:3753）を指定すると、その1行だけを返す。ほかのパラメータは無視する。まとめた行の各記録は group_members に入る。', 'Return just the row with this ID (e.g. decode:3753); other parameters are ignored. Members of a grouped row are in group_members.'), '—'),
    ]
    fields = [
        ('id', 'string', T('出典:キー（例 decode:9451）。行の識別子。', 'source:key (e.g. decode:9451); row identifier.')),
        ('source_ids', 'array', T('出典サイト側の番号（例 DECODE R1876, cyphersolver #152）。統一ID とは別に持つ情報。', 'The sources’ own numbers (e.g. DECODE R1876, cyphersolver #152), kept beside the Cryptoole ID.')),
        ('cid', 'string', T('統一記録ID（国＋年－連番、例 FR1591-3）。一度振ったら変わらない。', 'Cryptoole record ID (country + year - serial, e.g. FR1591-3); never changes once given.')),
        ('sid', 'string|null', T('統一シリーズID（CS + 5桁）。まとめた行のみ。', 'Cryptoole series ID (CS + 5 digits); grouped rows only.')),
        ('status', 'string', T('open（未解決）／solved（解決）／na（不明）', 'open / solved / na (unknown)')),
        ('status_detail', 'string|null', T('partly（一部解読）／key_only（鍵のみ判明）', 'partly / key_only')),
        ('type', 'string', 'cipher / key / manual / other'),
        ('sources', 'string[]', T('この行に含まれる出典（同じ暗号をまとめた場合は複数）', 'Sources in this row (several when merged)')),
        ('title_ja, title_en', 'string', T('題名（日本語／英語）', 'Title (Japanese / English)')),
        ('url', 'string', T('主出典の該当ページ', 'Page at the main source')),
        ('date_ja, date_en', 'string', T('暗号の日付（表示用）', 'Cipher date (for display)')),
        ('date_sort', 'string|null', T('YYYY-MM-DD（不明部分は 00）', 'YYYY-MM-DD (00 where unknown)')),
        ('solved_sort', 'string|null', T('解決日 YYYY-MM-DD（Cryptiana の記述から抽出）', 'Solve date YYYY-MM-DD (extracted from Cryptiana’s text)')),
        ('added', 'string', T('このデータベースに初めて入った日', 'Date first added to this database')),
        ('languages', 'string[]', T('言語コード', 'Language codes')),
        ('region, century', 'string, int|null', T('地域コード、世紀', 'Region code, century')),
        ('details_ja, details_en', 'string', T('所蔵番号・言語・地域・解決情報を1行にまとめた表示用の文', 'One-line display text: shelfmark, language, region, solve info')),
        ('note_ja', 'string|null', T('短い背景説明（cyphersolver の項目）', 'Short context (cyphersolver items)')),
        ('satoru_page', 'string|null', T('satoru.net の解読ページ', 'satoru.net decipherment page')),
        ('no_longer_listed', 'bool', T('出典の一覧から外れた（CryptoCellar では解読済みを意味する）', 'Dropped from the source list (for CryptoCellar: broken)')),
        ('same_cipher', 'object[]', T('同じ暗号とみなした他出典の記録 {source, url, title_ja, title_en}', 'Records judged to be the same cipher {source, url, title_ja, title_en}')),
    ]
    body = (f'<h1>{sidemenu.LOGO_HTML} API</h1>'
            f'<p class="lead">{T(f"Cryptoole（未解決暗号のオープン検索エンジン、{total:,} 件）を検索して JSON で返す API。登録・キー不要で、誰でも自由に使える。ブラウザから直接呼べる（CORS 許可）。",
                                 f"Search Cryptoole, the open search engine for unsolved ciphers ({total:,} rows), and get JSON. No sign-up or key; free for anyone to use. Callable from browsers (CORS enabled).")}</p>'
            f'<section><h2>{T("エンドポイント", "Endpoint")}</h2><pre><code>GET {BASE}</code></pre>'
            f'<p>{T("例", "Examples")}:</p><ul><li>{ex("q=dinteville")}</li><li>{ex("status=open&source=cyphersolver&sort=date")}</li>'
            f'<li>{ex("status=solved&source=cryptiana&sort=solved&limit=20")}</li><li>{ex("type=key&century=16&language=it&offset=100&limit=50")}</li></ul></section>'
            f'<section><h2>{T("パラメータ", "Parameters")}</h2>' + table([T('名前', 'Name'), T('内容', 'Meaning'), T('既定', 'Default')], params) + '</section>'
            f'<section><h2>{T("応答", "Response")}</h2><pre><code>{{\n  "total": 1285,      // {e("条件に合う件数 / matching rows")}\n  "all": {total},       // {e("全件数 / all rows")}\n  "offset": 0,\n  "items": [ {{ … }} ]  // {e("最大 limit 件 / up to limit items")}\n}}</code></pre>'
            + table([T('項目', 'Field'), T('型', 'Type'), T('内容', 'Meaning')], [(code(a), code(b), c) for a, b, c in fields])
            + f'<p class="note">{T("次のページは offset に offset+limit を渡して取る（total に達するまで）。エラー時は HTTP 500 と {\"error\": …} を返す。応答は5分間キャッシュされる。", "Page through results with offset = offset + limit until total. Errors return HTTP 500 with {\"error\": …}. Responses are cached for 5 minutes.")}</p></section>'
            f'<section><h2>{T("コード表", "Code tables")}</h2><h3>{T("出典", "Sources")} (source)</h3>'
            + table([T('コード', 'Code'), T('名前', 'Name'), T('件数', 'Rows')], [(code(k), f'<a href="{e(v[2])}">{T(e(v[0]), e(v[1]))}</a>', counts['src'].get(k, 0)) for k, v in SRC.items()])
            + f'<h3>{T("言語", "Languages")} (language)</h3>'
            + table([T('コード', 'Code'), T('言語', 'Language'), T('件数', 'Rows')], [(code(k), T(*LANG[k]), counts['lang'].get(k, 0)) for k in LANG if k != 'xx' and counts['lang'].get(k)])
            + f'<h3>{T("地域", "Regions")} (region)</h3>'
            + table([T('コード', 'Code'), T('地域', 'Region'), T('件数', 'Rows')], [(code(k), T(*REG[k]), counts['reg'].get(k, 0)) for k in REG])
            + '</section>'
            f'<section><h2>{T("使い方の例", "Usage")}</h2><pre><code>curl "{BASE}?q=dinteville"\n\n'
            f'fetch("{BASE}?status=open&amp;limit=10")\n  .then(r =&gt; r.json())\n  .then(d =&gt; console.log(d.total, d.items.map(x =&gt; x.title_en)));</code></pre></section>'
            f'<section><h2>{T("利用条件", "Terms")}</h2><ul>'
            f'<li>{T("API とこのデータベースの構成（分類・日本語題名・対応づけ）は自由に使ってよい。出典として「Cryptoole（satoru.net）」とリンクを示してもらえると助かる。", "The API and this database’s compilation (classification, Japanese titles, cross-links) are free to use. A credit link to “Cryptoole (satoru.net)” is appreciated.")}</li>'
            f'<li>{T("各項目の題名・所蔵番号・状況などは、それぞれの出典（Cryptiana・cyphersolver・CryptoCellar・DECODE）に由来する。再利用するときは各項目の出典（sources と url）を示すこと。DECODE の画像はこの API に含まれず、利用には所蔵機関の許可が要る場合がある。", "Titles, shelfmarks, statuses etc. come from the respective sources (Cryptiana, cyphersolver, CryptoCellar, DECODE); when reusing, cite each item’s source (sources and url). DECODE images are not part of this API and may need the holding library’s permission.")}</li>'
            f'<li>{T("短時間に大量のリクエストを送らないこと。全件が必要なときは limit=200 で順に取る。", "Please don’t flood the server; to fetch everything, page through with limit=200.")}</li>'
            f'<li>{T(f"データは出典を取り直すたびに更新される（最終取得 {e(updated)}）。内容の正確さは保証しない。", f"Data is refreshed whenever the sources are re-fetched (last {e(updated)}). No warranty of accuracy.")}</li></ul></section>'
            f'<footer>satorunet · <a href="/crypt/">crypt</a> · <a href="./">Cryptoole</a> · <a href="/crypt/timeline/">{T("更新の時系列", "Timeline of updates")}</a> · <a href="https://github.com/satorunet/cryptoole/blob/main/api.cgi">api.cgi</a> · <a href="https://github.com/satorunet/cryptoole">GitHub</a></footer>')
    BAR = re.search(r'<header class="bar">.*?</header>', (C / 'timeline/index.html').read_text(encoding='utf-8'), re.S).group(0)
    BAR = sidemenu.cbar(BAR, T)
    menu = sidemenu.drawer(T, [('./', 'Cryptoole（未解決暗号のオープン検索）', 'Cryptoole (open search for unsolved ciphers)'), ('spec.html', '未解決暗号の統一フォーマット（仕様案）', 'Unified format for unsolved ciphers (draft)'), ('/crypt/', 'crypt トップ', 'crypt home')])
    css = CSS + sidemenu.CSS + ('pre{background:var(--paper);border:1px solid var(--line);border-radius:8px;padding:10px 12px;overflow-x:auto;font-size:13px;line-height:1.55}'
                                '.grid{overflow-x:auto}.grid table{border-collapse:collapse;width:100%;font-size:14px}.grid th,.grid td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}'
                                '.grid th{font:600 13px system-ui,sans-serif;color:var(--muted)}h3{font-size:15px;margin:16px 0 6px}section{margin:20px 0}')
    page = (f'{head}{sidemenu.EARLY}{sidemenu.ICON}<title>Cryptoole API</title><meta name="author" content="satorunet">'
            f'<meta name="description" content="Cryptoole（未解決暗号のオープン検索エンジン）の公開 API の仕様。登録不要・CORS 対応で誰でも使える。"><link rel="canonical" href="{sidemenu.SEARCH_URL}api.html">\n'
            f'<style>{css}</style></head><body><main>\n{BAR}\n{body}\n{menu}\n</main>\n<script>(function(){{{LANGJS}{sidemenu.JS}}})();</script></body></html>\n')
    page = page.replace('href="/crypt/', 'href="https://satoru.net/crypt/')
    (H / 'api.html').write_text(page, encoding='utf-8')
    (H / 'api.cgi.txt').write_text((H / 'api.cgi').read_text(encoding='utf-8'), encoding='utf-8')
