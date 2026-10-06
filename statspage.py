"""Write /stats.html: counts compared by number solved — solvers, solve dates (year, month, cumulative), sources, centuries,
decades and countries. Counted per record (a series counts each record in it); regenerated on every udb.py build."""
import collections, datetime, re, sys
from pathlib import Path
H = Path(__file__).resolve().parent
sys.path.insert(0, str(H))
import sidemenu

TABS = [('top', '概要', 'Overview'), ('time', '解読の推移', 'Solves over time'), ('who', '解読者ランキング', 'Decipherers'), ('src', '出典別', 'By source'), ('age', '年代別', 'By period'), ('ctry', '国別', 'By country')]
TABJS = ("function mvi(sb){var i=document.querySelector('.stabs .sind');if(!i||!sb)return;i.style.width=sb.offsetWidth+'px';i.style.transform='translateX('+sb.offsetLeft+'px)';}"
         "var tb=document.querySelectorAll('.stabs [data-tab]'),tp=document.querySelectorAll('.tp');"
         "function show(k,push){var ok=false;tb.forEach(function(b){var on=b.dataset.tab===k;b.setAttribute('aria-selected',String(on));if(on)ok=true;});if(!ok)return;"
         "tp.forEach(function(p){p.hidden=p.dataset.tab!==k;if(!p.hidden)p.querySelectorAll('.cw').forEach(function(c){c.scrollLeft=c.scrollWidth;});});var bar=document.querySelector('.stabs'),sb=bar.querySelector('[aria-selected=\"true\"]');mvi(sb);if(sb){var l=sb.offsetLeft-bar.offsetLeft,r=l+sb.offsetWidth;if(l<bar.scrollLeft)bar.scrollLeft=l-8;else if(r>bar.scrollLeft+bar.clientWidth)bar.scrollLeft=r-bar.clientWidth+8;}if(push){try{history.replaceState(null,'','#'+k);}catch(e){}}}"
         "var bar=document.querySelector('.stabs'),pin=document.getElementById('stabs-pin');function hdr(){var h=document.querySelector('header');return h?Math.round(h.getBoundingClientRect().bottom):0;}function fit(){bar.style.top=hdr()+'px';mvi(bar.querySelector('[aria-selected=\"true\"]'));}fit();addEventListener('resize',fit);if(document.fonts)document.fonts.ready.then(fit);setTimeout(function(){bar.classList.add('anim');},50);tb.forEach(function(b){b.addEventListener('click',function(){var hh=hdr(),stuck=pin.getBoundingClientRect().top<hh;show(b.dataset.tab,true);if(stuck)scrollTo(0,pin.getBoundingClientRect().top+scrollY-hh);});});"
         "show((location.hash||'').slice(1)||tb[0].dataset.tab,false);window.addEventListener('hashchange',function(){show(location.hash.slice(1),false);});")
TOPC = {'solved': '#2e7d4f', 'open': '#a3161b', 'na': '#7a7468'}
TOPL = {'solved': ('解読済', 'Solved'), 'open': ('未解読', 'Unsolved'), 'na': ('不明', 'Unknown')}

def split_names(s):
    """'Victor and Thomas Bosbach' -> ['Victor Bosbach', 'Thomas Bosbach'] (same rule as the case page)."""
    a = [n.strip() for n in re.split(r'\s*(?:,|、|;|&|\band\b|\bwith\b)\s*', s or '') if n.strip()]
    out = []
    for i, n in enumerate(a):
        nx = a[i + 1] if i + 1 < len(a) else ''
        if ' ' not in n and ' ' in nx and n[:1].isupper(): n = n + ' ' + nx.split()[-1]
        out.append(re.sub(r'\s*[(\[][^)\]]*[)\]]', '', n).strip() or n)
    return out

