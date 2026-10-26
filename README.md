> 素材发布变更（2026-10-20）：业务媒体与旧完整部署包已移除，请先阅读[私有素材配置说明](PRIVATE_MEDIA.md)。下文历史验收记录不代表仓库仍含示例素材。

# 接驳车遗留物检测与溯源系统

当前为 **Windows 部署版 1.1.0，部署手册第 2 版**。完整系统位于仓库根目录，包含统一前端、四路算法后端、六种 YOLOv10 通用权重；业务视频须本地配置。

- [部署操作手册](部署操作手册.md)
- [多接驳车视频接入与替换](视频接入说明.md)：每辆车单独目录、最多四个视频、无需修改原文件名，缺少的线路显示未接通。
- [遗留物报警规则](报警规则说明.md)：稳定转交触发黄警，连续5个检测帧满足遗留条件自动触发红警。

## 界面版本

- `main`：移除车辆位置示意区域，扩大实时画面，预览最长边1920像素、JPEG质量95。
- [codex/v1.1.0-map-47ee4e9](https://github.com/ll1161396786/Detection-and-traceability-main/tree/codex/v1.1.0-map-47ee4e9)：保留车辆位置示意窗口的版本，准确对应提交 `47ee4e996e6ef2ce486c57431478f7c5426e36b1`。

分支名称包含原部署版本及提交短号，避免与同为1.1.0的其他界面修订混淆。后续修改默认只在本地进行，收到明确要求后再同步GitHub。

## 安装与启动

1. 获取最新源码及 LFS 模型权重，按 PRIVATE_MEDIA.md 在本地配置视频。
2. 使用 environment.yml 创建并激活目标机器的 Conda 环境，按 GPU/驱动选择匹配的 torch/torchvision。
3. 执行 `python -m pip install -r requirements-app.txt`，按手册完成真实推理自检。
4. 已激活环境中运行 `python deploy/serve.py`，默认访问 `http://127.0.0.1:5180/`。
5. 使用 stop-deploy.cmd 或服务窗口 Ctrl+C 停止。

`install.cmd` 默认固定安装 cu129，不能自动适配所有 GPU；指定 Conda Python 也只是创建新的 .runtime。它保留供确认相容的机器使用。通用部署按手册的 Conda 流程执行；start-deploy.cmd 仍只对应旧 .runtime 流程。默认仅本机访问，单进程 Waitress 服务，无需 Node.js 或数据库。

## 从 Git 克隆

六个通用模型使用 Git LFS。`git lfs pull` 仅获取模型；业务视频、图片和旧部署包已移除。

```powershell
git lfs install
git clone --branch main https://github.com/ll1161396786/Detection-and-traceability-main.git
```

## 功能

- 接驳车 04 四路实时预测与示例视频循环检测。
- 选择 YOLOv10n/s/m/b/l/x，停止后切换，再启动生效。
- 疑似/确认遗留物、可能所属人关联和人工确认。
- 物品及所属人照片点击放大。
- 当前四路任务照片清理，历史结果保存在本地 `airport-detective-backend/data/`。

重建后的仓库仅发布清洁的 `main`，不上传原分支和提交历史。旧版环境记录与开发说明仍随源码保留，正式部署以 [部署操作手册](部署操作手册.md) 为准。
