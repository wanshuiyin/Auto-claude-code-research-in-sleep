//! ARIS multi-file memory system.
//!
//! Memories are stored as individual markdown files in `~/.config/aris/memories/`.
//! Each file has YAML frontmatter with name and description.
//! The system prompt gets a catalog (name + description per file),
//! and the model uses read_file to load specific memories on demand.

use std::fs;
use std::path::PathBuf;

pub struct MemoryEntry {
    pub name: String,
    pub description: String,
    pub path: PathBuf,
}

/// Directory for multi-file memories.
pub fn memories_dir() -> PathBuf {
    let home = std::env::var("HOME").unwrap_or_else(|_| ".".into());
    PathBuf::from(home)
        .join(".config")
        .join("aris")
        .join("memories")
}

/// Load all memory entries (name + description from frontmatter).
pub fn load_memory_catalog() -> Vec<MemoryEntry> {
    let dir = memories_dir();
    if !dir.exists() {
        return Vec::new();
    }

    let mut entries = Vec::new();
    let Ok(read_dir) = fs::read_dir(&dir) else {
        return entries;
    };

    for entry in read_dir.flatten() {
        let path = entry.path();
        // Reject symlinks to prevent directory traversal
        if fs::symlink_metadata(&path).is_ok_and(|m| m.file_type().is_symlink()) {
            continue;
        }
        if path.extension().is_some_and(|ext| ext == "md") {
            if let Ok(content) = fs::read_to_string(&path) {
                let (name, description) = parse_memory_frontmatter(&content);
                let name = name.unwrap_or_else(|| {
                    path.file_stem()
                        .unwrap_or_default()
                        .to_string_lossy()
                        .to_string()
                });
                entries.push(MemoryEntry {
                    name,
                    description: description.unwrap_or_default(),
                    path,
                });
            }
        }
    }

    entries.sort_by(|a, b| a.name.cmp(&b.name));
    entries
}

fn parse_memory_frontmatter(content: &str) -> (Option<String>, Option<String>) {
    let trimmed = content.trim_start();
    if !trimmed.starts_with("---") {
        return (None, None);
    }
    let rest = &trimmed[3..].trim_start_matches('\n');
    let Some(end) = rest.find("\n---") else {
        return (None, None);
    };
    let frontmatter = &rest[..end];

    let mut name = None;
    let mut description = None;
    for line in frontmatter.lines() {
        if let Some(val) = line.strip_prefix("name:") {
            name = Some(val.trim().to_string());
        } else if let Some(val) = line.strip_prefix("description:") {
            description = Some(val.trim().to_string());
        }
    }
    (name, description)
}

/// Render the memory catalog for system prompt injection.
/// Only includes name + description + path (not full content).
/// Sanitizes fields to prevent prompt injection.
pub fn render_memory_catalog(entries: &[MemoryEntry]) -> String {
    if entries.is_empty() {
        return String::new();
    }
    let mut lines = Vec::new();
    for entry in entries {
        let name = sanitize_field(&entry.name, 60);
        let desc = if entry.description.is_empty() {
            String::new()
        } else {
            format!(" — {}", sanitize_field(&entry.description, 120))
        };
        lines.push(format!("- {}{} → `{}`", name, desc, entry.path.display()));
    }
    lines.join("\n")
}

/// Sanitize a string for safe prompt injection: truncate and remove control chars.
fn sanitize_field(s: &str, max_len: usize) -> String {
    s.chars()
        .filter(|c| !c.is_control() || *c == '\n')
        .take(max_len)
        .collect::<String>()
        .replace('\n', " ")
}

/// Migrate old single-file memory.md to multi-file format.
pub fn migrate_legacy_memory() {
    let home = std::env::var("HOME").unwrap_or_else(|_| ".".into());
    let legacy_path = PathBuf::from(&home)
        .join(".config")
        .join("aris")
        .join("memory.md");

    if !legacy_path.exists() {
        return;
    }

    let Ok(content) = fs::read_to_string(&legacy_path) else {
        return;
    };
    if content.trim().is_empty() {
        return;
    }

    let dir = memories_dir();
    let target = dir.join("legacy.md");
    if target.exists() {
        return; // Already migrated
    }

    if fs::create_dir_all(&dir).is_ok() {
        let migrated = format!(
            "---\nname: Legacy Memory\ndescription: Migrated from memory.md\n---\n\n{}",
            content.trim()
        );
        let _ = fs::write(&target, migrated);
    }
}
