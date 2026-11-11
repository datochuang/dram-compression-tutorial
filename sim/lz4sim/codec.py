"""LZ4 block codec and the stream checksum.

Compression uses the reference liblz4 through the lz4 package, raw block format
(no frame, no stored size). Real hardware produces different but equally valid
streams, so the oracle for COMPRESS is "decompresses to the page and fits the
limit", never byte equality with these streams.
"""
import zlib

import lz4.block


def compress(page):
    return lz4.block.compress(bytes(page), store_size=False)


def decompress(blob, size):
    try:
        out = lz4.block.decompress(bytes(blob), uncompressed_size=size)
    except lz4.block.LZ4BlockError:
        return None
    return out if len(out) == size else None


def checksum(data):
    return zlib.crc32(data) & 0xFFFFFFFF
