"""Loader for interface.json: register offsets, bit fields, struct pack/unpack, enums, rules."""
import json
import os
from types import SimpleNamespace

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'interface.json')


class Spec:
    def __init__(self, path=PATH):
        with open(path, encoding='utf-8') as f:
            self.raw = raw = json.load(f)
        self.version = raw['version']
        self.const = SimpleNamespace(**{k: v['value'] for k, v in raw['constants'].items()})
        self.registers = raw['registers']
        self.off = {r['name']: r['offset'] for r in self.registers}       # name -> offset
        self.reg_at = {r['offset']: r for r in self.registers}            # offset -> register
        self.config_regs = {r['name'] for r in self.registers if r.get('config')}
        self.mask = {}                                                    # (reg, field) -> (lsb, mask)
        for r in self.registers:
            for fl in r.get('fields', ()):
                self.mask[r['name'], fl['name']] = (fl['lsb'], ((1 << fl['width']) - 1) << fl['lsb'])
        self.structs = raw['structs']
        self.enum = {}
        self.enum_name = {}
        for name, e in raw['enums'].items():
            vals = {k: v['value'] for k, v in e['values'].items()}
            self.enum[name] = SimpleNamespace(**vals)
            self.enum_name[name] = {v: k for k, v in vals.items()}
        self.rules = {r['id']: r for r in raw['rules']}

    # ---- bit fields
    def bit(self, reg, field):
        return self.mask[reg, field][1]

    def get(self, reg, field, value):
        lsb, m = self.mask[reg, field]
        return (value & m) >> lsb

    # ---- structures
    def size(self, struct):
        return self.structs[struct]['size']

    def pack(self, struct, values):
        st = self.structs[struct]
        b = bytearray(st['size'])
        for fl in st['fields']:
            v = values.get(fl['name'], 0)
            n, off = fl['size'], fl['offset']
            if 'count' in fl:
                for i, x in enumerate(v or ()):
                    if i >= fl['count']:
                        raise ValueError(f"{struct}.{fl['name']}: more than {fl['count']} items")
                    b[off + i * n:off + (i + 1) * n] = int(x).to_bytes(n, 'little')
            else:
                b[off:off + n] = int(v).to_bytes(n, 'little')
        return bytes(b)

    def unpack(self, struct, data):
        st = self.structs[struct]
        out = {}
        for fl in st['fields']:
            n, off = fl['size'], fl['offset']
            if 'count' in fl:
                out[fl['name']] = [int.from_bytes(data[off + i * n:off + (i + 1) * n], 'little')
                                   for i in range(fl['count'])]
            else:
                out[fl['name']] = int.from_bytes(data[off:off + n], 'little')
        return out


SPEC = Spec()
