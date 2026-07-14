# ARIS 快速配置指南

> 从零开始，手把手完成 ARIS 的全部配置。完成后你就可以使用 ARIS 的完整研究工作流。
>
> 本指南面向 **macOS 本地 + 远程 Linux GPU 服务器** 环境，使用 **Claude Code 作为执行者、Codex MCP（GPT）作为审稿人** 的推荐配置。
>
> [English](SETUP_GUIDE.md) | 中文版

---

## 第一步：安装必要工具

### 1.1 Claude Code

Claude Code 是 Anthropic 的 CLI 工具，ARIS 的所有 skill 都在它上面运行。安装方式见 [Claude Code 官方文档](https://docs.anthropic.com/en/docs/claude-code)。

```bash
claude --version   # 验证安装
```

### 1.2 Codex CLI + MCP 注册

Codex CLI 是 OpenAI 的 CLI 工具，ARIS 通过它调用 GPT 作为跨模型审稿人。安装方式见 [Codex CLI 官方文档](https://developers.openai.com/codex)。

安装完成后，先做一次性 ChatGPT 登录（浏览器流程），再把 Codex CLI 注册成 Claude Code 的 MCP server：

```bash
codex --version   # 验证安装
codex login       # 一次性 ChatGPT 登录（已登录可跳过）
claude mcp add codex -s user -- codex mcp-server
```

- `codex`（add 后面）— 注册名称。ARIS 的 skill 硬编码了这个名字，**不要改**
- `-s user` — 全局生效，所有项目都能用
- `codex mcp-server` — Codex CLI 内置的子命令，启动 MCP 服务模式

注册后需要**重启 Claude Code** 才会生效。验证：

```bash
claude mcp list | grep codex
# 应显示: codex: codex mcp-server - ✓ Connected
```

### 1.3 LaTeX 环境（可选）

工作流 3（论文写作）需要，含 `latexmk` 和 `pdfinfo`：

```bash
brew install --cask mactex    # 或: brew install basictex
brew install poppler          # 提供 pdfinfo

# 验证
latexmk --version && pdfinfo -v
```
> 如果只用工作流 1 和 2（找 idea + 自动 review），不需要安装 LaTeX 环境。

## 第二步：创建研究项目

```bash
mkdir ~/your-paper-project
cd ~/your-paper-project
git init
touch CLAUDE.md
```

- `git init` — 部分技能需要 git 来定位项目根目录
- `CLAUDE.md` — Claude Code 的项目配置文件，安装脚本会向其中写入 ARIS 信息

## 第三步：安装 Skills

通过符号链接将 ARIS skill 安装到项目中（推荐的项目级安装方式）：

```bash
# 1. 克隆 ARIS 一次到稳定位置，~/aris_repo 是本地目录名，可自定义
git clone https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git ~/aris_repo

# 2. 在每个使用 ARIS 的项目中安装（通过符号链接）：
cd ~/your-paper-project
bash ~/aris_repo/tools/install_aris.sh

# 只装需要的 skill（选择性安装）：
bash ~/aris_repo/tools/install_aris.sh --list-groups                  # 查看 10 个功能分组
bash ~/aris_repo/tools/install_aris.sh --groups paper-core,lit-search # 按组安装
bash ~/aris_repo/tools/install_aris.sh --skills paper-writing         # 按 skill 安装（依赖自动带上）
# 全新安装时不带任何选择参数（且在终端里跑）会进入交互式逐组选择菜单

# 其他常用：
bash ~/aris_repo/tools/install_aris.sh --dry-run        # 预览安装计划，不实际执行
bash ~/aris_repo/tools/install_aris.sh --uninstall      # 按安装清单卸载，不影响其他文件
```

脚本会显示安装计划并要求确认（输入 `y`），详见 [`install_aris.sh`](tools/install_aris.sh)：

```
.claude/skills/<skill>        ← 每个 skill 一个符号链接 → ~/aris_repo/skills/<skill>
.aris/installed-skills.txt    ← 安装清单（追踪 ARIS 创建的每条 skill symlink）
.aris/tools                   ← → ~/aris_repo/tools/（工具脚本）
CLAUDE.md                     ← 更新 ARIS 配置区块
```

符号链接直接引用 ARIS 仓库源文件，不复制内容。更新时分两种情况：

```bash
# 情况一：上游修改了已有技能的内容
# 符号链接自动生效，只需拉取最新代码
cd ~/aris_repo && git pull

# 情况二：上游新增或删除了技能目录
# 需要先拉取最新代码，再重新运行安装脚本
cd ~/aris_repo && git pull
cd ~/your-paper-project
bash ~/aris_repo/tools/install_aris.sh
```

## 第四步：配置 GPU 服务器

如果你的实验需要跑在远程 GPU 服务器上，需要两步：SSH 免密登录 + 写入服务器信息。

### 4.1 配置 SSH 免密登录

确保本地有 SSH 密钥，没有的话先生成：

```bash
ls ~/.ssh/id_*.pub
# 有输出 → 已有密钥，跳过下一条命令
# No such file → 执行：

ssh-keygen -t ed25519   # 一路回车即可
```

将公钥复制到服务器：

```bash
# 需要输入一次服务器密码
ssh-copy-id username@your-server-ip
```

验证免密登录（不应再要求输入密码）：

```bash
ssh username@your-server-ip "echo ok"
```

### 4.2 写入服务器信息

在项目的 `CLAUDE.md` 末尾添加以下内容，根据你的实际情况替换：

```markdown
## Remote Server

- gpu: remote
- SSH: `ssh username@your-server-ip` (key-based auth, no password)
- GPU: 8x RTX 4090 (24GB)
- Conda env: `YOUR_ENV` (Python 3.x + PyTorch x.x.x)
- Activate: `eval "$(/path/to/miniconda3/bin/conda shell.bash hook)" && conda activate YOUR_ENV`
- Code directory: `/home/user/experiments/`
- Use `tmux` for background jobs: `tmux new -d -s exp0 'bash -c "..."'`
```

也可以使用 `screen`：`screen -dmS exp0 bash -c '...'`（ARIS README 默认使用 `screen`）。

验证远程环境（在本地 Mac 上运行，替换为你的实际值）：

```bash
ssh username@your-server-ip 'eval "$(/path/to/miniconda3/bin/conda shell.bash hook)" && conda activate YOUR_ENV && python --version && python -c "import torch; print(torch.__version__, torch.cuda.device_count())"'
```

应输出 Python 版本、PyTorch 版本和 GPU 数量。

## 第五步：初始化 Research Wiki

Research Wiki 是 ARIS 的核心知识库，自动积累你整个研究过程中读过的论文、产生的想法、跑过的实验。其他 skill 会自动往里写入内容，你不需要手动维护。

在研究项目目录下打开 Claude Code，输入：

```
/research-wiki init
```

它会创建 `research-wiki/` 目录，详见 [`research_wiki.py`](tools/research_wiki.py)：

```
research-wiki/
  index.md               ← 分类索引（自动生成）
  log.md                 ← 时间线日志
  gap_map.md             ← 领域空白地图
  query_pack.md          ← 压缩摘要（供 /idea-creator 使用）
  papers/                ← /alphaxiv、/arxiv 等自动写入
  ideas/                 ← /idea-creator 自动写入
  experiments/           ← /result-to-claim 自动写入
  claims/                ← 科学声明
  graph/                 ← 关系图谱（edges.jsonl）
```

## 第六步：验证

重启 Claude Code，在研究项目目录下测试：

**1. 测试 MCP 连通性** — 在 Claude Code 中输入：

```
用 codex MCP 问一下 GPT：1+1 等于几
```

收到 GPT 的回答说明跨模型通信正常。

**2. 测试技能识别** — 在 Claude Code 中输入：

```
/alphaxiv https://arxiv.org/abs/1706.03762
```

正常调用说明技能安装成功。该技能还会自动将论文写入 Research Wiki，你可以在 `research-wiki/papers/` 下查看。

---

全部完成后，你的研究项目结构如下：

```
~/your-paper-project/
  CLAUDE.md               ← ARIS 配置 + GPU 服务器信息
  .claude/skills/          ← 技能符号链接
  .aris/
    installed-skills.txt   ← 安装清单
    tools/                 ← → ARIS 仓库 tools/
  research-wiki/           ← 知识库（自动积累）
  .git/                    ← git 仓库
```

接下来就可以开始使用 ARIS 的研究工作流了：

```
claude
> /idea-discovery "你的研究方向"              # 工作流 1 — 方向要具体！不要 "NLP"，要 "离散扩散语言模型的 factorized gap"
> /experiment-bridge                         # 工作流 1.5 — 有计划了？实现 + 部署 + 收结果
> /auto-review-loop "你的论文主题或范围"         # 工作流 2：审稿 → 修复 → 再审，一夜完成
> /paper-writing "NARRATIVE_REPORT.md"       # 工作流 3：研究叙事 → 精修 PDF
> /rebuttal "paper/ + reviews" — venue: ICML  # 工作流 4：解析 review → 起草 rebuttal → follow-up
> /resubmit-pipeline "paper/" — venue: NeurIPS  # 工作流 5：移植到新 venue（纯文本，不跑新实验）
> /paper-talk "paper/" — venue: ICLR            # 工作流 6：论文 → Beamer + PPTX + 讲稿 + 评审审计
> /research-pipeline "你的研究方向"            # 全流程：W1 → 1.5 → 2 → handoff；默认到 NARRATIVE_REPORT.md 停。加 `— auto_write: true, venue: ICLR` 才连 W3 写论文
```
