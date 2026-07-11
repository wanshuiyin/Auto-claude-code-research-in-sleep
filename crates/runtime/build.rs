use std::collections::hash_map::DefaultHasher;
use std::env;
use std::fs;
use std::hash::{Hash, Hasher};
use std::path::Path;
use walkdir::WalkDir;

const MAX_FILE_SIZE: u64 = 512 * 1024;
// v0.4.22: "txt" added for skills/paper-poster-html/LICENSES/posterly-MIT.txt —
// the vendored posterly (MIT) license text that its NOTICE.md points at; shipping
// the vendored scripts without the license text is an attribution gap.
const ALLOWED_EXTS: &[&str] = &[
    "md", "py", "sh", "tex", "cls", "bst", "toml", "yaml", "yml", "json", "html", "txt",
];
/// Skill directory name prefixes to exclude from bundling. v0.4.12 changed
/// from exact-match list to `starts_with` semantics so future variants like
/// `skills-codex-foo/` are auto-excluded without code change.
const EXCLUDED_SKILL_PREFIX: &str = "skills-codex";

fn main() {
    let out_dir = env::var("OUT_DIR").unwrap();
    let out_path = Path::new(&out_dir);
    let assets_dir = Path::new("assets");

    println!("cargo:rerun-if-changed=assets");

    let mut skill_names: Vec<String> = Vec::new();
    let mut skill_safe_names: Vec<String> = Vec::new();
    let mut resource_entries: Vec<(String, String)> = Vec::new();

    // ------ Walk assets/tools/ → key = "tools/<rel>" (shared cross-skill helpers) ------
    let tools_root = assets_dir.join("tools");
    if tools_root.exists() {
        let tools_meta =
            fs::symlink_metadata(&tools_root).expect("symlink_metadata for assets/tools");
        if tools_meta.file_type().is_symlink() {
            panic!(
                "assets/tools is a symlink, refusing to bundle: {}",
                tools_root.display()
            );
        }
        bundle_tree(&tools_root, "tools", out_path, &mut resource_entries);
    }

    // ------ Walk assets/skills/ ------
    let skills_root = assets_dir.join("skills");
    if skills_root.exists() {
        let skills_meta =
            fs::symlink_metadata(&skills_root).expect("symlink_metadata for assets/skills");
        if skills_meta.file_type().is_symlink() {
            panic!(
                "assets/skills is a symlink, refusing to bundle: {}",
                skills_root.display()
            );
        }
        let mut top_entries: Vec<_> = fs::read_dir(&skills_root)
            .expect("read assets/skills")
            .collect::<Result<Vec<_>, _>>()
            .expect("read assets/skills entry");
        top_entries.sort_by_key(|e| e.file_name());

        for entry in top_entries {
            let ft = entry.file_type().expect("file_type for top entry");
            if ft.is_symlink() {
                panic!(
                    "symlink at assets/skills top level: {}",
                    entry.path().display()
                );
            }
            if !ft.is_dir() {
                continue;
            }

            let name = entry.file_name().to_string_lossy().to_string();

            // Exclude review-snapshot mirrors (not user-facing skills).
            // v0.4.12: starts_with covers future variants too.
            if name.starts_with(EXCLUDED_SKILL_PREFIX) {
                continue;
            }

            if name == "shared-references" {
                // shared-references → key prefix "shared-references/", recursive
                bundle_tree(
                    &entry.path(),
                    "shared-references",
                    out_path,
                    &mut resource_entries,
                );
                continue;
            }

            // For a real skill dir, SKILL.md is required
            let skill_md = entry.path().join("SKILL.md");
            if !skill_md.exists() {
                // Unknown dir with no SKILL.md and not shared-references — skip silently.
                // (Old build.rs emitted these; v0.4.8 excludes them.)
                continue;
            }

            // Reject SKILL.md being a symlink (would silently chase target via fs::copy).
            let skill_md_meta =
                fs::symlink_metadata(&skill_md).expect("symlink_metadata for SKILL.md");
            if skill_md_meta.file_type().is_symlink() {
                panic!(
                    "SKILL.md is a symlink, refusing to bundle: {}",
                    skill_md.display()
                );
            }

            // Register as a bundled skill. Copy SKILL.md to OUT_DIR with a sanitized name
            // so include_str! can reference it.
            let safe = sanitize_filename(&format!("skill_{name}.md"));
            let dest = out_path.join(&safe);
            fs::copy(&skill_md, &dest).expect("copy skill SKILL.md");
            skill_names.push(name.clone());
            skill_safe_names.push(safe);

            // Recursively bundle everything else under this skill dir, key prefix
            // "skills/<name>/", except SKILL.md itself (already handled above).
            let key_prefix = format!("skills/{name}");
            bundle_tree_excluding(
                &entry.path(),
                &key_prefix,
                out_path,
                &mut resource_entries,
                &["SKILL.md"],
            );
        }
    }

    // ------ Codegen ------
    let mut code = String::from(
        "/// Bundled ARIS skills compiled into the binary.\n\
         pub static BUNDLED_SKILLS: &[(&str, &str)] = &[\n",
    );
    for (name, safe) in skill_names.iter().zip(skill_safe_names.iter()) {
        code.push_str(&format!(
            "    (\"{name}\", include_str!(concat!(env!(\"OUT_DIR\"), \"/{safe}\"))),\n"
        ));
    }
    code.push_str("];\n\n");

    code.push_str(
        "/// Bundled helper files (`.py`, `.sh`, `.tex`, `.cls`, `.bst`, `.md`, configs) for skills.\n\
         /// Keys use one of three namespaces:\n\
         /// - `tools/<rel>` — shared, cross-skill helpers (from assets/tools/)\n\
         /// - `skills/<name>/<rel>` — skill-local helpers and templates\n\
         /// - `shared-references/<rel>` — always-extracted reference docs\n\
         pub static BUNDLED_RESOURCES: &[(&str, &str)] = &[\n",
    );
    for (key, safe_name) in &resource_entries {
        code.push_str(&format!(
            "    (\"{key}\", include_str!(concat!(env!(\"OUT_DIR\"), \"/{safe_name}\"))),\n"
        ));
    }
    code.push_str("];\n");

    fs::write(out_path.join("bundled_skills.rs"), code).expect("write bundled_skills.rs");

    println!(
        "cargo:warning=Embedded {} bundled skills, {} helper resources",
        skill_names.len(),
        resource_entries.len()
    );
}

