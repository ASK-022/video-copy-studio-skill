# 内容中台完整桌面版 1.3.1：安装与更新

内容中台包含编导台与剪辑台，适用于 Windows 10／11 x64。[正式版下载页](https://github.com/ASK-022/video-copy-studio-skill/releases/tag/contenthub-v1.3.1) 使用 `ContentHub-` 文件名，与独立 VideoCopyStudio 文案客户端及 Agent Skill 分别安装和更新。

## 首次安装或已有资源

下载 `ContentHub-Setup-v1.3.1-x64.exe`，运行后选择程序安装目录。已有通过自检的完整 r1 资源根目录时，选择“选择已有资源”；不要只选 Models 子目录。程序、模型资源、个人资料分别保存，已有模型不随普通程序更新重复下载。

没有资源时可在线“下载并准备资源”；首次准备数 GB，需等模型加载和转写自检完成。本轮未重测新电脑从公网首次下载全部资源，不把部分下载当作安装完成。也可按下节准备完整离线安装。

## 完整离线安装

将本版程序和离线准备文件、已有 r1 资源放在同一个文件夹中，保持原文件名：

1. [本版下载页](https://github.com/ASK-022/video-copy-studio-skill/releases/tag/contenthub-v1.3.1) 的 `ContentHub-Setup-v1.3.1-x64.exe`、`ContentHub-Offline-Install-v1.3.1.exe`、`VC_redist.x64.exe`、`contenthub-resources-r1.json`、`README-ContentHub-Offline.txt` 与 `SHA256SUMS-OFFLINE.txt`。
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

按 `contenthub-resources-r1.json` 或仓库 [r1 固定清单](../releases/contenthub/resources/r1.json)核对大小和 SHA256，然后双击 `ContentHub-Offline-Install-v1.3.1.exe`。助手校验并准备独立资源，再打开完整 EXE 的标准安装向导；程序和资源可分别选择位置。不要逐个手工解压 ZIP，不要改名，无需旧式的 6 个程序分包。微软运行库使用其原版安装界面。

## 已有客户端更新与失败恢复

已有完整桌面版先保存未提交内容并等待转写、生成与导出任务完成，再从“检查更新”下载签名更新并点“更新并重启”。1.3.1 签名更新使用完整程序包，分片由更新器自动校验与重组，无需手工安装；已有 r1 模型资源直接复用。

更新使用独立程序版本目录，保留旧程序、资料、加密 Key、项目和模型。新程序须通过工作台启动检查；启动失败恢复旧版。1.3.1 由对应程序版本的更新组件处理更新，避免调用安装根目录中遗留的旧组件。资源契约不兼容时使用完整安装器。Windows 用户加密的 Key 不能直接当作跨用户凭据。

历史失败回滚记录、用户主动回滚与本次启动失败分别显示，避免已经正常使用的版本仍反复提示“启动未通过，已恢复旧版”。只有实际启动失败才显示失败回滚结果。

## 旧文案工坊并存与编导服务重连

旧文案工坊与内容中台可以分别保留，不需要为了修复会话提示而卸载旧版、清空资料或删除模型。1.3.1 为不同本机端口隔离会话，避免另一实例覆盖当前会话。编导页面遇到明确的会话失效提示时，会重新握手并自动重试一次；其他权限或业务错误仍按原错误显示。

编导服务意外退出后，点击“编导台”会尝试重连，保留页面中尚未保存的文案、所选文件和设置。该恢复不等于恢复已经中断的转写或生成任务；操作系统重启或用户关闭整个客户端前，仍应保存工作。旧独立文案客户端使用自己的更新通道，不会因此自动升级为内容中台。

## 功能与自己的服务配置

本版读取手机视频旋转信息，按实际显示方向判断横竖屏；AI 混剪遇画幅方向不匹配时停止自动修改，需先在画布比例中明确选择目标方向。1.3.0 的 AI 口播粗剪与逐句审片继续保留，按真实时间戳选镜并保护原声。剪映草稿默认保留原素材和可编辑时间线，普通导出不再依赖浏览器；需要烘焙效果时主动选择效果渲染。智能体和命令入口统一使用 AskFilm，补充 PATH 缺失时的本地入口。此前时间线选段换产品、智能混剪、可编辑画布、剪辑快捷键、原文件口播预览，以及编导、拆解、案例库和团队配置包入口继续保留。生成与云服务仍需要自己的授权和额度；采用素材或外部生成仍按客户端的确认流程执行。

团队 API 包通过“设置 → 服务商”预览后导入，按当前 Windows 用户加密；云转写配置与文字 AI 服务分别处理。公开软件不附带私人配置包、发布者身份或 OAuth 会话。飞书仍需每位用户自己的官方应用配置、登录授权及目标资源权限。

## 本轮验证范围

同一份 1.3.1 候选源码的 72 组必需检查已通过。候选双工作台启动、合成测试音频实际本地转写（33 字）、22 个已有模型文件复用与未改动检查，以及隔离环境中的随包命令入口检查已完成。

真实打包客户端已验证同一个浏览器会话中旧文案服务与两个当前端口并存、并发会话恢复，以及编导服务退出后通过编导台重连，未保存文案、文件选择和设置保留。实际界面验收使用独立测试资料，没有使用个人 Key 或生产稿件。

1.2.3 与 1.3.0 的旧版更新组件已分别完成升级至 1.3.1 和新进程强退后的失败回滚实测；本版更新组件也完成从 1.3.0 正常更新及新进程提前退出后回滚至 1.3.0 的实测。测试资料、加密假 Key、项目与模型保留。这些结果针对上述路径，不代表所有历史版本或每种故障都已实测。

本轮没有新增付费生成、真实音频云转写或飞书云写入验收。公开软件与私人 API 配置包分别交付，个人配置、项目和模型不进入公开软件附件。首次从公网下载全部资源的边界见上文。

本轮仅使用 GitHub，蓝奏云后补。完整桌面版采用独立 `contenthub-v1.3.1` 通道，独立文案客户端和 Agent Skill 的 latest 不变。
