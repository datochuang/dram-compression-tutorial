from lz4sim.formats import (COTEntry, BaselineDesc, VariantDesc, Completion, F_VALID, F_RAW,
                            OP_COMPRESS, OP_DECOMPRESS, ST_OK, pack_list_chunk, unpack_list_chunk)


def test_entry_running_example():
    e = COTEntry(F_VALID, 5, 2296, 0xDEADBEEF, (0x51A2F, 0x80013, 0x5F002, 0x6B410, 0x6B411))
    b = e.pack()
    assert len(b) == 32
    assert b[0] == 1 and b[1] == 5
    assert b[2:4] == (2296).to_bytes(2, 'little')
    assert b[4:8] == (0xDEADBEEF).to_bytes(4, 'little')
    assert b[8:11] == bytes([0x2F, 0x1A, 0x05])
    assert b[23:32] == bytes(9)
    assert COTEntry.unpack(b) == e
    assert COTEntry.unpack(memoryview(b)).chunks == e.chunks


def test_list_chunk():
    nums = list(range(0x5D0A5, 0x5D0A5 + 169))
    b = pack_list_chunk(0x7388B, nums)
    assert len(b) == 512
    nxt, got = unpack_list_chunk(b)
    assert nxt == 0x7388B and got == nums


def test_descriptors_and_completion():
    d = BaselineDesc(OP_COMPRESS, handle=0x14567, frame_pa=0x9A2B4000, limit=3584, tag=7)
    b = d.pack()
    assert len(b) == BaselineDesc.SIZE == 16
    assert BaselineDesc.unpack(b) == d

    v = VariantDesc(OP_DECOMPRESS, frame_pa=0x9A2B4000, chunks=(0x51A2F, 0x80013, 0x5F002, 0x6B410, 0x6B411),
                    limit=4096, comp_len=2296, flags=F_RAW, checksum=0x12345678, tag=0x14567)
    b = v.pack()
    assert len(b) == VariantDesc.SIZE == 48
    assert b[1] == 5
    assert b[20:23] == bytes([0x2F, 0x1A, 0x05])
    assert VariantDesc.unpack(b) == v

    c = Completion(ST_OK, 2296, 0x12345678, 0x14567, 0, 283853)
    b = c.pack()
    assert len(b) == Completion.SIZE == 16
    assert Completion.unpack(b) == c
