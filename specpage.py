"""Write /spec.html: the readable page of ID-SPEC.md (the unified format for unsolved ciphers: IDs, series, dates, solutions).
ID-SPEC.md stays the source; this page is regenerated on every udb.py build."""
import re, sys
from pathlib import Path
import markdown
H = Path(__file__).resolve().parent
sys.path.insert(0, str(H))
import sidemenu

def write(CSS, head, BAR, LANGJS, T, menu_links):
    md = (H / 'ID-SPEC.md').read_text(encoding='utf-8')
    title = re.match(r'#\s*(.+)', md).group(1).strip()
    html = markdown.markdown(md, extensions=['tables', 'fenced_code', 'toc'], output_format='html5')
    # table of contents from the h2 headings
    toc = ''.join(f'<li><a href="#{a}">{re.sub(r"<[^>]+>", "", h)}</a></li>' for a, h in re.findall(r'<h2 id="([^"]+)">(.*?)</h2>', html))
    html = re.sub(r'<table>', '<div class="grid"><table>', html).replace('</table>', '</table></div>')
    intro = (f'</h1><p class="note">{T("検討中の案。未解決暗号を一元管理するための ID・シリーズ・日付・解決の記録のルールをまとめたもの。", "A draft under discussion: the rules for IDs, series, dates and solution records used to manage unsolved ciphers in one place.")}</p>'
             f'<nav class="toc" aria-label="目次 / Contents"><b>{T("目次", "Contents")}</b><ul>{toc}</ul></nav>')
    body = '<p class="crumb"><a href="./">← Cryptoole</a></p>' + html.replace('</h1>', intro, 1)
    css = CSS + sidemenu.CSS + (
        '.crumb{margin:4px 0 6px;font-size:14px}.spec h1{font-size:24px;line-height:1.35}.spec h2{font-size:18px;margin-top:28px;padding-top:6px;border-top:1px solid var(--line)}'
        '.spec h3{font-size:15.5px;margin-top:18px}.spec p,.spec :not(.navl)>li{font-size:15px;line-height:1.75}.spec code{font-size:.9em;background:var(--paper);border:1px solid var(--line);border-radius:4px;padding:0 4px}'
        '.spec pre{background:var(--paper);border:1px solid var(--line);border-radius:8px;padding:10px 12px;overflow-x:auto;font-size:13px;line-height:1.5}.spec pre code{border:0;padding:0;background:none}'
        '.grid{overflow-x:auto}.grid table{border-collapse:collapse;width:100%;font-size:14px;margin:8px 0}.grid th,.grid td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}'
        '.grid th{font:600 13px system-ui,sans-serif;color:var(--muted)}.toc{border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin:12px 0 18px;background:var(--paper)}'
        '.toc b{font-size:13px;color:var(--muted)}.toc ul{list-style:none;margin:6px 0 0;padding:0;font-size:14px;line-height:1.9}.toc li{margin:0;padding:0;border:0;background:none}.toc li::before{content:none}.toc a{display:inline;border:0;padding:0;background:none;text-decoration:none}.toc a:hover{text-decoration:underline}')
    bar = sidemenu.cbar(BAR, T)
    page = (f'{head}{sidemenu.EARLY}{sidemenu.ICON}<title>{title} — Cryptoole</title><meta name="author" content="satorunet">'
            f'<link rel="canonical" href="{sidemenu.SEARCH_URL}spec.html">\n<style>{css}</style></head><body><main class="spec">\n{bar}\n{body}\n'
            f'<footer>satorunet · <a href="./">Cryptoole</a> · <a href="ID-SPEC.md">ID-SPEC.md</a></footer>\n{sidemenu.drawer(T, menu_links)}\n</main>\n'
            f'<script>(function(){{{LANGJS}{sidemenu.JS}}})();</script></body></html>\n')
    page = page.replace('href="/crypt/', 'href="https://satoru.net/crypt/')
    (H / 'spec.html').write_text(page, encoding='utf-8')
