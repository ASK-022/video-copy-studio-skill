# 文案工坊 · Agent Skill

本地视频/音频或公开链接 → SenseVoice 转写 → AI 纠错与结构分析 → 同商品裂变/换商品套结构 → 文案汇总、Excel 拍摄表、可选飞书电子表格。

这是可分发的 Skill 与客户端源码包，不是内含模型和所有依赖的离线 EXE。完整本地运行时当前支持 **Windows 10/11 + Python 3.10–3.12**。Agent 需要执行本机命令的能力；纯聊天或远程云 Agent 无法直接访问用户桌面文件。

## 安装到 Agent

下载正式 Release 的 `video-copy-studio-v版本.zip`，校验同页 `.sha256`，解压后进入 `video-copy-studio` 文件夹。安装说明与参数文档均在包内。

```powershell
# 三选一；仅复制 Skill，不上传文件或安装大模型
python scripts/install_skill.py --agent codex
python scripts/install_skill.py --agent claude
python scripts/install_skill.py --agent openclaw
# 其他支持 SKILL.md 的 Agent：指定其实际技能目录
python scripts/install_skill.py --agent custom --skills-dir "C:/YourAgent/skills"
```

同名目录已存在时安装器会停止；确认升级可加 `--update`，旧版会保留备份。安装完重启 Agent 或新开会话。

默认目录：Codex `~/.codex/skills/video-copy-studio`；Claude Code `~/.claude/skills/video-copy-studio`；OpenClaw `~/.openclaw/skills/video-copy-studio`。是否自动发现还取决于各 Agent 的配置。其他 Agent 可手动复制完整文件夹并按其文档注册。

## 首次准备运行时

进入**已安装的 Skill 目录**执行：

```powershell
python scripts/bootstrap.py
python scripts/bootstrap.py --install --download-ffmpeg
python scripts/studio_agent.py doctor
python scripts/studio_agent.py start --open
```

- `bootstrap` 不加参数只检查；`--install` 才联网下载固定版本上游转写源码与 Python 依赖。首次可能较久，进度/错误日志在运行时目录的 `bootstrap.log`。
- FFmpeg 已安装时可替换为 `--install --ffmpeg "C:/ffmpeg/bin/ffmpeg.exe"`；同目录须有 `ffprobe.exe`。
- 默认使用 CPU，不需要 GPU；SenseVoice/VAD/标点/时间对齐模型首次转写按需下载，不在 ZIP 中。
- 默认运行时目录是 `%LOCALAPPDATA%/VideoCopyStudio`；可设置 `VIDEO_COPY_STUDIO_HOME` 或每次传 `--runtime-home`。该目录保存依赖、模型、个人数据与加密 Key，更新 Skill 不会删除它。
- 如果端口 8777 已被其他程序占用，初始化时用 `--port 8787`，不要停掉无关程序。
- 用户原有转写环境可用 `--register-existing --asr-root PATH --python PATH --ffmpeg PATH` 注册；不复制模型或密钥。

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
