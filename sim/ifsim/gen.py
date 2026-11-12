"""Generate the documents that must never drift from interface.json: the interface spec and the C header.

A template is Markdown with {{name}} placeholders. Each placeholder is filled
by a function here; everything else in the template is hand-written prose.
"""
import os
import re

from .params import Budgets, Params, PARAM_DOC
from .report import md_budget_defs, md_params, table
from .spec import SPEC

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.join(HERE, 'templates')

# The running example: one DECOMPRESS and one COMPRESS on the full-size address map.
EX = {
    'decompress_desc': ('job_desc', dict(opcode=2, count=5, limit=4096, frame_pa=0x9863_4000, comp_len=2296, flags=0,
                                         checksum=0xDEADBEEF, tag=0x2A7, chunk=(0x51A2F, 0x80013, 0x5F002, 0x6B410, 0x6B411))),
    'decompress_cpl': ('completion', dict(status=0, flags=0, length=4096, checksum=0xDEADBEEF, tag=0x2A7, aux=0)),
    'compress_desc': ('job_desc', dict(opcode=1, count=7, limit=3584, frame_pa=0x97A1_C000, comp_len=0, flags=0, checksum=0,
                                       tag=0x2A8, chunk=(0x1C044, 0x1C045, 0x30A71, 0x30A75, 0x412E0, 0x412E1, 0x66B3F))),
    'compress_cpl': ('completion', dict(status=0, flags=0, length=1837, checksum=0xF7AD14BD, tag=0x2A8, aux=0)),
    'cot_after_compress': ('cot_entry', dict(flags=1, count=4, comp_len=1837, checksum=0xF7AD14BD,
                                             chunk=(0x1C044, 0x1C045, 0x30A71, 0x30A75))),
}
HEX_FIELDS = {'frame_pa', 'checksum', 'tag', 'chunk', 'flags'}
ENUM_OF = {('job_desc', 'opcode'): 'opcode', ('completion', 'status'): 'status'}


def _hex(b):
    return ' '.join(f'{x:02X}' for x in b)


def example(key, spec=SPEC):
    """The example as it lies in memory: one row per field, real bytes first."""
    return fields(*EX[key], spec=spec)


def fields(struct, vals, spec=SPEC):
    """Any value of a structure as it lies in memory."""
    raw = spec.pack(struct, vals)
    rows = []
    for f in spec.structs[struct]['fields']:
        n = f['size'] * f.get('count', 1)
        v = vals.get(f['name'], 0)
        if (struct, f['name']) in ENUM_OF:
            shown = f"{spec.enum_name[ENUM_OF[struct, f['name']]][v]}（{v}）"
        elif 'count' in f:
            shown = '、'.join(f'0x{x:05X}' for x in v) + ('，其餘填 0' if len(v) < f['count'] else '')
        elif f['name'] in HEX_FIELDS:
            shown = f'0x{v:0{f["size"] * 2}X}'
        else:
            shown = str(v)
        rows.append((f'0x{f["offset"]:02X}', f'`{_hex(raw[f["offset"]:f["offset"] + n])}`', f'`{f["name"]}`', shown))
    return table(('Offset', '記憶體裡的 byte，由低位址到高位址', '欄位', '值'), rows)


def registers(spec=SPEC):
    rows = [(f'0x{r["offset"]:02X}', f'`{r["name"]}`', r['access'], f'0x{r["reset"]:08X}',
             '是' if r.get('config') else '', r['desc']) for r in spec.registers]
    return table(('Offset', 'Register', '存取', 'Reset 值', 'config', '說明'), rows)


def register_fields(spec=SPEC):
    out = []
    for r in spec.registers:
        if not r.get('fields'):
            continue
        rows = []
        for f in r['fields']:
            hi = f['lsb'] + f['width'] - 1
            bits = f'{hi}:{f["lsb"]}' if f['width'] > 1 else str(f['lsb'])
            rows.append((bits, f'`{f["name"]}`', f.get('access', r['access']), f['desc']))
        out.append(f'**`{r["name"]}`，offset 0x{r["offset"]:02X}**\n\n' + table(('Bit', '欄位', '存取', '說明'), rows))
    return '\n\n'.join(out)


def struct(name, spec=SPEC):
    st = spec.structs[name]
    rows = []
    for f in st['fields']:
        size = f'{f["count"]} × {f["size"]}' if 'count' in f else str(f['size'])
        rows.append((f'0x{f["offset"]:02X}', size, f'`{f["name"]}`', f['desc']))
    return table(('Offset', '大小 B', '欄位', '說明'), rows)


def enum(name, spec=SPEC):
    with open(os.path.join(HERE, 'interface.json'), encoding='utf-8') as f:
        import json
        vals = json.load(f)['enums'][name]['values']
    return table(('值', '名稱', '說明'), [(v['value'], f'`{k}`', v['desc']) for k, v in vals.items()])


def constants(spec=SPEC):
    import json
    with open(os.path.join(HERE, 'interface.json'), encoding='utf-8') as f:
        c = json.load(f)['constants']
    rows = [(f'`{k}`', f'0x{v["value"]:08X}' if k == 'ID_VALUE' else v['value'], v['desc']) for k, v in c.items()]
    return table(('常數', '值', '說明'), rows)


