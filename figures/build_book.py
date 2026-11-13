#!/usr/bin/env python3
"""Build kernel-sw-figures.html from README.md in this folder.

The HTML is one self-contained file: the figures are embedded as JPEG
data URIs so it can be read on a device that has no access to this folder.

    python3 figures/build_book.py
    python3 figures/build_book.py SOURCE.md OUT.html

With two arguments it builds another document the same way. Image paths are
read relative to the source file.

Only the Markdown subset used by the source is handled: #/##/### headings,
paragraphs, "- " lists, pipe tables, one image per line, **bold**, `code`.
A [text](target) link is written as its text only: relative targets do not
resolve from a file that travels alone.
"""
import base64
import html
import io
import re
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
SRC = HERE / 'README.md'
OUT = HERE / 'kernel-sw-figures.html'
JPEG_QUALITY = 90
BASE = HERE                     # folder that image paths are relative to

CSS = """
:root{--bg:#fbfaf7;--fg:#1f2328;--muted:#5c6570;--line:#d9d6cf;--card:#ffffff;
--code:#efece5;--accent:#b4541a;--th:#f1eee7}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#16181b;
--fg:#e6e3dc;--muted:#9aa3ad;--line:#33373d;--card:#1e2125;--code:#2a2e33;
--accent:#f0a36b;--th:#24282d}}
:root[data-theme="dark"]{--bg:#16181b;--fg:#e6e3dc;--muted:#9aa3ad;--line:#33373d;
--card:#1e2125;--code:#2a2e33;--accent:#f0a36b;--th:#24282d}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);line-height:1.7;
font:16px/1.7 -apple-system,"PingFang TC","Noto Sans TC","Microsoft JhengHei",sans-serif}
main{max-width:1080px;margin:0 auto;padding:24px 16px 80px}
h1{font-size:1.7rem;line-height:1.3;margin:.2em 0 .8em}
h2{font-size:1.3rem;margin:2.4em 0 .6em;padding-top:.6em;border-top:2px solid var(--line)}
h3{font-size:1.15rem;margin:2.6em 0 .5em;color:var(--accent)}
p{margin:.6em 0}
ul{margin:.5em 0;padding-left:1.3em}
li{margin:.3em 0}
code{background:var(--code);padding:.08em .35em;border-radius:4px;
font:0.9em ui-monospace,SFMono-Regular,Menlo,monospace;word-break:break-word}
.tbl{overflow-x:auto;margin:.8em 0}
table{border-collapse:collapse;width:100%;font-size:.93rem}
th,td{border:1px solid var(--line);padding:.4em .6em;text-align:left;vertical-align:top}
th{background:var(--th);white-space:nowrap}
figure{margin:1em 0}
figure img{display:block;width:100%;height:auto;border:1px solid var(--line);
border-radius:6px;background:#fff}
figcaption{font-size:.85rem;color:var(--muted);margin-top:.35em}
nav{background:var(--card);border:1px solid var(--line);border-radius:8px;
padding:.6em 1em;margin:1.2em 0}
nav ol,nav ul{margin:.3em 0 .8em;padding-left:1.4em;columns:2;column-gap:2em}
nav ul{list-style:none;padding-left:.2em}
nav a{color:var(--fg);text-decoration:none;border-bottom:1px solid var(--line)}
@media (max-width:640px){nav ol,nav ul{columns:1}}
@media print{body{background:#fff}h3{break-before:page}nav{display:none}
main{max-width:none;padding:0}}
"""


def inline(text):
    out = html.escape(text, quote=False)
    out = re.sub(r'(?<!!)\[([^\]]+)\]\((https?://[^)]+)\)', r'<a href="\2">\1</a>', out)
    out = re.sub(r'(?<!!)\[([^\]]+)\]\([^)]+\)', r'`\1`', out)
    out = re.sub(r'`([^`]+)`', r'<code>\1</code>', out)
    out = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', out)
    return out


def image_tag(alt, name):
    im = Image.open(BASE / name).convert('RGB')
    buf = io.BytesIO()
    im.save(buf, 'JPEG', quality=JPEG_QUALITY, optimize=True)
    data = base64.b64encode(buf.getvalue()).decode('ascii')
    return (f'<figure><img alt="{html.escape(alt)}" width="{im.width}" '
            f'height="{im.height}" src="data:image/jpeg;base64,{data}">'
            f'<figcaption>{inline(alt)}　<code>{html.escape(re.sub(r'^([.][.]/)+', '', name))}</code>'
            f'</figcaption></figure>')


def cells(line):
    return [c.strip() for c in line.strip().strip('|').split('|')]


def convert(lines):
    body, toc, i, n = [], [], 0, 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
        elif m := re.match(r'(#{1,3}) (.+)', line):
            level, text = len(m.group(1)), m.group(2)
            n += 1
            if level > 1:
                toc.append((level, n, text))
            body.append(f'<h{level} id="s{n}">{inline(text)}</h{level}>')
            if level == 1:
                body.append('<!--toc-->')
            i += 1
        elif m := re.match(r'!\[(.*)\]\((.+)\)$', line):
            body.append(image_tag(m.group(1), m.group(2)))
            i += 1
        elif line.startswith('|'):
            head = cells(line)
            i += 2
            rows = []
            while i < len(lines) and lines[i].startswith('|'):
                rows.append(cells(lines[i]))
                i += 1
            t = ['<div class="tbl"><table><thead><tr>']
            t += [f'<th>{inline(c)}</th>' for c in head]
            t.append('</tr></thead><tbody>')
            for r in rows:
                t.append('<tr>' + ''.join(f'<td>{inline(c)}</td>' for c in r) + '</tr>')
            t.append('</tbody></table></div>')
            body.append(''.join(t))
        elif line.startswith('- '):
            items = []
            while i < len(lines) and lines[i].startswith('- '):
                items.append(f'<li>{inline(lines[i][2:])}</li>')
                i += 1
            body.append('<ul>' + ''.join(items) + '</ul>')
        else:
            body.append(f'<p>{inline(line)}</p>')
            i += 1
    figs = [(k, t) for lv, k, t in toc if lv == 3]
    secs = [(k, t) for lv, k, t in toc if lv == 2]
    nav = ['<nav><strong>章節</strong><ol>']
    nav += [f'<li><a href="#s{k}">{inline(re.sub(r"^[0-9]+[.] ", "", t))}</a></li>' for k, t in secs]
    nav.append('</ol><strong>圖</strong><ul>')
    nav += [f'<li><a href="#s{k}">{inline(t)}</a></li>' for k, t in figs]
    nav.append('</ul></nav>')
    return '\n'.join(body).replace('<!--toc-->', ''.join(nav))


def main(argv):
    global BASE
    if len(argv) not in (0, 2):
        print('usage: build_book.py [SOURCE.md OUT.html]', file=sys.stderr)
        return 2
    src, out = (Path(argv[0]).resolve(), Path(argv[1]).resolve()) if argv else (SRC, OUT)
    BASE = src.parent
    lines = src.read_text(encoding='utf-8').splitlines()
    title = lines[0].lstrip('# ').strip()
    page = (f'<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{html.escape(title)}</title><style>{CSS}</style></head>'
            f'<body><main>{convert(lines)}</main></body></html>')
    out.write_text(page, encoding='utf-8')
    print(f'{out.name}: {out.stat().st_size // 1024} KB')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
