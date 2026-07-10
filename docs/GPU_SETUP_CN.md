# 🖥️ GPU 配置(自动跑实验用)

> [← 返回 README](../README_CN.md#gpu-server-setup) · 在 CLAUDE.md 里声明 GPU 服务器,让 ARIS 帮你跑实验。

当 GPT-5.6-Sol 审稿说"需要补一个消融实验"或"加一个 baseline 对比"时，Claude Code 会自动写实验脚本并部署到你的 GPU 服务器。为此，Claude Code 需要知道你的服务器环境。

在项目的 `CLAUDE.md` 中添加服务器信息：

```markdown
## 远程服务器

- SSH：`ssh my-gpu-server`（密钥免密登录）
- GPU：4x A100
- Conda 环境：`research`（Python 3.10 + PyTorch）
- 激活：`eval "$(/opt/conda/bin/conda shell.bash hook)" && conda activate research`
- 代码目录：`/home/user/experiments/`
- 后台运行用 `screen`：`screen -dmS exp0 bash -c '...'`
```

Claude Code 读到这些就知道怎么 SSH、激活环境、启动实验。GPT-5.6-Sol（审稿人）只决定**做什么实验**——Claude Code 根据你的 `CLAUDE.md` 搞定**怎么跑**。

如果你已经在 GPU 服务器上，可以添加以下到你的 `CLAUDE.md`：
```markdown
## GPU 环境

- 这台机器有直接 GPU 访问（不需要 SSH）
- GPU：4x A100 80GB
- 实验环境：`YOUR_CONDA_ENV`（Python 3.x + PyTorch）
- 激活前任何 Python 命令：`激活实验环境的命令`（uv, conda 等）
- 代码目录：`/home/YOUR_USERNAME/YOUR_CODE_DIRECTORY/`
```

**没有 GPU 服务器？** Review 和改写功能不受影响，只有需要跑实验的修复会被跳过（标记为"需人工跟进"）。或者按需租 GPU 跑实验，见下方 Vast.ai 集成。
## ☁️ Vast.ai 按需 GPU

没 GPU？从 [Vast.ai](https://vast.ai) 按需租。ARIS 分析你的训练任务（模型大小、数据集、时间），找能放下的最便宜 GPU，按**总成本**（不是 $/hr）排序展示，然后租 → 跑 → 收 → 销毁全自动。

在项目 `CLAUDE.md` 加：

```markdown
## Vast.ai
- gpu: vast                  # 从 vast.ai 按需租 GPU
- auto_destroy: true         # 实验跑完自动销毁（默认）
- max_budget: 5.00           # 可选：估算超过这个数会警告
```

**📖 完整配置指南 → [integrations/VAST_GPU_GUIDE_CN.md](integrations/VAST_GPU_GUIDE_CN.md)** 包含：
- 账号 + `vastai` CLI + API key + SSH key 准备工作（5 个步骤）
- ARIS 如何挑 GPU 并展示实时成本排序表
- 手动租用：`/vast-gpu`（list / rent / destroy）
- 典型花费区间（RTX 4090 消融 ~$0.30-2/次，A100/H100 baseline ~$2-10/次）
- 什么时候用 `gpu: vast` 比 `gpu: remote` / `gpu: local` 更划算

**也不想租？** Review 和改写类 skill 仍可用，只有需要跑实验的修复会被跳过（标记为"需人工跟进"）。
