#!/usr/bin/env python3
"""Give an NX2Apple shell IPA its 16:9 cover and a custom App Icon set.

Why this exists: `export_shell` mirrors the framework through a whitelist
(binary, Info.plist, game.manifest.json, profile.tsv, dm/, msl/), so a
`banner.png` dropped into the framework never reaches the package, and the
shell template's default icons win. Rewriting the finished zip is the only
reliable place to add both.

Rules that matter:
  * icons replace the same-named entries (never append: zipfile then warns
    "Duplicate name" and installers behave unpredictably)
  * only the icons and the banner are STORED; everything else stays DEFLATED
    (storing a 2 GB shader image turns a 0.98 GB package into 2.12 GB)

Usage:
  python repack_ipa_artwork.py --src in.ipa --out out.ipa \\
      --banner banner.png --icon AppIcon1024.png \\
      [--title-id 01008F6008C5E000] [--app Payload/DmShell.app/]
"""

import argparse
import io
import os
import plistlib
import sys
import zipfile

from PIL import Image

# (file name, pixel size) — iPhone + iPad families, TARGETED_DEVICE_FAMILY = 1,2
SIZES = [
    ("AppIcon60x60@2x.png", 120),
    ("AppIcon60x60@3x.png", 180),
    ("AppIcon76x76@2x.png", 152),
    ("AppIcon76x76@1x.png", 76),
    ("AppIcon40x40@2x.png", 80),
    ("AppIcon40x40@3x.png", 120),
    ("AppIcon29x29@2x.png", 58),
    ("AppIcon29x29@3x.png", 87),
    ("AppIcon20x20@2x.png", 40),
    ("AppIcon20x20@3x.png", 60),
]


def make_png(src, size):
    im = Image.open(src).convert("RGBA")
    bg = Image.new("RGB", im.size, (0, 0, 0))  # iOS icons must be opaque
    bg.paste(im, mask=im.split()[-1])
    im = bg.resize((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def icon_keys():
    primary = ["AppIcon60x60"]
    ipad = ["AppIcon60x60", "AppIcon76x76"]
    return {
        "CFBundleIcons": {"CFBundlePrimaryIcon": {
            "CFBundleIconFiles": primary, "CFBundleIconName": "AppIcon"}},
        "CFBundleIcons~ipad": {"CFBundlePrimaryIcon": {
            "CFBundleIconFiles": ipad, "CFBundleIconName": "AppIcon"}},
        "CFBundleIconFiles": ipad,  # legacy key
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="IPA produced by export_shell")
    ap.add_argument("--out", required=True, help="IPA to write")
    ap.add_argument("--banner", help="16:9 cover, lands in the game framework")
    ap.add_argument("--icon", help="square source image, 1024 px recommended")
    ap.add_argument("--title-id", default="01008F6008C5E000")
    ap.add_argument("--app", default="Payload/DmShell.app/",
                    help="app folder inside Payload (keep the trailing slash)")
    a = ap.parse_args()

    app = a.app if a.app.endswith("/") else a.app + "/"
    fw_banner = "%sFrameworks/DmGame%s.framework/banner.png" % (app, a.title_id)

    src = zipfile.ZipFile(a.src)
    raw = src.read(app + "Info.plist")
    fmt = plistlib.FMT_BINARY if raw[:6] == b"bplist" else plistlib.FMT_XML
    pl = plistlib.loads(raw)
    pl.update(icon_keys())
    new_plist = plistlib.dumps(pl, fmt=fmt)

    pngs = {n: make_png(a.icon, s) for n, s in SIZES} if a.icon else {}
    for name in pngs:
        print("  %-26s %7d B" % (name, len(pngs[name])))
    banner = open(a.banner, "rb").read() if a.banner else None

    with zipfile.ZipFile(a.out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as out:
        for info in src.infolist():
            n = info.filename
            if n == app + "Info.plist":
                data = new_plist
            elif n.startswith(app) and n[len(app):] in pngs:
                continue  # replaced below
            elif banner is not None and n == fw_banner:
                continue
            else:
                data = src.read(n)
            zi = zipfile.ZipInfo(n, date_time=info.date_time)
            zi.external_attr = info.external_attr
            zi.create_system = info.create_system
            out.writestr(zi, data, zipfile.ZIP_DEFLATED)
        for name, blob in pngs.items():
            zi = zipfile.ZipInfo(app + name)
            zi.external_attr = 0o644 << 16
            out.writestr(zi, blob, zipfile.ZIP_STORED)
        if banner is not None:
            zi = zipfile.ZipInfo(fw_banner)
            zi.external_attr = 0o644 << 16
            out.writestr(zi, banner, zipfile.ZIP_STORED)
    src.close()

    z = zipfile.ZipFile(a.out)
    names = z.namelist()
    dups = sorted({n for n in names if names.count(n) > 1})
    print("size %d entries %d dups %s" % (os.path.getsize(a.out), len(names), dups))
    print("banner %s" % (fw_banner in names))
    print("icons %s" % [n[len(app):] for n in names if n.startswith(app) and n.endswith('.png')])
    print("zip test %s" % (z.testzip(),))
    mf = "%sFrameworks/DmGame%s.framework/game.manifest.json" % (app, a.title_id)
    if mf in names:
        print("manifest %s" % mf)
    return 0 if not dups and z.testzip() is None else 1


if __name__ == "__main__":
    sys.exit(main())
