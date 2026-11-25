# Antigravity 复核协议（定时任务通用契约）

> **本文件是唯一契约。** 各定时任务 SKILL.md 只写三件事：**审查对象 / 审查标准 / 处理方式**；
> 工具调用方式、隐私红线、降级策略、模型档位一律以本文件为准，SKILL.md 不重复、也不得与之冲突。
>
> **权威副本（本文件）**：`/Users/yihanglv/Developer/aris_repo/mcp-servers/antigravity-exec/aris-antigravity-review-protocol.md`
> **本机路径**：`~/.claude/aris-antigravity-review-protocol.md` —— 指向权威副本的**符号链接**。
> **改协议请改仓库内本文件**，改完由 `bash <aris_repo>/tools/install_aris.sh "$HOME" --all` 同步；
> 不要直接编辑 `~/.claude/aris-antigravity-review-protocol.md`（它是链接，改它等于改仓库源）。
>
> 本协议第 2–7 节的每一条都经过 Antigravity 独立审查并据此修订（2026-11-24）。
> 第 0 节（对 ARIS 通用约定的显式偏离）与附录 A 于 2026-11-24 收编进 ARIS 时新增。

---

## 0. ⛔ 对 ARIS 通用约定的显式偏离（`cwd` 与送审方式）

ARIS 的通用审阅约定见 `skills/shared-references/reviewer-backends.md`：

> "Artifact-grounded reviews still give the reviewer primary file paths and ask it
> to read them. Set cwd to a directory that contains the review inputs."

该约定适用于**本机内部产物**的评审（论文草稿、实验结果、代码）：审阅者读的是用户自己的
文件，路径本身不构成风险。

**本管线不适用该约定。这是一处显式偏离，禁止被"改回去"。**

本管线审阅的是**即将外发到外部平台**的内容（社区评论 / 帖子、评测文案、公众号选题、
FlowUs 摘要）。Antigravity 是**外部模型服务**，且已实测：

> **它能读到自身工作目录下的任何文件，并把该目录的绝对路径写进上下文。**

因此本管线的契约与 ARIS 通用约定**方向相反**：

| | ARIS 通用约定 | 本管线（显式偏离） |
|---|---|---|
| 待审文本 | 给文件路径，让审阅者自己读 | **在内存中脱敏后内联进 `prompt`**（§2.2） |
| `cwd` | 指向装着 review inputs 的目录 | **恒为 `/tmp`**（§2.4） |
| 脱敏副本 | 不适用 | **严禁落盘**（§2.2） |

若把 `cwd` 改回业务目录（`~/Documents/...`、仓库目录、`$TMP_DIR`），等于把
**本机用户名 + 业务路径 + 同目录下未脱敏原件**一并递给外部模型。
**禁止照 ARIS 通用约定把 `cwd` 改成 review inputs 目录。**

除本节外，本协议其余条款与 ARIS 通用约定一致：工具名、model/effort 钉死、完成性检查
（`status=SUCCESS`）、`REVIEW_UNAVAILABLE` 语义、续接工具的适用范围、每轮调用预算。
ARIS 侧对本次偏离的登记见 `skills/shared-references/reviewer-backends.md` 的
**"Exception — outbound-publication pipelines"** 段。

---

## 1. 工具契约

| 项 | 值 |
|---|---|
| 工具 | `mcp__antigravity__antigravity` |
| `cwd` | **恒为 `/tmp`**。见 §2.4 —— 这是硬约束，不是建议 |
| `prompt` | **直接内联**脱敏后的待审文本 + 审查要求。不传文件路径让对方去读盘 |
| `model` / `effort` | 见下表；**`effort` 必须与模型名后缀一致**（`gemini-4-hydrogen-high` → `high`）。不一致时 CLI 直接报错 `conflicts with --effort` |

| 复核模型 | model | effort |
|---|---|---|
| **统一档，不分轻重** | `gemini-4-hydrogen-high` | `high` |

> 复核模型统一为 **Gemini 4 Hydrogen (High)**，不按任务类型分档。CLI 实测回传
> `selectedModelLabel: "Gemini 4 Hydrogen (High)"`、`effortSource: cli_selected_model_variant`。
> **`effort` 必须与模型名后缀一致**（`gemini-4-hydrogen-high` → `high`）；不一致时 CLI 直接报
> `conflicts with --effort` 或 `invalid model selection`。