def rules(prefix, spec=SPEC):
    how = {'checker': '模擬器執行中檢查', 'audit': '模擬結束時 audit', 'test': '注入測試', 'review': '人工 review'}
    rows = [(f'`{rid}`', r['text'], how[r['check']]) for rid, r in spec.rules.items() if rid.startswith(prefix)]
    return table(('編號', '規則', '怎麼驗'), rows)


def version(spec=SPEC):
    import json
    with open(os.path.join(HERE, 'interface.json'), encoding='utf-8') as f:
        return json.load(f)['version']


def fill(text, extra=None):
    """Replace every {{name}} or {{name:arg}} in text."""
    funcs = {'registers': registers, 'register_fields': register_fields, 'constants': constants, 'version': version,
             'params': lambda: md_params(Params()), 'budgets': lambda: md_budget_defs(Budgets())}
    with_arg = {'struct': struct, 'enum': enum, 'rules': rules, 'example': example}
    extra = extra or {}

    def sub(m):
        name, _, arg = m.group(1).partition(':')
        if m.group(1) in extra:
            v = extra[m.group(1)]
            return v() if callable(v) else str(v)
        if arg:
            return with_arg[name](arg)
        return funcs[name]()

    out = re.sub(r'\{\{([A-Za-z0-9_:.\-]+)\}\}', sub, text)
    return out


def render(template, extra=None):
    with open(os.path.join(TEMPLATES, template), encoding='utf-8') as f:
        return fill(f.read(), extra)


# ---- C header
def c_header(spec=SPEC):
    import json
    with open(os.path.join(HERE, 'interface.json'), encoding='utf-8') as f:
        j = json.load(f)
    L = ['/* LZ4 accelerator HW/FW interface, version ' + j['version'] + '.',
         ' * Generated from sim/ifsim/interface.json by `python3 sim/run_if.py gen-spec`. Do not edit by hand.',
         ' * All multi-byte fields are little-endian. */',
         '#ifndef LZ4_HWIF_H', '#define LZ4_HWIF_H', '', '#include <stdint.h>', '', '/* Constants */']
    for k, v in j['constants'].items():
        val = f'0x{v["value"]:08X}u' if k == 'ID_VALUE' else f'{v["value"]}u'
        L.append(f'#define LZ4_{k:<22} {val}')
    L += ['', '/* Register offsets */']
    for r in j['registers']:
        L.append(f'#define LZ4_REG_{r["name"]:<18} 0x{r["offset"]:02X}u   /* {r["access"]} */')
    L += ['', '/* Register fields */']
    for r in j['registers']:
        for f in r.get('fields', ()):
            base = f'LZ4_{r["name"]}_{f["name"]}'
            mask = ((1 << f['width']) - 1) << f['lsb']
            L.append(f'#define {base + "_SHIFT":<34} {f["lsb"]}u')
            L.append(f'#define {base + "_MASK":<34} 0x{mask:08X}u')
    for name, e in j['enums'].items():
        L += ['', f'/* {name} */']
        if name == 'flag':
            for k, v in e['values'].items():
                L.append(f'#define LZ4_FLAG_{k:<17} 0x{v["value"]:02X}u')
            continue
        L.append(f'enum lz4_{name} {{')
        for k, v in e['values'].items():
            L.append(f'    LZ4_{name.upper()}_{k} = {v["value"]},')
        L.append('};')
    ctype = {1: 'uint8_t', 2: 'uint16_t', 4: 'uint32_t'}
    for name, st in j['structs'].items():
        L += ['', f'struct lz4_{name} {{']
        for f in st['fields']:
            if 'count' in f:
                L.append(f'    uint8_t  {f["name"]}[{f["count"]}][{f["size"]}];   /* 0x{f["offset"]:02X}: {f["count"]} numbers of {f["size"] * 8} bits */')
            else:
                L.append(f'    {ctype[f["size"]]:<8} {f["name"]};   /* 0x{f["offset"]:02X} */')
        end = max(f['offset'] + f['size'] * f.get('count', 1) for f in st['fields'])
        if end < st['size']:
            L.append(f'    uint8_t  pad[{st["size"] - end}];   /* 0x{end:02X} */')
        L.append('};')
        L.append(f'_Static_assert(sizeof(struct lz4_{name}) == {st["size"]}, "lz4_{name} size");')
    L += ['', '/* A chunk number is 24 bits, stored low byte first. */',
          'static inline uint32_t lz4_chunk_get(const uint8_t c[3])',
          '{', '    return (uint32_t)c[0] | ((uint32_t)c[1] << 8) | ((uint32_t)c[2] << 16);', '}',
          'static inline void lz4_chunk_set(uint8_t c[3], uint32_t n)',
          '{', '    c[0] = (uint8_t)n; c[1] = (uint8_t)(n >> 8); c[2] = (uint8_t)(n >> 16);', '}',
          '', '/* Rule ids of the interface spec, for assertions and log messages. */']
    for rid in spec.rules:
        L.append(f'#define LZ4_RULE_{rid.replace("-", "_"):<14} "{rid}"')
    L += ['', '#endif /* LZ4_HWIF_H */', '']
    return '\n'.join(L)


def write_spec(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    files = {'hw-fw-interface.md': render('hw_fw_interface.tmpl.md'), 'lz4_hwif.h': c_header()}
    for name, text in files.items():
        with open(os.path.join(out_dir, name), 'w', encoding='utf-8') as f:
            f.write(text)
    return [os.path.join(out_dir, n) for n in files]
