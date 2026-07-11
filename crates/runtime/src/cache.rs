//! Cache directory management for bundled ARIS skill helpers.
//!
//! v0.4.8 introduces a global versioned cache at `~/.config/aris/cache/<version>/`
//! that replaces the cwd-based extraction model from v0.4.7 and earlier. The
//! cache materialises [`BUNDLED_RESOURCES`](crate::BUNDLED_RESOURCES) at process
//! startup so that:
//!
//! 1. SKILL.md helper paths resolve consistently regardless of the user's cwd
//! 2. Bash subprocesses inherit `$ARIS_CACHE_DIR` and find helpers via it
//! 3. cwd is never polluted with bundled helper files
//!
//! See `idea-stage/v0.4.8/T1_cache_design.md` and `T2_extraction_report.md`.

use serde::Serialize;
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

/// Process-global extraction report. Set exactly once by [`extract_bundle`].
static EXTRACTION_REPORT: OnceLock<ExtractionReport> = OnceLock::new();

/// Full process-level extraction report. Produced once at startup.
#[derive(Debug, Clone, Serialize)]
pub struct ExtractionReport {
    /// Aris CLI version this cache belongs to (`CARGO_PKG_VERSION`).
    pub version: String,

    /// Final cache root that was actually used. `None` iff [`Self::hard_error`].
    #[serde(skip_serializing_if = "Option::is_none")]
    pub used_dir: Option<PathBuf>,

    /// True iff both home-cache and temp-dir fallback failed. Bundled helpers
    /// are unavailable; skills fall back to layer 4 (project workspace) or fail.
    pub hard_error: bool,

    /// Fallback chain attempted, each entry human-readable. Consumers should
    /// not parse these.
    pub paths_tried: Vec<String>,

    /// Relative bundle keys that were extracted successfully
    /// (e.g. `"tools/arxiv_fetch.py"`, `"skills/research-wiki/research_wiki.py"`).
    pub extracted: Vec<String>,

    /// Per-file failure entries. Empty on full success.
    pub failed: Vec<ExtractionError>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ExtractionError {
    pub key: String,
    pub error: String,
}

/// Returns the global [`ExtractionReport`] set by [`extract_bundle`].
///
/// `None` only in test code that bypasses startup. Production code paths
/// (which always run [`extract_bundle`] first via `aris-cli` main) always see
/// `Some`.
#[must_use]
pub fn extraction_report() -> Option<&'static ExtractionReport> {
    EXTRACTION_REPORT.get()
}

/// Materialise [`BUNDLED_RESOURCES`](crate::BUNDLED_RESOURCES) to a cache
/// directory.
///
/// 1. Tries `~/.config/aris/cache/<version>/` first.
/// 2. On home failure (permission, disk, missing HOME, etc.), falls back to
///    `std::env::temp_dir()/aris-cache-<version>/`.
/// 3. If both fail, returns a report with `hard_error = true`.
///
/// Idempotent: only the first call sets the global; subsequent calls return
/// the same report.
pub fn extract_bundle() -> &'static ExtractionReport {
    EXTRACTION_REPORT.get_or_init(extract_bundle_inner)
}

fn extract_bundle_inner() -> ExtractionReport {
    let version = env!("CARGO_PKG_VERSION").to_string();
    let mut paths_tried = Vec::new();

    // Layer 1: home cache
    let home_cache = home_cache_dir(&version);
    match try_extract_to(&home_cache) {
        Ok((extracted, failed)) => {
            paths_tried.push(format!("{} (ok)", home_cache.display()));
            return ExtractionReport {
                version,
                used_dir: Some(home_cache),
                hard_error: false,
                paths_tried,
                extracted,
                failed,
            };
        }
        Err(err) => {
            paths_tried.push(format!("{} ({})", home_cache.display(), err));
        }
    }

    // Layer 2: temp-dir fallback
    let temp_cache = std::env::temp_dir().join(format!("aris-cache-{version}"));
    match try_extract_to(&temp_cache) {
        Ok((extracted, failed)) => {
            paths_tried.push(format!("{} (ok)", temp_cache.display()));
            return ExtractionReport {
                version,
                used_dir: Some(temp_cache),
                hard_error: false,
                paths_tried,
                extracted,
                failed,
            };
        }
        Err(err) => {
            paths_tried.push(format!("{} ({})", temp_cache.display(), err));
        }
    }

    // Both failed — hard error, no usable cache dir
    ExtractionReport {
        version,
        used_dir: None,
        hard_error: true,
        paths_tried,
        extracted: Vec::new(),
        failed: Vec::new(),
    }
}

