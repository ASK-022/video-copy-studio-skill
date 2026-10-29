# 完整桌面版更新执行器

本目录是完整桌面发行中更新、资源准备、蓝奏云安装助手及其校验代码的源码参考，不是文案 Skill 的启动目录。完整桌面主工程使用 `AskFilm/apps/desktop` 与 `AskFilm/scripts` 布局；这些构建脚本保留该工程中的相对路径。请勿将个人资料或签名私钥放入此目录。

`contenthub_update.py` 构建为稳定启动器和外部更新执行器，版本程序并排保存，签名清单和完整文件清单通过后才切换。两项工作台健康回执确认成功；失败或中断恢复旧版和资料元数据。`contenthub-updates.mjs` 负责检查、分片下载、缓存复用、忙碌保护和执行器交接。`contenthub-update-public.json` 仅包含发布公钥。

`contenthub-resources-setup.py` 使用独立资源目录和临时短路径准备 Python、依赖、浏览器与模型，验收后保存真实路径。`contenthub_download_setup.py` 校验蓝奏云 ZIP 分包并重组标准安装器。NSIS 的 `contenthub-installer.nsh` 为版本化覆盖安装保留旧版本，并在卸载时仅清理标记的软件版本，保留用户资料和模型。

发布时先构建并验收完整桌面程序，再使用 `build-contenthub-update.py` 对比基线程序生成增量和 16 MiB 分片。对 `payload.json` 的原始规范化字节用仓库既有 RSA-3072 发布私钥签名，生成 `update.json`。私钥不进入源码、客户端、分包或发布附件。发布清单中的版本、大小、SHA256 和固定下载地址必须同时匹配。

完整桌面版使用 `contenthub-v*` 标签和 `releases/contenthub/latest.json`，不会改写文案客户端的 `releases/latest.json` 或 GitHub 默认 latest 发布。
