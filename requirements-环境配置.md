> 素材发布变更（2026-10-20）：业务媒体与旧完整部署包已移除，请先阅读[私有素材配置说明](PRIVATE_MEDIA.md)。下文历史验收记录不代表仓库仍含示例素材。

# 环境配置需求与部署说明

> 本文记录原电脑环境基线。跨电脑部署以 [部署操作手册](部署操作手册.md) 第 2 版为准，按目标 GPU/驱动选择 PyTorch；不要将本文的 cu129 或 .venv 路径当作通用要求。

适用项目：`total-program`，包含 `airport-detective-frontend` 与 `airport-detective-backend`。  
核对日期：2026-10-16。本文依据当前代码、依赖清单和本机实际 Python 环境编写。

## 1. 运行方式与必要组件

| 组件 | 正常运行是否需要 | 当前情况 |
|---|---|---|
| Windows 64 位 | 是，本项目当前按 Windows 启动方式交付 | 使用 PowerShell、`.cmd` 启动脚本 |
| Python 64 位 | 是 | 已核对版本 3.10.18；后端依赖文件面向 Python 3.10/3.11，优先复用已验证的 3.10 |
| Python 第三方依赖 | 是 | 见第 3 节和后端 `requirements.txt` |
| 浏览器 | 是 | 支持现代 JavaScript、Fetch、Blob 图片和 `AbortSignal.timeout` 的浏览器 |
| NVIDIA GPU 与驱动 | GPU 推理需要 | 本机 RTX 5060，约 7.9 GiB 可见显存；程序也有 CPU 回退路径 |
| Node.js / npm | 仅前端独立开发、构建和测试需要 | 本机 Node.js v24.14.0；一体化启动不依赖 Node.js |
| MySQL / Redis 等数据库 | 不需要 | 当前任务和证据写入本地文件 |
| 联网 | 安装依赖时需要，运行时不要求在线下载模型 | 模型、视频和前端资源均在本地；后端禁用模型自动安装并设置 Hugging Face 离线模式 |

一体化方式由 Flask 同时提供页面、API 和预测图片。前端约每 600 ms 通过 HTTP 获取四路状态，再请求最新预测 JPEG；当前没有 WebSocket 推送。

## 2. 硬件和存储要求

- 当前已验证设备为 NVIDIA GeForce RTX 5060，CUDA 可用。六个模型均已在本机完成加载和单帧推理。
- 四路检测共享一个模型，通过轮询处理四个视频源；不会为每路分别加载一份模型。较大模型的耗时与显存需求应以目标机器实测为准。
- CPU 模式可用于基本功能验证，四路处理速度需要另行实测。
- 磁盘需容纳 Python 环境、六个权重、四个视频，以及不断增长的任务记录、物品照片和人员照片。应根据实际检测时长预留空间；当前没有自动按天清理所有历史任务的机制。
- 后端目录必须允许当前用户写入 `data/`。中文路径沿用当前项目结构即可。

## 3. Python 依赖

### 3.1 核心推理环境

| 项目 | 当前实测版本 |
|---|---|
| Python | 3.10.18，64 位 |
| torch | 2.8.0+cu129 |
| torchvision | 0.23.0+cu129 |
| PyTorch CUDA 构建版本 | 12.9 |
| 显卡 | NVIDIA GeForce RTX 5060 |

