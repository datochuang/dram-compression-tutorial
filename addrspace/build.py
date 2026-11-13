"""Build the address-space view.

    python3 build.py OUT.html [--fragment] [--3d | --mmu | --rhythm]

Reads page.src.html (or page3d.src.html with --3d, or mmu3d.src.html with --mmu,
the CPU-MMU view, which has its own small model in mmu_sim.js and takes no example
data; or rhythm3d.src.html with --rhythm, the two-rhythms view with its model in rhythm_sim.js), puts the example data from example_data.py in place of the DATA marker, pastes every /*INCLUDE name.js*/
file in place and writes one self-contained page. sim.js is the part both pages
share. --fragment leaves out the document skeleton, which is the form the
Artifact tool wants.
"""
import json
import re
import sys
from pathlib import Path

from example_data import build

HERE = Path(__file__).resolve().parent


def render(fragment=False, name='page.src.html'):
    src = (HERE / name).read_text(encoding='utf-8')
    src = re.sub(r'/\*INCLUDE ([\w.]+)\*/', lambda m: (HERE / m.group(1)).read_text(encoding='utf-8'), src)
    marker = '/*DATA*/null'
    if name in ('mmu3d.src.html', 'rhythm3d.src.html'):
        assert marker not in src
    else:
        assert src.count(marker) == 1
        src = src.replace(marker, json.dumps(build(), separators=(',', ':')))
    head, body = src.split('<!--BODY-->')
    if fragment:
        return head + body
    return ('<!doctype html>\n<html lang="zh-Hant">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            + head + '</head>\n<body>' + body + '</body>\n</html>\n')


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    out = Path(args[0])
    name = 'rhythm3d.src.html' if '--rhythm' in sys.argv else 'mmu3d.src.html' if '--mmu' in sys.argv else 'page3d.src.html' if '--3d' in sys.argv else 'page.src.html'
    out.write_text(render('--fragment' in sys.argv, name), encoding='utf-8')
    print(f'[addrspace] wrote {out} ({out.stat().st_size} B)')
