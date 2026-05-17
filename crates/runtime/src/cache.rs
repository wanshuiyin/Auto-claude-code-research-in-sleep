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
}