> 桥接已注册在 user scope，**自身已带代理环境**（`http_proxy` / `https_proxy` / `all_proxy` 指向 `127.0.0.1:7890`），
> 任务里**不要**自行设置代理变量，也**不要**因为"没设代理"而判定调用失败。
>
> **续接工具 `mcp__antigravity__antigravity-reply` 默认禁用**，仅在 §6 首次返回 `unusable` 补齐材料重送那一次允许使用，
> 其余任何情况禁止调用（严禁多轮追问、严禁复审）。

---

## 2. ⛔ 隐私红线（优先级高于本任务其余一切）

Antigravity 是**外部模型服务**。送审材料必须同时满足：

### 2.1 只送该送的内容

1. **只送「本轮即将外发的内容」或「其目的地本就是外部的内容」**；
2. **严禁送入**：API Key / 凭据 / token（`credentials.json`、`~/.cdsapirc`、`.env` 等）、
   未发表手稿或论文正文、投稿期刊名、稿中未公开的具体数值、
   本机真实路径、个人姓名、账号标识、
   `research_context`、`preflight_latest.json`、`MEMORY.md`、`research-workflow.md`
   等**明文标注"仅供本机判读"**的上下文、
   `~/.minimax/agents/mavis/memory/` 下的归档全文。

### 2.2 脱敏在内存里做，不要落盘

- 对待审文本做替换：**本机路径 → `<PATH>`、姓名 → `<NAME>`、稿中未公开的具体数值 → `<NUM>`**。
- **公开数值、日期、版本号、arXiv/DOI 编号一律保留**（把公开数字也脱敏会让文本不可读）。
- **严禁在磁盘上新建或删除任何脱敏副本文件**——新建/删除本身就是新增写操作，会撞上本任务的写白名单与安全护栏。
- 脱敏后的文本**直接作为字符串拼进 `prompt`**。

### 2.3 占位符必须声明

在 `prompt` 里**必须**附上这一句，否则对方会把占位符当成未替换的模板变量误报：

> 文中的 `<PATH>`、`<NAME>`、`<NUM>` 是送审前刻意脱敏的占位符，原件中已有真实值。请勿将占位符本身报为问题，也请勿因此判定 `unusable`。

### 2.4 `cwd` 恒为 `/tmp`（这是已验证的泄漏面）

**实测**：Antigravity 能读到自身工作目录下的任何文件，并把该目录的绝对路径写进上下文。
所以 `cwd` 一旦指向业务目录（`~/Documents/...`、仓库目录、`$TMP_DIR`），
就等于把**本机用户名 + 业务路径 + 同目录下未脱敏原件**一并递给了外部模型。

> 本条是 **§0 对 ARIS 通用约定的显式偏离**：通用约定要求 `cwd` 指向 review inputs 目录，
> 本管线**必须相反**。**禁止照 ARIS 通用约定改回去。**

**因此**：
- `cwd` **只能是 `/tmp`**；
- 待审文本**一律内联进 `prompt`**，不要让对方去读你的业务目录；
- 若确需对方读文件，只允许读 `/tmp` 下你**本轮自己写的、已脱敏**的文件；
- 在 `prompt` 里明确写一句：**「只审下面内联的文本，不要自行读取工作目录下的其他文件」**。

---

## 3. 审查要求（写进 `prompt` 的固定骨架）

要求 Antigravity **只报有据可依的具体问题**，按此结构回答：

```
1. verdict: clean | issues_found | unusable
2. issues: 逐条 —— 位置或原文引用 + 问题 + 具体改法
3. must_fix: 必须改的硬伤（事实/逻辑自相矛盾、指令或代码会跑错、明显残缺或损坏）；没有就填 none
4. nice_to_have: 可选改进；没有就填 none
5. confidence: high | medium | low
```

同时必须交代清楚四件事，否则它会替你做判断：

- **它只读不写**：不得假设自己能修改文件，每条问题都要给出「具体改法」；
- **它不是本任务的验收人**：字数上限、脱敏规则、限流上限、路径核验、闸门判据**由本任务自己的硬门禁把关**，
  它只提问题，不替你放行也不替你否决。因此**不要**让它把"字数超限""脱敏不彻底"判成 `must_fix`
  ——它看到的是截断且带占位符的片段，做不了这种机械校验，这类判断只会有假阳性；
- **占位符是正常的**（§2.3）；
- **宁缺毋滥**：没有真问题就回 `clean`，不许为了显得有用而编造问题。

---

## 4. 处理方式（决定这一轮怎么走）

