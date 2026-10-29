# 输入、输出参数

所有动作通过 UTF-8 JSON 文件输入：

```powershell
& "$env:LOCALAPPDATA\VideoCopyStudio\studio.cmd" invoke --request request.json
```

CLI 公共参数放在子命令前：`--base-url http://127.0.0.1:8777`、`--runtime-home PATH`。不支持远程公网服务地址。

`doctor` 的 `models_ready=true` 表示安装期实际加载/推理自检通过且文件清单仍完整；`service` 是当前运行中的 HTTP 服务状态。`start --open` 在未启动时启动本地服务，再打开浏览器；已启动则直接打开。模型与依赖日志保存在运行时目录。自定义运行时目录时替换上面的 `VideoCopyStudio` 路径。

## 动作参数

| action | 必填参数 | 可选参数与默认值 | 输出 |
|---|---|---|---|
| health | 无 | 无 | 转写运行时是否就绪、AI 是否配置 |
| list | 无 | 无 | 当前参考库任务摘要，不含回收站 |
| providers | 无 | 无 | 模型名称、地址、已配置标志；不返回密钥 |
| import | `file` 或 `url` 二选一 | `facts=""`，`auto_ai=false`，链接 `provider=local/tikhub` | 新建 `id`，后续作为 `job_id` |
| get | `job_id` | 无 | 原始/校对稿、结构、商品资料、批次、报告、检测结果 |
| correct | `job_id` | `text=当前校对稿`，`facts=参考商品资料` | 异步任务 id；局部纠错并拆结构/提取商品 |
| analyze | `job_id` | `text=当前校对稿`，`facts=参考商品资料` | 异步任务 id；按原文覆盖顺序拆结构 |
| extract-product | `job_id` | 同上 | 异步任务 id；有原文证据的商品资料 |
| generate | `job_id` | `mode=same`、`count=3`、`facts=已提取商品资料`、`direction=""`、`quality_check=true` | 异步任务 id；结果逐批保存到 batches |
| stop | `job_id` | 无 | 停止后续生成；当前一轮可能仍完成 |
| report | `job_id` | `scene=transcript`、`visual_mode=local`、`vision_provider_id=""` | 异步任务 id；报告保存在 reports |
| markers | `job_id` | `options={}` | 异步任务 id；仅标记，无剪辑动作 |
| export | `job_id`、`output` | `batch_id=latest`、`indices=全部`、`format=xlsx`、`template=script`、`table_options={}`、`edits={}`、`overwrite=false` | 已验证的输出路径、字节数、脚本数 |
| export-report | `job_id`、`output` | `scene=transcript`、`format=md/json`、`overwrite=false` | 报告文件路径 |
| feishu | `job_id` | 与 export 的选稿参数相同；`write=false` | 默认预览配置目标；write=true 才追加 |
| products | 无 | 无 | 本机商品卡片，不含归档商品 |
| product-get | `product_id` | 无 | 商品资料、当前版本与历史 |
| product-save | `product` | 更新时提供 `product_id` 和 `product.base_version` | 商品新版本；必须人工核对后 `product.confirmed=true` |
| plan | `count` | `focus={}`、`offset=0`、`limit=14`（最多 30） | 分页方向预览，不调用 AI |
| manuscript | `job_id` | `batch_id=latest`、`script_index=1`、可选 `revision` | 当前成稿及版本列表，或指定版本全文 |
| save-manuscript | `job_id`、`base_revision`、`text` | `batch_id`、`script_index`、`segments` | 本机文件中的新成稿版本 |
| restore-manuscript | `job_id`、`base_revision`、`revision` | `batch_id`、`script_index` | 新增恢复版本，旧版本保留 |
| rewrite | `job_id`、`base_revision` | `batch_id`、`script_index`、`direction` | 异步单条重写，使用批次商品快照；结果为新版本 |
| import-script | `text` 或 `file` 二选一 | `title`、`facts`、`auto_ai=true`；file 为本机 DOCX/PDF/TXT | 新参考任务 `id`；异步读取与结构分析，不执行 ASR 或默认纠错 |
| extract-material | `job_id`、`text` / `images` / `document` 三选一 | `mode=switch`（same/switch），images 为 1–5 个本机图片路径，document 为单个本机文档路径 | 独立商品提取记录 `id`，后续作为 `import_id` |
| material-status | `job_id`、`import_id` | 无 | 提取状态、来源文字、商品候选、待核对项与实际服务商 |
| apply-material | `job_id`、`import_id`、`text` | text 为核对后的商品资料 | 填入原参考对应模式的商品草稿，不更改参考口播或自动保存商品库 |
| resume | `job_id` | `batch_id=latest` | 按原批次商品、模型与结构补齐缺少的文案，保留原成稿和采用状态 |
| preview-script | `text` 或 `file` 二选一 | `title` | 仅本机读取，返回预览 id；不创建参考或调用 AI |
| get-preview | `preview_id` | 无 | 预览状态、原始正文与建议拆分 |
| confirm-preview | `preview_id`、`parts`、`confirmed=true` | `facts`、`auto_ai=true`、`project`、`product_label` | 按已确认拆分创建独立参考，返回 jobs；相同确认可安全重试 |
| review-drafts | `job_id` | `batch_id`、`indices`（从1开始）、`threshold=80` | 选中成稿的本机文本重合、开头相似度与参考对比；每次最多300条 |
| set-editorial | `job_id`、`status` | `batch_id`、`indices`、`note` | 批量更新采用状态及审核意见，使用读取时的状态版本防止覆盖 |
| set-metadata | `job_id`、`metadata` | metadata 可含 title/project/product_label/tags/base_version | 参考重命名、项目和商品分类、标签；有并发修改时返回冲突 |
| tasks | 无 | 无 | 当前任务阶段、已保存进度与未完成批次数量 |

