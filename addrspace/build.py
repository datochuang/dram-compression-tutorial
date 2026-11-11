"""Build the address-space view.

    python3 build.py OUT.html [--fragment]

Reads page.src.html, puts the example data from example_data.py in place of the
DATA marker and writes one self-contained page. --fragment leaves out the
document skeleton, which is the form the Artifact tool wants.
"""
import json
import sys
from pathlib import Path

from example_data import build

HERE = Path(__file__).resolve().parent


def render(fragment=False):
    src = (HERE / 'page.src.html').read_text(encoding='utf-8')
    marker = '/*DATA*/null'
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
    out.write_text(render('--fragment' in sys.argv), encoding='utf-8')
    print(f'[addrspace] wrote {out} ({out.stat().st_size} B)')
