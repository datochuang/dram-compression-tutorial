"""interface.json is the single source: its layouts must agree with the formats lz4sim already uses."""
import os
import re

from lz4sim.formats import COTEntry, VariantDesc, Completion, F_VALID, F_RAW, OP_COMPRESS, OP_DECOMPRESS, ST_OK
from ifsim.spec import SPEC

CHUNKS = (0x51A2F, 0x80013, 0x5F002, 0x6B410, 0x6B411)


def test_job_desc_layout_matches_lz4sim():
    d = dict(opcode=SPEC.enum['opcode'].DECOMPRESS, count=5, limit=3072, frame_pa=0x8123_4000, comp_len=2296,
             flags=SPEC.enum['flag'].RAW, checksum=0xDEADBEEF, tag=0x1234_5678, chunk=CHUNKS)
    b = SPEC.pack('job_desc', d)
    assert len(b) == 48 == VariantDesc.SIZE
    assert b == VariantDesc(OP_DECOMPRESS, 0x8123_4000, CHUNKS, 3072, 2296, F_RAW, 0xDEADBEEF, 0x1234_5678).pack()
    u = SPEC.unpack('job_desc', b)
    assert u['tag'] == 0x1234_5678 and tuple(u['chunk'][:5]) == CHUNKS


def test_completion_layout_matches_lz4sim():
    c = dict(status=SPEC.enum['status'].OK, flags=SPEC.enum['flag'].RAW, length=2296, checksum=0xCAFEF00D, tag=77, aux=3)
    b = SPEC.pack('completion', c)
    assert len(b) == 16 == Completion.SIZE
    assert b == Completion(ST_OK, 2296, 0xCAFEF00D, 77, F_RAW, 3).pack()
    assert SPEC.unpack('completion', b) == c


def test_cot_entry_layout_matches_lz4sim():
    e = dict(flags=SPEC.enum['flag'].VALID, count=5, comp_len=2296, checksum=0xDEADBEEF, chunk=CHUNKS)
    b = SPEC.pack('cot_entry', e)
    assert len(b) == 32
    assert b == COTEntry(F_VALID, 5, 2296, 0xDEADBEEF, CHUNKS).pack()


def test_enums_match_lz4sim():
    assert SPEC.enum['opcode'].COMPRESS == OP_COMPRESS and SPEC.enum['opcode'].DECOMPRESS == OP_DECOMPRESS
    assert SPEC.enum['status'].OK == ST_OK


def test_registers_do_not_overlap():
    offs = [r['offset'] for r in SPEC.registers]
    assert len(set(offs)) == len(offs) and all(o % 4 == 0 for o in offs)
    for r in SPEC.registers:
        bits = 0
        for f in r.get('fields', ()):
            m = ((1 << f['width']) - 1) << f['lsb']
            assert not bits & m, f"{r['name']}.{f['name']} overlaps another field"
            bits |= m
        assert bits < 1 << 32


def test_struct_fields_do_not_overlap():
    for name, st in SPEC.structs.items():
        used = bytearray(st['size'])
        for f in st['fields']:
            n = f['size'] * f.get('count', 1)
            assert f['offset'] + n <= st['size'], f'{name}.{f["name"]} runs past the end'
            assert not any(used[f['offset']:f['offset'] + n]), f'{name}.{f["name"]} overlaps'
            used[f['offset']:f['offset'] + n] = b'\x01' * n


def test_every_checker_rule_is_implemented():
    """A rule marked checker or audit must be evaluated somewhere in checkers.py."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(here, 'ifsim', 'checkers.py')).read()
    used = set(re.findall(r"'((?:FW|HW|AUDIT)-[A-Z0-9-]+)'", src))
    for rid, r in SPEC.rules.items():
        assert r['check'] in ('checker', 'audit', 'test', 'review')
        if r['check'] in ('checker', 'audit'):
            assert rid in used, f'{rid} has no checker'
    assert used <= set(SPEC.rules), f'checkers.py names unknown rules: {used - set(SPEC.rules)}'