`job_id`、`batch_id` 必须使用服务实际返回的值。`indices` 从 **1** 开始；`edits` 的键是字符串序号，如 `{"2":"修改后的第二条正文"}`。编辑稿只用于本次复制/导出/写入，不改原结构和评分。

## 生成参数

五项工作流预览：`list` 可提供 `q/project/product_label/tag/start/end`，日期格式 YYYY-MM-DD，搜索覆盖原文及当前保存成稿。采用状态 `review/edit/adopted/shoot/published/discarded` 分别表示待审核、需修改、已采用、待拍摄、已发布、弃用。状态筛选不自动改变导出勾选；Web 可用「只勾选当前筛选」。相似度分析使用当前成稿，每次1–300条，仅提供本机文本重合提示，不自动删稿。

`resume` 不接收替换商品、条数或新结构，使用生成批次原有快照追加缺少的条数；模型配置已经变化时须恢复原配置，避免静默改用其他服务。原成稿版本和采用状态保留。`preview-script` 只读正文，`confirm-preview.parts` 是用户明确选定的各份 `{title,text}`；原始读取正文仍留存。`confirmed=true` 表示该选择符合用户指示或已核对，不能自行替用户认定内容。返回的 jobs 每份独立，之后分别 wait/analyze/generate。

`import-script` 导入的是完整参考脚本，与提取商品资料不同。DOCX/PDF/TXT 先在本机读取正文，单份最大 20 MB、2 万字，PDF 最多 40 页，扫描 PDF 使用本地 OCR。旧版 `.doc` 需另存为 `.docx`。原文件不发送 AI，只发送读取后的文字；原文保留在 raw，不虚构音视频或时间戳。用空行分段时保留段数、原句与顺序（最多 40 段），没有空行分段时按营销功能分析。PDF 复杂排版及扫描识别结果须核对。`auto_ai=false` 仅导入文字，之后用 analyze 分析，再 generate。不要把含多份独立脚本的文档当作一份混合参考；让用户拆分上传或明确挑选一份。

商品图片先在本机 OCR，只有识别文字发送到当前文字服务商；每张最多 12 MB、合计最多 30 MB，支持 PNG/JPG/WebP。不凭外观推测商品。商品文案直接发送文字；待核对内容独立返回，不自动用于生成。商品提取有自己的状态，使用 `material-status` 查询到 `status=done`，不能用参考任务的 done 状态当作提取完成。核对候选后再 `apply-material`，原视频商品与目标商品分别保留。

商品 `document` 支持 DOCX/PDF/TXT，大小与页数上限同上；本机读正文后沿用商品文案提取。结果含 `kind=document`、`document_name`、`source_text` 和候选资料；待核对项仍不自动加入可用卖点。

Web「脚本改写」支持拖拽、多选和分次追加文档，列表可逐个移除待上传文件；导入后的删除将对应参考移入回收站。每个文件单独建立参考并显示上传结果，失败项可重试；成功项不会再次上传。CLI 的 `import-script` 每次仍只接收一份文件，多文件调用时逐份提交并分别保存返回的任务 ID，不能合并正文当作同一参考。

- `product_id` 可选择商品库；不给 `facts` 时 CLI 自动取该商品资料及版本。显式指定 `product_version` 可以锁定版本；资料更新冲突后重新核对，不自动替用户确认。`product` 字段包含 `name`、`facts`（已确认卖点）、`aliases`、`pending`、`forbidden`、`audience`、`tone`、`source`；待确认信息不进入生成事实。
- `focus`: `enabled=true`、`audience`、`scenario`、`tone`、`strength=light/balanced/strong`、`custom={"1":"第一条方向"}`。方向变化始终服从原段数、顺序和功能；不增加商品事实。
- `script_index` 从 1 开始。修改前读取当前 `revision` 并传为 `base_revision`，冲突时保留编辑内容，再读取版本；不盲目覆盖另一窗口的修改。
- 导出默认使用所选脚本的当前成稿；`edits` 仍可显式提供一次性导出文本。原生成分段和质检评分不会自动套到手改或单条重写版本。

