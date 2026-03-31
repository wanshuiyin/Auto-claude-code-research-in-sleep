# Experiment Tracker

| Run ID | Milestone | Purpose | System / Variant | Split | Metrics | Priority | Status | Notes |
|--------|-----------|---------|------------------|-------|---------|----------|--------|-------|
| R001 | M0 | sanity | ResNet-18 retrain oracle | clean CIFAR-100 + `F_random` | retain acc, forget gap | MUST | TODO | establish oracle |
| R002 | M0 | sanity | ResNet-18 retain-only FT | clean CIFAR-100 + `F_random` | retain acc, forget gap | MUST | TODO | cheap baseline |
| R003 | M0 | sanity | ResNet-18 ascent-style local unlearning | clean CIFAR-100 + `F_random` | retain acc, forget gap | MUST | TODO | compare to R001/R002 |
| R004 | M1 | shift | source-trained systems on `T_noise` | CIFAR-100-C noise + `F_random` | OOD gap, retain acc | MUST | TODO | first target family |
| R005 | M1 | shift | source-trained systems on `T_blur` | CIFAR-100-C blur + `F_random` | OOD gap, retain acc | MUST | TODO | second target family |
| R006 | M1 | shift | source-trained systems on `T_digital` | CIFAR-100-C digital + `F_random` | OOD gap, retain acc | MUST | TODO | third target family |
| R007 | M1 | shift | source-trained systems on `T_blur` | CIFAR-100-C blur + `F_cluster` | OOD gap, retain acc | MUST | TODO | harder semantic shift |
| R008 | M0 | diagnostic | FSS/RFE extraction | clean vs `T_noise` / `T_blur` / `T_digital` | FSS, RFE, LR | MUST | TODO | verify expected direction |
| R009 | M2 | theory | synthetic linear sweep | controlled overlap grid | OOD gap vs FSS/RFE | MUST | TODO | theorem validation |
| R010 | M3 | prediction | index vs naive forget score | all completed source-target pairs | corr, AUROC | MUST | TODO | core predictor table |
| R011 | M4 | actionability | choose/abstain policy | completed shift pairs | risk-cost frontier | MUST | TODO | practical value |
| R012 | M5 | extension | severity sweep or second backbone | strongest shift family + `F_cluster` | OOD gap | NICE | TODO | only after main story holds |
