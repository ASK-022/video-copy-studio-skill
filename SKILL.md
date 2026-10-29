---
name: video-copy-studio
description: 将视频、音频、公开短视频链接或直接提供的脚本文档转成参考文案，纠错拆解后保留原结构生成同商品或换商品文案；从商品图片、文字或文档提取商品资料；导出 Excel 或写入指定飞书表格。适用于参考改写与团队文案交付，不执行素材匹配、自动删减或成片渲染。
---

# 文案工坊

使用随包提供的本地客户端和 JSON CLI 完成任务。CLI 仅访问当前电脑的回环地址，运行时、模型和凭据在 Skill 目录外独立保存。

## 触发与边界

- 用户要求视频转文字、提取口播、纠错、内容总结、爆款拆解、视频转脚本、提示词反推，或以参考视频保留骨架生成新文案时使用。
- 用户直接粘贴脚本或上传 DOCX/PDF/TXT，要求保留结构生成不同版本时，使用 `import-script`，无需先转成音视频。商品资料文档则用 `extract-material` 的 `document` 参数，不能混为参考脚本。
- 用户要求把已生成文案汇总为 Excel、逐条 TXT，或安排素材拍摄需求时使用。
- 自然语言示例：“这条视频转写并纠错”“保留原结构生成 7 条同商品文案”“换成我的产品套这个结构”“导出脚本文案表”。
- 仅生成文案不表示允许写入飞书。云端画面分析、付费解析和飞书写入须与用户明确选择的服务和目的匹配。

## 使用条件

- 本地 Agent 能执行命令并访问输入文件。完整运行时支持 Windows 10/11 x64；一键安装会补齐独立 Python 3.10–3.12 环境。不把 Windows 本地功能宣称为云端 Agent、macOS 或 Linux 原生可用。
- 首次安装需联网下载依赖与模型，并验证加载/推理成功；不在第一次转写时才下载必需模型。无需 GPU；资源占用取决于模型和视频长度。
- 文件最大 500 MB、最长 30 分钟；无音轨的视频不能转写。公开链接受平台访问限制，失败后说明原因并优先使用用户下载的本地文件。
- AI 纠错、结构分析、生成和报告需要用户自己的兼容 AI 服务配置。TikHub、Cue、视觉模型、飞书均为可选，分别配置；不共用服务商 Key。
- 新机器安装与首次配置见 [README.md](README.md)。不要复制其他人的 `.studio`、模型缓存、浏览器资料或加密密钥。

## Agent 调用

一键安装后优先使用运行时的 CLI 入口（支持未配置系统 Python PATH 的机器）：

```powershell
& "$env:LOCALAPPDATA\VideoCopyStudio\studio.cmd" doctor
& "$env:LOCALAPPDATA\VideoCopyStudio\studio.cmd" start --open
```

自定义运行时目录时替换上述目录。也可使用 `runtime.json` 中的 `python` 解释器执行下列脚本；工作目录为 Skill 目录，其他目录使用脚本绝对路径：

```powershell
python scripts/studio_agent.py doctor
python scripts/studio_agent.py start --open
python scripts/studio_agent.py invoke --request request.json
python scripts/studio_agent.py wait --job-id JOB_ID --timeout 30
```

完整输入字段、输出结构和动作说明见 [references/parameters.md](references/parameters.md)；机器可读约定见 [references/input.schema.json](references/input.schema.json)。先按动作阅读相关参数，不必一次读取全部客户端源码。

## 按请求完成流程