fn home_cache_dir(version: &str) -> PathBuf {
    PathBuf::from(crate::home_dir())
        .join(".config")
        .join("aris")
        .join("cache")
        .join(version)
}

/// Extract all [`BUNDLED_RESOURCES`](crate::BUNDLED_RESOURCES) under
/// `cache_dir`. Returns `(extracted_keys, per_file_failures)`. Returns `Err`
/// only when `cache_dir` itself cannot be created.
fn try_extract_to(cache_dir: &Path) -> Result<(Vec<String>, Vec<ExtractionError>), String> {
    std::fs::create_dir_all(cache_dir)
        .map_err(|e| format!("create_dir_all({}): {e}", cache_dir.display()))?;

    let mut extracted = Vec::new();
    let mut failed = Vec::new();
    for (key, content) in crate::BUNDLED_RESOURCES {
        match extract_one(cache_dir, key, content) {
            Ok(()) => extracted.push((*key).to_string()),
            Err(error) => failed.push(ExtractionError {
                key: (*key).to_string(),
                error,
            }),
        }
    }
    Ok((extracted, failed))
}

/// Materialise a single bundled resource via tmp-then-rename.
fn extract_one(cache_dir: &Path, key: &str, content: &str) -> Result<(), String> {
    // Defensive key-path validation: bundle keys should never be tampered, but
    // since they pass through the include_str! ↔ runtime boundary as text, we
    // refuse to write any key that resolves outside cache_dir.
    let rel = Path::new(key);
    if rel.is_absolute() {
        return Err(format!("absolute path rejected: {key}"));
    }
    for component in rel.components() {
        match component {
            std::path::Component::ParentDir => {
                return Err(format!("parent-dir segment rejected: {key}"));
            }
            std::path::Component::Prefix(_) => {
                // Windows drive prefixes like `C:` or `\\?\C:` — never legitimate in a bundle key
                return Err(format!("Windows drive prefix rejected: {key}"));
            }
            std::path::Component::RootDir => {
                // Leading `/` (POSIX root) or `\` (Windows current-drive root).
                // `is_absolute()` may return false for the latter, but `join`
                // would still escape `cache_dir` by jumping to drive root.
                return Err(format!("root-dir segment rejected: {key}"));
            }
            _ => {}
        }
    }

    let target = cache_dir.join(rel);
    let parent = target.parent().ok_or("no parent dir for target")?;
    std::fs::create_dir_all(parent)
        .map_err(|e| format!("create_dir_all({}): {e}", parent.display()))?;

    // Strategy: write to <basename>.tmp.<pid>.<rand>, then rename to target.
    //
    // Unix (fs::rename) is atomic overwrite, even if target exists — safe.
    //
    // Windows: rename FAILS if target exists. We do NOT remove-then-rename
    // because that would (a) make a concurrently-running aris instance see
    // NotFound on the cached helper mid-window, and (b) report a false
    // "failed" when the existing file is already correct content. Instead we
    // accept "first writer wins" on Windows: leave existing target intact,
    // report failed, and let the report surface the situation. Same-version
    // cache contents are deterministic (build-time bundled bytes), so a
    // pre-existing file is the same content the second writer would produce.
    let basename = target
        .file_name()
        .map(|s| s.to_string_lossy().into_owned())
        .ok_or("target has no file name")?;
    let tmp_name = format!(
        "{basename}.tmp.{pid}.{suffix}",
        pid = std::process::id(),
        suffix = rand_suffix()
    );
    let tmp_path = parent.join(&tmp_name);
    std::fs::write(&tmp_path, content)
        .map_err(|e| format!("write tmp {}: {e}", tmp_path.display()))?;

    if let Err(rename_err) = std::fs::rename(&tmp_path, &target) {
        // First-writer-wins fallback (mainly Windows, where fs::rename refuses
        // to overwrite). The bundle is deterministic — bytes for a given key
        // are identical across processes of the same aris version. So if the
        // existing target already has the bytes we wanted to write, that's a
        // success, not a failure. Only when the existing content differs do
        // we report failed (and leave the existing file intact — never
        // remove it, to avoid letting a concurrent reader see NotFound).
        let cleanup_tmp = || {
            let _ = std::fs::remove_file(&tmp_path);
        };
        match std::fs::read(&target) {
            Ok(existing) if existing == content.as_bytes() => {
                cleanup_tmp();
                Ok(())
            }
            Ok(_) => {
                cleanup_tmp();
                Err(format!(
                    "rename {} -> {} failed and existing target has different content: {rename_err}",
                    tmp_path.display(),
                    target.display()
                ))
            }
            Err(read_err) => {
                cleanup_tmp();
                Err(format!(
                    "rename {} -> {}: {rename_err} (and target unreadable: {read_err})",
                    tmp_path.display(),
                    target.display()
                ))
            }
        }
    } else {
        Ok(())
    }
}