/// Recursively walk `root`, emit (key, content) for every allowed file.
/// Key shape: "<key_prefix>/<rel-to-root>". Symlinks → panic. WalkDir errors → panic.
/// Entries sorted for deterministic build output.
fn bundle_tree(
    root: &Path,
    key_prefix: &str,
    out_path: &Path,
    entries: &mut Vec<(String, String)>,
) {
    bundle_tree_excluding(root, key_prefix, out_path, entries, &[])
}

fn bundle_tree_excluding(
    root: &Path,
    key_prefix: &str,
    out_path: &Path,
    entries: &mut Vec<(String, String)>,
    excluded_rels: &[&str],
) {
    for raw in WalkDir::new(root)
        .follow_links(false)
        .sort_by_file_name()
        .into_iter()
    {
        let entry: walkdir::DirEntry = match raw {
            Ok(e) => e,
            Err(e) => panic!("WalkDir error under {}: {}", root.display(), e),
        };
        let ft = entry.file_type();
        if ft.is_symlink() {
            panic!(
                "symlink in assets, refusing to bundle: {}",
                entry.path().display()
            );
        }
        if !ft.is_file() {
            continue;
        }

        let path = entry.path();
        let rel = path.strip_prefix(root).unwrap();
        let rel_str = rel.to_string_lossy().replace('\\', "/");

        // Defense: reject ".." segments (WalkDir shouldn't produce them, but be paranoid)
        if rel.components()
            .any(|c| matches!(c, std::path::Component::ParentDir))
        {
            panic!("parent-dir segment in asset path: {rel_str}");
        }

        // Exclude root-level files like SKILL.md (handled separately by caller)
        if excluded_rels.contains(&rel_str.as_str()) {
            continue;
        }

        // Extension allow-list (cheap check first)
        let ext = rel
            .extension()
            .and_then(|e| e.to_str())
            .unwrap_or("");
        if !ALLOWED_EXTS.contains(&ext) {
            continue;
        }

        // File-size cap — for allow-listed files, EXCEED = panic (not silent skip)
        let meta = fs::metadata(path).expect("metadata");
        if meta.len() > MAX_FILE_SIZE {
            panic!(
                "asset exceeds {}KB cap: {} ({} bytes). Bump MAX_FILE_SIZE in build.rs or trim the file.",
                MAX_FILE_SIZE / 1024,
                rel_str,
                meta.len()
            );
        }

        // Compose key and write a sanitized copy under OUT_DIR.
        // Sanitized name has a content-hash prefix to defeat collisions like
        // `a/b__c.py` vs `a__b/c.py` (both naively collapse to `a__b__c.py`).
        let key = format!("{key_prefix}/{rel_str}");
        let safe = sanitize_filename(&key);
        let dest = out_path.join(&safe);
        if let Some(parent) = dest.parent() {
            fs::create_dir_all(parent).expect("create out parent dir");
        }
        fs::copy(path, &dest).expect("copy asset");

        entries.push((key, safe));
    }
}

fn sanitize_filename(key: &str) -> String {
    let mut h = DefaultHasher::new();
    key.hash(&mut h);
    let hash = format!("{:08x}", h.finish() as u32);
    let flat = key.replace('/', "__").replace('\\', "__");
    format!("{hash}_{flat}")
}
