# `skills-codex` 说明

这是主线 `skills/` 的 Codex 原生镜像 / 适配层，不是独立主线产品。

## 当前范围

- 基座覆盖：主线 `skills/` 的 `88` 个 skill 全量同步
- 支持目录：`shared-references/`，与主线 `30/30` 名称完整对齐
- reviewer-heavy skill 的默认 reviewer 契约：
  - 首轮：`spawn_agent`
  - 续接：`send_input`
  - 模型：`gpt-6-astra`；deep 审阅 `ultra`，regular 审阅 `xhigh`
  - 基础 Codex 自审：`review_independence: same-family`、
    `acceptance_status: provisional`
  - 其他 reviewer：在完整包中选择后端；验收取决于实际模型身份、已完成的审阅范围及对应 gate

## 推荐安装方式

Codex 路线默认推荐项目级安装：

```bash
git clone https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git ~/aris_repo
cd ~/your-project

bash ~/aris_repo/tools/install_aris_codex.sh .
```

安装后会形成扁平布局：

```text
.agents/skills/<skill-name> -> ~/aris_repo/skills/skills-codex/<skill-name>
.aris/installed-skills-codex.txt
AGENTS.md   # 自动写入 Codex 管理块
```

上游更新后收敛：

```bash
cd ~/aris_repo && git pull
bash ~/aris_repo/tools/install_aris_codex.sh ~/your-project --reconcile
```

只卸载受管的 Codex skill：

```bash
bash ~/aris_repo/tools/install_aris_codex.sh ~/your-project --uninstall
```

## 选择 Reviewer

完整包支持[可选 reviewer](shared-references/reviewer-backends.md)。单次调用可加
`— reviewer: antigravity`，也可选 `grok`、`claude-code` 或 `codex`。
项目默认值由用户创建 `.aris/reviewer.json`：

```json
{"backend": "antigravity", "model": "gemini-4-argon-high", "effort": "high"}
```

按链接中的契约单独注册相应 MCP。`claude-code` 使用 CLI 已配置的 provider，
不接受 effort 覆盖。选择通道本身不代表跨家族审阅或通过验收。
旧 `agy` 路由仍用 `gemini-review`，与 `antigravity` 不同。

## 迁移已冻结的 Partial Overlay

`skills-codex-claude-review/` 和 `skills-codex-gemini-review/` 作为旧快照冻结。
保留目录和已有链接，但完整包的技能更新不再触发它们重新生成。新安装使用完整包；
旧 overlay 安装参数仅供兼容，不表示继续同步功能。

**项目受管 symlink：** 先用 `readlink` 检查 `.agents/skills/<name>`，备份
`.aris/installed-skills-codex.txt` 及定制过的源文件。编辑 symlink 指向的技能就是
编辑仓库目标文件，切换前须保留这些改动。省略两种 overlay 参数，先预览：

```bash
bash ~/aris_repo/tools/install_aris_codex.sh ~/your-project --reconcile --dry-run
```

确认计划中的链接改指向 `skills/skills-codex/` 后，再去掉 `--dry-run` 执行。
真实目录会被报告为冲突，不会被替换。未受管的旧链接须先确认目标，再只对相应技能
加 `--replace-link <skill-name>`，同样先预览。保留旧 overlay 目录；个人改动按需
手动合并到选定的完整包源文件。

**全局复制安装：** 将 `~/.codex/skills/` 中受影响的技能目录备份到该发现目录之外。
逐个比较已安装技能、冻结 overlay 源和对应完整包技能，单独保留个人改动。
在临时目录准备完整包替换项，重新合并定制并检查后，只替换已核对的技能目录。
不要把整个 overlay 盖回完整包，也不要批量覆盖现有技能。随后设置项目 reviewer
配置并注册对应桥接。这里没有自动写入全局设置的迁移命令；安装变更后重启 Codex
以重新加载技能。

## Copy 安装与更新

如果你明确想用 copy 安装，而不是受管 symlink：

```bash
mkdir -p ~/.codex/skills
cp -a ~/aris_repo/skills/skills-codex/. ~/.codex/skills/
```

更新 copy 安装请使用：

```bash
bash ~/aris_repo/tools/smart_update_codex.sh
bash ~/aris_repo/tools/smart_update_codex.sh --apply
```

项目级 copy 安装则使用：

```bash
bash ~/aris_repo/tools/smart_update_codex.sh --project ~/your-project
bash ~/aris_repo/tools/smart_update_codex.sh --project ~/your-project --apply
```

`smart_update_codex.sh` 会拒绝更新由 `install_aris_codex.sh` 管理的 symlink 安装，并提示改用 `install_aris_codex.sh --reconcile`。

## 不允许降级的 Skill

以下 4 个 skill 不允许静默降级：

- `comm-lit-review`
- `research-lit`
- `paper-poster-html`
- `pixel-art`

如果缺少所需能力，必须明确提示用户去配置，不允许自动改成简化路径继续跑。