- `mode`: `same` 同商品裂变；`switch` 换商品套原结构（此时必须显式给目标商品 `facts`）；`original` 按主题原创骨架。
- `count`: 大于 0 的整数，服务每次最多请求 2 条、逐步保存；数量多时耗时/用量随之增加，没有“无条件免费生成”承诺。
- `facts`: 最大 5000 字，填写确认过的商品和卖点。不能把原商品价格、功效和背书自动迁移给新商品。
- `direction`: 最大 2000 字；`quality_check` 控制六维质检与一次改写。
- 原创另可给 `target_duration=60`（10–1800 秒）、`audience`（300 字内）、`purpose`（100 字内）。

## 报告与检测参数

`scene`: `transcript` 视频文字稿、`summary` 内容总结、`breakdown` 爆款拆解、`storyboard` 分镜脚本、`prompts` 提示词/TTS/JSON；`all` 是五类报告，不包括文案生成。

`visual_mode`: `local` 本机 OCR；`cue` 向 Cue 发送公开链接；`vision` 向选定视觉模型发送抽样画面，需 `vision_provider_id`。只在用户选择对应服务时用。

检测 `options`：`silence_db=-35`、`silence_seconds=0.6`、`repeat_similarity=88`、`scene_threshold=3`、`min_scene_seconds=0.5`。检测结果是候选与建议，无自动删除接口。

## 导出参数

`format`: `txt` 汇总文案、`zip` 每条一个纯口播 TXT、`json` 所选脚本与原分段/编辑正文、`xlsx` Excel。

| template | 表头/行粒度 |
|---|---|
| script | 产品、脚本文案、参考视频链接、需求时间、拍摄完成时间；每条脚本一行 |
| shooting | 产品、素材需求数量、参考视频1、画面镜头需求、镜头参考1、镜头参考2、需求时间、完成情况；汇总所选脚本为一条素材需求 |
| archive | 序号、标题、完整口播、字数、生成方式、参考来源、生成时间、稿件版本 |

`table_options`：`product` 产品名，`reference_url` 参考链接，`required_time` 需求时间说明，`completion` 拍摄完成时间/情况；拍摄表另可给 `quantity` 正整数、`shot_requirements` 镜头需求、`shot_reference_1/2` 参考链接或说明。留空不虚构；未提供镜头需求时可汇总已有分段拍摄建议并注明待确认。显式传空字符串可清空建议。镜头图片不自动插入，可在 Excel 中后补。

示例：

```json
{"action":"import-script","file":"C:/Scripts/reference.docx","auto_ai":true}
```

```json
{"action":"import-script","text":"开场原文。\n\n商品介绍原文。\n\n结尾原文。","auto_ai":true}
```

```json
{"action":"import","file":"C:/Videos/reference.mp4","facts":"商品：桌面茶香香薰","auto_ai":true}
```

```json
{"action":"generate","job_id":"使用导入返回的id","mode":"same","count":7,"direction":"口语化，保留原来的结构"}
```

```json
{"action":"export","job_id":"使用导入返回的id","batch_id":"latest","indices":[1,3],"format":"xlsx","template":"script","table_options":{"product":"茶香香薰"},"output":"C:/Deliverables/scripts.xlsx"}
```

## 输出与完成判断

成功：`{"ok":true,"data":...}`；失败：`{"ok":false,"error":"可读原因"}` 且进程退出码非零。
输出外壳的机器约定见 [output.schema.json](output.schema.json)。

提交异步动作的 `id` 只表示已受理。使用 `wait --job-id ID --timeout 30` 查询：

```json
{"ok":true,"data":{"job_id":"…","status":"working","pending":true,"message":"正在生成…","error":"","generation_progress":{"completed":2,"total":7}}}
```

最终 `status=done` 且 `pending=false` 才能报告该任务完成；另检查生成的实际条数与请求条数。`status=error` 时先用 get 查看已保留结果。`wait` 超时会返回 pending，不会取消任务，也不重复提交。

`get` 可能包含较长文案，请按需要保存为本地 JSON，不在聊天中重复打印全部内容。绝不打印用户 API Key、App Secret 或原始配置文件。

## 计算设备

`action=compute`：不填 `compute_mode` 时查询；`refresh=true` 重新检测。填写 `compute_mode=auto|gpu|cpu` 保存下一次转写使用的偏好。输出包含 `mode`、`selected_device`、`gpu`、`cpu_available`、`last_run` 和 `scope`。准备可选 GPU 环境的条件和命令见 [gpu.md](gpu.md)。
