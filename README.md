# 文案工坊 · Agent Skill

本地视频/音频或公开链接 → SenseVoice 转写 → AI 纠错与结构分析 → 同商品裂变/换商品套结构 → 文案汇总、Excel 拍摄表、可选飞书电子表格。

完整本地运行时支持 **Windows 10/11 64 位（x64）**。首次在线安装会自动准备 Python、依赖和模型；发布 ZIP 不包含大模型，不是离线安装包。Agent 需要执行本机命令的能力；纯聊天或远程云 Agent 无法直接访问用户桌面文件。

## 一条命令安装

让同事的 Agent 在 **Windows PowerShell** 执行这一行即可，不需要预装 Git、Python 或模型：

```powershell
irm https://raw.githubusercontent.com/ASK-022/video-copy-studio-skill/main/install.ps1 | iex
```

安装器自动获取最新正式 Release、核验 SHA256，安装到本机已经存在的 Codex / Claude Code / OpenClaw 目录；同时装有多个 Agent 时会分别安装。没有检测到这些 Agent 目录时默认安装到 Codex。已有同名版本会先保留目录外备份再更新。

随后自动完成：

1. 优先使用已有的 64 位 Python 3.10–3.12；找不到时从官方 Python NuGet 下载独立 Python，核验 SHA256，不改系统 PATH。
2. 安装独立虚拟环境、CPU 版 PyTorch、转写/导出/检测依赖，准备 FFmpeg / FFprobe 和公开播放页使用的独立 Chromium。
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

安装器参数：`-Agent auto/codex/claude/openclaw/custom`；自定义目录配合 `-SkillsDir`；`-SkillOnly` 只装技能、不下载运行时；`-NoOpen` 不打开浏览器；`-Python` 指定已有 Python；`-RuntimeHome` 指定独立运行时目录。升级不复制、清除或共享个人 Key 和素材。

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
- 其他 Agent：要求调用 `video-copy-studio` Skill，提供本地文件/公开链接与具体交付物。

详细的使用条件与触发条件见 [SKILL.md](SKILL.md)，输入输出字段见 [references/parameters.md](references/parameters.md)，请求约定见 [references/input.schema.json](references/input.schema.json)。

文件最大 500 MB、最长 30 分钟。链接解析失败不等于音频转写失败，可改用下载后的本地文件。图片中的商品功效与识别猜测仍需确认；静音、重复和场景检测只做标记，不自动删减。尚未提供素材匹配、自动剪辑或 MP4 成片导出。

## 更新与维护

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