fn rand_suffix() -> String {
    use std::collections::hash_map::DefaultHasher;
    use std::hash::{Hash, Hasher};
    use std::time::{SystemTime, UNIX_EPOCH};
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.subsec_nanos())
        .unwrap_or(0);
    let mut h = DefaultHasher::new();
    nanos.hash(&mut h);
    std::process::id().hash(&mut h);
    format!("{:08x}", h.finish() as u32)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn extract_one_writes_simple_file() {
        let tmp = std::env::temp_dir().join(format!("aris-test-{}", rand_suffix()));
        let _ = std::fs::remove_dir_all(&tmp);
        std::fs::create_dir_all(&tmp).unwrap();
        extract_one(&tmp, "tools/foo.py", "print('hi')").unwrap();
        let dst = tmp.join("tools").join("foo.py");
        assert!(dst.is_file(), "{} should exist", dst.display());
        assert_eq!(std::fs::read_to_string(&dst).unwrap(), "print('hi')");
        let _ = std::fs::remove_dir_all(&tmp);
    }

    #[test]
    fn extract_one_rejects_absolute_key() {
        let tmp = std::env::temp_dir().join(format!("aris-test-{}", rand_suffix()));
        let _ = std::fs::remove_dir_all(&tmp);
        std::fs::create_dir_all(&tmp).unwrap();
        let err = extract_one(&tmp, "/etc/passwd", "evil").unwrap_err();
        assert!(err.contains("absolute"), "got: {err}");
        let _ = std::fs::remove_dir_all(&tmp);
    }

    #[test]
    fn extract_one_rejects_parent_segment() {
        let tmp = std::env::temp_dir().join(format!("aris-test-{}", rand_suffix()));
        let _ = std::fs::remove_dir_all(&tmp);
        std::fs::create_dir_all(&tmp).unwrap();
        let err = extract_one(&tmp, "tools/../escape.py", "evil").unwrap_err();
        assert!(err.contains("parent-dir"), "got: {err}");
        let _ = std::fs::remove_dir_all(&tmp);
    }

    // Unix only: fs::rename is atomic overwrite. On Windows fs::rename fails
    // when target exists; cache contract is "first writer wins with identical
    // content", so we don't test overwrite there.
    #[cfg(unix)]
    #[test]
    fn extract_one_overwrites_existing() {
        let tmp = std::env::temp_dir().join(format!("aris-test-{}", rand_suffix()));
        let _ = std::fs::remove_dir_all(&tmp);
        std::fs::create_dir_all(&tmp).unwrap();
        extract_one(&tmp, "tools/x.py", "v1").unwrap();
        extract_one(&tmp, "tools/x.py", "v2").unwrap();
        let got = std::fs::read_to_string(tmp.join("tools/x.py")).unwrap();
        assert_eq!(got, "v2", "should overwrite existing content");
        let _ = std::fs::remove_dir_all(&tmp);
    }

    #[test]
    fn extract_one_rejects_root_segment() {
        let tmp = std::env::temp_dir().join(format!("aris-test-{}", rand_suffix()));
        let _ = std::fs::remove_dir_all(&tmp);
        std::fs::create_dir_all(&tmp).unwrap();
        // Leading "/" — Path::new will produce a RootDir component
        let err = extract_one(&tmp, "/tools/x.py", "evil").unwrap_err();
        // Either is_absolute path or root-dir component is caught; both messages OK
        assert!(
            err.contains("absolute") || err.contains("root-dir"),
            "got: {err}"
        );
        let _ = std::fs::remove_dir_all(&tmp);
    }

    /// v0.4.9 T29: every bundle key cited inside a bundled SKILL.md prose
    /// must resolve to an actual entry in BUNDLED_RESOURCES. Guards against
    /// the H6 regression where SKILL.md `python3 tools/foo.py` references
    /// silently 404'd because foo.py was never bundled.
    ///
    /// Detection rule (deliberately narrow to avoid false positives from
    /// prose mentions): we match the runtime-injected `$ARIS_CACHE_DIR/`
    /// substitution pattern that v0.4.8+ SKILL.md migrations use, and we
    /// match unprefixed `python3 tools/<helper>` literals that survived
    /// from the v0.4.7 era. shared-references/* doesn't need direct
    /// invocation references; templates/ are read via fs paths not exec.
    #[test]
    fn bundle_inventory_skill_md_refs_resolve_to_bundled_resources() {
        use regex::Regex;
        let bundled_keys: std::collections::HashSet<&'static str> =
            crate::BUNDLED_RESOURCES.iter().map(|(k, _)| *k).collect();

        // Match either:
        //   "$ARIS_CACHE_DIR/<key>" or "${ARIS_CACHE_DIR:-.}/<key>"
        //   bare "tools/<helper>.{py,sh}" (legacy literal still in some SKILLs)
        let cache_re = Regex::new(
            r#"\$\{?ARIS_CACHE_DIR(?::-[^}]*)?\}?/((?:tools|skills/[a-zA-Z0-9_-]+|shared-references)/[a-zA-Z0-9_./-]+\.(?:py|sh|tex|cls|bst|md|toml|yaml|yml|json))"#,
        )
        .expect("compile cache_re");
        let legacy_re = Regex::new(
            r#"(?m)\bpython3\s+(?:"|)?(tools/[a-zA-Z0-9_./-]+\.(?:py|sh))(?:"|)?"#,
        )
        .expect("compile legacy_re");

        let mut missing: Vec<(String, String)> = Vec::new();
        for (skill_name, content) in crate::BUNDLED_SKILLS {
            for cap in cache_re.captures_iter(content) {
                let key = &cap[1];
                if !bundled_keys.contains(key) {
                    missing.push((skill_name.to_string(), key.to_string()));
                }
            }
            for cap in legacy_re.captures_iter(content) {
                let key = &cap[1];
                if !bundled_keys.contains(key) {
                    missing.push((skill_name.to_string(), key.to_string()));
                }
            }
        }

        assert!(
            missing.is_empty(),
            "SKILL.md references {} bundle key(s) that are NOT in BUNDLED_RESOURCES:\n{}",
            missing.len(),
            missing
                .iter()
                .map(|(s, k)| format!("  /{s}: {k}"))
                .collect::<Vec<_>>()
                .join("\n")
        );
    }

    /// v0.4.11 — verify the SKILLS_SOURCE_COMMIT file recorded by
    /// `tools/sync_main_skills.sh` exists and looks like a valid 40-char
    /// hex SHA.
    ///
    /// If `origin/main` resolves (CI w/ `fetch-depth: 0`), also check
    /// the pin is an ancestor of `origin/main` (warn-only — release
    /// commits intentionally outpace the source-commit pin by one).
    ///
    /// Hard-fails if the file is missing or malformed so the next
    /// release can't ship a bundle of unknown provenance.
    #[test]
    fn skills_source_commit_pin_present_and_well_formed() {
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("assets")
            .join("SKILLS_SOURCE_COMMIT");
        let raw = std::fs::read_to_string(&path).unwrap_or_else(|err| {
            panic!(
                "missing {} ({}). Run `bash tools/sync_main_skills.sh` first; \
                 see idea-stage/v0.4.11/sync_plan.md",
                path.display(),
                err
            )
        });
        let commit = raw.trim();
        assert_eq!(
            commit.len(),
            40,
            "SKILLS_SOURCE_COMMIT must be a 40-char SHA, got {:?} ({} chars)",
            commit,
            commit.len()
        );
        assert!(
            commit.chars().all(|c| c.is_ascii_hexdigit()),
            "SKILLS_SOURCE_COMMIT must be lowercase hex, got {:?}",
            commit
        );

        // Best-effort: if git + origin/main is reachable, verify the pin
        // is an ancestor of origin/main. Skipped silently when the
        // current shell can't resolve origin/main (local dev, sandbox).
        let main_check = std::process::Command::new("git")
            .args(["rev-parse", "--verify", "--quiet", "origin/main"])
            .output();
        if let Ok(out) = main_check {
            if out.status.success() {
                let main_sha = String::from_utf8_lossy(&out.stdout).trim().to_string();
                if !main_sha.is_empty() && main_sha != commit {
                    let ancestor = std::process::Command::new("git")
                        .args(["merge-base", "--is-ancestor", commit, &main_sha])
                        .status();
                    if let Ok(status) = ancestor {
                        if !status.success() {
                            eprintln!(
                                "WARN: SKILLS_SOURCE_COMMIT {} is NOT an ancestor of \
                                 origin/main {}. The skills bundle may be stale or \
                                 diverged. Re-run sync_main_skills.sh before releasing.",
                                commit, main_sha
                            );
                        }
                    }
                }
            }
        }
    }

    /// v0.4.11 — extended helper-reference resolver coverage.
    ///
    /// Existing `bundle_inventory_skill_md_refs_resolve_to_bundled_resources`
    /// covers `$ARIS_CACHE_DIR/...` and `python3 tools/...`. Main SKILL.md
    /// also uses two more resolver layers which were previously uncovered:
    ///   - `.aris/tools/<helper>` (canonical resolver Layer 1)
    ///   - `${ARIS_REPO}/tools/<helper>` or `<ARIS_REPO>/tools/<helper>`
    ///     (resolver Layer 2 — user override / dev mode)
    #[test]
    fn skill_md_aris_tools_and_repo_refs_resolve_to_bundled() {
        use regex::Regex;
        use std::collections::HashSet;

        let bundled_keys: HashSet<&'static str> =
            crate::BUNDLED_RESOURCES.iter().map(|(k, _)| *k).collect();

        let aris_tools_re = Regex::new(
            r#"\.aris/(tools/[a-zA-Z0-9_./-]+\.(?:py|sh|tex|cls|bst|md|toml|yaml|yml|json))"#,
        )
        .expect("compile aris_tools_re");
        let repo_tools_re = Regex::new(
            r#"(?:\$\{?ARIS_REPO\}?|<ARIS_REPO>)/(tools/[a-zA-Z0-9_./-]+\.(?:py|sh|tex|cls|bst|md|toml|yaml|yml|json))"#,
        )
        .expect("compile repo_tools_re");

        let mut missing: Vec<(String, String)> = Vec::new();
        for (skill_name, content) in crate::BUNDLED_SKILLS {
            for cap in aris_tools_re.captures_iter(content) {
                let key = &cap[1];
                if !bundled_keys.contains(key) {
                    missing.push((skill_name.to_string(), key.to_string()));
                }
            }
            for cap in repo_tools_re.captures_iter(content) {
                let key = &cap[1];
                if !bundled_keys.contains(key) {
                    missing.push((skill_name.to_string(), key.to_string()));
                }
            }
        }

        assert!(
            missing.is_empty(),
            "SKILL.md references {} `.aris/tools/...` or `$ARIS_REPO/tools/...` \
             key(s) that are NOT in BUNDLED_RESOURCES:\n{}",
            missing.len(),
            missing
                .iter()
                .map(|(s, k)| format!("  /{s}: {k}"))
                .collect::<Vec<_>>()
                .join("\n")
        );
    }

    /// v0.4.11 — cross-skill references in SKILL.md should resolve to
    /// other bundled skills. Warn-only (not hard fail) because SKILL.md
    /// may intentionally mention not-yet-bundled or planned skills, and
    /// we don't want to block emergency hot-fixes when main is mid-
    /// refactor.
    ///
    /// Run with `cargo test ... -- --nocapture` to see warning output.
    #[test]
    fn skill_md_cross_skill_references_bundled_warn_only() {
        use regex::Regex;
        use std::collections::HashSet;

        let bundled_names: HashSet<&'static str> =
            crate::BUNDLED_SKILLS.iter().map(|(n, _)| *n).collect();

        let re = Regex::new(
            r#"(?i)\b(?:Use|See|Via|The|Run|Invoke|Calls?|Runs?|Trigger)\s+`?/([a-z][a-z0-9-]+)`?(?P<after>\.?(?:\s+(?:skill|workflow|pipeline)\b|[\s,;:!?)）]|$))"#,
        )
        .expect("compile cross-skill regex");

        let mut unresolved: Vec<(&'static str, String)> = Vec::new();
        for (skill_name, content) in crate::BUNDLED_SKILLS {
            for cap in re.captures_iter(content) {
                let referenced = &cap[1];
                if !bundled_names.contains(referenced) {
                    unresolved.push((*skill_name, referenced.to_string()));
                }
            }
        }

        if !unresolved.is_empty() {
            let mut seen: HashSet<(&'static str, String)> = HashSet::new();
            let mut summary: Vec<String> = Vec::new();
            for (s, r) in &unresolved {
                let key = (*s, r.clone());
                if seen.insert(key) {
                    summary.push(format!("  /{}: -> /{}", s, r));
                }
            }
            eprintln!(
                "WARN: {} cross-skill reference(s) point to non-bundled \
                 skill(s). This is allowed (roadmap mentions, mid-refactor), \
                 but verify each before release:\n{}",
                summary.len(),
                summary.join("\n")
            );
        }
    }

    /// v0.4.22 exact-inventory drift test: the `tools/` slice of
    /// BUNDLED_RESOURCES is EXACTLY the 28-helper whitelist that
    /// tools/sync_main_skills.sh ships. Set-equality (not subset) so BOTH
    /// failure modes are caught: a helper missing after a sync (the
    /// pre-v0.4.22 gap — the script's RUNTIME_HELPERS lagged what synced
    /// SKILL.md files referenced) AND a stale 29th file lingering in
    /// assets/tools/ (the sync script never auto-prunes).
    #[test]
    fn bundled_tools_inventory_is_exactly_the_sync_whitelist() {
        use std::collections::BTreeSet;

        // Mirror of RUNTIME_HELPERS in tools/sync_main_skills.sh (v0.4.22).
        const EXPECTED: &[&str] = &[
            // baseline (v0.4.8/0.4.9 era)
            "tools/arxiv_fetch.py",
            "tools/deepxiv_fetch.py",
            "tools/exa_search.py",
            "tools/openalex_fetch.py",
            "tools/research_wiki.py",
            "tools/save_trace.sh",
            "tools/semantic_scholar_fetch.py",
            "tools/verify_paper_audits.sh",
            "tools/verify_papers.py",
            // v0.4.11 additions
            "tools/extract_paper_style.py",
            "tools/figure_renderer.py",
            "tools/paper_illustration_image2.py",
            "tools/overleaf_setup.sh",
            "tools/overleaf_audit.sh",
            "tools/verify_wiki_coverage.sh",
            "tools/watchdog.py",
            "tools/experiment_queue/build_manifest.py",
            "tools/experiment_queue/queue_manager.py",
            // v0.4.13 meta_opt hooks
            "tools/meta_opt/log_event.sh",
            "tools/meta_opt/check_ready.sh",
            // v0.4.22 additions (referenced by synced SKILL.md files)
            "tools/capture_filter.py",
            "tools/evidence_check.py",
            "tools/iteration_log.py",
            "tools/provenance.py",
            "tools/run_state.py",
            "tools/threat_scan.py",
            "tools/meta_opt/trigger_eval.py",
            "tools/meta_opt/trigger_evals.sample.json",
        ];
        assert_eq!(EXPECTED.len(), 28, "whitelist mirror must stay at 28");

        let expected: BTreeSet<&str> = EXPECTED.iter().copied().collect();
        let actual: BTreeSet<&str> = crate::BUNDLED_RESOURCES
            .iter()
            .map(|(k, _)| *k)
            .filter(|k| k.starts_with("tools/"))
            .collect();

        let missing: Vec<&&str> = expected.difference(&actual).collect();
        let stale: Vec<&&str> = actual.difference(&expected).collect();
        assert!(
            missing.is_empty() && stale.is_empty(),
            "bundled tools/ inventory drifted from the sync whitelist.\n\
             missing (in whitelist, not bundled): {missing:?}\n\
             stale (bundled, not in whitelist — sync never prunes; remove or whitelist): {stale:?}"
        );
    }

    /// v0.4.22: the vendored posterly MIT license text must ship with the
    /// vendored paper-poster-html scripts (its NOTICE.md points at this
    /// path). Guards the build.rs ALLOWED_EXTS "txt" addition — without it
    /// the file is silently dropped at embed time (attribution gap).
    #[test]
    fn posterly_mit_license_text_is_bundled() {
        let key = "skills/paper-poster-html/LICENSES/posterly-MIT.txt";
        let entry = crate::BUNDLED_RESOURCES.iter().find(|(k, _)| *k == key);
        let (_, content) = entry.unwrap_or_else(|| {
            panic!(
                "{key} not in BUNDLED_RESOURCES — did build.rs ALLOWED_EXTS \
                 lose \"txt\", or did the sync drop the LICENSES dir?"
            )
        });
        assert!(
            content.contains("MIT License"),
            "bundled posterly license text does not look like an MIT license"
        );
    }
}
