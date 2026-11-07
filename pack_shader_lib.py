#!/usr/bin/env python
"""Pack a shader library folder into the single `b-<chain>.img` the app carries.

`dm/tools/shader_lib.py pack` does the same thing one file at a time through `write()`, which is
correct but spends most of its time on per-file open/read/close and (on Windows) on antivirus
scanning every file it creates. This keeps the exact image format from `shader_lib.write` — the
header, the 16-byte alignment, the entry table, the name pool — and only changes how the bytes
reach the file: one big buffered output, source files copied in large chunks.

The result is verified by `romfs.Image()`, the same read the host performs, so a malformed image
is never published. The folder is left in place; the caller removes it once the build is done.

Usage:
    python pack_shader_lib.py <b-chain folder> [--engine REPO]

    REPO resolves from --engine, then $NSPB_REPO, then the current directory's ../engine.

Why it matters: 107,386 loose files make signing take 39 minutes and make the iOS install fail
with `early eof` (iOS writes each file into the app container separately). One image brings the
IPA from 107,446 entries to 60, signs in ~2 minutes, and installs cleanly.
"""
import argparse
import os
import sys

ALIGN = 16                                    # shader_lib.ALIGN: Metal is handed a pointer into the map
# what the host reads (shader_lib.APP_SUFFIXES), minus the build's own report and dotfiles
SUFFIXES = ('.metallib', '.json', '.tsv')
LEAVE_OUT = ('_b_build.json',)


def engine_root(explicit=None):
    for cand in (explicit, os.environ.get('NSPB_REPO'), os.path.join(os.getcwd(), '..', 'engine')):
        if cand and os.path.isfile(os.path.join(cand, 'dm', 'tools', 'romfs.py')):
            return os.path.abspath(cand)
    sys.exit('[RED] cannot find the engine (pass --engine or set NSPB_REPO)')


def collect(folder):
    out = {}
    for e in os.scandir(folder):
        if not e.is_file(follow_symlinks=False):
            continue
        n = e.name
        if n.startswith('.') or '.tmp' in n or n in LEAVE_OUT:
            continue
        if not n.endswith(SUFFIXES):
            continue
        out[n] = e.path
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('folder', help='the b-<chain> folder dmsh_build.py wrote')
    ap.add_argument('--engine', help='the NxNative engine checkout (or set NSPB_REPO)')
    a = ap.parse_args(argv)

    repo = engine_root(a.engine)
    sys.path.insert(0, os.path.join(repo, 'dm', 'tools'))
    import romfs  # noqa: E402  (needs the engine on sys.path first)

    folder = os.path.normpath(a.folder)
    image = folder + '.img'
    part = image + '.part'
    files = collect(folder)
    if not files:
        sys.exit(f'[RED] no shader libraries in {folder}')

    names = sorted(n.encode() for n in files)
    total = sum(os.path.getsize(files[n.decode()]) for n in names)
    print(f'{len(names):,} files, {total / 2**30:.2f} GB -> {image}', flush=True)

    ents = []
    off = romfs.HEAD.size
    done = 0
    step = max(1, len(names) // 20)
    with open(part, 'wb', buffering=1 << 26) as out:
        out.write(b'\0' * off)
        for i, name in enumerate(names):
            source = files[name.decode()]
            off += -off % ALIGN
            out.seek(off)
            n = 0
            with open(source, 'rb', buffering=1 << 20) as f:
                while True:
                    b = f.read(4 << 20)
                    if not b:
                        break
                    out.write(b)
                    n += len(b)
            ents.append((name, off, n))
            off += n
            done += n
            if (i + 1) % step == 0:
                print(f'  {i + 1:,}/{len(names):,}  {done / 2**30:.2f} GB', flush=True)

        out.seek(off)
        pool, idx = bytearray(), bytearray(romfs.ENT.pack(1, len(names), 0, 0, 0, 0))
        for name, a_, b_ in ents:
            idx += romfs.ENT.pack(a_, b_, len(pool), len(name), 1, 0)
            pool += name
        out.write(idx)
        out.write(pool)
        out.seek(0)
        out.write(romfs.HEAD.pack(romfs.MAGIC, off, len(idx) + len(pool), len(names) + 1))

    romfs.Image(part)                          # the read the host performs: never publish a broken image
    os.replace(part, image)
    size = os.path.getsize(image)
    print(f'done: {image}  {size:,} bytes ({size / 2**30:.2f} GB)', flush=True)


if __name__ == '__main__':
    main()
