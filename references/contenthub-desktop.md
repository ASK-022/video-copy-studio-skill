# 内容中台完整桌面版 1.3.0：安装与更新

内容中台包含编导台与剪辑台，适用于 Windows 10／11 x64。[正式版下载页](https://github.com/ASK-022/video-copy-studio-skill/releases/tag/contenthub-v1.3.0) 使用 `ContentHub-` 文件名，与独立 VideoCopyStudio 文案客户端及 Agent Skill 分别安装和更新。

## 首次安装或已有资源

下载 `ContentHub-Setup-v1.3.0-x64.exe`，运行后选择程序安装目录。已有通过自检的完整 r1 资源根目录时，选择“选择已有资源”；不要只选 Models 子目录。程序、模型资源、个人资料分别保存，已有模型不随普通程序更新重复下载。

没有资源时可在线“下载并准备资源”；首次准备数 GB，需等模型加载和转写自检完成。本轮未重测新电脑从公网首次下载全部资源，不把部分下载当作安装完成。也可按下节准备完整离线安装。

## 完整离线安装

本轮 1.3.0 未提供新的离线准备向导，继续使用下列 1.2.3 离线安装资源准备 r1。准备完成后，可运行 `ContentHub-Setup-v1.3.0-x64.exe`，选择已有 r1 资源升级程序；不要把旧向导或资源文件改名为 1.3.0。

旧版离线准备文件保持原名放在同一个文件夹中：

1. [本版下载页](https://github.com/ASK-022/video-copy-studio-skill/releases/tag/contenthub-v1.2.3) 的 `ContentHub-Setup-v1.2.3-x64.exe`、`ContentHub-Offline-Install-v1.2.3.exe`、`VC_redist.x64.exe`、`contenthub-resources-r1.json` 与对应 SHA256 清单。
2. [原 r1 发布页](https://github.com/ASK-022/video-copy-studio-skill/releases/tag/contenthub-v1.1.1) 的全部 25 个资源 ZIP。它们继续沿用原始字节与下载地址：

- [`ContentHub-Resources-r1-01.zip`](https://github.com/ASK-022/video-copy-studio-skill/releases/download/contenthub-v1.1.1/ContentHub-Resources-r1-01.zip)
- [`ContentHub-Resources-r1-02.zip`](https://github.com/ASK-022/video-copy-studio-skill/releases/download/contenthub-v1.1.1/ContentHub-Resources-r1-02.zip)
- [`ContentHub-Resources-r1-03.zip`](https://github.com/ASK-022/video-copy-studio-skill/releases/download/contenthub-v1.1.1/ContentHub-Resources-r1-03.zip)
- [`ContentHub-Resources-r1-04.zip`](https://github.com/ASK-022/video-copy-studio-skill/releases/download/contenthub-v1.1.1/ContentHub-Resources-r1-04.zip)
- [`ContentHub-Resources-r1-05.zip`](https://github.com/ASK-022/video-copy-studio-skill/releases/download/contenthub-v1.1.1/ContentHub-Resources-r1-05.zip)
- [`ContentHub-Resources-r1-06.zip`](https://github.com/ASK-022/video-copy-studio-skill/releases/download/contenthub-v1.1.1/ContentHub-Resources-r1-06.zip)
- [`ContentHub-Resources-r1-07.zip`](https://github.com/ASK-022/video-copy-studio-skill/releases/download/contenthub-v1.1.1/ContentHub-Resources-r1-07.zip)
- [`ContentHub-Resources-r1-08.zip`](https://github.com/ASK-022/video-copy-studio-skill/releases/download/contenthub-v1.1.1/ContentHub-Resources-r1-08.zip)
- [`ContentHub-Resources-r1-09.zip`](https://github.com/ASK-022/video-copy-studio-skill/releases/download/contenthub-v1.1.1/ContentHub-Resources-r1-09.zip)
- [`ContentHub-Resources-r1-10.zip`](https://github.com/ASK-022/video-copy-studio-skill/releases/download/contenthub-v1.1.1/ContentHub-Resources-r1-10.zip)
- [`ContentHub-Resources-r1-11.zip`](https://github.com/ASK-022/video-copy-studio-skill/releases/download/contenthub-v1.1.1/ContentHub-Resources-r1-11.zip)
- [`ContentHub-Resources-r1-12.zip`](https://github.com/ASK-022/video-copy-studio-skill/releases/download/contenthub-v1.1.1/ContentHub-Resources-r1-12.zip)
- [`ContentHub-Resources-r1-13.zip`](https://github.com/ASK-022/video-copy-studio-skill/releases/download/contenthub-v1.1.1/ContentHub-Resources-r1-13.zip)
- [`ContentHub-Resources-r1-14.zip`](https://github.com/ASK-022/video-copy-studio-skill/releases/download/contenthub-v1.1.1/ContentHub-Resources-r1-14.zip)
- [`ContentHub-Resources-r1-15.zip`](https://github.com/ASK-022/video-copy-studio-skill/releases/download/contenthub-v1.1.1/ContentHub-Resources-r1-15.zip)
- [`ContentHub-Resources-r1-16.zip`](https://github.com/ASK-022/video-copy-studio-skill/releases/download/contenthub-v1.1.1/ContentHub-Resources-r1-16.zip)
- [`ContentHub-Resources-r1-17.zip`](https://github.com/ASK-022/video-copy-studio-skill/releases/download/contenthub-v1.1.1/ContentHub-Resources-r1-17.zip)
- [`ContentHub-Resources-r1-18.zip`](https://github.com/ASK-022/video-copy-studio-skill/releases/download/contenthub-v1.1.1/ContentHub-Resources-r1-18.zip)
- [`ContentHub-Resources-r1-19.zip`](https://github.com/ASK-022/video-copy-studio-skill/releases/download/contenthub-v1.1.1/ContentHub-Resources-r1-19.zip)
- [`ContentHub-Resources-r1-20.zip`](https://github.com/ASK-022/video-copy-studio-skill/releases/download/contenthub-v1.1.1/ContentHub-Resources-r1-20.zip)
- [`ContentHub-Resources-r1-21.zip`](https://github.com/ASK-022/video-copy-studio-skill/releases/download/contenthub-v1.1.1/ContentHub-Resources-r1-21.zip)
- [`ContentHub-Resources-r1-22.zip`](https://github.com/ASK-022/video-copy-studio-skill/releases/download/contenthub-v1.1.1/ContentHub-Resources-r1-22.zip)
- [`ContentHub-Resources-r1-23.zip`](https://github.com/ASK-022/video-copy-studio-skill/releases/download/contenthub-v1.1.1/ContentHub-Resources-r1-23.zip)
- [`ContentHub-Resources-r1-24.zip`](https://github.com/ASK-022/video-copy-studio-skill/releases/download/contenthub-v1.1.1/ContentHub-Resources-r1-24.zip)
- [`ContentHub-Resources-r1-25.zip`](https://github.com/ASK-022/video-copy-studio-skill/releases/download/contenthub-v1.1.1/ContentHub-Resources-r1-25.zip)

按 `contenthub-resources-r1.json` 或仓库 [r1 固定清单](../releases/contenthub/resources/r1.json)核对大小和 SHA256，然后双击 `ContentHub-Offline-Install-v1.2.3.exe`。助手校验并准备独立资源，再打开完整 EXE 的标准安装向导；程序和资源可分别选择位置。不要逐个手工解压 ZIP，不要改名，无需旧式的 6 个程序分包。微软运行库使用其原版安装界面。

## 已有客户端更新与失败恢复

v1.1.0、v1.1.1、v1.2.0、v1.2.1 或 v1.2.3 完整桌面版可从“检查更新”下载签名更新，先保存未提交内容并等待转写、生成与导出任务完成，再点“更新并重启”。1.3.0 当前签名清单选择完整程序包，115 个分片由更新器校验与重组，无需手工安装；已有 r1 模型资源直接复用。

更新使用独立程序版本目录，保留旧程序、资料、加密 Key、项目和模型。新程序须通过工作台启动检查；启动失败恢复旧版。资源契约不兼容时使用完整安装器。Windows 用户加密的 Key 不能直接当作跨用户凭据。

## 功能与自己的服务配置

本版新增 AI 口播粗剪与逐句审片，按真实时间戳选镜并保护原声。剪映草稿默认保留原素材和可编辑时间线，普通导出不再依赖浏览器；需要烘焙效果时主动选择效果渲染。智能体和命令入口统一使用 AskFilm，补充 PATH 缺失时的本地入口。此前时间线选段换产品、智能混剪、可编辑画布、剪辑快捷键、原文件口播预览，以及编导、拆解、案例库和团队配置包入口继续保留。生成与云服务仍需要自己的授权和额度；采用素材或外部生成仍按客户端的确认流程执行。

团队 API 包通过“设置 → 服务商”预览后导入，按当前 Windows 用户加密；云转写配置与文字 AI 服务分别处理。公开软件不附带私人配置包、发布者身份或 OAuth 会话。飞书仍需每位用户自己的官方应用配置、登录授权及目标资源权限。

## 本轮验证范围

本轮同源开发回归、候选双工作台启动、合成音频实际本地转写和已有模型复用已完成。剪映导出回归包括原素材可编辑导出、62507 帧零渲染、变速与原声、显式效果渲染，以及崩溃恢复与取消。

公开 141 项附件的大小和原生 SHA256 已与本机软件文件及校验清单逐件核对，137 个分片与不可变 tag 中的 Git 文件一致。当前完整程序包使用 115 个分片；新的 full-only 签名清单与 tag 中保留的历史清单分别验签，完整程序包的实际字节未改变。

本轮没有新增付费生成、真实音频云转写或飞书云写入验收。公开软件与私人 API 配置包分别交付，个人配置、项目和模型不进入公开软件附件。

本轮仅使用 GitHub，蓝奏云后补。完整桌面版采用独立 `contenthub-v1.3.0` 通道，独立文案客户端和 Agent Skill 的 latest 不变。