def write(CSS, head, BAR, LANGJS, T, menu_links, recs, SRC, MARK, COUNTRY):
    """recs: one dict per record: src, top (solved/open/na), year (cipher), cc (country), solvers [names], solved (YYYY-MM-DD, 00 = unknown)."""
    e = lambda s: str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
    n = len(recs); c = collections.Counter(r['top'] for r in recs)
    rate = lambda s, o: f'{s * 100 / (s + o):.1f}%' if s + o else '—'

    def stack(rows, label_w='9em'):
        """rows: [(label_html, Counter)] -> stacked bars of solved/unsolved/unknown with counts and solve rate."""
        h = ''
        for lab, v in rows:   # each row is its own 100 %: the shares compare across rows of very different size
            t = sum(v.values()) or 1
            segs = ''.join(f'<i style="width:{v[k] * 100 / t:.3f}%;background:{TOPC[k]}" title="{TOPL[k][0]} {v[k]:,}"></i>' for k in ('solved', 'open', 'na') if v[k])
            h += (f'<div class="br"><div class="bl" style="width:{label_w}">{lab}</div><div class="bb"><span class="bs">{segs}</span>'
                  f'<span class="bn">{t:,}<small>{T("解読率 ", "solved ")}{rate(v["solved"], v["open"])}</small></span></div></div>')
        return h

    def bars(rows, color='#2e7d4f', label_w='7em'):
        mx = max((v for _, v in rows), default=1) or 1
        return ''.join(f'<div class="br"><div class="bl" style="width:{label_w}">{lab}</div><div class="bb"><span class="bs"><i style="width:{v * 100 / mx:.3f}%;background:{color}"></i></span>'
                       f'<span class="bn">{v:,}</span></div></div>' for lab, v in rows)

    def columns(rows, color='#2e7d4f', h=150, every=1, stacked=False):
        """Vertical bars that always fit the width: rows [(label, value)] or, stacked, [(label, Counter)]. Labels thinned to about 8."""
        if not rows: return ''
        tot = lambda v: sum(v.values()) if stacked else v
        mx = max(tot(v) for _, v in rows) or 1
        step = max(1, -(-len(rows) // 8))
        cols = ''
        for i, (lab, v) in enumerate(rows):
            if stacked:
                segs = ''.join(f'<i style="height:{v[k] * 100 / mx:.2f}%;background:{TOPC[k]}"></i>' for k in ('solved', 'open', 'na') if v[k])
                tip = f'{lab}: ' + ', '.join(f'{TOPL[k][1]} {v[k]}' for k in ('solved', 'open', 'na') if v[k])
                top = ''
            else:
                segs = f'<i style="height:{v * 100 / mx:.2f}%;background:{color}"></i>' if v else ''
                tip = f'{lab}: {v}'
                top = f'<b style="bottom:calc({v * 100 / mx:.2f}% + 2px)">{v}</b>' if v else ''
            cols += (f'<div class="cc" title="{e(tip)}"><div class="cb">{top}{segs}</div>'
                     f'<span class="cl">{e(lab) if i % step == 0 else ""}</span></div>')
        return f'<div class="col" style="height:{h}px">{cols}</div>'

    def line(points, color='#2e7d4f', h=160):
        """Cumulative line that fits the width: points [(date 'YYYY-MM-DD', cumulative)]."""
        if len(points) < 2: return ''
        d0 = datetime.date.fromisoformat(points[0][0]); d1 = datetime.date.fromisoformat(points[-1][0]); span = max(1, (d1 - d0).days)
        mx = points[-1][1]
        xy = [((datetime.date.fromisoformat(d) - d0).days * 1000 / span, 100 - v * 100 / mx) for d, v in points]
        path = ' '.join(f'{"M" if i == 0 else "L"}{x:.1f},{y:.2f}' for i, (x, y) in enumerate(xy))
        yrs = [y for y in range(d0.year + 1, d1.year + 1)]
        stp = max(1, -(-len(yrs) // 7)); stp = next(s for s in (1, 2, 5, 10, 20, 50) if s >= stp)
        ticks = ''.join(f'<span style="left:{(datetime.date(y, 1, 1) - d0).days * 100 / span:.2f}%">{y}</span>' for y in yrs if y % stp == 0)
        return (f'<div class="ln" style="height:{h}px"><svg viewBox="0 -4 1000 108" preserveAspectRatio="none" aria-hidden="true">'
                f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2.5" vector-effect="non-scaling-stroke"/></svg>'
                f'<b class="lv" style="top:0">{mx}</b><div class="lt">{ticks}</div></div>')

    sec = collections.defaultdict(list)
    # 1. overview
    sec['top'].append(f'<div class="kpi"><div><b>{n:,}</b>{T("記録", "records")}</div>'
               + ''.join(f'<div style="--c:{TOPC[k]}"><b>{c[k]:,}</b>{T(*TOPL[k])} <small>{c[k] * 100 / n:.1f}%</small></div>' for k in ('solved', 'open', 'na'))
               + f'<div><b>{rate(c["solved"], c["open"])}</b>{T("解読率", "solved rate")}</div></div>'
               + f'<p class="note">{T("「出典別」「年代別」「国別」の帯グラフは、各行の中での割合（解読済・未解読・不明）。数字はその行の件数と解読率。", "The bars under By source, By period and By country show the shares within each row (solved, unsolved, unknown); the numbers are the row’s count and solved rate.")}</p>'
               + f'<p class="note">{T("記録単位で数える（まとめたシリーズは中の記録ごと、複数の出典にある同じ暗号は1件）。解読率＝解読済 ÷（解読済＋未解読）。状況が不明の記録は解読率に含めない。", "Counted per record (a series counts each record in it; the same cipher in several sources counts once). Solved rate = solved ÷ (solved + unsolved); records of unknown status are left out of the rate.")}</p>')
    # 2. solve dates
    sol = [r for r in recs if r['top'] == 'solved' and r['solved'][:4].isdigit()]
    by_y = collections.Counter(int(r['solved'][:4]) for r in sol)
    if by_y:
        ys = list(range(min(by_y), max(by_y) + 1))
        sec['time'].append(f'<section><h2>{T("解読された年", "Year solved")}</h2><p class="note">{T(f"解読日が分かる {len(sol):,} 件（出典が解読日を記している記録のみ）。", f"The {len(sol):,} records whose solve date the sources give.")}</p>'
                   + columns([(str(y), by_y[y]) for y in ys]) + '</section>')
        recent = [r for r in sol if r['solved'][5:7] != '00']
        if recent:
            by_m = collections.Counter(r['solved'][:7] for r in recent)
            a, b = min(by_m), max(by_m); ms = []
            y, m = int(a[:4]), int(a[5:7])
            while f'{y:04d}-{m:02d}' <= b:
                ms.append(f'{y:04d}-{m:02d}'); m += 1
                if m > 12: y, m = y + 1, 1
            ms = ms[-36:]
            sec['time'].append(f'<section><h2>{T("解読された月", "Month solved")}</h2><p class="note">{T("月まで分かる解読（直近36か月）。", "Solves dated to the month (last 36 months).")}</p>'
                       + columns([(k[2:].replace('-', '/'), by_m[k]) for k in ms]) + '</section>')
            days = sorted(r['solved'] for r in recent if r['solved'][8:] != '00')
            if days:
                latest = sorted((r for r in recent if r['solved'][8:] != '00'), key=lambda r: r['solved'], reverse=True)[:12]
                sec['time'].append(f'<section><h2>{T("最近の解読", "Recent solves")}</h2><ul class="rl">'
                           + ''.join(f'<li><span class="d">{r["solved"]}</span><a href="case.html?id={e(r["row"])}">{T(e(r["tj"]), e(r["te"]))}</a>'
                                     + (f'<span class="who">{e("・".join(r["solvers"]))}</span>' if r['solvers'] else '') + '</li>' for r in latest) + '</ul></section>')
        cum, pts = 0, []
        for d in sorted(r['solved'].replace('-00', '-01') for r in sol):
            cum += 1; pts.append((d, cum))
        sec['time'].append(f'<section><h2>{T("解読数の累計", "Solves over time (cumulative)")}</h2>' + line(pts) + '</section>')
    # 3. solvers
    sv = collections.Counter(nm for r in recs if r['top'] in ('solved', 'open') for nm in r['solvers'])
    if sv:
        sec['who'].append(f'<section><h2>{T("解読者ランキング", "Decipherer ranking")}</h2><p class="note">{T("出典が解読者を記している記録のみ（Cryptiana・cipher-readings）。一部解読も含む。名前から、その人の解読した暗号を検索できる。", "Only records whose sources name the decipherer (Cryptiana, cipher-readings); partial readings included. Each name searches the ciphers they read.")}</p>'
                   + bars([(f'<span class="rk{" md m" + str(rk) if rk <= 3 else ""}" title="{rk}">{rk}</span><a href="./?q={e(nm)}">{e(nm)}</a>', v) for rk, nm, v in ranked(sv.most_common())], label_w='12em') + '</section>')
    # 4. sources
    by_s = collections.defaultdict(collections.Counter)
    for r in recs: by_s[r['src']][r['top']] += 1
    mk = lambda s: f'<span class="mk" style="background:{MARK[s][1]}">{MARK[s][0]}</span>'
    sec['src'].append(f'<section><h2>{T("出典ごと", "By source")}</h2>' + legend(T) + stack([(mk(s) + T(SRC[s][0].split("（")[0], SRC[s][1].split(" (")[0]), by_s[s]) for s in SRC if by_s[s]], '11em') + '</section>')
    # 5. when the ciphers were written
    by_c = collections.defaultdict(collections.Counter); by_d = collections.defaultdict(collections.Counter)
    for r in recs:
        y = r['year']
        by_c[(y - 1) // 100 + 1 if y else 0][r['top']] += 1
        if y and 1400 <= y < 2000: by_d[y // 10 * 10][r['top']] += 1
    sec['age'].append(f'<section><h2>{T("暗号の年代（世紀）", "When written (century)")}</h2>' + legend(T)
               + stack([(T(f'{k}世紀', f'{k}th c.') if k else T('年代不明', 'undated'), by_c[k]) for k in sorted(by_c, key=lambda k: (k == 0, k))]) + '</section>')
    if by_d:
        ds = list(range(min(by_d), max(by_d) + 10, 10))
        sec['age'].append(f'<section><h2>{T("暗号の年代（10年ごと）", "When written (by decade)")}</h2>' + legend(T) + columns([(str(d), by_d[d]) for d in ds], stacked=True) + '</section>')
    # 6. countries
    cn = {cc: (ja, en) for cc, ja, en, _ in COUNTRY}
    by_k = collections.defaultdict(collections.Counter)
    for r in recs: by_k[r['cc']][r['top']] += 1
    top = sorted((k for k in by_k if k in cn), key=lambda k: -sum(by_k[k].values()))[:15]
    sec['ctry'].append(f'<section><h2>{T("国ごと（出自・上位15）", "By country of origin (top 15)")}</h2>' + legend(T)
               + stack([(T(*cn[k]), by_k[k]) for k in top] + [(T('不明', 'unknown'), by_k['xx'])], '9em') + '</section>')

    body = (f'<p class="crumb"><a href="./" id="back">{T("検索へ戻る", "Back to search")}</a></p><h1>{T("未解読暗号の解読状況統計", "Decipherment statistics of unsolved ciphers")}</h1>'
            + '<div id="stabs-pin"></div><div class="stabs" role="tablist" aria-label="統計 / Statistics">' + ''.join(f'<button type="button" role="tab" data-tab="{k}" aria-selected="false">{T(ja, en)}</button>' for k, ja, en in TABS if sec[k]) + '<span class="sind" aria-hidden="true"></span></div>'
            + ''.join(f'<div class="tp" id="tp-{k}" role="tabpanel" data-tab="{k}"{"" if i == 0 else " hidden"}>' + ''.join(sec[k]) + '</div>' for i, (k, ja, en) in enumerate(t for t in TABS if sec[t[0]]))
            + f'<p class="note upd">{T("集計日", "Counted")} {datetime.date.today().isoformat()}</p>')
    css = CSS + sidemenu.CSS + sidemenu.LOGO_CSS + (
        'h1{font-size:24px;margin:4px 0 12px}.tp h2{font-size:17px;margin:26px 0 6px;padding-top:6px;border-top:1px solid var(--line)}.note{font-size:13px;color:var(--muted);margin:4px 0 10px}'
        '.crumb{margin:4px 0 6px;font-size:14px}#back{display:inline-flex;align-items:center;gap:6px}#back::before{content:"";width:.85em;height:.85em;background:currentColor;-webkit-mask:url(back.svg) center/contain no-repeat;mask:url(back.svg) center/contain no-repeat}'
        '.kpi{display:grid;grid-template-columns:repeat(5,1fr);border:1px solid var(--line);border-radius:12px;overflow:hidden;background:var(--paper)}'
        '.kpi div{padding:10px 8px;text-align:center;border-right:1px solid var(--line);font-size:12.5px;color:var(--c,var(--muted));font-weight:600}.kpi div:last-child{border-right:0}'
        '.kpi b{display:block;font:700 22px Georgia,serif;color:var(--ink)}.kpi small{font-weight:500;color:var(--muted)}'
        '@media (max-width:600px){.kpi{grid-template-columns:repeat(2,1fr)}.kpi div{border-bottom:1px solid var(--line)}.kpi div:first-child{grid-column:1/-1}}'
        '.br{display:flex;align-items:center;gap:10px;margin:5px 0;font-size:13.5px}.bl{flex:none;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}'
        '.bb{flex:1;display:flex;align-items:center;gap:8px;min-width:0}.bs{flex:1;display:flex;height:14px;border-radius:4px;overflow:hidden;background:color-mix(in srgb,var(--line) 45%,transparent)}.bs i{display:block;height:100%}'
        '.bn{flex:none;min-width:5.5em;font-variant-numeric:tabular-nums;font-weight:600}.bn small{display:block;font-weight:400;font-size:11px;color:var(--muted)}'
        '.lgd{display:flex;gap:14px;font-size:12px;color:var(--muted);margin:2px 0 6px}.lgd i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:-1px}'
        '.col{display:flex;align-items:stretch;gap:2px;margin:6px 0 4px;padding-bottom:18px;position:relative}.cc{flex:1 1 0;min-width:0;display:flex;flex-direction:column;position:relative}'
        '.cb{flex:1;display:flex;flex-direction:column-reverse;justify-content:flex-start;position:relative;border-bottom:1px solid var(--line)}.cb i{display:block;width:100%;border-radius:2px 2px 0 0}'
        '.cb b{position:absolute;left:50%;transform:translateX(-50%);font:600 9.5px system-ui,sans-serif;color:var(--ink);white-space:nowrap}'
        '.cc:last-child .cb b{left:auto;right:0;transform:none}.cc:first-child .cb b{left:0;transform:none}.cc:last-child .cl{left:auto;right:0}.cc .cl{position:absolute;top:100%;left:0;margin-top:3px;font:10.5px system-ui,sans-serif;color:var(--muted);white-space:nowrap}'
        '.ln{position:relative;margin:10px 0 26px;border-bottom:1px solid var(--line)}.ln svg{width:100%;height:100%;display:block;overflow:visible}.lv{position:absolute;right:0;font:600 11px system-ui,sans-serif}'
        '.lt{position:absolute;left:0;right:0;top:100%;height:18px}.lt span{position:absolute;transform:translateX(-50%);margin-top:4px;font:10.5px system-ui,sans-serif;color:var(--muted)}'
        '.cw{overflow-x:auto;padding:4px 0}.cw svg{display:block}.cw .cl{font:11px system-ui,sans-serif;fill:var(--muted)}.cw .cv{font:600 10.5px system-ui,sans-serif;fill:var(--ink)}.cw .gl{stroke:var(--line);stroke-width:1}'
        '.mk{display:inline-block;font:700 10px/16px system-ui,sans-serif;color:#fff;border-radius:999px;padding:0 6px;margin-right:6px}'
        '.rl{list-style:none;margin:0;padding:0;font-size:14px}.rl li{display:flex;flex-wrap:wrap;gap:2px 10px;padding:6px 0;border-bottom:1px solid var(--line)}'
        '.rk{display:inline-block;min-width:1.8em;margin-right:4px;font:700 12px system-ui,sans-serif;color:var(--muted);text-align:right}.rk.md{min-width:0;width:20px;height:20px;line-height:20px;border-radius:50%;text-align:center;color:#fff;margin-right:6px;margin-left:calc(1.8em - 20px);font-size:11px;box-shadow:inset 0 -2px 0 rgba(0,0,0,.18),0 1px 2px rgba(0,0,0,.15)}.rk.m1{background:linear-gradient(145deg,#f3d36b,#c79a1e)}.rk.m2{background:linear-gradient(145deg,#e3e5e8,#9a9ea6)}.rk.m3{background:linear-gradient(145deg,#e1a774,#a8642e)}.rl .d{font:12.5px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;color:var(--muted)}.rl .who{color:var(--muted);font-size:13px}.upd{margin-top:24px}'
        '.tp{min-height:calc(100vh - 110px)}.stabs{position:sticky;top:49px;z-index:5;background:var(--bg);display:flex;gap:0;margin:6px 0 14px;border-bottom:1px solid var(--line);overflow-x:auto;scrollbar-width:none}.stabs::-webkit-scrollbar{display:none}'
        '.stabs button{flex:none;font:inherit;font-size:14px;border:0;background:none;color:var(--muted);padding:10px 14px;cursor:pointer;border-bottom:3px solid transparent;margin-bottom:-1px;white-space:nowrap}'
        '.stabs button:hover{color:var(--ink)}.stabs button[aria-selected="true"]{color:var(--ink);font-weight:600}'
        '.stabs .sind{position:absolute;left:0;bottom:0;height:3px;width:0;border-radius:3px 3px 0 0;background:var(--accent);pointer-events:none}.stabs.anim .sind{transition:transform .32s cubic-bezier(.2,.8,.2,1),width .32s cubic-bezier(.2,.8,.2,1)}@media (prefers-reduced-motion:reduce){.stabs.anim .sind{transition:none}}'
        '.tp>section:first-child h2{border-top:0;margin-top:14px}')
    bar = sidemenu.cbar(BAR, T)
    page = (f'{head}{sidemenu.EARLY}{sidemenu.ICON}<title>未解読暗号の解読状況統計 — Cryptoole</title><meta name="author" content="satorunet">'
            f'<link rel="canonical" href="{sidemenu.SEARCH_URL}stats.html">\n<style>{css}</style></head><body><main class="st">\n{bar}\n{body}\n'
            f'<footer>satorunet · <a href="./">Cryptoole</a> · <a class="gh" href="https://github.com/satorunet/cryptoole">GitHub</a></footer>\n{sidemenu.drawer(T, menu_links)}\n</main>\n'
            f'<script>(function(){{{LANGJS}{sidemenu.JS}{TABJS}}})();</script></body></html>\n')
    page = page.replace('href="/crypt/', 'href="https://satoru.net/crypt/')
    (H / 'stats.html').write_text(page, encoding='utf-8')

def ranked(items):
    """[(name, n)] sorted by n -> [(rank, name, n)]; equal counts share a rank and the next count takes the next number (1, 2, 3, 4, 4, 4, 5 …)."""
    out = []
    for nm, v in items:
        out.append(((out[-1][0] if out[-1][2] == v else out[-1][0] + 1) if out else 1, nm, v))
    return out

def legend(T):
    return '<div class="lgd">' + ''.join(f'<span><i style="background:{TOPC[k]}"></i>{T(*TOPL[k])}</span>' for k in ('solved', 'open', 'na')) + '</div>'
