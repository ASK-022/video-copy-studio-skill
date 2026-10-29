# 本地转写计算设备

设置 → 服务 → 本地转写设备，选择自动、GPU 或 CPU，保存后对下一次转写生效。自动模式优先 GPU；已识别的 CUDA 错误只自动重试一次 CPU，保留错误日志。指定 GPU 不会将 CPU 执行标成 GPU 成功。

GPU 环境与原 CPU 环境分开安装。当前准备脚本适用于 Windows x64、Python 3.12、支持 CUDA 12.8 的 NVIDIA 驱动；会从 PyTorch 官方下载数 GB 的可选依赖，网络及磁盘空间须足够。只在用户要求准备 GPU 时执行安装，不在读取设备状态时下载。

在线安装的 Agent 入口：

```powershell
& "$env:LOCALAPPDATA\VideoCopyStudio\studio.cmd" setup-gpu --install
```

去掉 `--install` 仅验证现有 GPU 环境。自定义运行时可使用 `studio_agent.py --runtime-home 路径 setup-gpu --install`。

离线文案客户端可以用安装目录自带的 Python，指定该客户端注册的运行时配置：

```powershell
& ".\Runtime\python\python.exe" ".\App\scripts\setup_gpu.py" --runtime-config "$env:LOCALAPPDATA\VideoCopyStudioOffline\runtime.json" --install
```

内容中台的资源目录也可用其中的 Python 执行新版 `setup_gpu.py`，`--runtime-config` 必须指向这套资源实际注册的配置。不要把其他人的资料或配置复制过来。准备完成后在设置中“重新检测”，再保存 GPU 或自动。

安装只创建转写引擎旁的 `.venv-gpu` 并应用引擎的设备兼容修复，不替换 CPU 的 PyTorch。GPU 环境复用当前 CPU 环境的其他依赖与必要兼容钩子；两个目录保持原位置，不能把这个虚拟环境直接复制给其他电脑。

Agent 输入：`{"action":"compute","refresh":true}` 检测设备；`{"action":"compute","compute_mode":"cpu"}` 保存偏好，取值 `auto`、`gpu`、`cpu`。输出包含 `mode`、`selected_device`、`gpu`、`cpu_available`、`last_run`、`scope`。`last_run` 是当前服务启动后最近一次任务的实际设备；历史任务保留 `asr_compute` 快照。不要将“GPU 可用”当成某次任务已使用 GPU 的证据。

本地语音识别、标点和时间对齐可使用 GPU。截图、OCR、静音与场景检测仍采用各自工具；短音频整体耗时受进程启动和模型加载影响，不保证整体任务按推理速度同比加速。
