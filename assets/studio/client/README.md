# 文案工坊

本地工作区新增：成稿自动落盘与版本恢复、逐段对照编辑、可复用商品库、逐条方向预览和单条重写。手工编辑保存到每个任务的 `manuscripts/`，生成原稿始终保留；商品卡片保存在本机 `products.json`，待确认资料不用于生成。新功能先供本机体验，GitHub 正式发布包仍按 Release 版本更新。

商品资料可从图片或自己的商品文案提取。图片支持选择、拖入和粘贴，先本机 OCR 再由所选文字服务整理，不发送原图；文案直接使用文字服务。核对后填回对应模式，待核对项不自动加入卖点。提取任务与原视频处理相互独立，重启前也会检查是否仍有提取任务。

本机 MVP：本地文件/公开链接 → SenseVoice → DeepSeek 局部纠错 → 真实原文结构 → 同商品/换商品逐段生成。

从工作区双击 `启动文案工坊.cmd`。默认端口 8777，默认只绑定 127.0.0.1。独立 Chrome/Edge 应用窗口，未打包 EXE。

## 运行与依赖

复用 `tools/video-transcriber/.venv` 和已下载的 SenseVoice 模型。上游仓库：https://github.com/Acclerate/video-transcriber ，本次基础提交 `bfce75fb1d9cf3e8444d531a4f96ec49faa467cf`。上游本机异步锁修复见 `outputs/video-transcriber-local.patch`。本客户端通过子进程调用原工具 CLI。

FFmpeg 当前位于 `E:/openfilm/resources/runtime/ffmpeg/ffmpeg.exe`，可通过环境变量 `FFMPEG_PATH` 覆盖。上游 `.env` 记录 ASCII 模型缓存目录。新增依赖见 `requirements.txt`；当前 Python 环境中已安装。

```powershell
& tools/video-transcriber/.venv/Scripts/python.exe -m client.app
```

链接解析优先调用已安装的 video-parse-transcribe 解析模式；抖音失败后用临时 Chrome 会话读取公开视频/音轨，其余平台用 yt-dlp。浏览器在独立子进程中运行，避免 Windows 服务事件循环影响浏览器驱动。平台限制会显式报错，不自动走付费云转写。

## 数据与 AI

`.studio/` 被 Git 忽略。音视频、转写、生成批次和原始结构快照均保存在本机。Key 使用 Windows 当前用户 DPAPI 加密，不通过 API 返回；修改接口地址时必须重新填写对应 Key。设置测试只向该服务发送 OK 测试消息，任务只发送文字与商品资料。

多服务商配置保存在 `.studio/providers.json`，原 `.studio/ai.json` 自动迁移为第一条配置，且保留为当前选用服务的兼容镜像。TikHub独立配置保持不变。每个文字服务商分别保存名称、地址、模型、加密Key和可选JSON模式，可分别测试并切换；只支持已实现的Chat Completions兼容文字协议。运行中的任务持有所选客户端快照，切换不会更改该任务后续分批请求的目标。

纠错返回互不重叠且能唯一定位的替换项；结构必须逐字覆盖原文且保留顺序。纠错/重拆结构完成后自动提取商品资料，每项附输入中的原文引用，效果保证、时长、促销等分入待确认列表。自动填入同商品资料框，不覆盖已手动编辑内容，换商品模式使用独立草稿。

生成使用已保存结构并强制验证段数、id、role、顺序，手工编辑文案后要求重拆结构。条数接受无业务上限的正整数，每轮最多请求2条，逐轮保存和更新进度。停止请求在当前API调用返回后生效，失败或停止保留已完成结果。生成批次保留参考结构快照。校验仅覆盖结构与基本格式，不保证生成事实准确。

API 使用当前会话 HttpOnly Cookie、同源写请求标记和 Host/Origin 校验。无远程访问和账户系统。任务串行转写，AI 任务最多并行两个，同一任务禁止重复操作。重启会把未完成任务标记为中断。

## 验证

```powershell
& tools/video-transcriber/.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Windows DPAPI 测试需正常用户权限；受限沙盒无法访问用户密钥目录。测试使用临时目录与虚拟 Key、模拟 HTTP 响应，不消耗 AI 额度。真实媒体和真实 AI 证据分别在 `outputs/copy-studio-media-trial.json`、`outputs/copy-studio-ai-trial.json`。

尚未包含自动素材匹配、成片剪辑和 MP4 导出。已支持参考视频/音频预览、本机 OCR、检测标记及团队 Skill 在线安装。平台链接可用性受公开访问条件影响，不保证所有内容可解析。
