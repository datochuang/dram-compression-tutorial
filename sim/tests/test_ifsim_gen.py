"""The documents in spec/ are generated. These tests fail when one of them is stale or was edited by hand."""
import json
import os

import pytest

from ifsim import gen
from ifsim import report as R
from ifsim.__main__ import SPEC_DIR, main
from ifsim.spec import SPEC


def read(name):
    with open(os.path.join(SPEC_DIR, name), encoding='utf-8') as f:
        return f.read()


def test_interface_spec_is_up_to_date():
    text = gen.render('hw_fw_interface.tmpl.md')
    assert '{{' not in text
    assert text == read('hw-fw-interface.md'), 'run: python3 sim/run_if.py gen-spec'


def test_c_header_is_up_to_date():
    assert gen.c_header() == read('lz4_hwif.h'), 'run: python3 sim/run_if.py gen-spec'


def test_every_rule_is_in_the_spec_and_the_header():
    spec, header = read('hw-fw-interface.md'), read('lz4_hwif.h')
    for rid in SPEC.rules:
        assert f'`{rid}`' in spec
        assert f'"{rid}"' in header


def test_examples_in_the_spec_are_the_packed_bytes():
    """The bytes shown in section 2 unpack to the values shown beside them."""
    for key, (struct, vals) in gen.EX.items():
        back = SPEC.unpack(struct, SPEC.pack(struct, vals))
        for name, v in vals.items():
            got = back[name]
            if isinstance(v, tuple):
                got = tuple(got)[:len(v)]
            assert got == v, (key, name)


def test_results_document_matches_its_data():
    data = json.loads(read('sim-results-v0.json'))
    text = gen.render('sim_results.tmpl.md', R.results_extra(data, SPEC))
    assert '{{' not in text
    assert text == read('sim-results-v0.md'), 'run: python3 sim/run_if.py results --reuse'


def test_stored_results_have_no_violation():
    data = json.loads(read('sim-results-v0.json'))
    assert data['base_irq']['violations'] == 0 and data['base_poll']['violations'] == 0
    for s in data['sweeps'].values():
        for _, row in s['rows']:
            assert row.get('violations') == 0
    for f in data['faults'].values():
        assert f['violations'] == 0


def test_command_line_run(capsys):
    main(['run', '--cfg', 'small', '--n', '3000', '--set', 'wait_mode=poll', '--rules'])
    out = capsys.readouterr().out
    assert 'PASS' in out and '`HW-IRQ-1`' in out


def test_command_line_sweep(capsys):
    main(['sweep', '--n', '2000', '--axis', 'wait_mode=irq,poll'])
    out = capsys.readouterr().out
    assert out.count('\n') == 4


def test_command_line_rejects_an_unknown_parameter():
    with pytest.raises(SystemExit):
        main(['run', '--set', 'no_such=1'])
