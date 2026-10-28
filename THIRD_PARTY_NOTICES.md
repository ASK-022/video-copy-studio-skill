# 第三方组件

Agent Skill ZIP 包含文案工坊的 Agent 接口、客户端与安装脚本，不含模型和 FFmpeg。完整离线客户端另含经验证的公开依赖、模型及原版 FFmpeg 发行文件，保留各原始许可证和模型卡；不包含 Codex 专属运行时、第三方视频解析 Skill、用户资料或共享凭据。

- 本版在 `assets/bootstrap/video-transcriber-pinned.zip` 中提供未改动的上游源码快照；原始获取地址为 [Acclerate/video-transcriber](https://github.com/Acclerate/video-transcriber) 下载固定提交 `bfce75fb1d9cf3e8444d531a4f96ec49faa467cf`，下载包有 SHA256 校验。上游 README 声明为 MIT；运行时安装保留上游文件与声明，修复 `asyncio.Lock` 用法，并加入仅在本应用进程内生效的 SentencePiece 中文路径兼容钩子，不修改系统库。
- FunASR / SenseVoice、ModelScope、PyTorch、RapidOCR、PySceneDetect、RapidFuzz、yt-dlp、Playwright、openpyxl、pypdfium2 / PDFium、packaging 通过各自官方软件包分发渠道安装，遵守各自许可证。
- FFmpeg 可使用自行安装的版本；可选下载源为 `gyan.dev` 的 Windows 构建。FFmpeg 及其构建选项对应的许可证不因本包改变。
- 没有合适 Python 时优先安装包内 `assets/bootstrap/python-3.12.10.nupkg` 中的 Python 官方应用本地发行包（3.12.10，SHA256 固定），不修改系统 PATH；保留原包中的许可证，并随包附上 `assets/bootstrap/LICENSE-PYTHON.txt`。自动下载的 FFmpeg 使用 Gyan 官方 GitHub 镜像与校验一致的构建。Playwright Chromium 通过 Playwright 下载机制安装，使用 cnpm 公开的 npmmirror 镜像并在失败时回退官方源，浏览器与模型不进入发布 ZIP。Python 依赖可从清华、华为镜像或官方 PyPI 获取，原包许可证继续适用。
- DeepSeek、TikHub、Cue、飞书为可选外部服务，需要每位使用者单独配置账号、权限与密钥；未包含任何共享凭据。

完整离线客户端的模型来源为魔搭公开仓库 `iic/SenseVoiceSmall`、`damo/punc_ct-transformer_zh-cn-common-vocab272727-pytorch` 和 `iic/speech_timestamp_prediction-v1-16k-offline`，模型卡声明 Apache License 2.0，原模型卡随对应资源目录提供。Python 和各依赖的许可证在 `Runtime/python` 及各 `.dist-info` 下；Chromium 原始发行文件保存在 `Browsers`；Gyan FFmpeg 9.0.2 的原始许可证、说明和文档保存在 `FFmpeg`。Gyan 构建声明 GPLv3，构建与对应源码信息见 https://www.gyan.dev/ffmpeg/builds/ 。各第三方组件的许可证分别适用。

蓝奏云分发变体只对已校验原始资源分块包装，不修改应用和模型内容，原始许可证仍随完整客户端保留。另附未经修改的 Microsoft Visual C++ x64 Redistributable，来自 https://aka.ms/vc14/vc_redist.x64.exe，已核验 Microsoft Corporation 数字签名；保留微软安装器内许可条款，使用者自行按微软界面准备系统运行库。
