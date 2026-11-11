# NX2Apple 聚合壳 + 宝可梦紫：真机跑通全流程（Windows · iOS 27）

> 这套流程和本仓 `README.md` 里的「单游戏版」是两条不同路线。
> **新版壳（v1.3.0 起的 Windows 构建器）给引擎传的是 `<framework>/dm` 绝对路径 + `manifest.modules`**，
> 所以不再需要手工装配旧壳、不再需要往 `Documents/<titleId>/` 铺 main.fixups.tsv 那一套。
> 旧路线的结论已作废，别再照着调。

环境：Windows 11 x64 · iPhone 17 Pro Max · iOS 27.0 · 无 Mac · 无付费开发者账号（iSigner 自签）
引擎：[NxNative / NS Port Builder](https://github.com/seedds/nxnative) v1.3.0
日期：2026-11-11

---

## 0. 结果概览（这一版是已经跑起来的实测值）

| 项目 | 值 |
|---|---|
| 游戏 | 宝可梦 紫（Pokémon Violet） |
| Title ID | `01008F6008C5E000` |
| 壳 bundle | `org.nxnative.shell.SXHD48L9TQ`，shell commit `daba995ab521` |
| framework | `DmGame01008F6008C5E000.framework`，主二进制 92,211,040 B |
| 模块 | `modules = [main, sdk]`，nro_count 2 |
| 着色器链 | `89f44f9b6bb0`，`msl/b-89f44f9b6bb0.img` 2,073,219,238 B |
| 着色器数量 | 30,142（`[4/6] 30142 of 30142 ready`） |
| 产物 IPA | `NX2Apple.ipa` 约 1.05 GB，80 条目，zip 校验 `bad None` |
| 包内 romfs | 无（瘦身正确，游戏数据单独推送到手机） |

真机实测（手机回传 `log.txt`，帧 1 → 300）：

```
[dm] fs RomFS image .../games/01008F6008C5E000/romfs.img: 39 entries
[dm] fs mount data: → romfs.img (read-only)
[dm] fs mount save0: → .../save.work (transactional save, swapped in atomically on Commit)
[dm] [nvn-mtl] Metal device Apple A19 Pro GPU
[dm] [msl] host shader libraries: 13, compiled for iphoneos by Apple metal version 32023.850
[dm] >>> nnMain
[dm] [nvn] timing up to frame 300: frame time p50 33.33 / p95 34.54 / max 336.90 ms; GPU p50 6.24 ms
[dm] [nvn] on-screen up to frame 300: 289 frames, dropped 2, footprint 1099 MiB
```

30 fps 是游戏自己锁的：日志 `the game sets present interval 1 → 2`（`main+0x13fa444`）。
GPU 只用 6.2 ms，性能余量五倍以上——**不是卡，是游戏原生节奏**。

---

## 1. 为什么换壳（旧路线死因，省你三天）

| 症状 | 旧壳 `DmShell`（129,072 B） | 新壳 v1.3.0 |
|---|---|---|
| 启动即崩 | `[dm] FATAL open 01008F6008C5E000/main.fixups.tsv` + `CRASH sig=6` | — |
| 传参 | 裸 titleId，引擎自己去 Documents 下乱找 | `<framework>/dm` **绝对路径** + `manifest.modules` |
| 依据 | — | `frontend-ios/Sources/ShellHost/EngineLaunchPlan.swift:83` |

结论：**旧壳无论怎么铺文件都不会好**，因为路径契约根本不同。手改 cwd、反汇编找字符串引用、三处铺 `main.fixups.tsv` 全是白工。

---

## 2. 环境前置

```
C:\Users\<user>\AppData\Local\NS Port Builder\     工具链（dotnet SDK 10.0.403 / llvm-mingw clang 23.1.4 / iPhoneOS27.2.sdk 24B8118 / zstd）
D:\nspb\shell\src\NX2Apple-main\                     源码（frontend-qt + frontend-ios + engine）
D:\nspb\shell\winbuild\NX2Apple\                       Windows 构建器安装目录（含 _internal 与 shell_template）
D:\nspb\shell\winbuild\work_violet\                   本次构建工作区
```

两个必须记住的约束：

1. **`PYTHONPATH` 必须指向源码版的 `nspb_qt`**，不能用 `_internal\nspb_qt`，否则报 `python312.dll conflicts`。
2. **工作根要在纯 ASCII 路径**（`D:\nspb\...`），中文路径会让 `metal.exe` 按 ANSI/GBK 解码失败，产出成千上万条 `LLVM ERROR`。

```powershell
$py   = 'C:\Users\<user>\AppData\Local\NS Port Builder\venv\Scripts\python.exe'   # 3.12.10
$env:PYTHONPATH = 'D:\nspb\shell\src\NX2Apple-main\frontend-qt'
$env:NSPB_REPO  = 'D:\nspb\shell\winbuild\NX2Apple\engine'
```

---

## 3. 唯一的源码补丁：模拟堆 96 MB → 384 MB

**文件**：`frontend-qt\nspb_qt\win\arm64_emu.py:610`

```python
heap_size: int = 384 << 20      # 原值 96 << 20
```

不打这个补丁，`[dm] DM_OODLE_SERVE` 解 21,009,849 → 70,786,896 字节时必炸：

```
[dm] DM_OODLE_SERVE: request 26502: emulated heap full (96 MB)
```

> 这个值不要回滚。它是唯一一个「必须改源码」的点，其余问题都靠参数和缓存解决。

---

## 4. 构建：六步与它的真实耗时

入口是构建器的 `build_ipa_from_nsp.py`（内部按 `[n/6]` 打印阶段）。

```powershell
$env:J = '3'        # 并发，默认 8；本机 24 核 / 16 GB / 页面文件仅 6 GB
& $py 'D:\破解\破甲\evidence\run_build_violet.py'
```

成功那一版（`build_violet6.log`）的六步：

```
[1/5] pack v0 ✓ 0:00  5.0 GB
[2/6] rewrite ✓ reused
[3/6] shader split ✓ 30,142 shaders reused
[4/6] iOS shaders ✓ 30,142 of 30,142 shaders ready, reused (inputs unchanged)
[5/6] game framework ✓ 1:01
        driver exit 0
```

**缓存复用是唯一能让这台机器跑完的办法**：只要 `shader\cache` 的 `inputs.tsv` stamp 没变，`[3/6]` / `[4/6]` 都是 0 秒；只有第一次要真编 30,142 个。

### 4.1 失败矩阵（照这个判，别再瞎试）

| 日志特征 | 真因 | 处理 |
|---|---|---|
| `shader split` 里 `decoder in the Mac host failed on a 2042 → 6248 byte stream` | 堆满，不是解码器坏 | 打 §3 的 384 MB 补丁 |
| `MemoryError` at `uc.mem_write` | 同上 | 同上 |
| `DM_OODLE_SERVE ... emulated heap full (96 MB)` | 同上 | 同上 |
| `malformed or corrupted AST file ... prefix.h` + `LLVM ERROR: out of memory`（exit 3221225725） | Windows 页面文件被并发榨干 | **降 J**，不要改页面文件 |
| `[WinError 1455] 页面文件太小` | 同上 | 同上（J 从 4 降到 3 就过） |

> 页面文件本机是 `C:\pagefile.sys` 1024 MB + `D:\pagefile.sys` 5314 MB，**不要动**。
> 解法是低并发 + 缓存复用，不是扩容。

---

## 5. ★ romfs 身份补丁（这一步不做，手机上永远「缺少游戏数据」）

构建器生成的清单里，`romfs_identity` 写的是**它自己重打包的 5.41 GB 镜像**身份：

```
size=5412377703  index=dda12a9ec8c1176c
```

而手机上放的是**完整 romfs**（38 项，含 `arc/data.trpfs` 5,400,895,216 + `audio/wwise/Stream.pck` 974,760,211）：

```
size=6678553818  index=040fff3c5772fbdf
```

壳按 `size + index` 严格比对（依据 `patches/0004-ios-slim-ipa.patch`：only a Documents/romfs.img with the same size and index hash），不一致就判「另一版本 / 数据缺失」。

**所以两处 manifest 都要改：**

```
work_violet\shell-framework\DmGame01008F6008C5E000.framework\game.manifest.json
shell_root\frameworks\DmGame01008F6008C5E000.framework\game.manifest.json
```

改成：

```
DMROMFSID1 title=01008F6008C5E000 version=1.0 build=v0 size=6678553818 index=040fff3c5772fbdf
```

一条命令（本仓 `tools/patch_romfs_identity.py`）：

```powershell
& $py tools\patch_romfs_identity.py `
  'D:\nspb\shell\winbuild\work_violet\shell-framework\DmGame01008F6008C5E000.framework\game.manifest.json' `
  'D:\nspb\shell\winbuild\shell_root\frameworks\DmGame01008F6008C5E000.framework\game.manifest.json' `
  --size 6678553818 --index 040fff3c5772fbdf
```

用引擎自己算一遍手机那份镜像，确认这两个数是真值：

```powershell
& $py 'D:\nspb\shell\winbuild\NX2Apple\engine\dm\tools\romfs_image.py' --identity 'D:\nspb\games\01008F6008C5E000_build\RomFS.img'
```

> ⚠️ **重跑 `[5/6]` 会重新生成清单并丢掉这个补丁。** 只要重建 framework，就再打一次。

---

## 6. 导出壳 IPA

```powershell
$env:NSPB_SHELL_TEMPLATE = 'D:\nspb\shell\winbuild\NX2Apple\_internal\shell_template\DmShell.app'
```

然后调 `nspb_qt.win.shell_export.export_shell(...)`（本机脚本在 `%TEMP%\re_export.py`）：

| 参数 | 值 |
|---|---|
| `root` | `D:\nspb\shell\winbuild\shell_root` |
| `repo` | `...\NX2Apple\engine` |
| `framework` | `work_violet\shell-framework\DmGame01008F6008C5E000.framework` |
| `title_id` | `01008F6008C5E000` |
| `name` | `Pokemon Violet` |

期望日志：

```
pack: 70 entries, 2207747097 bytes
packed: 70 entries, stored 0.00 GB, deflated 2.06 GB, archive 0.98 GB, reused 0 files in 123 s
OK True IPA D:\nspb\shell\winbuild\shell_root\export\NX2Apple.ipa
```

三个已踩过的坑：

1. 不设 `NSPB_SHELL_TEMPLATE` → `shell.exportFailed: missing DmShell.app template`
2. `pack_ipa.py` 不接受 PowerShell 的 `'prefix='$var` 拼接，会报 `not <archive path>=<file or folder>`。**整条拼成一个字符串参数**。
3. `export_shell` 结束时会把 `export\stage\` 清掉，别指望之后还能拿 stage 补文件。

---

## 7. 封面与 App 图标的注入（导出白名单会吃掉它们）

### 现象

把 `banner.png` 放进 `work_violet\...\framework\`，重导出后包里仍然没有：

```
banner: []      # IPA 里搜不到任何 banner
icons:  ['Payload/DmShell.app/AppIcon60x60@2x.png', 'AppIcon76x76@2x~ipad.png']   # 官方默认图标
```

原因是 `export_shell` 通过 `mirror_framework()` 镜像 framework 时只复制白名单文件（主二进制 / `Info.plist` / `game.manifest.json` / `profile.tsv` / `dm\` / `msl\`），`banner.png` 不在里面，还会把镜像目录里的多余文件清掉。

### 解法：在最终 zip 上一次写入

用本仓 `tools/repack_ipa_artwork.py`：

```powershell
& $py tools\repack_ipa_artwork.py `
  --src   'D:\nspb\shell\winbuild\shell_root\export\NX2Apple.ipa' `
  --out   'D:\nspb\shell\winbuild\PokemonViolet-NX2Apple-v2.ipa' `
  --banner 'D:\nspb\shell\winbuild\work_violet\shell-framework\DmGame01008F6008C5E000.framework\banner.png' `
  --icon   'D:\nspb\shell\icon\AppIcon1024.png'
```

它会做四件事：

1. 写 `Payload/DmShell.app/Info.plist` 的 `CFBundleIcons` / `CFBundleIcons~ipad` / `CFBundleIconFiles`
2. 生成 10 个尺寸的 AppIcon（20/29/40/60 + 76，含 @2x/@3x），铺黑底保证不透
3. 把 `banner.png` 写进 `Frameworks/DmGame<TID>.framework/banner.png`
4. **删掉原始包里同名图标条目**，避免 zip 里出现重名（重名会让安装器行为不确定）

两个必须注意的细节：

- 同尺寸图标必须**替换**而不是追加，否则 `zipfile` 报 `Duplicate name`
- 除 `.png` / `banner` 外全部用 `ZIP_DEFLATED`。曾经的写法把 2.07 GB 的 `b-<chain>.img` 走 `STORED`，包从 0.98 GB 直接涨到 2.12 GB

结果：

```
size 1050960850 entries 80 dups [] banner True zip test None
identity ok True        # romfs_identity 仍是手机侧 6678553818 / 040fff3c5772fbdf
```

封面规范：**16:9**（壳按 `min(width*9/16, 220)` 裁）；方形 icon 用 `icon.<ext>`，横版用 `banner.<ext>`，命名在 `GameCatalogue.swift` 里按前缀匹配。

---

## 8. 装机与验收

### 8.1 装机

iSigner 自签（免费 Apple ID 即可），把 IPA 拖进去重签安装。**游戏数据不会因为覆盖安装丢失**（在 `Documents` 里）。

### 8.2 六项验收与判读

| 项 | 判据（日志） | 本次结果 |
|---|---|---|
| 进入游戏 | 出现 `[dm] >>> nnMain` 且 `timing up to frame N` | ✅ 300 帧 |
| 数据识别 | `fs RomFS image ...: N entries` + `fs mount data:` | ✅ 39 entries 已挂载 |
| 中文 | `boot: DM_LANG=...` | ⚠️ 默认 `en-US`，见 8.3 |
| 存档读档 | `fs mount save0: → .../save.work (transactional save)` | ✅ 目录就绪，实存实读需人工点一次 |
| 触控布局 | `front end: layout overlay ... picture {...} controls {...}` + `right-stick hint shown` | ✅ |
| 帧率 | `timing up to frame N: frame time p50 ...` + `on-screen ... dropped` | ✅ 30 fps / 300 帧丢 2 |
| 封面图标 | 包内 `banner.png` + 图标条目 | ✅ 见 §7 |

### 8.3 切中文

不用重打包，游戏卡片 → 齿轮 → **Game language** → 简体中文，重启游戏。
可选语言来自 `dm\launcher.json` 的 `DM_LANG` 行，16 项里含 `zh-Hans` / `zh-Hant`。

### 8.4 帧率的真相

- 默认 30 fps 是游戏自己要求的 `present interval 2`，和 Switch 原机一致。
- 想更清晰：`DM_PRESENT_UPSCALE` 由 `off` → `metalfx`。
- **不建议** `DM_PRESENT_INTERVAL=display` 强行提到 60：紫按帧计数驱动动画与战斗节奏，改了会整体变速（引擎注释只建议对「不数帧」的游戏这样改）。

### 8.5 后段掉帧（可选优化）

```
[nvn-mtl] pipeline prewarm list .../pso_manifest.tsv: 0 lines
[nvn] pipelines ... draws that waited: hybrid off 42 / 709.4 ms
frame interval up to frame 300: >33.3ms 151 / 299 frames
```

不是性能不足，是**新 pipeline 现场编译**。要消除就生成 `pso_manifest.tsv` 预编译清单（`DM_PSO_PREBUILD=1` 已经在跑，但清单为空）。

---

## 9. 再装第二款游戏（朱 / ZA）

一个 App 装多游戏是壳的原生能力，规则只有三条：

1. **每个游戏一个 framework**：`DmGame<TID>.framework`，各自独立的 `dm\` 表与 `msl\b-<chain>.img`
2. **每个游戏一份 manifest，身份按手机侧真实 romfs 改**（§5）
3. **每款游戏的 romfs 单独推到手机**：`Documents/games/<TID>/romfs.img`

步骤：

```
① 取该版本可用的 romfs（要么用构建器重打包的，要么用完整 dump 的，二选一）
② 跑同一套构建（[1/6] → [5/6]），J=3
③ 用 §5 的脚本按手机侧镜像算 identity 并写进两处 manifest
④ 重跑 export_shell，一次导出包含所有 framework 的 IPA
⑤ 装机后逐个游戏首启，按 §8.2 六项判读
```

> 朱（`0100A3D008C5C000` 系）与 ZA（需 2.0.2 / v393216）本次都还没有本机素材。
> 素材到手后按上面五步走，不需要再动电脑上任何配置。

---

## 10. 踩坑速查（已验证死路，不要重试）

| 尝试 | 结果 |
|---|---|
| 手工装配旧壳 + 外置模块 | `FATAL open <titleId>/main.fixups.tsv` |
| 反汇编旧壳找字符串引用（`adrp add`） | 0 条（chained fixups + 字面池 + stub） |
| 用 `_internal` 版 nspb_qt 跑 CLI | `python312.dll conflicts` |
| 文件名写成 `RomFS(1).img` / `RomFS 2.img` | 壳直接跳过 |
| 不设 `NSPB_SHELL_TEMPLATE` 直接调 `export_shell` | `missing DmShell.app template` |
| `pack_ipa.py` 用 `'prefix='$var` 拼参数 | `not <archive path>=<file or folder>` |
| 单纯把 `J` 提到 4/3 | 反复 `WinError 1455`，正确解是低并发 + 缓存 |
| 把 `banner.png` 放 framework 里等导出带走 | 被白名单镜像吃掉，包内没有 |
| 图标用追加方式写入 zip | `Duplicate name`，条目重复 |
| `.img` 走 `STORED` 重打包 | 包体 0.98 GB → 2.12 GB |

---

## 11. 产物与哈希

```
D:\nspb\shell\winbuild\
├── shell_root\export\NX2Apple.ipa              1,049,988,538 B  （导出原包，无封面）
├── PokemonViolet-NX2Apple-v2.ipa               1,050,960,850 B  （★ 带封面 + 红黑图标）
│     SHA256  D8C4BFC3796AF7CF38EAFBBC1EF055E4D1EF5218DD48F345079200D126C6082F
├── build_violet6.log                           成功构建日志
└── work_violet\
    ├── shell-framework\DmGame01008F6008C5E000.framework\
    │     ├── DmGame01008F6008C5E000             92,211,040 B
    │     ├── game.manifest.json                 romfs_identity 已打补丁
    │     ├── banner.png                         923,219 B，1920×1080
    │     ├── dm\  (15 张表 + c1_full.tsv / launcher.json / shader_map.tsv / pso_manifest.tsv)
    │     └── msl\b-89f44f9b6bb0.img             2,073,219,238 B
    ├── shader\  1.56 GB（含 pkg 与 cache）
    ├── patched_v0\  0.08 GB
    └── extract\  5.08 GB
```

手机侧（数据，不可删）：

```
Documents/Documents/games/01008F6008C5E000/romfs.img     6,678,553,818 B，39 entries
Documents/games/01008F6008C5E000/save.work                事务式存档目录
```

---

## 12. 下次一句话怎么唤起

把这段直接发给助手即可：

> 照 `koyops/switch-to-ios-guide` 的 `nx2apple-shell-violet.md` 那套来，游戏是 `<游戏名> <TID>`，
> romfs 在 `<路径>`，J=3，构建完记得打 romfs 身份补丁再导出，最后用 `tools/repack_ipa_artwork.py` 补封面和图标。

---

## 13. 参考

- 上游：[seedds/nxnative](https://github.com/seedds/nxnative)
- 传参契约：`frontend-ios/Sources/ShellHost/EngineLaunchPlan.swift:83`
- 瘦身与身份比对：`patches/0004-ios-slim-ipa.patch`
- 帧率实现：`dm/gfx/nvn/hle_nvn.c:1922-1935`
- 游戏清单：`dm/games/` 下各 `game.tsv` 与 `README.md`
- 兼容列表：`GAMES.md`
- 旧单游戏路线：本仓 `README.md`