| 复核结果 | 动作 |
|---|---|
| `must_fix` 非空 | **先把改法映射回原件修正**（见下方三条约束），再执行外发命令。**改后不复审**（防循环） |
| `must_fix` 为空（含 `verdict: clean`，或 `issues_found` 但只有 `nice_to_have`） | 直接进入外发步骤。`nice_to_have` 本轮不改，防画蛇添足 |
| `unusable`（材料本身没写清） | 视为 `must_fix` 处理：**在**脱敏**前提下**把材料补齐再送审一次，**最多重送一次**。补齐时**绝不可**为了"让对方看懂"而补入未脱敏原件、未截断全文或禁送上下文 |
| 工具报错 / 状态非 SUCCESS / 超时 / **返回内容未按 §3 结构输出** | **绝不重试、绝不阻塞本任务**：记 `REVIEW_UNAVAILABLE`，按原流程继续外发 |

### 修正时的三条硬约束（防占位符污染原件）

1. **切勿把 `<PATH>` / `<NAME>` / `<NUM>` 占位符写进原件** —— 那是脱敏产物，不是正文；
2. 若某条改法**违反本任务自己的硬门禁**（字数上限、格式、脱敏规则、限流），**忽略该条**；
3. 改完**必须重新过一遍本任务原有的本地硬门禁**（字数/格式/脱敏校验），确认仍然通过，再执行外发命令。

> **改后不复审。** 修正后的原件**直接进入外发**，不再送第二轮 Antigravity。
> 复审等于让修复者验收自己的修复，会变成循环；§6 的「总计 ≤ 2 次」里的第二次，
> **只留给 §4 的 `unusable` 补送**这一种情形。

> **降级是「放行」，不是「否决」。** 这些定时任务自带硬门禁，复核只是额外的第二双眼睛；
> Antigravity 侧故障不该让整条科研/策展流水线停摆。
> 但 `REVIEW_UNAVAILABLE` 必须留下痕迹：任务回执里**若有**「本轮识别但未执行」一类栏目就写进去；
> 回执是单行零打扰格式的任务则静默继续。

---

## 5. 留痕

**不新增任何写操作。** 复核结论只体现为：(a) 待审内容的修正、(b) 回执里的一句说明（若该任务回执格式允许）。
不新建日志文件、不写 `review_logs/`——那些路径往往不在本任务「仅授权执行的写操作」白名单里。

需要事后追溯时，Antigravity 侧的会话记录在 `~/.codex/state/antigravity-exec/threads/`（按 `threadId` 索引）。

---

## 6. 成本控制

- **每轮最多 1 次复核调用**；仅当首次返回 `unusable` 时可补送 1 次，**总计 ≤ 2 次**。
- 补送那一次**才允许**用 `mcp__antigravity__antigravity-reply`（只传 `threadId` 与 `prompt`，沿用首次的 cwd/model/effort）。
- 待审文本控制在 **~200 行以内**；超长先自己截取关键段落再内联。
- 空轮 / 跳过分支 / 无产出的轮次**一律不调用**。

---

## 附录 A · ARIS 技能与工具链调用约定（非审查位）

本附录供各定时任务的**上游执行阶段**（Antigravity 复核之前）使用。**审查位不受本附录影响。**

### A.1 工具链解析链（各任务统一用这一段，不要各写各的）

ARIS 的 helper 可能位于四层之一。按 `skills/shared-references/integration-contract.md` §2 的规范链解析：

```bash
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" || exit 1
if [ -z "${ARIS_REPO:-}" ] && [ -f .aris/installed-skills.txt ]; then
    ARIS_REPO=$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills.txt 2>/dev/null) || true
fi
if [ -z "${ARIS_REPO:-}" ] && [ -f "$HOME/.aris/repo" ]; then
    ARIS_REPO=$(cat "$HOME/.aris/repo" 2>/dev/null) || true
fi
HELPER=".aris/tools/<helper>"
[ -f "$HELPER" ] || HELPER="tools/<helper>"
[ -f "$HELPER" ] || { [ -n "${ARIS_REPO:-}" ] && HELPER="$ARIS_REPO/tools/<helper>"; }
[ -f "$HELPER" ] || HELPER=""
```

> 定时任务**没有**项目内 `.aris/`，实际命中的是第 4 层（`$HOME/.aris/repo` → `/Users/yihanglv/Developer/aris_repo`）。
> 本机 `~/.aris/tools` 是个**失效的旧链接**（指向不存在的 `/Users/yihanglv/aris_repo/tools`），解析链会自然跳过它。

### A.2 本管线可用的 ARIS 文献/元数据技能

