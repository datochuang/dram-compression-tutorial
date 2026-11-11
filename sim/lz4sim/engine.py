"""The LZ4 engine: the datapath that both accelerator designs instantiate unchanged.

This is the part of the LZ4 HW that does not depend on who owns the metadata:

  compress    read one 4096 B frame, run LZ4, decide stored-raw or incompressible
  scatter     write the stream into the given 512 B chunks, in order
  gather      read the given chunks back and cut the stream to its length
  decompress  check the CRC of the stream, run LZ4 (or copy a raw page), write the frame
  timing      streaming time of one page at the engine rate

The engine is stateless between jobs and never looks at a descriptor, the COT,
the free-chunk stack or the bitmap. Where the chunk numbers, the stream length
and the checksum come from is the business of the wrapper around it:

  BaselineAccel (hardware-leaning)   pops chunk numbers from its own stack and reads
                                     or writes the COT entry itself
  SoftwareAccel (software-leaning)   takes all of them from the descriptor the kernel
                                     filled in

Both wrappers are in accel.py and hold exactly one Lz4Engine. A change to the
datapath made here applies to both designs.
"""
from math import ceil

from .codec import compress, decompress, checksum
from .formats import ST_INCOMPRESSIBLE


class Lz4Engine:
    def __init__(self, cfg, dram):
        self.cfg = cfg
        self.dram = dram

    # ---- timing
    def _stream_ns(self, nbytes, bytes_per_cycle):
        return nbytes / bytes_per_cycle / self.cfg.clock_hz * 1e9

    def comp_ns(self):
        """Streaming time of one page through the compressor."""
        return self._stream_ns(self.cfg.page, self.cfg.comp_bytes_per_cycle)

    def decomp_ns(self):
        """Streaming time of one page through the decompressor."""
        return self._stream_ns(self.cfg.page, self.cfg.decomp_bytes_per_cycle)

    # ---- compress side
    def compress_frame(self, frame_pa, limit):
        """Read the frame and encode it.

        Returns (blob, raw, status). status None means the page can be stored in
        ceil(len(blob) / chunk) chunks; raw says the blob is the page itself.
        """
        page = self.dram.read(frame_pa, self.cfg.page)
        blob = compress(page)
        if len(blob) >= self.cfg.page:
            if limit >= self.cfg.page:
                return bytes(page), True, None
            return None, False, ST_INCOMPRESSIBLE
        if len(blob) > limit:
            return None, False, ST_INCOMPRESSIBLE
        return blob, False, None

    def chunks_for(self, blob):
        return ceil(len(blob) / self.cfg.chunk)

    def scatter(self, blob, chunks):
        cs = self.cfg.chunk
        for i, c in enumerate(chunks):
            self.dram.write(self.cfg.chunk_pa(c), blob[i * cs:(i + 1) * cs])

    checksum = staticmethod(checksum)

    # ---- decompress side
    def gather(self, chunks, n):
        cs = self.cfg.chunk
        return b''.join(self.dram.read(self.cfg.chunk_pa(c), cs) for c in chunks)[:n]

    def decompress_to_frame(self, chunks, comp_len, raw, csum, frame_pa):
        """Gather, check, decode and write the frame. False means a bad stream; the frame is untouched."""
        blob = self.gather(chunks, comp_len)
        if checksum(blob) != csum:
            return False
        if raw:
            page = blob if len(blob) == self.cfg.page else None
        else:
            page = decompress(blob, self.cfg.page)
        if page is None:
            return False
        self.dram.write(frame_pa, page)
        return True
