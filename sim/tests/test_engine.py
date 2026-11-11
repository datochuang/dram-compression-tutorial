"""The LZ4 engine is one module that both accelerator designs share."""
import inspect
import os

from lz4sim import accel
from lz4sim.config import SMALL
from lz4sim.dram import DRAM
from lz4sim.engine import Lz4Engine
from lz4sim.formats import ST_INCOMPRESSIBLE
from lz4sim.sim import Simulation, VARIANTS


def test_both_designs_use_the_same_engine():
    engines = [type(Simulation(v, SMALL).accel.eng) for v in VARIANTS]
    assert engines == [Lz4Engine] * len(VARIANTS)
    # neither wrapper carries a private copy of the datapath
    src = inspect.getsource(accel)
    assert 'codec' not in src and 'lz4.block' not in src
    for cls in (accel.BaselineAccel, accel.SoftwareAccel):
        assert not {'_encode', '_decode', '_scatter', '_gather'} & set(vars(cls))


def _engine():
    dram = DRAM(SMALL)
    return Lz4Engine(SMALL, dram), dram


def test_round_trip_through_scattered_chunks():
    eng, dram = _engine()
    src, dst = SMALL.fc_base, SMALL.fc_base + SMALL.page
    page = (b'LZ4 engine shared by both designs. ' * 80 + os.urandom(1500))[:SMALL.page]
    dram.write(src, page)
    blob, raw, status = eng.compress_frame(src, 3584)
    assert status is None and not raw and len(blob) < 3584
    n = eng.chunks_for(blob)
    chunks = [907, 12, 4410, 3, 77, 2048, 5][:n]          # not contiguous, not ordered
    assert len(chunks) == n
    eng.scatter(blob, chunks)
    assert eng.gather(chunks, len(blob)) == blob
    assert eng.decompress_to_frame(chunks, len(blob), False, eng.checksum(blob), dst)
    assert dram.read(dst, SMALL.page) == page


def test_bad_stream_leaves_the_frame_alone():
    eng, dram = _engine()
    src, dst = SMALL.fc_base, SMALL.fc_base + SMALL.page
    dram.write(src, bytes(range(256)) * 4 + bytes(SMALL.page - 1024))
    blob, raw, status = eng.compress_frame(src, 3584)
    chunks = list(range(40, 40 + eng.chunks_for(blob)))
    eng.scatter(blob, chunks)
    pa = SMALL.chunk_pa(chunks[0]) + 9
    dram.write(pa, bytes([dram.read(pa, 1)[0] ^ 0x40]))
    before = dram.read(dst, SMALL.page)
    assert not eng.decompress_to_frame(chunks, len(blob), False, eng.checksum(blob), dst)
    assert dram.read(dst, SMALL.page) == before


def test_incompressible_and_raw():
    eng, dram = _engine()
    src, dst = SMALL.fc_base, SMALL.fc_base + SMALL.page
    page = os.urandom(SMALL.page)
    dram.write(src, page)
    assert eng.compress_frame(src, 3584) == (None, False, ST_INCOMPRESSIBLE)
    blob, raw, status = eng.compress_frame(src, SMALL.page)
    assert status is None and raw and blob == page
    chunks = list(range(100, 108))
    eng.scatter(blob, chunks)
    assert eng.decompress_to_frame(chunks, SMALL.page, True, eng.checksum(blob), dst)
    assert dram.read(dst, SMALL.page) == page