| ARIS 技能 | helper | 典型调用 | 落盘 |
|---|---|---|---|
| `arxiv` | `arxiv_fetch.py` | `python3 "$ARXIV_FETCHER" search "id:<ARXIV_ID>" --max 1` | **search 不落盘**；`download` 子命令会写 PDF，**禁用** |
| `openalex` | `openalex_fetch.py` | `python3 "$OPENALEX_FETCHER" work "10.<DOI>"` ／ `search "<标题>" --max 3` | 不落盘 |
| `semantic-scholar` | `semantic_scholar_fetch.py` | `python3 "$S2_FETCHER" search "<QUERY>" --max 5` | 仅当 cwd 下存在 `research-wiki/` 时会写，故**必须在无 `research-wiki/` 的目录执行** |
| `research-lit` | 多个 | `/research-lit "<方向>"`（ARIS 技能入口） | 写 `.aris/verify-papers/**`、可选 `papers/`、`research-wiki/` —— **cwd 必须是本任务允许的写根或 `/tmp`** |

### A.3 本机可用性（2026-11-25 实测，定时任务跑在无人值守环境）

| 技能 | 可用性 | 说明 |
|---|---|---|
| `arxiv` | ✅ 可用 | 无需 key、无需 MCP；PDF 下载有 1 s 间隔与 429 退避，**本管线只做元数据核验，不下载 PDF** |
| `openalex` | ✅ 可用 | 无需 key（`requests` 已装）；结果含 venue / 年份 / 引用数 / OA / DOI |
| `semantic-scholar` | ⚠️ 可用但限流 | 无 `SEMANTIC_SCHOLAR_API_KEY` 时约 1 req/s，429 须**放弃本轮该调用**、不得死等 |
| `research-lit` | ✅ 降级可用 | 仅 arXiv / OpenAlex / Semantic Scholar 三个源会贡献结果；**至少一个源有结果才继续** |
| `exa-search` | ❌ 不可用 | 本机无 `exa_py` 模块、无 `EXA_API_KEY`；ARIS 侧策略是「不降级、直接报错」，**本管线不使用** |
| `gemini-search` | ❌ 不可用 | 本机未注册 `gemini-cli` MCP、未装 `gemini` / `gemini-mcp` CLI、无 `GEMINI_API_KEY`，**本管线不使用** |
| `citation-crosscheck` | ✅ 前置已就绪 | `openpyxl 3.1.5` 在默认 `python3`（`/opt/miniconda3/bin/python3` 3.13.9）与登录 shell 的 `/usr/bin/python3` 3.9.6 上**均可导入**；仍受 A.6 的产物变化门控与 staging 约束 |
| `meta-optimize` | ⚠️ hook 已装、数据待积累 | ARIS meta-logging hook 已装进全局 `~/.claude/settings.json`，日志固定写 `~/Documents/Research_Progress/.aris/meta/events.jsonl`（**不污染任何项目仓库**）；`/meta-optimize` 的就绪阈值是 ≥5 条 `skill_invoke`，不足时它自己告警跳过 |

> 结论：文献真实性核验在定时管线里**只用 `arxiv` + `openalex`（必要时 `semantic-scholar`）**，
> 不要把 `exa-search` / `gemini-search` 写进定时任务，否则每轮必然失败。
>
> **`python3` 有两个解释器**（默认 `/opt/miniconda3/bin/python3` 3.13.9；登录 shell 的
> `/usr/bin/python3` 3.9.6），二者现都已具备 `requests` 与 `openpyxl`；ARIS helper 一律以
> `python3 "$HELPER"` 调用，实际解释器取决于当轮 shell 的 PATH。

### A.4 写操作纪律（ARIS 技能会写文件）

1. **文献检索一律在 `/tmp` 下的空目录执行**（`cd /tmp && python3 "$ARXIV_FETCHER" …`），
   这样 `papers/`、`research-wiki/` 之类的相对写不会落进业务目录；
2. **禁用 `arxiv` 的 `download` 子命令**（会写 PDF）；只做 `search`；
3. 需要落盘的 ARIS 技能（`research-lit`、`citation-audit`、`citation-crosscheck` 等），
   **cwd 必须设成本任务「仅授权执行的写操作」白名单内的根目录**（如 `~/Documents/Research_Progress/`）
   或本任务自己的 `/tmp` 隔离目录；产物用完即随隔离目录清除；
4. **绝不**把 ARIS 技能指向用户科研目录直接跑（会在用户仓库里留下 `.aris/`、`*.xlsx`、`AUDIT.md` 等未跟踪产物）。

