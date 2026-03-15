# OpenClaw 适配指南（ARIS Workflow）

> 目标：在**没有 Claude Code slash 技能**的情况下，把 ARIS 的核心流程迁移到 OpenClaw 对话式执行。

## 1. 适配思路

ARIS 的本质是「科研流程编排」：

- Workflow 1：文献 → 想法 → 新颖性/可行性评估
- Workflow 2：实验执行 → 自动评审循环 → 迭代修复

在 OpenClaw 中，可用“阶段化任务 + 文件化产出”替代 slash skill。

---

## 2. 对应关系（ARIS → OpenClaw）

| ARIS /skill | OpenClaw 等价执行方式 | 产出文件 |
|---|---|---|
| `/research-lit` | 让 agent 执行文献扫描与结构化综述 | `outputs/lit_scan.md` |
| `/idea-creator` | 让 agent 生成候选方案 + MVP + 失败信号 | `outputs/idea_report.md` |
| `/run-experiment` | 生成实验矩阵、运行命令、日志路径规范 | `outputs/experiment_plan.md` / `outputs/runbook.md` |
| `/auto-review-loop` | 轮次化评审（评分+最小修复动作） | `outputs/review_loop.md` |
| 全流程 | 分阶段串联执行 | `outputs/final_summary.md` |

---

## 3. 最小可跑流程（可直接复制）

### 阶段1：文献扫描
```text
执行阶段1：按课题做文献扫描，输出 outputs/lit_scan.md，并给出5条研究空白。
```

### 阶段2：想法生成
```text
执行阶段2：基于 outputs/lit_scan.md 生成3个 idea，输出 outputs/idea_report.md，并给出 Top1/Top2。
```

### 阶段3：实验剧本
```text
执行阶段3：基于 Top1 生成实验矩阵与周计划，输出 outputs/experiment_plan.md 和 outputs/runbook.md。
```

### 阶段4：评审循环
```text
执行阶段4：开始 review loop，最多4轮；每轮输出评分、短板、最小修复动作，更新 outputs/review_loop.md。
```

---

## 4. OpenClaw 实施建议

1. **文件优先**：每阶段必须有明确文件产出，避免上下文漂移。  
2. **轮次控制**：review loop 默认最多 4 轮，避免无穷迭代。  
3. **证据可追溯**：涉及史料/数据时，强制记录来源与定位字段。  
4. **同步机制**：本地文件可同步到飞书文档，便于跨端审阅。  
5. **升级安全**：修改前先做备份提交，再做正式改动提交。

