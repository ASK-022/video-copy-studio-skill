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

`job_id`、`batch_id` 必须使用服务实际返回的值。`indices` 从 **1** 开始；`edits` 的键是字符串序号，如 `{"2":"修改后的第二条正文"}`。编辑稿只用于本次复制/导出/写入，不改原结构和评分。

## 生成参数

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
