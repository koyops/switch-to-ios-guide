#!/usr/bin/env python3
"""Write the phone-side romfs identity into an NX2Apple game.manifest.json.

The builder stamps the identity of the image it repacked itself (the slim,
5.41 GB one). The shell compares `size` and `index` byte-exact, so a phone
carrying the complete 6.68 GB romfs is judged "another version / data
missing" until both numbers are replaced with its own.

Get the real numbers with the engine:
  python engine/dm/tools/romfs_image.py --identity <RomFS.img>

Usage:
  python patch_romfs_identity.py <manifest> [<manifest> ...] \\
      --size 6678553818 --index 040fff3c5772fbdf
"""

import argparse
import json
import re
import sys

LINE = "DMROMFSID1 title=%s version=%s build=%s size=%d index=%s"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifests", nargs="+")
    ap.add_argument("--size", type=int, required=True)
    ap.add_argument("--index", required=True)
    ap.add_argument("--title", help="default: manifest title_id")
    ap.add_argument("--version", help="default: manifest display_version")
    ap.add_argument("--build", help="default: manifest package_version")
    a = ap.parse_args()

    bad = 0
    for path in a.manifests:
        with open(path, encoding="utf-8") as f:
            m = json.load(f)
        old = m.get("romfs_identity", "")
        tid = a.title or m.get("title_id")
        ver = a.version or m.get("display_version")
        build = a.build or m.get("package_version")
        new = LINE % (tid, ver, build, a.size, a.index)
        m["romfs_identity"] = new
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(m, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print("%s\n  was: %s\n  now: %s" % (path, old, new))
        if old and not re.match(r"DMROMFSID1 ", old):
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
