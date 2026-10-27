# 第三方组件

本包包含文案工坊的 Agent 接口、客户端与安装脚本；不打包第三方模型权重、FFmpeg 二进制、Codex 依赖运行时或第三方视频解析 Skill。

- 本地转写运行时从 [Acclerate/video-transcriber](https://github.com/Acclerate/video-transcriber) 下载固定提交 `bfce75fb1d9cf3e8444d531a4f96ec49faa467cf`，下载包有 SHA256 校验。上游 README 声明为 MIT；运行时安装保留上游文件与声明，修复 `asyncio.Lock` 用法，并加入仅在本应用进程内生效的 SentencePiece 中文路径兼容钩子，不修改系统库。
- FunASR / SenseVoice、ModelScope、PyTorch、RapidOCR、PySceneDetect、RapidFuzz、yt-dlp、Playwright、openpyxl 通过各自官方软件包分发渠道安装，遵守各自许可证。
- FFmpeg 可使用自行安装的版本；可选下载源为 `gyan.dev` 的 Windows 构建。FFmpeg 及其构建选项对应的许可证不因本包改变。
- 没有合适 Python 时下载 Python 官方 NuGet 的应用本地发行包（3.12.10，SHA256 固定），不修改系统 PATH；保留原包中的许可证。自动下载的 FFmpeg 使用 Gyan 官方 GitHub 镜像与校验一致的构建。Playwright Chromium 通过 Playwright 官方下载机制安装。
- DeepSeek、TikHub、Cue、飞书为可选外部服务，需要每位使用者单独配置账号、权限与密钥；未包含任何共享凭据。