应成对安装匹配的 torch 和 torchvision。CUDA 驱动需支持所选 PyTorch 构建；安装完成后以 `torch.cuda.is_available()` 和实际推理结果检查。本文 GPU 安装命令采用当前已验证的 cu129 组合，其版本对应关系见 [PyTorch 官方历史版本安装说明](https://pytorch.org/get-started/previous-versions/#v280)。

### 3.2 后端依赖文件与当前版本

正式的安装依赖清单位于 `airport-detective-backend/requirements.txt`。该文件没有包含 torch 和 torchvision，需要先单独安装。下表是核对时的环境快照，不是完整的传递依赖锁文件。

| 软件包 | requirements.txt 范围 | 当前安装版本 |
|---|---|---|
| Flask | >=3.0,<4 | 3.1.3 |
| Werkzeug | Flask 的依赖 | 3.1.8 |
| opencv-python | >=4.10,<5 | 4.12.0.88 |
| numpy | >=2,<2.3 | 2.2.6 |
| matplotlib | >=3.8,<3.11 | 3.10.9 |
| pandas | >=2.0,<3 | 2.3.3 |
| scipy | >=1.13,<1.16 | 1.15.3 |
| seaborn | >=0.13,<0.14 | 0.13.2 |
| PyYAML | >=6,<7 | 6.0.3 |
| requests | >=2.31,<3 | 2.34.2 |
| tqdm | >=4.66,<5 | 4.67.3 |
| psutil | >=5.9 | 7.2.2 |
| py-cpuinfo | >=9 | 9.0.0 |
| thop | >=0.1.1 | 0.1.1-2209072238 |
| huggingface-hub | >=0.23,<2 | 1.12.2 |
| safetensors | >=0.4 | 0.7.0 |
| imageio-ffmpeg | >=0.5,<0.7 | 0.6.0 |

YOLOv10 使用后端 `vendor/ultralytics` 中随项目交付的代码。`engine.py` 会优先加载该目录。迁移时必须携带 `vendor/`，不能只安装 PyPI 的最新版 ultralytics 来替代它。现有加载器已包含旧格式权重所需的兼容处理。

## 4. 目录和资源要求

```text
total-program/
├─ start-monitor.cmd
├─ airport-detective-frontend/
│  ├─ index.html
│  ├─ app.js
│  ├─ styles.css
│  ├─ live-client.js
│  ├─ live-monitor.css
│  ├─ public/
│  ├─ package.json
│  ├─ server.mjs
│  └─ build.mjs
└─ airport-detective-backend/
   ├─ .venv/
   ├─ app.py
   ├─ engine.py
   ├─ analytics.py
   ├─ live_monitor.py
   ├─ requirements.txt
   ├─ launch.ps1
   ├─ start.cmd
   ├─ vendor/ultralytics/
   ├─ models/
   │  ├─ yolov10n.pt
   │  ├─ yolov10s.pt
   │  ├─ yolov10m.pt
   │  ├─ yolov10b.pt
   │  ├─ yolov10l.pt
   │  └─ yolov10x.pt
   ├─ videos/
   │  ├─ camera-1.mp4
   │  ├─ camera-2.mp4
   │  ├─ camera-3.mp4
   │  └─ camera-4.mp4
   └─ data/
      ├─ shuttle-04.json
      └─ jobs/<任务编号>/
```

前后端应保持为同一父目录下的两个相邻文件夹，后端据此定位前端。六个权重已从用户提供的文件复制到 `models/` 并校验一致。

四路示例视频对应关系：

| 摄像头资源 | 原始视频文件名 |
|---|---|
| camera-1.mp4 | 本地私有视频（不公开） |
| camera-2.mp4 | 本地私有视频（不公开） |
| camera-3.mp4 | 本地私有视频（不公开） |
| camera-4.mp4 | 本地私有视频（不公开） |

## 5. 当前电脑直接启动

双击根目录 `start-monitor.cmd`，即可调用后端环境并自动打开浏览器。启动窗口需保持运行。

后端默认从 5180 端口开始寻找可用端口；请以启动窗口打印的地址为准，不能固定认为始终是 5181。也可在 PowerShell 中手动指定起始端口：

```powershell
Set-Location -LiteralPath 'C:\Users\pc\Desktop\新加坡合作项目\total-program\airport-detective-backend'
& '.\.venv\Scripts\python.exe' app.py --port 5181 --open
```

服务当前绑定 `127.0.0.1`，供本机访问。首页为前端，`/workbench` 为原后端工作台。

## 6. 换电脑时重建环境

现有 `.venv/pyvenv.cfg` 指向 `D:\Anaconda\envs\Experiment1`，且 `include-system-site-packages = true`。因此当前环境会使用该 Anaconda 环境中的软件包，直接复制 `.venv` 到另一台电脑不能保证可运行。

以下操作用于新机器或新部署副本；不要在正在使用的环境中直接覆盖 `.venv`。如果目标目录已有旧 `.venv`，先停止服务并将其改名备份，再创建独立环境。

### 6.1 创建 Python 环境

先安装 64 位 Python 3.10，并确保 Windows Python Launcher 可用。在后端目录执行：

```powershell
py -3.10 -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install --upgrade pip
```

### 6.2 安装 GPU 版 PyTorch

在具备相容 NVIDIA 驱动的目标机器执行：

```powershell
& '.\.venv\Scripts\python.exe' -m pip install torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cu129
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
& '.\.venv\Scripts\python.exe' -m pip check
```

驱动或硬件不适用于该构建时，应按 PyTorch 官方说明选择匹配组合并重新验证。本项目当前运行不需要 torchaudio。

没有 NVIDIA GPU、仅做 CPU 功能验证时，可在独立环境中改用 CPU 安装源：

```powershell
& '.\.venv\Scripts\python.exe' -m pip install torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cpu
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
```

### 6.3 自检

在后端目录执行：

```powershell
& '.\.venv\Scripts\python.exe' -c "import torch, torchvision, flask, cv2; print('torch:', torch.__version__); print('torchvision:', torchvision.__version__); print('CUDA:', torch.version.cuda); print('GPU available:', torch.cuda.is_available())"
& '.\.venv\Scripts\python.exe' -c "from engine import Detector; d=Detector(); print('device:', d.load('yolov10n.pt', 'auto'))"
& '.\.venv\Scripts\python.exe' app.py --port 5181 --open
```

GPU 部署应看到 `GPU available: True`；CPU 部署显示 False 属于预期。加载成功后，再通过页面启动四路检测，检查四路预测画面和警报图片。

## 7. 前端独立开发环境（可选）

前端使用原生 HTML/CSS/JavaScript；当前 `package.json` 没有第三方 npm 依赖，开发服务器只使用 Node.js 内置模块，无需为当前代码执行 `npm install`。本机核对版本为 Node.js v24.14.0。

先启动后端，再在另一个 PowerShell 窗口进入前端目录：

```powershell
Set-Location -LiteralPath 'C:\Users\pc\Desktop\新加坡合作项目\total-program\airport-detective-frontend'
$env:BACKEND_URL = 'http://127.0.0.1:5181'
npm run dev
```

`BACKEND_URL` 应与后端实际地址一致。Node 服务默认 5173，冲突时向后寻找可用端口；浏览器访问 Node 启动窗口打印的地址。`/api/` 请求由 Node 代理到后端，页面使用相对 API 地址。

```powershell
npm run check
node --check live-client.js
npm test
npm run build
```

`npm run check` 当前只检查 app.js 和 server.mjs，故上面额外列出 live-client.js 检查。构建产物位于前端 `dist/`。一体化启动直接提供前端源目录资源，不要求先构建。

## 8. 模型选择和结果存储

- 右上角提供 n、s、m、b、l、x 六种 YOLOv10 模型。先在左下角停止检测，等待停止完成，再选择模型并启动；四路统一使用所选模型。
- 当前四路检测默认使用 yolov10n.pt，输入尺寸 640、置信度阈值 0.25；后端自动选择 GPU 或 CPU。重启后可从上次任务状态恢复模型信息。
- 模型选择随启动请求的 `model` 字段传给 `/api/shuttles/04/start`；后端校验本地权重并将实际模型记录在任务参数中。
- 每一路对应 `data/jobs/<任务编号>/`：`preview.jpg` 为覆盖更新的预测画面，`crops/` 为物品图，`people/` 为人员图，`archive.json` 为遗留物档案。`data/shuttle-04.json` 记录当前四路任务编号。
- 当前实时四路流程不自动保存完整标注视频。原工作台的离线任务导出功能与实时四路流程不同。
- 页面「清除缓存」会先停止当前四路检测，再清理这四个任务的存档照片；原视频、模型、档案 JSON 和其他历史任务不会因此全部删除。

## 9. 常见问题

| 现象 | 检查与处理 |
|---|---|
| `.venv` 的 Python 启动失败 | 检查是否仍引用原电脑的 Anaconda；按第 6 节在目标机器重建 |
| 找不到 YOLOv10 或加载权重失败 | 检查 vendor/ultralytics 和 models/ 是否完整；从后端目录执行自检 |
| CUDA 不可用 | 核对 NVIDIA 驱动、PyTorch 构建和 torch.cuda.is_available()；不要仅依据本机 CUDA 工具版本判断 |
| GPU 内存不足或推理较慢 | 停止其他 GPU 任务，并在页面改选较小模型；核对实际任务报错 |
| 页面显示后端连接失败或 502 | 检查后端启动窗口和实际端口；独立前端模式核对 BACKEND_URL |
| 启动后进入了其他页面 | 原端口可能已有服务；使用本项目启动窗口打印的地址 |
| 四路视频无法打开 | 检查 videos/camera-1.mp4 至 camera-4.mp4 是否存在且能读取 |
| 照片写入失败 | 检查 data/ 写权限、磁盘空间及后端日志 |

本文记录了当前安装版本与部署步骤；本次编写未在全新机器重装全部依赖，因此新部署仍需执行自检和四路运行验收。不同硬件的帧率不作保证。
