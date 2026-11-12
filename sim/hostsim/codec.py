"""LZ4 block compression for the host simulation, from tools already on this machine.

Three back ends give a raw LZ4 block (no frame, no stored size):

    lib   liblz4 through the Python `lz4` package, in process. The default.
    cli   the `lz4` command-line tool, one process per page (about 3 ms each).
          The tool speaks the LZ4 frame format, so the block is cut out of the
          frame after compression and wrapped in one before decompression.
    hw    the encoder and decoder the hardware is specified to have, hwref.lz4core.
          Slower, and its blocks are a little longer than liblz4's.

`lib` and `cli` give the same bytes. `cli` is for the build tool and for
cross-checking `lib`; a long run uses `lib`. `hw` gives other bytes for the same
page; every decoder opens the blocks of every encoder.
"""
import shutil
import subprocess
import zlib

PAGE = 4096


def crc32(data):
    return zlib.crc32(data) & 0xFFFFFFFF


class LibCodec:
    name = 'lib'

    def __init__(self):
        import lz4.block
        self._b = lz4.block

    def compress(self, page):
        """The block, or None when it would not be smaller than the page."""
        out = self._b.compress(bytes(page), store_size=False)
        return out if len(out) < len(page) else None

    def decompress(self, stream, size=PAGE):
        """The page, or None when the stream is not a valid block of that size."""
        try:
            out = self._b.decompress(bytes(stream), uncompressed_size=size)
        except self._b.LZ4BlockError:
            return None
        return out if len(out) == size else None


class CliCodec:
    name = 'cli'
    ARGS = ('-1', '-B4', '-BI', '--no-frame-crc', '-c')      # one independent block, no checksums

    def __init__(self, tool=None):
        self.tool = tool or shutil.which('lz4')
        if not self.tool:
            raise RuntimeError('the lz4 command-line tool is not installed')
        self.header = self._run(self.ARGS, b'')[:7]          # magic, FLG, BD, header checksum
        self.calls = 0

    def _run(self, args, data, check=True):
        r = subprocess.run([self.tool, *args], input=data, capture_output=True)
        if r.returncode and check:
            raise RuntimeError(r.stderr.decode(errors='replace'))
        return None if r.returncode else r.stdout

    def compress(self, page):
        self.calls += 1
        frame = self._run(self.ARGS, bytes(page))
        word = int.from_bytes(frame[7:11], 'little')         # block size; bit 31 set: stored uncompressed
        return None if word >> 31 else frame[11:11 + word]

    def decompress(self, stream, size=PAGE):
        self.calls += 1
        frame = self.header + len(stream).to_bytes(4, 'little') + bytes(stream) + bytes(4)
        out = self._run(('-d', '-c'), frame, check=False)
        return out if out is not None and len(out) == size else None


class HwCodec:
    name = 'hw'

    def __init__(self):
        from hwref import lz4core
        self._c = lz4core

    def compress(self, page):
        out = self._c.encode(page).stream
        return out if len(out) < len(page) else None

    def decompress(self, stream, size=PAGE):
        return self._c.decode(stream, size).page


def make(name='lib'):
    return {'lib': LibCodec, 'cli': CliCodec, 'hw': HwCodec}[name]()
