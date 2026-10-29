## 内容中台完整桌面版 v1.1.0（编导台＋剪辑台）

[下载完整桌面安装包](https://github.com/ASK-022/video-copy-studio-skill/releases/tag/contenthub-v1.1.0) · [安装、资源准备与更新说明](references/contenthub-desktop.md)

[蓝奏云完整桌面版下载](https://wwbny.lanzoue.com/b0067df0cf)，提取码 `6s7g`。下载全部 6 个 ZIP 分包和安装助手，无需手动解压；助手校验后打开自选目录安装向导。

标准 EXE 安装向导可自选目录。顶部“检查更新”下载签名程序增量后，点击“更新并重启”；新版必须通过双工作台启动检查，失败自动恢复旧版和资料元数据。资料、加密 Key、项目与模型独立保存，已有模型直接复用。首次资源下载已在 Windows 全新目录中以无代理、无 pip 缓存方式验收，并完成实际转写。

这是完整桌面应用，和下方 VideoCopyStudio 文案客户端使用独立版本号与更新清单。首次从旧完整桌面测试包 v1.0.0 升级，请使用本完整安装器。

## v1.2.0 客户端更新与回滚

[蓝奏云 v1.2.0 升级与在线安装器](https://wwbny.lanzoue.com/b0067dem1a)，提取码 `1d0o`。

已有完整离线版 v1.1.3：下载本次 `VideoCopyStudio-Upgrade-v1.2.0.exe`，先关闭客户端，选择含 `VideoCopyStudio.exe` 的原安装目录，再点「升级并打开」。无需重新下载资源分包。此升级器自带程序增量，执行升级本身无需联网。

升级后进入「设置 → 检查更新 → 一键更新并重启」。客户端先验证发布签名，下载约 10MB 的程序增量并核验 SHA256，再关闭自身、保留旧程序、切换新版并验证服务启动；失败恢复旧版，意外中断则下次启动时恢复。转写、AI、商品资料提取或资料保存仍在进行时拒绝更新。页面尚未提交的编辑请先保存。

更新只替换 `App`、启动 EXE 和程序版本描述，复用 `Runtime`、`Models`、`Engine`、`Browsers`、`FFmpeg`。个人资料和加密 Key 保留在 `%LOCALAPPDATA%\VideoCopyStudioOffline`。不迁移数据格式；以后依赖变化不满足资源契约时必须使用新完整包，不能强行套用增量。自定义资料目录可通过升级器 `--data-dir` 指定。旧程序备份保留在安装目录 `.updates` 下，日志在资料目录 `updates/updater.log`。

版本清单镜像为 [Fastly CDN](https://fastly.jsdelivr.net/gh/ASK-022/video-copy-studio-skill@main/releases/latest.json) 和 [备用 CDN](https://gcore.jsdelivr.net/gh/ASK-022/video-copy-studio-skill@main/releases/latest.json)，并回退 GitHub；取签名有效的最高版本。两条线路在本次无代理请求中验证可用，均为 CDN 备用线路，不保证所有运营商实时可达。清单与增量包固定来自本仓库，镜像内容必须通过内置发布公钥校验。发布私钥不进入仓库或客户端。

新电脑仍先用下方 v1.1.3 完整离线资源包安装，再运行 v1.2.0 升级器；26个资源分包保持原名。在线安装器另提供 v1.2.0，新装或更新时继续复用已准备的模型；客户端内自动切换功能目前适用于完整离线客户端。在线版通过安装管理器升级。

# 文案工坊 · Agent Skill

视频/音频或公开链接 → 本地转写；脚本文档或粘贴原文 → 本机读取。两种入口均可分析结构，生成同商品裂变/换商品文案，汇总为 TXT、Excel 或写入指定飞书电子表格。

**v1.1.3** 新增完整离线客户端及可校验分包，保留国内下载源自动回退、内置基础 Python 与转写源码，保留 Windows EXE 安装管理器和更新检查，沿用 v1.1.0 的功能：提供并列的「视频创作」和「脚本改写」分区，支持脚本文档多选/拖拽上传、商品资料提取、成稿版本、逐段对照、商品库、定向裂变与单条重写。完整 Agent 参数见 [references/parameters.md](references/parameters.md)。

## v1.1.0 的使用方式

- **脚本改写**：直接粘贴原文，或拖入 DOCX / PDF / TXT；支持多选、分次追加与逐个移除。每份最大 20 MB、正文 2 万字，PDF 最多 40 页。导入时各文件分别建立参考，删除已导入文件会将对应参考移入回收站。两个创作分区分别展示参考记录，并保留各自尚未提交的输入。
- **保留原文结构**：有空行分段时保留段数、原句与顺序（最多 40 段），没有分段时按营销功能分析。脚本原文单独保存，不默认做语音识别纠错。生成支持同商品或换商品两种方式、自由填写条数、按人群/场景/语气分配方向。
- **商品资料**：自己的图片先本机 OCR，DOCX / PDF / TXT 先本机读取正文，扫描 PDF 使用本机 OCR；只有提取的文字交给当前选择的 AI。可核对、编辑后填入对应商品资料框或保存商品库，价格、功效等待核对项不自动用于生成。
- **成稿编辑**：逐段对照参考与改写结果，自动保存成稿版本；可查看历史、恢复为新版本或只重写一条。重写使用该批次的商品快照；未保存成功或版本冲突会明确提示。
- **团队交付**：沿用脚本汇总、单条/全部折叠、TXT、Excel 脚本文案表/拍摄需求表及指定飞书电子表格写入。导出使用当前成稿。

AI 生成需要每位同事自己的兼容服务配置。模型返回的段落或商品事实不符合校验时，该轮会停止，已完成文案保留；只有实际完成的条数才算生成成功。扫描识别和复杂 PDF 排版需对照原文件核对。

完整本地运行时支持 **Windows 10/11 64 位（x64）**。首次在线安装会自动准备 Python、依赖和模型；Agent Skill ZIP 不包含大模型；完整离线客户端使用上方的独立资源分包。Agent 需要执行本机命令的能力；纯聊天或远程云 Agent 无法直接访问用户桌面文件。

## 完整离线客户端

[蓝奏云完整离线版](https://wwbny.lanzoue.com/b0067dcq7i) · 提取码：`91e6`

[蓝奏云在线安装器](https://wwbny.lanzoue.com/b0067dcope) · 提取码：`5713`

完整离线版约 2.4 GB，解压后约 4.6 GB，建议预留 12 GB。请下载目录内全部 **26 个 `data*.zip` 分包**和 `VideoCopyStudio-Lanzou-Offline-Setup-v1.1.3.exe`，保持原名放在同一文件夹。清单已内置，双击安装器后自动校验、合并和解压，不必逐个手工解压。以后双击解压目录的 `VideoCopyStudio.exe` 打开客户端。

新电脑可先运行同目录的 `VC_redist.x64.exe`，按微软界面准备 C++ x64 运行库；已有更新版本可关闭该安装器。该文件来自[微软官方来源](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)，已核验有效的 Microsoft Corporation 数字签名，可能要求管理员权限或重启。同目录提供 SHA256 校验表。

独立 Python、CPU 推理依赖、Chromium、FFmpeg 和转写/标点/时间对齐/OCR 模型均已随包提供。安装和本地视频/音频转写无需联网；AI 改写、公开链接解析、飞书和检查更新仍需联网及自己的服务配置。个人资料与 Key 位于 `%LOCALAPPDATA%\VideoCopyStudioOffline`，与程序资源分开。

蓝奏版按本次账号的小于 100 MB 上限分包，接收者输入提取码即可看到下载文件。[GitHub 程序与源码备用入口](https://github.com/ASK-022/video-copy-studio-skill/releases)提供安装器、校验和分发工具源码；完整离线资源统一从上方蓝奏链接获取。维护者原始大 ZIP 可用于 U 盘或共享盘分发，与蓝奏小分包及专用安装器不可混用。

验证：46 项 Python 测试通过；蓝奏专用 EXE 界面与内置清单自检通过。实际从 26 个小 ZIP 安装到全新目录，并在禁止外网连接的测试进程中完成真实音频转写，记录到的外网连接尝试为 0；临时合并文件已自动清理。原始大包还验证过中文与空格目录搬移后的转写。

## 给同事的安装说明（可直接转发）

请在 Windows 10/11 64 位电脑上，从[蓝奏云在线版](https://wwbny.lanzoue.com/b0067dcope)（提取码 `5713`）下载 `VideoCopyStudio-Setup-v1.1.3.exe` 并双击，确认运行时目录后点击“安装 / 更新”；也可在 Windows PowerShell 执行下方的一条命令。无需预装 Git、Python 或模型，首次安装需保持联网并预留数 GB 空间，安装器会准备 Python、依赖、浏览器和转写模型，并做启动自检；必须等窗口显示“安装与自检完成”或终端显示安装成功，才算完整安装。完成后双击桌面 **Video Copy Studio** 打开本机页面，在右上角“设置”里填写自己的 AI 服务与 Key；本地转写不需要 AI Key。以后从桌面快捷方式打开，更新时先保存工作并等正在运行的任务完成，再打开“文案工坊安装管理器”点击“检查更新”，查看正式版说明后点击“安装 / 更新”；命令安装者可重跑同一命令，或下载 EXE 管理器；网页“设置”里也能检查版本并进入发布页。更新会保留个人资料、模型与 Key，旧服务不会被强制结束，更新后需正常关闭旧服务并重新打开；不便关闭时，可保存工作后重启电脑，再双击快捷方式。网络下载或自检失败时，安装会明确报错，可查看运行时目录的 `installer.log`（EXE）、`bootstrap.log`、`models.log` 或 `server.log`，修复后重跑；缺少浏览器时也可执行下方的 `studio.cmd repair-browser`。浏览器就绪不代表所有平台链接都能解析，遇到登录或平台访问限制，可改用本地视频文件。

## Windows EXE 安装与更新

[蓝奏云下载在线安装器](https://wwbny.lanzoue.com/b0067dcope)（提取码 `5713`） · [查看正式版与校验文件](https://github.com/ASK-022/video-copy-studio-skill/releases/latest)

EXE 内置本版应用源码安装包、图形界面、安装脚本、官方基础 Python 和固定提交的转写运行时源码；首次安装仍会联网下载模型及运行依赖。创作工作区继续在本机浏览器中使用，EXE 提供安装、启动、检查更新和日志入口。安装成功后会保留一份管理器到运行时目录，并创建“文案工坊安装管理器”桌面快捷方式。

管理器打开时自动做一次只读版本检查，也可手动点击“检查更新”；网页“设置”里的检查为手动触发。检查仅请求本仓库的公开 GitHub Release 信息，不发送素材、脚本或 Key；只接受正式版，按数字比较版本，不主动降级。发现新版后由用户点击安装，下载 ZIP 后核验 SHA256，并执行依赖、浏览器、模型及服务自检，不会在创作期间静默覆盖程序。管理器自身如有新版 EXE，可从发布页下载并使用；已打开的旧管理器不会被原地替换。网络断开或 GitHub 限流时可继续使用已安装的本机程序。

当前 EXE 未做代码签名，同页提供 `.exe.sha256`。可在 PowerShell 用 `Get-FileHash .\VideoCopyStudio-Setup-v1.1.3.exe -Algorithm SHA256` 对照校验；受单位软件策略限制时，请按单位要求安装。默认运行时位于 `%LOCALAPPDATA%\VideoCopyStudio`，与 GitHub 源码和个人 Agent 技能目录分开。

## 下载线路与无代理安装

v1.1.3 的在线安装按以下方式获取资源，设置仅对本次安装命令生效，不修改全局 pip 配置，不关闭 HTTPS 证书检查：

| 资源 | 首选 | 失败后的处理 |
|---|---|---|
| 基础 Python | 安装包内置的官方 Python 3.12.10 NuGet，校验固定 SHA256 | 缺少内置包的精简版才尝试官方 NuGet；校验失败直接停止 |
| 转写运行时源码 | 内置固定提交 ZIP，校验固定 SHA256 | 缺少内置包的精简版才连接 GitHub；校验失败直接停止 |
| Python 依赖 | 清华镜像 | 华为镜像 → PyPI 官方；每次只使用一个源 |
| Chromium | 已有浏览器缓存通过自检时复用；否则使用 npmmirror 镜像 | Playwright 官方下载服务；仍须实际启动自检 |
| FFmpeg / FFprobe | Gyan 构建下载站，核验固定 SHA256 | 同一构建的 Gyan GitHub Release |
| SenseVoice、标点和时间对齐模型 | 魔搭 ModelScope | 保留已下载缓存，网络修复后重试；不切换成未经验证的模型 |

Python 镜像地址参考[清华镜像使用说明](https://mirror.tuna.tsinghua.edu.cn/help/pypi/)；浏览器镜像使用 [cnpm 维护者公布的 Playwright 配置](https://github.com/cnpm/binary-mirror-config/blob/master/package.json)。如果设置过 `PLAYWRIGHT_DOWNLOAD_HOST`，浏览器会先尝试该自定义源，再使用默认回退线路。

EXE 仍属于在线安装器，不包含模型、PyTorch 或浏览器二进制。EXE 可从上方蓝奏云链接获取；在线安装器仍可通过 GitHub 获取正式版；完整离线客户端 v1.2.0 增加签名版本清单 CDN 镜像和程序增量更新。GitHub 不可达时，可手动从蓝奏目录获取新版安装器，已安装程序可继续在本机使用。不同单位网络、运营商和镜像同步状态可能不同，不能保证所有电脑都无需代理；所有源失败时明确保留错误和日志，不报告安装完成。

## 一条命令安装

让同事的 Agent 在 **Windows PowerShell** 执行这一行即可，不需要预装 Git、Python 或模型：

```powershell
irm https://raw.githubusercontent.com/ASK-022/video-copy-studio-skill/main/install.ps1 | iex
```

安装器自动获取最新正式 Release、核验 SHA256，安装到本机已经存在的 Codex / Claude Code / OpenClaw 目录；同时装有多个 Agent 时会分别安装。没有检测到这些 Agent 目录时默认安装到 Codex。已有同名版本会先保留目录外备份再更新。

随后自动完成：

1. 优先使用已有的 64 位 Python 3.10–3.12；找不到时从本版 ZIP 内置的官方 Python NuGet 包安装独立 Python，核验固定 SHA256，不改系统 PATH；旧的精简包缺少此资源时才尝试官方 NuGet。
2. 安装独立虚拟环境、CPU 版 PyTorch、转写/导出/检测依赖，准备 FFmpeg / FFprobe 和公开播放页使用的独立 Chromium。
   升级已有环境也会检查并补装本版新增依赖，包括 PDF 读取；`doctor` 中 `dependencies_ready=true` 表示依赖检查和 PDF 引擎自检通过。
3. **安装时下载并实际加载** SenseVoice Small、中文标点、中文时间对齐模型，并验证包内 OCR ONNX 模型；执行语音和 OCR 推理自检。首次转写无需再等待这些模型下载。
4. 创建桌面及开始菜单的 **Video Copy Studio** 快捷方式，启动 Web 服务，验证服务及模型就绪，自动打开浏览器。

已有运行时及模型会复用，保留个人资料；正在运行的客户端不会被强制重启。安装成功后重启 Agent 或新开会话，在客户端设置里填写**自己的** AI Key。没有 Key 也可以本地转写；AI 纠错和生成需要用户配置自己的服务。

首次安装会下载较大依赖与模型，请保持网络连接并预留数 GB 空间；终端显示完成才表示成功。网络失败、模型加载失败或端口被无关程序占用时，会明确报错并停止，可修复后重跑同一命令，不把部分安装报告为完成。

### 公开链接提示缺少 Playwright / Chromium

v1.0.4 起，新装和升级都使用**运行时登记的同一个 Python** 检查 Playwright，缺包时自动补装，再下载 Chromium 并实际启动、关闭一次。浏览器保存在运行时目录的 `browsers/`，启动服务时使用同一路径，不依赖其他 Python 环境或系统 Chrome。`doctor` 的 `browser_ready` 为实际启动自检结果。

先重跑上方一条命令升级。已升级且注册过运行时，仅需修复浏览器时，在 PowerShell 执行（自定义目录请替换路径）：

```powershell
& "$env:LOCALAPPDATA\VideoCopyStudio\studio.cmd" repair-browser
& "$env:LOCALAPPDATA\VideoCopyStudio\studio.cmd" doctor
```

修复命令会联网下载；出现 `browser_ready: true` 才表示浏览器可启动。下载超时或失败时，查看 `%LOCALAPPDATA%\VideoCopyStudio\bootstrap.log` 中的完整错误，确认网络可访问 Playwright 下载服务后重跑同一命令。首次安装失败、还没有 `studio.cmd` 时，直接重跑一条命令安装。

升级或修复前已运行的服务需要先正常关闭，再用桌面快捷方式重新打开，使新代码和浏览器路径生效。自检仅确认本机浏览器能运行；链接解析仍受平台页面、登录要求及访问限制影响。

## 打开 Web 客户端

- **第一次**：安装成功自动打开，默认地址是 [http://127.0.0.1:8777/](http://127.0.0.1:8777/)。
- **以后或重启电脑后**：双击桌面/开始菜单的 **Video Copy Studio**，它会启动本地服务并打开页面。
- **服务已经运行**：浏览器直接打开上述地址即可。没有设置开机自启动；重启电脑后先用快捷方式。
- 没有桌面快捷方式时，在 PowerShell 执行下面这一行（默认安装位置）；自定义 RuntimeHome 则换成对应目录：

```powershell
& "$env:LOCALAPPDATA\VideoCopyStudio\打开文案工坊.cmd"
```

只供本机访问，无需部署公网服务器。改了端口时，以安装器最终打印的 Web 地址为准。

Agent 无需依赖系统 PATH 中的 `python`，默认安装后的 CLI 入口为：

```powershell
& "$env:LOCALAPPDATA\VideoCopyStudio\studio.cmd" doctor
& "$env:LOCALAPPDATA\VideoCopyStudio\studio.cmd" start --open
```

明确只安装到某一种 Agent，可使用：

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/ASK-022/video-copy-studio-skill/main/install.ps1))) -Agent claude
```

下载线路默认国内镜像优先，失败后逐个回退；日志会显示正在使用的下载源。

安装器参数：`-Agent auto/codex/claude/openclaw/custom`；自定义目录配合 `-SkillsDir`；`-SkillOnly` 只装技能、不下载运行时；`-NoOpen` 不打开浏览器；`-Python` 指定已有 Python；`-RuntimeHome` 指定独立运行时目录；`-ReleaseTag v1.1.3` 指定正式版；`-PackagePath` 从带相邻 SHA256 文件的本地 ZIP 安装。`-Port` 指定全新运行时的端口；`-NoShortcuts` 用于独立验证时不创建个人快捷方式。升级不复制、清除或共享个人 Key 和素材。

## 手动安装到 Agent

下载正式 Release 的 `video-copy-studio-v版本.zip`，校验同页 `.sha256`，解压后进入 `video-copy-studio` 文件夹。安装说明与参数文档均在包内。

```powershell
# 三选一；仅复制 Skill，不上传文件或安装大模型
python scripts/install_skill.py --agent codex
python scripts/install_skill.py --agent claude
python scripts/install_skill.py --agent openclaw
# 其他支持 SKILL.md 的 Agent：指定其实际技能目录
python scripts/install_skill.py --agent custom --skills-dir "C:/YourAgent/skills"
```

同名目录已存在时安装器会停止；确认升级可加 `--update`，旧版保存在技能目录外的 `skill-backups/video-copy-studio/`，避免被 Agent 扫描成重复 Skill。安装完重启 Agent 或新开会话。

默认目录：Codex `~/.codex/skills/video-copy-studio`；Claude Code `~/.claude/skills/video-copy-studio`；OpenClaw `~/.openclaw/skills/video-copy-studio`。是否自动发现还取决于各 Agent 的配置。其他 Agent 可手动复制完整文件夹并按其文档注册。

## 首次准备运行时

进入**已安装的 Skill 目录**执行：

```powershell
python scripts/bootstrap.py
python scripts/bootstrap.py --install --download-ffmpeg
python scripts/studio_agent.py doctor
python scripts/studio_agent.py start --open
```

- 一条命令安装的用户不必再执行此节。手动部署需先准备 Python 3.10–3.12；`bootstrap` 不加参数只检查，`--install` 会下载固定版本上游、依赖、浏览器和模型。日志在运行时目录的 `bootstrap.log`、`models.log`。
- FFmpeg 已安装时可替换为 `--install --ffmpeg "C:/ffmpeg/bin/ffmpeg.exe"`；同目录须有 `ffprobe.exe`。
- 默认使用 CPU，不需要 GPU；SenseVoice、标点、时间对齐与 OCR 模型安装时验证，不在 ZIP 中。静音检测使用 FFmpeg，不需要额外 VAD 权重。
- 默认运行时目录是 `%LOCALAPPDATA%/VideoCopyStudio`；可设置 `VIDEO_COPY_STUDIO_HOME` 或每次传 `--runtime-home`。该目录保存依赖、模型、个人数据与加密 Key，更新 Skill 不会删除它。
- 如果端口 8777 已被其他程序占用，初始化时用 `--port 8787`，不要停掉无关程序。
- 用户原有转写环境可用 `--register-existing --asr-root PATH --python PATH --ffmpeg PATH` 注册；加 `--prepare-models` 验证/补齐模型。安装器升级已注册环境时自动补做这一步。不复制密钥。
- 注册已有客户端时，可用 `--data-dir PATH` 继续使用原有参考库；仅记录路径，不复制用户资料。后续升级保留注册的数据目录。

## 配置自己的服务

浏览器打开本地客户端右上角「设置」：添加自己的 DeepSeek 或 Chat Completions 兼容服务、模型与 Key，保存并测试。只做本地转写和检测可以不配置 AI。

TikHub / Cue / 视觉模型分别是可选服务，需各自的 Key，按服务商规则计费。飞书直写需要自己的企业自建应用、可编辑的 `/sheets/` 电子表格；在设置中填 App ID、App Secret 和目标表格链接，测试并选择工作表后保存。测试只读，实际写入需用户明确操作。

当前客户端保存 Key 使用 Windows 当前用户加密，不能把加密文件复制给另一个用户后当作共享账号。ZIP、GitHub 源码和更新包都不包含团队共享凭据。

## 给 Agent 的使用例子

- Codex：`使用 $video-copy-studio，把 C:/Videos/reference.mp4 转写并纠错，保留结构生成 7 条同商品文案，导出脚本文案表。`
- Claude Code：`/video-copy-studio 把这个视频转写并按原结构改写 3 条。`
- 脚本文档：`使用 video-copy-studio 导入 C:/Scripts/reference.docx，保留原结构生成 5 条同商品文案。`
- 商品资料：`从我提供的商品图片或文档提取商品名和卖点，供我核对后用于换商品套结构。`
- 其他 Agent：要求调用 `video-copy-studio` Skill，提供本地文件/公开链接与具体交付物。

详细的使用条件与触发条件见 [SKILL.md](SKILL.md)，输入输出字段见 [references/parameters.md](references/parameters.md)，请求约定见 [references/input.schema.json](references/input.schema.json)。

文件最大 500 MB、最长 30 分钟。链接解析失败不等于音频转写失败，可改用下载后的本地文件。图片中的商品功效与识别猜测仍需确认；静音、重复和场景检测只做标记，不自动删减。尚未提供素材匹配、自动剪辑或 MP4 成片导出。

## 更新与维护

下面的脚本用于单独检查或更新 Skill 文件，不负责准备运行依赖。团队日常完整升级请使用 EXE 管理器或重跑一条命令安装。

```powershell
# 检查正式 Release；不修改本地文件
python scripts/update_skill.py
# 用户确认升级后应用，保留旧版备份和独立运行时
python scripts/update_skill.py --apply
```

也可以下载新版 ZIP，执行 `install_skill.py --update`。不建议直接覆盖自己改动过的 Skill；备份目录可用于取回本地修改。

维护者修改 `VERSION` 后，运行 `python scripts/build_release.py --output dist`，把 ZIP 和 SHA256 文件发布到对应版本的 GitHub Release；团队更新器会读取最新正式 Release。可选自动发布模板见 `references/github-release-workflow.yml`，由仓库维护者启用。打包只收录白名单中的源码与文档，不包含个人数据目录、虚拟环境或模型。

## 第三方来源

见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。本包没有复制第三方模型和 Codex 的专属运行时；团队安装的 Excel 导出使用可安装的 openpyxl，不要求同事拥有这台电脑的 Node 路径。

## GitHub 下载

[源码仓库](https://github.com/ASK-022/video-copy-studio-skill) · [最新正式版本](https://github.com/ASK-022/video-copy-studio-skill/releases/latest)

### 维护者构建 Windows EXE

在 Windows x64 Python 环境安装 `pyinstaller>=6,<7`，运行 `python scripts/build_windows_exe.py --output dist`。脚本先生成白名单 ZIP，再打包 GUI、Python/Tk、安装脚本和本版 ZIP，输出 EXE 及 `.exe.sha256`。ZIP 不含 EXE，模型和个人数据均不进入发布包。Release 应同时上传 ZIP、EXE 和各自的 SHA256 文件。

### 维护者构建完整离线客户端

使用已通过安装与模型自检的 Windows x64 运行时：`python scripts/build_offline_client.py stage --source RUNTIME_HOME --work BUILD_DIR --output OUTPUT_DIR`。构建器仅收集公开应用源码、依赖和模型资源，排除个人资料、Key、任务和日志；使用独立基础 Python，不分发带绝对路径的虚拟环境。

发布给全新 Windows 电脑时，还需从微软官方来源获取原版 `VC_redist.x64.exe`，核验有效的 Microsoft Corporation 数字签名，为文件生成 SHA256，并与客户端分包放在同一下载目录。用户在需要时通过微软界面准备系统 C++ 运行库；`stage/package` 只生成应用资源，不安装或修改系统组件。

在禁止外网连接的测试进程中，验证首次启动、全部模型、本地音频转写以及搬移后的再次转写；将验收结果写入 `BUILD_DIR/offline-verified.json`，其中 `verified=true`、`external_attempts=0`、`client_sha256` 为客户端 EXE 的 SHA256。随后运行 `python scripts/build_offline_client.py package --work BUILD_DIR --output OUTPUT_DIR`，输出独立 ZIP 分包、清单、校验文件和离线安装器。分包均小于 GitHub 每附件 2 GiB 上限，安装器不需要联网或额外解压软件。

### 维护者构建蓝奏云小分包

先准备已验收的原始离线包，再运行 `python scripts/build_lanzou_package.py --input ORIGINAL_OFFLINE_DIR --output LANZOU_OUTPUT_DIR --work LANZOU_BUILD_DIR`。工具对原始 ZIP 做小于 100 MB 的标准 ZIP 包装，原始应用与模型内容不变；专用安装器内置清单，合并后再次核对原始 SHA256。发布前必须验证实际 EXE 的合并安装和禁止外网时的真实转写。
