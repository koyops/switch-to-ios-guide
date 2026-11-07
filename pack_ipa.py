#!/usr/bin/env python
"""Pack the iOS IPA from a finished work folder, with the environment the Windows shim needs.

Every macOS tool name the packers invoke (`xcrun`, `xcodebuild`, `metal`) is rewritten at the
subprocess boundary by the shim's `sitecustomize`, which only loads if this process passes the
shim folder on PYTHONPATH and the `.cmd` stand-ins on PATH. `nspb_qt.win.shim.build_env()` is the
one place that knows both, so this script starts from it instead of hand-setting variables.

Why this exists: `nspb_qt.win.driver` runs the whole pipeline, but it stalls at
`shader_lib.pack` (see the README). Running the stages separately and packing the IPA here keeps
every finished artifact reusable.

Usage:
    python pack_ipa.py --work DIR --out FILE [--engine REPO] [--inner DIR] [--title-id ID] ...

    --work   the build folder, i.e. <NSP folder>/<title ID>_build
    --inner  the folder holding nspb_qt (the packaged app's _internal, or a checkout)
    --engine the NxNative engine checkout

Every --flag that is not a path mirrors a game profile key so the IPA carries the right identity,
language and settings. They default to the values a Pokémon Sword build uses only when the flag
is omitted; pass them explicitly for another game.
"""
import argparse
import os
import subprocess
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--inner', required=True, help='folder holding nspb_qt (the app _internal)')
    ap.add_argument('--engine', required=True, help='the NxNative engine checkout')
    ap.add_argument('--work', required=True, help='the build folder (<NSP folder>/<title ID>_build)')
    ap.add_argument('--out', required=True, help='the .ipa to write')
    ap.add_argument('--title-id', default='0100ABF008968000', help='base game title ID (GAME)')
    ap.add_argument('--package', default='v0', help='the packed version folder under extract/')
    ap.add_argument('--patched', help='rewrite output folder (default <work>/patched_<package>)')
    ap.add_argument('--romfs', help='RomFS.img or RomFS folder (default <work>/extract/<pkg>/RomFS.img)')
    ap.add_argument('--profile', help='profile folder holding <title ID>/ (default <work>/profile)')
    ap.add_argument('--msl-ios', help='iOS shader libraries (default <work>/shader/ios)')
    ap.add_argument('--gfx', default='nvn', help='nvn / vulkan / gl')
    ap.add_argument('--name', help='home-screen name (default: the game name in control.nacp)')
    ap.add_argument('--app-version', help='CFBundleShortVersionString')
    ap.add_argument('--bundle-id', help='default org.nxnative.<title ID lower-case>')
    ap.add_argument('--team-id', default='0000000000')
    ap.add_argument('--lang', default='en-US')
    ap.add_argument('--pso-gpus', default='none', help='pipeline archive GPUs (none = build on device)')
    ap.add_argument('--show-fps', default='1')
    a = ap.parse_args(argv)

    sys.path.insert(0, os.path.abspath(a.inner))
    from nspb_qt.win import shim

    work = os.path.abspath(a.work)
    ex = os.path.join(work, 'extract', a.package)
    env = shim.build_env(python_exe=sys.executable)
    env.update(
        GAME=a.title_id,
        W=os.path.join(work, 'ipa'),
        PATCHED=os.path.abspath(a.patched or os.path.join(work, f'patched_{a.package}')),
        ROMFS=os.path.abspath(a.romfs or os.path.join(ex, 'RomFS.img')),
        MSL_IOS=os.path.abspath(a.msl_ios or os.path.join(work, 'shader', 'ios')),
        GFXAPI=a.gfx,
        FONT_PY=sys.executable,
        DM_TEAM_ID=a.team_id,
        DM_LANG=a.lang,
        DM_SHOW_FPS=a.show_fps,
        DM_PSO_GPUS=a.pso_gpus,
        CONTROL=os.path.join(ex, 'control.nacp'),
        DM_ICON=os.path.join(ex, 'icon.jpg'),
        DM_ROOT=work,
        WORK=os.path.join(work, 'tmp'),
        NSPB_REPO=os.path.abspath(a.engine),
    )
    # A derived or provisional profile lives outside the repository; DM_GAMES_FIRST makes every
    # tool (game.py, the shader tools, this packer) take it instead of the registered one.
    profile = os.path.abspath(a.profile or os.path.join(work, 'profile'))
    if os.path.isdir(os.path.join(profile, a.title_id)):
        env.update(DM_GAMES_DIR=profile, DM_GAMES_FIRST='1', DM_GAME=a.title_id)
    for key, val in (('DM_DISPLAY_NAME', a.name), ('DM_APP_VERSION', a.app_version),
                     ('DM_BUNDLE_ID', a.bundle_id)):
        if val:
            env[key] = val

    for d in (env['W'], env['WORK'], os.path.dirname(os.path.abspath(a.out))):
        if d:
            os.makedirs(d, exist_ok=True)

    cmd = [sys.executable, os.path.join(os.path.abspath(a.inner), 'nspb_qt', 'win', 'build_app.py'),
           os.path.abspath(a.out)]
    print('running:', ' '.join(cmd), flush=True)
    raise SystemExit(subprocess.call(cmd, env=env, cwd=work))


if __name__ == '__main__':
    main()