1. 先 `doctor`；`models_ready` 表示有加载成功的凭据且模型文件仍完整。服务已可用时直接调用，无须重复安装；没有可用服务且尚未注册运行时则按安装说明初始化，再 `start`。不得重启正在工作的实例来抢占端口。
2. 导入用户指定的文件或链接，保存返回的 `job_id`。仅转文字时 `auto_ai=false`；用户同时要求 AI 纠错/生成且已配置时可设为 true。
3. 导入、纠错、生成、报告与检测均可能异步。每次 `wait` 最多 60 秒；`pending=true` 表示继续查询，不是完成。`status=error` 时保留并报告已完成部分，不能把失败或停止说成全部成功。
4. 要保留结构时，先纠错/拆结构，再生成。`same` 保持商品，`switch` 必须提供目标商品事实；`original` 会重新设计骨架，只在用户要求原创时用。保持段落功能、数量和顺序。输入文案被改动后重新拆结构；不把识别猜测、拍摄建议或未经确认的价格功效当成事实。
5. 按用户要求生成报告、执行本地检测或导出，不默认运行全部报告。静音、重复口播和场景变化仅标记和建议，不自动剪掉；无实测时间戳时不编造字幕时间。
6. 导出明确指定的批次和脚本，默认最新批次，不混入历史商品。检查导出文件存在并报告路径；单条 TXT 正文不带编号标题，汇总 TXT 带区分标题。Excel 用 `script` 脚本文案表或 `shooting` 拍摄需求表；拍摄数量、时间、完成情况按用户填写，镜头建议需标明待确认。
7. 用户明确要求写飞书时，先用 `action=feishu, write=false` 返回目标与范围，再按已授权目标 `write=true`。不向未经指定的表格写入；同一内容重复提交有去重保护，结果不确定时不盲目重试。当前只支持 `/sheets/` 电子表格，真实连接仍须使用者自己的权限配置与实测。

## 更新

本地转写支持 GPU／CPU／自动设备选择。Agent 使用 `action=compute` 查询或保存偏好；只有用户要求安装 GPU 环境时执行 `setup-gpu --install`。设备状态、条件及在线／离线准备命令见 [references/gpu.md](references/gpu.md)。报告表格显示已有真实抽样截图，可放大定位、冻结表头或切换逐段阅读，不为补截图重新生成已完成报告。

本版本包含五项工作流：`resume` 按原批次快照补齐剩余，不重写已完成成稿；`preview-script/get-preview/confirm-preview` 先本机读取并按明确选择拆分导入；`review-drafts` 比较当前保存成稿的文本相似度；`set-editorial` 保存采用状态与审核意见；`set-metadata` 及 `list` 的搜索参数用于项目、商品、标签与日期管理。`tasks` 返回任务阶段和保存进度。字段见参数文档，发布版本与安装包以对应 Release 为准。

相似度是本机文本与开头重合提示，不代表语义理解或真实投放效果。拆分建议必须符合用户的明确要求或核对结果，不能把编号卖点自动当作多份脚本；保留读取的原始正文。确认请求相同可安全重试；确认后改拆分应新建预览，不重复创建相同参考。

自己的商品图片或文案可用 `extract-material` 提取，`material-status` 查询独立状态；核对候选资料后 `apply-material` 填回对应模式。图片只在本机 OCR，只有识别文字交给所选文字服务商，不发送原图。参考口播、原商品与目标商品资料保持独立，不能把待核对内容自动放进商品库的已确认卖点。

脚本原文与商品文档支持 DOCX/PDF/TXT，单份 20 MB、正文 2 万字内，PDF 最多 40 页。文档本机读取，扫描 PDF 用本机 OCR；只把读取文字交给当前 AI。直接脚本不默认纠错：保留原文，按空行保留已有分段；未分段时再分析结构。导入并等待 done 后复用 same/switch 生成，详见参数文档。

客户端还支持 `products/product-get/product-save`、`plan` 与 `manuscript/save-manuscript/restore-manuscript/rewrite`，字段见参数文档。商品资料须由用户核对，不能把提取结果自动保存为已确认商品；待确认资料不用于生成。修改成稿前读取 revision，使用 base_revision 防止覆盖另一窗口。单条重写使用生成批次的商品快照并新增版本，不重写其他稿件。导出默认使用当前成稿，原结构和原评分单独保留。

`python scripts/update_skill.py` 只检查 GitHub 正式 Release；用户要求升级时加 `--apply`。升级保存旧 Skill 备份，不移动或覆盖独立的运行时、用户视频和凭据。包内不包含共享 Key，也不需要 Agent 读取它们。
