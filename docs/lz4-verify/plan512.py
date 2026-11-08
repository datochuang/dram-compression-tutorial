# Numbers for the 512 MiB redesign. Every figure and table in section 9 should match this output.
MiB = 1 << 20
pin_img, pin_run, hrt = 34, 22, 36
ro, data, heap = 248, 26, 306
rw = data + heap
need = pin_img + pin_run + hrt + ro + rw
print('content without compression', need)
hot_ro, hot_rw = 30, 80
r_ro, r_rw = 0.55, 0.45
pages = (ro + rw) * 256
cot_exact = pages * 32 / MiB
print('compressible MiB', ro + rw, 'pages', pages, 'COT MiB', round(cot_exact, 2))
cot = 5
hot = hot_ro + hot_rw
fc = 140
ro_obj = ro * r_ro
cold_rw = rw - hot_rw
rw_obj = cold_rw * r_rw
pool_need = ro_obj + rw_obj
pool = 275
total = pin_img + pin_run + hrt + cot + pool + fc
print('hot set', hot, 'frame cache', fc, 'frame margin', fc - hot, f'{(fc-hot)/hot*100:.0f}%')
print('RO objects', round(ro_obj, 1), 'cold RW', cold_rw, 'RW objects', round(rw_obj, 1), 'pool need', round(pool_need, 1), 'pool', pool, 'pool margin', round(pool - pool_need, 1), f'{(pool-pool_need)/pool_need*100:.0f}%')
print('DRAM total', total)
used = pin_img + pin_run + hrt + cot + ro_obj + hot_ro + hot_rw + rw_obj
print('in use at peak', round(used, 1), 'margin', round(512 - used, 1), f'{(512-used)/512*100:.1f}%')
print('saving RO', round(ro - ro_obj - hot_ro, 1), 'RW', round(rw - hot_rw - rw_obj, 1), 'COT', -cot, 'total', round(need - used, 1))
boot = pin_img + pin_run + hrt + cot + ro_obj + data
print('boot in use', round(boot, 1), 'boot without', pin_img + pin_run + hrt + ro + data)
print('flash image', round(pin_img + ro_obj + ro * 256 * 32 / MiB + data, 1), 'RO COT entries MiB', round(ro * 256 * 32 / MiB, 2))
chunks = pool * 2048
print('pool chunks', chunks, hex(chunks), 'list bytes MiB', round(chunks * 3 / MiB, 2), 'RO chunks ~', round(ro_obj * 2048))
# PA map, DRAM at 0x8000_0000
pa = 0x80000000
for n, sz in [('Pinned', pin_img + pin_run), ('HRT', hrt), ('COT', cot), ('Pool', pool), ('Frame cache', fc)]:
    print(f'{n:12s} {pa:#x} {sz}'); pa += sz * MiB
print('end', hex(pa))
pool_base = 0x80000000 + (56 + 36 + 5) * MiB; cot_base = 0x80000000 + (56 + 36) * MiB
fc_base = pool_base + pool * MiB
print('cot base', hex(cot_base), 'pool base', hex(pool_base), 'fc base', hex(fc_base))
vbase = 0x7F1220000000
for name, va in [('RW example', 0x7F1234567000), ('RO example', 0x7F123A3F1000), ('malloc p', 0x7F122B1C0F80)]:
    off = va - vbase
    print(name, hex(va), 'offset MiB', round(off / MiB, 1), 'handle', hex(off >> 12), 'RW' if off < rw * MiB else 'RO' if off < (rw + ro) * MiB else 'OUT')
h = (0x7F1234567000 - vbase) >> 12
print('COT entry', hex(cot_base + h * 32))
# Example RW object 0x14567: its chunks must lie above the RO image (which fills the pool from chunk 0).
ro_chunks = 279347                      # exact chunk count of the RO image used in the text (136.4 MiB)
first_free = ro_chunks
print('RO image chunks', ro_chunks, hex(ro_chunks), 'MiB', round(ro_chunks * 512 / MiB, 2), 'first free chunk', hex(first_free))
rw_list = [0x51A2F, 0x80013, 0x5F002, 0x6B410, 0x6B411]
for c in rw_list + [0x70B3A, 0x5E519, 0x49D62, 0x47C1E, 0x5D0A4, 0x7388B]:
    assert first_free <= c < chunks, hex(c)
for c in rw_list: print('chunk', hex(c), 'PA', hex(pool_base + c * 512))
print('chunk PA byte 1100', hex(pool_base + 0x5F002 * 512 + 76))
print('list chunk 0x47C1E PA', hex(pool_base + 0x47C1E * 512))
# INIT: free chunks in groups of 170; the first of each group is the list chunk holding the other 169.
free = chunks - first_free
groups, rest = divmod(free, 170)
print('free chunks', free, 'list chunks', groups, 'left in SRAM', rest, 'SRAM range', hex(first_free + groups * 170), hex(chunks - 1), 'last list chunk', hex(first_free + (groups - 1) * 170), 'second', hex(first_free + 170))
print('INIT writes KB', round(groups * 512 / 1024))
# RO example page 0x1A3F1: COT entry and assumed chunk numbers
h_ro = (0x7F123A3F1000 - vbase) >> 12
print('RO entry', hex(cot_base + h_ro * 32), 'RO entries start', hex(cot_base + rw * 256 * 32), 'index in RO', hex(h_ro - rw * 256), 'file offset', hex((h_ro - rw * 256) * 32))
ro_ex = 0x1830C
print('RO example chunks', hex(ro_ex), hex(ro_ex + 3), 'PA', hex(pool_base + ro_ex * 512))
# Flash image layout: 4 KiB header, then pinned image, RO chunk image, RO COT entries, .data
off = 0x1000
lay = []
for n, sz in [('pinned image', pin_img * MiB), ('RO chunk image', ro_chunks * 512), ('RO COT entries', ro * 256 * 32), ('.data', data * MiB)]:
    lay.append((n, off, sz)); off += sz
for n, o, sz in lay: print(f'flash {n:15s} at {o:#010x} size {sz:#x}')
print('flash end', hex(off), 'MiB', round(off / MiB, 2))
print('.data frames', data * 256, 'end PA', hex(fc_base + data * MiB))
print('sample first RO pages: text 2296 -> 5 chunks 0..4, pointers 2149 -> 5 chunks 5..9, random RAW 8 chunks 0xA..0x11, zero 26 -> 1 chunk 0x12')

for f in [0x9A2B4000, 0x9C059000, 0x9E713000, 0x97A53000, 0x98C07000]:
    print('frame', hex(f), fc_base <= f < 0xA0000000)
p = 0x7F122B1C0F80
print('malloc pages', [hex(((p - vbase) >> 12) + i) for i in range(4)], 'p+5000', hex(p + 5000), hex((p + 5000 - vbase) >> 12), 'header', hex(p - 16))
print('RO starts at handle', hex(rw * 256), 'last handle', hex(pages - 1))
print('fc frames', fc * 256, 'hot pages', hot_ro * 256, hot_rw * 256)