### A.5 本管线**明确不使用**的 ARIS 技能及理由

| 技能 | 不使用的理由 |
|---|---|
| `research-review` | 多轮对话式评审（无机器可读 verdict、无固定轮数上限）、默认 backend 是 Codex `gpt-6-astra` 而非 Antigravity、自带 🔒 禁止被 `/schedule`/`CronCreate` 包裹。与硬约束 A（审查位唯一、≤ 2 次预算）直接冲突 |
| `auto-review-loop` / `auto-review-loop-llm` | `MAX_ROUNDS = 4` 的 review→fix→re-review 循环，产出是评分 + `verdict∈{ready,almost,not ready}`（不是逐条 must_fix），会变成验收人而非问题清单；自带 🔒；`auto-review-loop-llm` 所需的 `llm-chat` MCP 与 API key 本机也没有 |
| `proof-checker` | 结构上是**多轮**改-复审循环（`MAX_REVIEW_ROUNDS = 3`，Phase 3 用 `codex-reply` 续接线程记忆），且会**直接改写证明 `.tex` 源文件**；没有只读报告模式。自带 🔒 |
| `idea-discovery` | 其阶段链内含 `/research-review`，且 Phase 5 需要 GPU pilot；链内任何一环都会在定时管线里引入第二个外部评审权威 |
| `idea-creator` | 需要外部 jury（Codex）+ GPU pilot + `idea-stage/` 产物树；本机无本地论文语料（`papers/`、`literature/`）可供其 landscape survey，与本管线「无产物树、严守写白名单」的形态不匹配 |
| `meta-apply` | **只能由人手动 `/meta-apply` 落地**（ARIS 明文：landing gate 留在人手里）。定时任务**永不自动调用**它；只能把它作为「需用户拍板」的落地路径写进待办 |
| `exa-search` / `gemini-search` | 本机不可用，见 A.3 |

### A.6 可用的"一次性自审"技能与激活条件

`citation-audit`、`citation-crosscheck`、`result-to-claim`、`paper-claim-audit`、`experiment-audit`
在 ARIS 侧都是**单趟、非循环**的（无 `MAX_ROUNDS`；产出逐条 `must_fix` / `KEEP·FIX·REPLACE·REMOVE` /
`claim_supported` / per-claim `Fix:`，不是分数 + verdict）。它们同样自带
🔒「Do not wrap this skill in `/loop`, `/schedule`, or `CronCreate`」。

该 🔒 的理由是：**对不变产物按墙钟重跑裁决不会产生新信号**。因此在本管线中一律按
ARIS 自己给出的解法落地 —— **把"裁决"绑在产物变化上，而不是绑在时钟上**：

1. **激活判据（可观测，二者同时满足才跑）**：
   (a) 目标产物在本轮证据里**确实存在**（`.bib` / 手稿 `.tex` / 结果目录 / 实验目录）；
   (b) 该产物的身份标识（路径 + mtime 或内容 hash）**与上次审计记录的记录不同**。
2. **一次只跑一种**，且**每轮最多一次**外部审阅调用；
3. **只取第一趟的结果**，不进 ARIS 的修复/复审阶段（不跑 `proof-checker` 的 Phase 2/3、
   不跑 `citation-audit` 的 Step 6 交互修 `.bib`、不跑 `citation-crosscheck` 的 Step 5 改 `.bib`）；
4. **产物一律 staging**：把待审产物复制到本任务允许写根下的暂存目录再跑，
   绝不在用户的活文件树里跑、绝不让 ARIS 改用户的稿件或 `.bib`；
5. **失败即跳过**：审阅方不可用 / 产物缺失 / 证据不充分 → 记 `REVIEW_UNAVAILABLE`，本轮照常继续，
   绝不阻塞，也绝不因此判定材料不合格；
6. 它们的结论**只作为上游输入**：具体问题写进被审材料，再交给 §3 的 Antigravity 复核，
   **它们不是验收人**（`skills/shared-references/acceptance-gate.md`：
   "A goal/loop can DRIVE; it cannot ACQUIT."）。

> 本管线的**唯一**复核位始终是 §1–§4 的 Antigravity。A.6 的技能全部发生在它**之前**，
> 且**一律不得**路由到 Antigravity backend（否则会吃掉 §6 的 ≤ 2 次预算并与审查位争抢模型）：
> 调用时显式指定 `— reviewer: codex`，或让它们保持 ARIS 默认的 Codex backend。
