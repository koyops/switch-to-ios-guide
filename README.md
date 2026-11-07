# Switch 游戏移植 iOS 全流程实录：宝可梦剑

> 从 9.53 GB 的 NSP 到一个能跑在 iPhone 上的未签名 IPA。
> 完整记录了 **Windows 平台**上的全部构建步骤、踩过的 6 个坑、以及每个坑的根因与修复。
>
> 环境：Windows 10/11 x64 · Python 3.12 · .NET SDK 10 · LLVM-MinGW · Metal Developer Tools 6.2 · iPhoneOS 27.2 SDK
> 工具链：[NxNative / NS Port Builder](https://github.com/seedds/nxnative)
> 日期：2026-11-07

---

## 0. 结果概览

| 项目 | 值 |
|---|---|
| 游戏 | 宝可梦 剑（Pokémon Sword） |
| Title ID | `0100ABF008968000` |
| 版本 | base v0（display 1.0.0） |
| 源文件 | `剑.nsp` · 10,236,752,946 字节（9.53 GB） |
| 产物 | `PokMonSword.ipa` · 824,224,490 字节（0.768 GiB） |
| 产物 SHA256 | `5F5723F66F8BEA4324317D13C7039A0692142FD85AE680983032CACCBFA2C6DC` |
| IPA 条目数 | **60** |
| 着色器 | 36,805 个，**0 失败** |
| 打包模式 | slim（RomFS 不入包，单独推送） |
| 目标系统 | iOS 26.0+（`MinimumOSVersion = 26.0`） |

### 关键指标

```
提取:     ExeFS 6 模块 31.9 MB · RomFS 41,702 文件 / 9,707.6 MB
rewrite:  main / subsdk0 / subsdk1 / sdk  ·  11 秒（复用缓存）
split:    36,805 shaders
Metal:    36,805 编译成功，0 失败
变体库:   _bv 3,951 · _bx 20,651 · _bp 16,084 · 全部 0 失败
编译:     267 / 267 源文件 → arm64-apple-ios26.0
链接:     267 objects · 22 frameworks（ld64.lld）
签名:     ad-hoc + Increased Memory Limit entitlement
```

---

## 1. 前置准备

### 1.1 需要的工具

| 工具 | 版本要求 | 说明 |
|---|---|---|
| Python | 3.12+ | 脚本要求，`romfs.py` 用到 3.12 的 buffer protocol |
| .NET SDK | 10+ | 构建 `nx_extract`（C# 解包器） |
| LLVM-MinGW | 23.x | 替代 macOS 上的 clang，交叉编译 iOS |
| Metal Developer Tools | 6.2 | **必须**，Windows 版 Apple Metal 编译器 |
| iPhoneOS SDK | 27.2 | 从 Xcode 提取的 SDK |
| zstd / spirv-cross / glslangValidator | — | 已包含在 app 的 `wheels`/tools 里 |

### 1.2 Python 依赖

```powershell
# app 自带 wheels，离线安装
$app = "D:\破解\nx2apple\app\NS Port Builder"
python -m pip install --no-index --find-links "$app\wheels" `
  capstone lz4 fonttools backports.zstd zstandard pycryptodome
```

> ⚠️ `capstone` 必须是 **5.x**。6.x 改了 API 名（`CS_ARCH_ARM64` → 新名），rewriter 会崩。

### 1.3 密钥

需要 `prod.keys`。本次用的是 `prod20.2.0.keys`。

### 1.4 验证工具链

```powershell
$app = "D:\破解\nx2apple\app\NS Port Builder"
$env:PYTHONPATH = "$app\_internal"
$env:NSPB_REPO  = "$app\engine"
python -m nspb_qt.win.doctor
```

期望全部 `[ok]`：

```
[ok] .NET SDK 10                  SDK 10.0.403
[ok] LLVM (clang)                 23.1.4
[ok] ld64.lld (Mach-O linker)
[ok] iPhoneOS SDK                 27.2 24B8118
[ok] Metal Developer Tools        Apple metal version 32023.850
[ok] metal-tt (pipeline archive)  available
[ok] spirv-cross / zstd / glslangValidator
[ok] cross-compile / cross-link / Metal compile probe
```

---

## 2. ⚠️ 最重要的一条：工作目录必须是纯 ASCII 路径

**这是本流程最容易踩、且最难自查的坑。**

### 现象

36,805 个 shader 编译，产生 **13,043 条 `[RED]`**，日志里全是：

```
LLVM ERROR: Error opening 'D:\锟狡斤拷\games\...\mtlcache-ios-26080-3684.air':
  ...Unicode 字符... 无法映射到当前代码页
[RED] 77ddd6cd74fb037d: the alpha test and logic operation entry points do not build
```

### 根因

- 系统 ANSI 代码页 = **936（GBK）**
- 工作目录 `D:\破解` 含中文
- `metal.exe` 读命令行参数走 **ANSI**，不走 UTF-16
- VS Code / Python 以 UTF-8 传递路径字节

转码链：

```
破解
  → UTF-8 字节: E7 A0 B4 E8 A7 A3
  → metal.exe 按 GBK 解读: 鐮磋В
  → 该路径不存在
  → LLVM ERROR
```

36,805 次并发调用里约 **1/8** 撞上这个竞态。

### 修复

**把工程根目录放到纯 ASCII 路径下**：

```
D:\nspb\          ← 工作根（纯 ASCII）
├── engine\       ← 从 app 复制过来的引擎
├── _internal\    ← nspb_qt
└── games\        ← NSP 与构建产物
```

> 💡 `D:\nspb` 这个名字本身也有讲究：短、纯 ASCII、无空格。

### 验证

搬到 ASCII 路径后：

```
RED: 0   LLVM ERROR: 0   编码错乱: 0
```

**从 13,043 条错误 → 0 条。**

---

## 3. 目录布局

```
D:\nspb\
├── engine\                              # NxNative 引擎（从 app 复制）
│   ├── scripts\build_ipa_from_nsp.py
│   ├── dm\tools\                        # romfs.py / shader_lib.py / nx_extract
│   ├── dm\games\                        # 145 个游戏 profile
│   ├── dm\gfx\tools\                    # shader_split.py / shader_lib.py
│   ├── dm\ios\                          # iOS 层（Sources / Launcher.swift）
│   └── dm\host\                         # 宿主 C 代码（romfs_identity.h 等）
├── _internal\nspb_qt\win\               # Windows 适配层
│   ├── driver.py                        # 上游模块加载器 + patch
│   ├── build_app.py                     # 替代 build_ipa.sh
│   ├── shim.py                          # xcrun / metal 命令重写
│   └── toolchain.py
├── pack_ipa.py                          # 我自己写的打包入口
├── pack_shader_lib.py                   # 我自己写的 shader 库打包器
└── games\
    ├── 剑.nsp
    └── 0100ABF008968000_build\          # 构建工作区
        ├── extract\v0\                  # ExeFS / RomFS.img / control.nacp / icon.jpg
        ├── profile\0100ABF008968000\    # 派生 profile + shader 表
        ├── patched_v0\                  # rewrite 后的模块
        ├── shader\
        │   ├── pkg\                     # 36,805 个 shader 的原始数据
        │   ├── cache\b-<chain>\         # Mac 输出 + inputs.tsv stamp
        │   └── ios\b-<chain>.img        # ★ 单文件 shader 库（关键优化）
        ├── logs\
        └── ipa\
```

---

## 4. 完整构建流程

### 4.1 一步到位（推荐）

```powershell
cd D:\nspb
$env:PYTHONPATH = "D:\nspb\_internal"
$env:NSPB_REPO  = "D:\nspb\engine"

python -m nspb_qt.win.driver "D:\nspb\games" `
  -k "D:\破解\switch_assets\prod20.2.0.keys" `
  --progress lines
```

驱动会依次执行：`nx_extract 构建 → 提取 → rewrite → shader split → iOS shaders → app build → IPA pack`。

> ⚠️ 这条命令在 shader 阶段会卡在 `pack_libraries`（见 §6.4），实际推荐拆分执行。

### 4.2 分步执行（可控，推荐）

#### Step 1 · 校验密钥与包

```powershell
$nx   = "D:\破解\tools\nx_extract\nx_extract.dll"
$dn   = "$env:LOCALAPPDATA\NS Port Builder\dotnet\dotnet.exe"
$keys = "D:\破解\switch_assets\prod20.2.0.keys"
$nsp  = "D:\nspb\games\剑.nsp"

# 只读 header，验证密钥能开包
& $dn $nx $keys --keys $nsp
# 期望: the keys open all 1 packages

# 读标题与内容
& $dn $nx $keys --title    $nsp   # title 0100abf008968000
& $dn $nx $keys --contents $nsp   # content Application 0100abf008968000 0
```

#### Step 2 · 提取

```powershell
$out = "D:\nspb\games\0100ABF008968000_build\extract\v0"
New-Item -ItemType Directory -Force -Path $out | Out-Null

& $dn $nx $keys $nsp - $out --romfs-image
```

期望输出：

```
title 0100abf008968000
display version 1.0.0
name Pokémon Sword
icon AmericanEnglish (96782 bytes)
ExeFS: 6 files 31.9 MB
main build id 8dafedbb5be81c2c0160161159a791e6
sdk  build id fcf93a41b08c5193a1410d262602dc62
subsdk0 build id 93ff8252d975adf07230cb86c83301c5
subsdk1 build id a36dac0e0a5ed3b41482b6bb85625c73
RomFS.img: 41702 files 9707.6 MB
```

#### Step 3 · 派生 profile

因为手上是 **base v0**，而引擎 profile 注册的是 **v458752（1.3.2）**，所以要派生：

```powershell
$env:DM_GAMES_DIR  = "D:\nspb\games\0100ABF008968000_build\profile"
$env:DM_GAMES_FIRST = "1"
$env:DM_GAME        = "0100ABF008968000"
```

派生 profile 会写入 `build\profile\0100ABF008968000\game.tsv`，包含本版本自己的 build 行：

```
build  v0  1.0.0  main=8dafedbb5be81c2c0160161159a791e6  ...
```

#### Step 4 · Rewrite（代码改写）

`patch_nso.py` 对 4 个模块并行改写，只在 Apple 内核不允许的地方动指令。

```powershell
# 通常由 driver 自动执行；单独跑：
$env:DM_REWRITE_J = "4"
```

产物在 `patched_v0\`，每个模块有 `*.patched.bin` + `*.cuts.tsv` / `*.gates.tsv` / `*.fixups.tsv`。

期望输出（log 里）：

```
[dm] main:    gates 44  patch_off 0x2810000
[dm] subsdk0: gates 13  patch_off 0x730000
[dm] subsdk1: gates 2   patch_off 0x880000
[dm] sdk:     gates 108 patch_off 0xce0000
```

#### Step 5 · Shader split

从 RomFS 里挖出全部 BNSH 着色器。

```powershell
python "D:\nspb\engine\dm\gfx\tools\shader_split.py" `
  "D:\nspb\games\0100ABF008968000_build\extract\v0\RomFS.img" `
  "D:\nspb\games\0100ABF008968000_build\extract\v0\ExeFS\main" `
  "D:\nspb\games\0100ABF008968000_build\shader\pkg" `
  "…\tables\shader_map.tsv" "…\tables\shader_facts.tsv" "…\tables\shader_pairs.tsv" `
  "…\tables\pso_pairs.tsv"
```

期望：`shaders: 36805 (…)`

#### Step 6 · Metal 编译（最耗时）

```powershell
$sh      = "D:\nspb\games\0100ABF008968000_build\shader"
$xlate   = "D:\nspb\engine\dm\gfx\tools\dmsh_xlate_bin\dmsh_xlate"
$env:XLATE      = $xlate
$env:IOSOUT     = "$sh\ios"
$env:DMSH_TARGETS = "mac,ios"
$env:DM_ALLOW_OTHER_METAL = "1"

python "D:\nspb\engine\dm\gfx\tools\own_compilers.py" "$sh\pkg" "$sh\cache"
```

期望 log 结尾：

```
shaders 36805: ok 36805,
shader cache: hit 0, rebuilt 36805
shadow-input libraries (<key>_bv): 3951 generated, 0 failed
alpha test and logic operation libraries (<key>_bx): 20651 generated, 0 failed
pulling libraries (<key>_bp): 16084 generated, 0 failed
```

> ⏱ **耗时约 70 分钟**（36,805 个 × ~0.11 秒）。这一步是整流程的瓶颈。

#### Step 7 · ★ 打包 shader 库为单文件（关键优化）

**默认行为**：`dmsh_build.py` 产出 107,386 个散文件（`*_b.metallib` / `*_b.json` / 变体库）。

**问题**：散文件会让签名和安装慢到不可用（见 §6.5）。

**修复**：合成单个 `b-<chain>.img`。

```powershell
python "D:\nspb\pack_shader_lib.py" `
  "D:\nspb\games\0100ABF008968000_build\shader\ios\b-223f10d34f97"
```

期望输出：

```
107,386 files, 1.67 GB -> ...\b-223f10d34f97.img
  ... (进度)
done: ...\b-223f10d34f97.img  1,800,772,140 bytes (1.68 GB)
```

然后把原文件夹移走（保留备份）：

```powershell
Rename-Item "...\shader\ios\b-223f10d34f97" "...\shader\ios\_folder_backup"
```

> ⚠️ `build_app.py` 的 `shader_lib_has()` **同时接受** `b-<chain>/` 文件夹和 `b-<chain>.img` 镜像。宿主 `msl_image.h` 也是原地读镜像，不解包。

#### Step 8 · 打包 IPA

我写了一个入口脚本，把 shim 环境、profile 路径、所有 `DM_*` 变量一次性设好：

```python
#!/usr/bin/env python
# D:\nspb\pack_ipa.py
import os, subprocess, sys

INNER = r'D:\nspb\_internal'
REPO  = r'D:\nspb\engine'
WORK  = r'D:\nspb\games\0100ABF008968000_build'
OUT   = r'D:\nspb\games\PokMonSword.ipa'

sys.path.insert(0, INNER)
from nspb_qt.win import shim

env = shim.build_env(python_exe=sys.executable)
env.update(
    GAME='0100ABF008968000',
    W=os.path.join(WORK, 'ipa'),
    PATCHED=os.path.join(WORK, 'patched_v0'),
    ROMFS=os.path.join(WORK, 'extract', 'v0', 'RomFS.img'),
    MSL_IOS=os.path.join(WORK, 'shader', 'ios'),
    GFXAPI='nvn',
    FONT_PY=sys.executable,
    DM_DISPLAY_NAME='Pokemon Sword',
    DM_BUNDLE_ID='org.nxnative.0100abf008968000',
    DM_TEAM_ID='0000000000',
    DM_LANG='en-US',
    DM_SHOW_FPS='1',
    DM_PSO_GPUS='none',
    DM_APP_VERSION='1.0.0',
    DM_ICON=os.path.join(WORK, 'extract', 'v0', 'icon.jpg'),
    CONTROL=os.path.join(WORK, 'extract', 'v0', 'control.nacp'),
    DM_GAMES_DIR=os.path.join(WORK, 'profile'),
    DM_GAMES_FIRST='1',
    DM_GAME='0100ABF008968000',
    DM_ROOT=WORK,
    WORK=os.path.join(WORK, 'tmp'),
    NSPB_REPO=REPO,
)
os.makedirs(env['W'], exist_ok=True)
os.makedirs(env['WORK'], exist_ok=True)

cmd = [sys.executable, os.path.join(INNER, 'nspb_qt', 'win', 'build_app.py'), OUT]
raise SystemExit(subprocess.call(cmd, env=env, cwd=WORK))
```

执行：

```powershell
cd D:\nspb
python pack_ipa.py
```

期望输出：

```
[11:24:55] app: Pokemon Sword 1.0.0 (org.nxnative.0100abf008968000), language en-US
[11:24:55] generate Gen/ (profile header, embedded modules, tables)
[11:24:56] launcher: DM_OPMODE DM_PRESENT_UPSCALE ...
[11:24:56] standard font: C:\Windows\Fonts\msyh.ttc
[11:25:00] compile: 0 of 267 files (clang, arm64-apple-ios26.0), 267 up to date
[11:25:00] link: 267 objects, 22 frameworks (ld64.lld)
[11:25:04] sign: ad-hoc with Increased Memory Limit entitlement (606656 B)
[11:25:04] packing a slim IPA without the RomFS
[11:26:52] done: ...\PokMonSword.ipa (0.77 GiB)
```

> ⏱ **约 2 分钟**（因为只有 60 个条目）

---

## 5. 部署到 iPhone

### 5.1 签名安装

用 **iSigner** / Sideloadly / AltStore 等工具，以你自己的 Apple ID 重签。

```
拖入: C:\Users\Administrator\Desktop\PokMonSword.ipa  (0.768 GB)
```

**关键**：确认拖入的是 **60 条目**、**~786 MB** 的版本。
旧版是 1.68 GB / 107,446 条目，会因 `early eof` 安装失败。

### 5.2 推送 RomFS（必须）

slim IPA **不含游戏数据**。

源文件：`D:\nspb\games\0100ABF008968000_build\extract\v0\RomFS.img`（9.48 GB）

**方式 A · 文件 App（推荐，省空间）**

1. 用夸克 App 下载 `RomFS.img` 到手机
2. 打开 Pokemon Sword → 设置页 → **Game data** → **Choose game data…**
3. 选中该文件（会存 security-scoped bookmark，之后一直用）

**方式 B · 爱思助手 / iMazing**

连接电脑 → 应用 → Pokemon Sword → 文件 → 拖入 Documents 根目录

> ⚠️ 文件名大小写**不敏感**（代码用 `caseInsensitiveCompare`），`RomFS.img` / `romfs.img` 都认。

**方式 C · macOS 命令行**

```bash
xcrun devicectl device copy to --device <UDID> \
  --domain-type appDataContainer \
  --domain-identifier org.nxnative.0100abf008968000 \
  --source RomFS.img --destination Documents/romfs.img
```

### 5.3 语言设置

游戏原生支持简体中文（`control.nacp` 里有 `zh-Hans`）：

| 方式 | 操作 |
|---|---|
| 启动器 | Game → Game language → 简体中文 |
| 环境变量 | `Documents/env.txt` 写 `DM_LANG=zh-Hans` |

---

## 6. 踩坑记录（6 个真实 bug）

> 所有 bug 都是 **Windows 平台特有**，macOS 上不会出现。
> 每个都记录了现象、根因、修复和验证。

### 6.1 `romfs.py` — 路径分隔符

**文件**：`dm/tools/romfs.py` · `_resolve()`

**现象**：`RomFS.img` 里的任何路径都读不到，`romfs_marker` 校验必然失败。

```
FileNotFoundError: 'D:\...\RomFS.img\bin'   (注意：把镜像当目录了)
```

**根因**：

```python
# 原始代码
p = _os.path.abspath(_os.fsdecode(path))
parts = p.split('/')          # ← Windows 返回反斜杠
for i, part in enumerate(parts):
    if not part.endswith('.img'): continue
    image = '/'.join(parts[:i + 1])
```

Windows 的 `abspath()` 返回 `D:\path\to\RomFS.img\...`，用 `/` 拆只得到**一个**未拆分组件，永远找不到 `.img`。

**修复**：

```python
parts = p.split(_os.sep)              # 用平台分隔符
...
image = _os.sep.join(parts[:i + 1])
...
return loaded, '/'.join(parts[i + 1:])   # 镜像内部仍用 /
```

**验证**：

```python
src = rfs.source(d)
(src / 'bin').exists()               # True
(src / 'bin/sound/NX64/wwise/bank/Stream.pck').is_file()   # True
```

---

### 6.2 `romfs.py` — `os.pread` 不存在

**文件**：`dm/tools/romfs.py` · `_File.readinto()`

**现象**：

```
AttributeError: module 'os' has no attribute 'pread'. Did you mean: 'read'?
```

**根因**：`os.pread()` 是 POSIX 专有。Windows 没有。

**修复**：

```python
if hasattr(_os, 'pread'):
    _pread = _os.pread
else:
    def _pread(fd, size, offset):
        _os.lseek(fd, offset, _os.SEEK_SET)
        return _os.read(fd, size)
```

> 安全性说明：只有镜像文件的 fd 会走到这里，且每个 `_File` 独占自己的描述符，不存在 seek 竞态。

---

### 6.3 `romfs.py` — 文本模式导致提前 EOF

**文件**：`dm/tools/romfs.py` · `_File.__init__()`

**现象**：读 GFPAK 文件头，`struct.unpack_from` 报缓冲不足：

```
struct.error: unpack_from requires a buffer of at least 32 bytes
              ... (actual buffer size is 16)
```

**根因**：

```python
self.fd = _os.open(image.path, _os.O_RDONLY)   # ← Windows 默认文本模式
```

Windows 的 `os.open()` **默认文本模式**，遇到 `0x1A`（Ctrl+Z）就当 EOF 停止——恰好卡在 16 字节。并且 `\r\n` 会被折叠成 `\n`，破坏二进制。

**修复**：

```python
def _open_readonly(path):
    return _os.open(path, _os.O_RDONLY | getattr(_os, 'O_BINARY', 0))
```

**验证**：

```python
with rfs.open(gfpak_path, 'rb') as f:
    h = f.read(0x20)      # 32 字节，magic = b'GFLXPACK'
```

---

### 6.4 `game.py` — 冒号拆分路径（最危险）

**文件**：`dm/games/game.py` · `extra_dirs()`

**现象**：派生 profile 被静默忽略，`load()` 回落到**仓库里的 profile**。

```
game profile: 0100ABF008968000
v0 is not a version game profile 0100ABF008968000 registers (v458752 1.3.2)
→ derived game profile for v0: D:\nspb\engine\dm\games\0100ABF008968000   ← 写进仓库了！
```

**根因**：

```python
return [Path(p) for p in os.environ.get('DM_GAMES_DIR', '').split(':') if p]
```

POSIX 用 `:` 分隔多个路径。但 **Windows 盘符自带冒号**：

```
D:\nspb\games\0100ABF008968000_build\profile
→ split(':') → ['D', '\\nspb\\games\\...']    ← 路径被拦腰截断
```

**危险在哪**：如果不拦住，shader split 会把 base v0 的表**写进仓库那套为 1.3.2 调好的 41,516 条 shader 表**。

**修复**：

```python
def split_paths(value):
    return [p for p in value.split(os.pathsep) if p]   # os.pathsep: ':' POSIX, ';' Windows
```

**验证**：

```python
os.environ['DM_GAMES_DIR'] = r'D:\nspb\games\0100ABF008968000_build\profile'
gamemod.extra_dirs()   # [WindowsPath('D:/nspb/games/0100ABF008968000_build/profile')]
gamemod.load('0100ABF008968000').dir   # 正确指向 build\profile\...
```

**善后**：已核对仓库 `dm/games/0100ABF008968000/` 下 8 个文件的时间戳与大小，**全部未变，未被污染**。

---

### 6.5 `romfs.id` — CRLF 导致身份校验失败（真机卡死）

**文件**：`dm/tools/romfs_image.py` · `__main__`

**现象**：App 能装能开，但一进游戏就报：

```
[RED] boot: This app's game file identity (romfs.id) cannot be read; install the app again.
     Expected: 0100ABF008968000 1.0.0 (build v0, 10180968999 bytes, index 0000000000000000).
[RED] boot: Documents/RomFS.img is not the image this build needs (verdict 2); not used
```

`verdict 2` = `ROMFS_ID_BAD`。

**根因**：`romfs.id` 文件末尾是 **CRLF**，而 C 解析器只认 `\n`：

```python
# 生成端（romfs_image.py）
print(identity(*sys.argv[2:6]))    # Windows text mode → '\r\n'
```

```c
// 读取端（dm/host/romfs_identity.h）
const char *e = p; while (*e && *e != ' ' && *e != '\n') e++;   // 只在 ' ' 或 '\n' 停
...
unsigned long long x = strtoull(num, &end, hex ? 16 : 10);
if (!vn || *end || errno) return 0;                              // *end == '\r' → 失败
```

于是 `index` 的值里混进 `\r`：`"63ac99366071e214\r"`，`strtoull` 在 `\r` 处停下 → 解析失败。

**证据**：

```
修复前 98 字节: ...index=63ac99366071e214\r\n
修复后 97 字节: ...index=63ac99366071e214\n
```

**修复（两处）**：

```python
# ① romfs_image.py：绕过 text mode
try: sys.stdout.buffer.write(identity(*sys.argv[2:6]).encode() + b'\n')

# ② build_app.py：写入前再规范一次（双保险）
rid_file.write_bytes(
    r_id.stdout.replace(b'\r\n', b'\n').replace(b'\r', b'\n').rstrip(b'\n') + b'\n')
```

**验证**：

```powershell
python -c "import zipfile; print(repr(zipfile.ZipFile('...ipa').read('Payload/DmIOS.app/romfs.id')[-6:]))"
# b'1e214\n'   ← 纯 LF
```

---

### 6.6 `shader_lib.write` — 十万散文件拖垮签名与安装

**现象（三层）**：

1. **签名 39 分钟**（iSigner 解压 107,446 个条目）
2. **安装失败** `early eof`

```
"Failed to install app on device"
IdeviceError(Socket(Custom { kind: UnexpectedEof, error: "early eof" }))
vendor\isideload\src\sideload\install.rs:184
```

3. **`shader_lib.py pack` 只有 0.19 MB/s**（1.67 GB 要 2 小时）

**根因**：

- iOS 安装时逐个文件写入 App 容器，10 万次小文件写入让 USB/iOS 栈超时
- Windows Defender 实时扫描**每个新建文件**，`shader_lib.write()` 的逐文件循环被拖成 0.19 MB/s

**修复 A · 单文件化**

```powershell
python "D:\nspb\pack_shader_lib.py" "...\shader\ios\b-223f10d34f97"
```

我重写了打包器，保持 `shader_lib.write` 的**完全相同**格式（header + 16 字节对齐 + entry table + name pool），只改字节落盘方式：

```python
# 原始（逐文件 open/read/close，被 AV 拖死）
with romfs.open(source, 'rb') as f:
    while b := f.read(8 << 20): out.write(b); n += len(b)

# 改进（大缓冲 + 大块读）
with open(part, 'wb', buffering=1 << 26) as out:      # 64 MB 输出缓冲
    with open(source, 'rb', buffering=1 << 20) as f:   # 1 MB 输入缓冲
        while True:
            b = f.read(4 << 20)                        # 4 MB 一次
            if not b: break
            out.write(b); n += len(b)
```

**效果**：0.19 MB/s → **2.5 MB/s**（13 倍），10 分钟完成。

**修复 B · 加 Defender 白名单**

```powershell
Add-MpPreference -ExclusionPath "D:\nspb"
```

**最终效果**：

| | 散文件 | 单文件 .img |
|---|---|---|
| IPA 条目 | 107,446 | **60** |
| IPA 体积 | 1.68 GB | **0.768 GB** |
| 签名耗时 | 39 分钟 | **2 分钟** |
| 安装结果 | ❌ `early eof` | ✅ **成功** |

**为什么体积反而小了**：散装时每个 4–8 KB 小文件在 zip 里都有独立头开销（30–80 字节 × 10 万），合成一个大文件后这部分全消失，且大文件压缩率更高。

**真机验证**：宿主 `dm/gfx/nvn/msl_image.h` 原地读镜像，不解包——**已确认能正常渲染**。

---

## 7. 性能基准

| 阶段 | 首次 | 复用后 |
|---|---|---|
| nx_extract 构建 | 2 秒 | 2 秒 |
| 提取（9.53 GB NSP） | ~8 分钟 | 0 秒（reused） |
| rewrite（4 模块） | 50 秒 | 11 秒 |
| shader split（41,702 文件） | 4 分钟 | 0 秒 |
| **Metal 编译（36,805 shader）** | **70 分钟** | 0 秒（缓存） |
| shader_lib 打包 | 10 分钟 | 0 秒 |
| app 编译（267 文件） | 30 秒 | 5 秒 |
| IPA 打包 | 2 分钟 | 2 分钟 |
| **合计** | **~1 小时 35 分** | **~2 分钟** |

> 瓶颈明确是 **Metal 编译**。Windows 上每个 shader 起一个 `metal.exe` 进程（约 100 ms/次），
> 65 个并发也只能压到 ~500 shader/分钟。

---

## 8. 已知限制

| 项 | 状态 | 说明 |
|---|---|---|
| **App 图标** | ❌ 空白 | 缺 Pillow。`pip install pillow` 后重打即可 |
| **PSO pipeline archive** | 未内置 | `DM_PSO_GPUS=none`，device 首启自建 base（慢但能用） |
| **base v0 vs 1.3.2** | 派生 profile | 引擎注册的是 v458752，本次走派生路径（实测可跑） |
| **DLC** | 未包含 | 网盘有 `剑\DLC\1.nsp` / `2.nsp`（仅 150 KB，是授权占位不是内容） |
| **Metal 编译器版本** | 有差异 | Windows 版 `32023.850` vs 测试用 `32023.922`，靠 `DM_ALLOW_OTHER_METAL=1` 放行 |

---

## 9. 复用清单（打下一个游戏）

| 步骤 | 操作 |
|---|---|
| 1 | 确认工作根是**纯 ASCII 路径** |
| 2 | 查 `engine\dm\games\` 有没有该游戏的 profile（145 个） |
| 3 | 有 → 直接构；无 → 会先出 survey 再生成 provisional profile |
| 4 | `nx_extract` 提取 |
| 5 | rewrite |
| 6 | shader split |
| 7 | Metal 编译（**耗时瓶颈**） |
| 8 | **`pack_shader_lib.py` 打包成单文件** ← 必做 |
| 9 | `pack_ipa.py` 出 IPA |
| 10 | 签名安装 + 推送 RomFS |

### 引擎已支持的重量级游戏（145 个中的一部分）

```
塞尔达: 王国之泪 / 旷野之息 / 织梦岛 / 御天之剑HD / 智慧的再现
马力欧: 奥德赛 / 惊奇 / 3D世界+狂怒世界 / 赛车8豪华版 / RPG / 千年之门
宝可梦: 剑 / 盾 / 朱 / 紫 / 传说阿尔宙斯 / 晶灿钻石 / 传说Z-A / Pokopia
角色扮演: 异度神剑123 / 火焰纹章风花雪月·Engage / 女神异闻录5R·4G / 真女神转生5V
         勇者斗恶龙XI S·III·VII·I&II / 歧路旅人1·2 / 尼尔自动人形 / 十三机兵
动作:    猎天使魔女123 / 黑暗之魂重制 / 怪物猎人崛起 / 银河战士Dread·Prime
        空洞骑士·丝之歌 / 哈迪斯·哈迪斯II / 卡比与被遗忘之地 / 皮克敏4
独立:    星露谷 / 蔚蓝 / 死亡细胞 / 以撒的结合 / 吸血鬼幸存者类 / 巴拉特罗
```

---

## 10. 附录 · 产物清单

```
D:\nspb\games\
├── 剑.nsp                                   9.53 GB   源
├── PokMonSword.ipa                          0.768 GB  产物
└── 0100ABF008968000_build\
    ├── extract\v0\RomFS.img                 9.48 GB   游戏数据（需推送到设备）
    ├── extract\v0\ExeFS\                    31.9 MB   代码模块
    ├── patched_v0\                          ~70 MB    rewrite 产物
    ├── shader\pkg\                          ~400 MB   36,805 shader 原始数据
    ├── shader\cache\b-223f10d34f97\         1.81 GB   Mac 输出 + stamp
    ├── shader\ios\b-223f10d34f97.img        1.68 GB   ★ 单文件 shader 库
    ├── profile\0100ABF008968000\            派生 profile + 表
    └── logs\                                各阶段完整日志
```

### 关键哈希

```
IPA           SHA256  5F5723F66F8BEA4324317D13C7039A0692142FD85AE680983032CACCBFA2C6DC
RomFS.img     SHA256  36AAA3D87FA772ADCC2A35E91DD11362CB3A047554EE352A396656CECA708296
RomFS.img     size    10,180,968,999 bytes
shader .img   size    1,800,772,140 bytes
shader chain          223f10d34f97
profile inputs        29a0644abb76
```

### 模块 build ID（base v0）

```
main    8dafedbb5be81c2c0160161159a791e6
sdk     fcf93a41b08c5193a1410d262602dc62
subsdk0 93ff8252d975adf07230cb86c83301c5
subsdk1 a36dac0e0a5ed3b41482b6bb85625c73
rtld    39e10c07096696c9c4e228496c4bc44d
```

---

## 11. 参考

- [NxNative 上游仓库](https://github.com/seedds/nxnative)
- `engine/AGENTS.md` — 引擎架构与开发约定
- `engine/docs/agents/symptoms.md` — 症状索引
- `engine/docs/reference/rewriter.md` — 代码改写规则
- `engine/docs/reference/shaders.md` — 着色器链

---

*本文档由实际构建过程整理，所有 bug 修复均在 `D:\nspb` 工作副本中验证通过。*
