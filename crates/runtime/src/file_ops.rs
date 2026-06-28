use std::cmp::Reverse;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::time::Instant;

use glob::Pattern;
use regex::RegexBuilder;
use serde::{Deserialize, Serialize};
use walkdir::WalkDir;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct TextFilePayload {
    #[serde(rename = "filePath")]
    pub file_path: String,
    pub content: String,
    #[serde(rename = "numLines")]
    pub num_lines: usize,
    #[serde(rename = "startLine")]
    pub start_line: usize,
    #[serde(rename = "totalLines")]
    pub total_lines: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ReadFileOutput {
    #[serde(rename = "type")]
    pub kind: String,
    pub file: TextFilePayload,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct StructuredPatchHunk {
    #[serde(rename = "oldStart")]
    pub old_start: usize,
    #[serde(rename = "oldLines")]
    pub old_lines: usize,
    #[serde(rename = "newStart")]
    pub new_start: usize,
    #[serde(rename = "newLines")]
    pub new_lines: usize,
    pub lines: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct WriteFileOutput {
    #[serde(rename = "type")]
    pub kind: String,
    #[serde(rename = "filePath")]
    pub file_path: String,
    pub content: String,
    #[serde(rename = "structuredPatch")]
    pub structured_patch: Vec<StructuredPatchHunk>,
    #[serde(rename = "originalFile")]
    pub original_file: Option<String>,
    #[serde(rename = "gitDiff")]
    pub git_diff: Option<serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct EditFileOutput {
    #[serde(rename = "filePath")]
    pub file_path: String,
    #[serde(rename = "oldString")]
    pub old_string: String,
    #[serde(rename = "newString")]
    pub new_string: String,
    #[serde(rename = "originalFile")]
    pub original_file: String,
    #[serde(rename = "structuredPatch")]
    pub structured_patch: Vec<StructuredPatchHunk>,
    #[serde(rename = "userModified")]
    pub user_modified: bool,
    #[serde(rename = "replaceAll")]
    pub replace_all: bool,
    #[serde(rename = "gitDiff")]
    pub git_diff: Option<serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct GlobSearchOutput {
    #[serde(rename = "durationMs")]
    pub duration_ms: u128,
    #[serde(rename = "numFiles")]
    pub num_files: usize,
    pub filenames: Vec<String>,
    pub truncated: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct GrepSearchInput {
    pub pattern: String,
    pub path: Option<String>,
    pub glob: Option<String>,
    #[serde(rename = "output_mode")]
    pub output_mode: Option<String>,
    #[serde(rename = "-B")]
    pub before: Option<usize>,
    #[serde(rename = "-A")]
    pub after: Option<usize>,
    #[serde(rename = "-C")]
    pub context_short: Option<usize>,
    pub context: Option<usize>,
    #[serde(rename = "-n")]
    pub line_numbers: Option<bool>,
    #[serde(rename = "-i")]
    pub case_insensitive: Option<bool>,
    #[serde(rename = "type")]
    pub file_type: Option<String>,
    pub head_limit: Option<usize>,
    pub offset: Option<usize>,
    pub multiline: Option<bool>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct GrepSearchOutput {
    pub mode: Option<String>,
    #[serde(rename = "numFiles")]
    pub num_files: usize,
    pub filenames: Vec<String>,
    pub content: Option<String>,
    #[serde(rename = "numLines")]
    pub num_lines: Option<usize>,
    #[serde(rename = "numMatches")]
    pub num_matches: Option<usize>,
    #[serde(rename = "appliedLimit")]
    pub applied_limit: Option<usize>,
    #[serde(rename = "appliedOffset")]
    pub applied_offset: Option<usize>,
}

pub fn read_file(
    path: &str,
    offset: Option<usize>,
    limit: Option<usize>,
) -> io::Result<ReadFileOutput> {
    let absolute_path = normalize_path(path)?;
    let content = fs::read_to_string(&absolute_path)?;
    let lines: Vec<&str> = content.lines().collect();
    let start_index = offset.unwrap_or(0).min(lines.len());
    let end_index = limit.map_or(lines.len(), |limit| {
        start_index.saturating_add(limit).min(lines.len())
    });
    let selected = lines[start_index..end_index].join("\n");

    Ok(ReadFileOutput {
        kind: String::from("text"),
        file: TextFilePayload {
            file_path: absolute_path.to_string_lossy().into_owned(),
            content: selected,
            num_lines: end_index.saturating_sub(start_index),
            start_line: start_index.saturating_add(1),
            total_lines: lines.len(),
        },
    })
}

pub fn write_file(path: &str, content: &str) -> io::Result<WriteFileOutput> {
    let absolute_path = normalize_path_allow_missing(path)?;
    let original_file = fs::read_to_string(&absolute_path).ok();
    if let Some(parent) = absolute_path.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(&absolute_path, content)?;

    Ok(WriteFileOutput {
        kind: if original_file.is_some() {
            String::from("update")
        } else {
            String::from("create")
        },
        file_path: absolute_path.to_string_lossy().into_owned(),
        content: content.to_owned(),
        structured_patch: make_patch(original_file.as_deref().unwrap_or(""), content),
        original_file,
        git_diff: None,
    })
}

pub fn edit_file(
    path: &str,
    old_string: &str,
    new_string: &str,
    replace_all: bool,
) -> io::Result<EditFileOutput> {
    let absolute_path = normalize_path(path)?;
    let original_file = fs::read_to_string(&absolute_path)?;
    if old_string == new_string {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "old_string and new_string must differ",
        ));
    }
    if !original_file.contains(old_string) {
        return Err(io::Error::new(
            io::ErrorKind::NotFound,
            "old_string not found in file",
        ));
    }

    let updated = if replace_all {
        original_file.replace(old_string, new_string)
    } else {
        original_file.replacen(old_string, new_string, 1)
    };
    fs::write(&absolute_path, &updated)?;

    Ok(EditFileOutput {
        file_path: absolute_path.to_string_lossy().into_owned(),
        old_string: old_string.to_owned(),
        new_string: new_string.to_owned(),
        original_file: original_file.clone(),
        structured_patch: make_patch(&original_file, &updated),
        user_modified: false,
        replace_all,
        git_diff: None,
    })
}

pub fn glob_search(pattern: &str, path: Option<&str>) -> io::Result<GlobSearchOutput> {
    let started = Instant::now();
    let base_dir = path
        .map(normalize_path)
        .transpose()?
        .unwrap_or(std::env::current_dir()?);
    let search_pattern = if Path::new(pattern).is_absolute() {
        pattern.to_owned()
    } else {
        base_dir.join(pattern).to_string_lossy().into_owned()
    };

    let mut matches = Vec::new();
    let entries = glob::glob(&search_pattern)
        .map_err(|error| io::Error::new(io::ErrorKind::InvalidInput, error.to_string()))?;
    for entry in entries.flatten() {
        if entry.is_file() {
            matches.push(entry);
        }
    }

    matches.sort_by_key(|path| {
        fs::metadata(path)
            .and_then(|metadata| metadata.modified())
            .ok()
            .map(Reverse)
    });

    let total = matches.len();
    let truncated = total > 100;
    let filenames = matches
        .into_iter()
        .take(100)
        .map(|path| path.to_string_lossy().into_owned())
        .collect::<Vec<_>>();

    Ok(GlobSearchOutput {
        duration_ms: started.elapsed().as_millis(),
        // v0.4.20: report the TOTAL number of matched files, not the (capped)
        // number returned. Previously `filenames.len()` meant a 1000-match glob
        // reported `num_files: 100, truncated: true`, so the model believed only
        // 100 files matched. `filenames` still holds at most 100 entries.
        num_files: total,
        filenames,
        truncated,
    })
}

pub fn grep_search(input: &GrepSearchInput) -> io::Result<GrepSearchOutput> {
    let base_path = input
        .path
        .as_deref()
        .map(normalize_path)
        .transpose()?
        .unwrap_or(std::env::current_dir()?);

    let regex = RegexBuilder::new(&input.pattern)
        .case_insensitive(input.case_insensitive.unwrap_or(false))
        .dot_matches_new_line(input.multiline.unwrap_or(false))
        .build()
        .map_err(|error| io::Error::new(io::ErrorKind::InvalidInput, error.to_string()))?;

    let glob_filter = input
        .glob
        .as_deref()
        .map(Pattern::new)
        .transpose()
        .map_err(|error| io::Error::new(io::ErrorKind::InvalidInput, error.to_string()))?;
    let file_type = input.file_type.as_deref();
    let output_mode = input
        .output_mode
        .clone()
        .unwrap_or_else(|| String::from("files_with_matches"));
    let context = input.context.or(input.context_short).unwrap_or(0);

    let mut filenames = Vec::new();
    let mut content_lines = Vec::new();
    let mut total_matches = 0usize;

    for file_path in collect_search_files(&base_path)? {
        if !matches_optional_filters(&file_path, glob_filter.as_ref(), file_type) {
            continue;
        }

        let Ok(file_contents) = fs::read_to_string(&file_path) else {
            continue;
        };

        if output_mode == "count" {
            let count = regex.find_iter(&file_contents).count();
            if count > 0 {
                filenames.push(file_path.to_string_lossy().into_owned());
                total_matches += count;
            }
            continue;
        }

        let lines: Vec<&str> = file_contents.lines().collect();
        // v0.4.21 (#5): with `multiline:true` the regex enables dot_matches_new_line
        // so a pattern may span lines, but per-line `regex.is_match(line)` can never
        // match a newline-free line — multiline silently matched nothing in content/
        // default mode (count mode already scans the whole file). When multiline is
        // set, derive matched line indices from whole-file matches. `Match::end()` is
        // EXCLUSIVE, so map the END line from the LAST MATCHED BYTE (`m.end() - 1`),
        // counting newlines over `as_bytes()` (never slice `&str` at a non-char
        // boundary — counting `b'\n'` over bytes is always safe). Clamp to the last
        // line; skip empty files. The non-multiline branch is behavior-identical to
        // the previous per-line loop.
        let multiline = input.multiline.unwrap_or(false);
        let matched_lines: Vec<usize> = if multiline && !lines.is_empty() {
            let bytes = file_contents.as_bytes();
            let count_nl = |upto: usize| bytes[..upto].iter().filter(|&&b| b == b'\n').count();
            let last = lines.len() - 1;
            let mut set = std::collections::BTreeSet::new();
            for m in regex.find_iter(&file_contents) {
                let start_line = count_nl(m.start()).min(last);
                let end_byte = if m.end() > m.start() { m.end() - 1 } else { m.start() };
                let end_line = count_nl(end_byte).min(last);
                for l in start_line..=end_line {
                    set.insert(l);
                }
            }
            set.into_iter().collect()
        } else if multiline {
            Vec::new()
        } else {
            lines
                .iter()
                .enumerate()
                .filter(|(_, line)| regex.is_match(line))
                .map(|(index, _)| index)
                .collect()
        };
        total_matches += matched_lines.len();

        if matched_lines.is_empty() {
            continue;
        }

        filenames.push(file_path.to_string_lossy().into_owned());
        if output_mode == "content" {
            for index in matched_lines {
                let start = index.saturating_sub(input.before.unwrap_or(context));
                let end = (index + input.after.unwrap_or(context) + 1).min(lines.len());
                for (current, line) in lines.iter().enumerate().take(end).skip(start) {
                    let prefix = if input.line_numbers.unwrap_or(true) {
                        format!("{}:{}:", file_path.to_string_lossy(), current + 1)
                    } else {
                        format!("{}:", file_path.to_string_lossy())
                    };
                    content_lines.push(format!("{prefix}{line}"));
                }
            }
        }
    }

    let (filenames, applied_limit, applied_offset) =
        apply_limit(filenames, input.head_limit, input.offset);
    let content_output = if output_mode == "content" {
        let (lines, limit, offset) = apply_limit(content_lines, input.head_limit, input.offset);
        return Ok(GrepSearchOutput {
            mode: Some(output_mode),
            num_files: filenames.len(),
            filenames,
            num_lines: Some(lines.len()),
            content: Some(lines.join("\n")),
            num_matches: None,
            applied_limit: limit,
            applied_offset: offset,
        });
    } else {
        None
    };

    Ok(GrepSearchOutput {
        mode: Some(output_mode.clone()),
        num_files: filenames.len(),
        filenames,
        content: content_output,
        num_lines: None,
        num_matches: (output_mode == "count").then_some(total_matches),
        applied_limit,
        applied_offset,
    })
}

fn collect_search_files(base_path: &Path) -> io::Result<Vec<PathBuf>> {
    if base_path.is_file() {
        return Ok(vec![base_path.to_path_buf()]);
    }

    let mut files = Vec::new();
    for entry in WalkDir::new(base_path) {
        let entry = entry.map_err(|error| io::Error::other(error.to_string()))?;
        if entry.file_type().is_file() {
            files.push(entry.path().to_path_buf());
        }
    }
    Ok(files)
}

fn matches_optional_filters(
    path: &Path,
    glob_filter: Option<&Pattern>,
    file_type: Option<&str>,
) -> bool {
    if let Some(glob_filter) = glob_filter {
        let path_string = path.to_string_lossy();
        if !glob_filter.matches(&path_string) && !glob_filter.matches_path(path) {
            return false;
        }
    }

    if let Some(file_type) = file_type {
        let extension = path.extension().and_then(|extension| extension.to_str());
        if extension != Some(file_type) {
            return false;
        }
    }

    true
}

fn apply_limit<T>(
    items: Vec<T>,
    limit: Option<usize>,
    offset: Option<usize>,
) -> (Vec<T>, Option<usize>, Option<usize>) {
    let offset_value = offset.unwrap_or(0);
    let mut items = items.into_iter().skip(offset_value).collect::<Vec<_>>();
    let explicit_limit = limit.unwrap_or(250);
    if explicit_limit == 0 {
        return (items, None, (offset_value > 0).then_some(offset_value));
    }

    let truncated = items.len() > explicit_limit;
    items.truncate(explicit_limit);
    (
        items,
        truncated.then_some(explicit_limit),
        (offset_value > 0).then_some(offset_value),
    )
}

fn make_patch(original: &str, updated: &str) -> Vec<StructuredPatchHunk> {
    let mut lines = Vec::new();
    for line in original.lines() {
        lines.push(format!("-{line}"));
    }
    for line in updated.lines() {
        lines.push(format!("+{line}"));
    }

    vec![StructuredPatchHunk {
        old_start: 1,
        old_lines: original.lines().count(),
        new_start: 1,
        new_lines: updated.lines().count(),
        lines,
    }]
}

fn normalize_path(path: &str) -> io::Result<PathBuf> {
    let candidate = if Path::new(path).is_absolute() {
        PathBuf::from(path)
    } else {
        std::env::current_dir()?.join(path)
    };
    candidate.canonicalize()
}

fn normalize_path_allow_missing(path: &str) -> io::Result<PathBuf> {
    let candidate = if Path::new(path).is_absolute() {
        PathBuf::from(path)
    } else {
        std::env::current_dir()?.join(path)
    };

    if let Ok(canonical) = candidate.canonicalize() {
        return Ok(canonical);
    }

    if let Some(parent) = candidate.parent() {
        let canonical_parent = parent
            .canonicalize()
            .unwrap_or_else(|_| parent.to_path_buf());
        if let Some(name) = candidate.file_name() {
            return Ok(canonical_parent.join(name));
        }
    }

    Ok(candidate)
}

#[cfg(test)]
mod tests {
    use std::time::{SystemTime, UNIX_EPOCH};

    use super::{edit_file, glob_search, grep_search, read_file, write_file, GrepSearchInput};

    fn temp_path(name: &str) -> std::path::PathBuf {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("time should move forward")
            .as_nanos();
        std::env::temp_dir().join(format!("clawd-native-{name}-{unique}"))
    }

    #[test]
    fn reads_and_writes_files() {
        let path = temp_path("read-write.txt");
        let write_output = write_file(path.to_string_lossy().as_ref(), "one\ntwo\nthree")
            .expect("write should succeed");
        assert_eq!(write_output.kind, "create");

        let read_output = read_file(path.to_string_lossy().as_ref(), Some(1), Some(1))
            .expect("read should succeed");
        assert_eq!(read_output.file.content, "two");
    }

    #[test]
    fn edits_file_contents() {
        let path = temp_path("edit.txt");
        write_file(path.to_string_lossy().as_ref(), "alpha beta alpha")
            .expect("initial write should succeed");
        let output = edit_file(path.to_string_lossy().as_ref(), "alpha", "omega", true)
            .expect("edit should succeed");
        assert!(output.replace_all);
    }

    // v0.4.20 (#7): when a glob matches more than the 100-file cap, `num_files`
    // must report the TOTAL matched, not the (capped) number returned — the
    // model would otherwise believe only 100 files matched.
    #[test]
    fn glob_search_reports_total_match_count_when_truncated() {
        let dir = temp_path("glob-truncate-dir");
        std::fs::create_dir_all(&dir).expect("directory should be created");
        for i in 0..150 {
            write_file(
                dir.join(format!("f{i:03}.rs")).to_string_lossy().as_ref(),
                "x",
            )
            .expect("file write should succeed");
        }
        let out = glob_search("**/*.rs", Some(dir.to_string_lossy().as_ref()))
            .expect("glob should succeed");
        assert_eq!(out.num_files, 150, "num_files must be the TOTAL matched");
        assert_eq!(out.filenames.len(), 100, "returned list is still capped at 100");
        assert!(out.truncated);
    }

    #[test]
    fn globs_and_greps_directory() {
        let dir = temp_path("search-dir");
        std::fs::create_dir_all(&dir).expect("directory should be created");
        let file = dir.join("demo.rs");
        write_file(
            file.to_string_lossy().as_ref(),
            "fn main() {\n println!(\"hello\");\n}\n",
        )
        .expect("file write should succeed");

        let globbed = glob_search("**/*.rs", Some(dir.to_string_lossy().as_ref()))
            .expect("glob should succeed");
        assert_eq!(globbed.num_files, 1);

        let grep_output = grep_search(&GrepSearchInput {
            pattern: String::from("hello"),
            path: Some(dir.to_string_lossy().into_owned()),
            glob: Some(String::from("**/*.rs")),
            output_mode: Some(String::from("content")),
            before: None,
            after: None,
            context_short: None,
            context: None,
            line_numbers: Some(true),
            case_insensitive: Some(false),
            file_type: None,
            head_limit: Some(10),
            offset: Some(0),
            multiline: Some(false),
        })
        .expect("grep should succeed");
        assert!(grep_output.content.unwrap_or_default().contains("hello"));
    }

    // ---- v0.4.21 (#5): grep_search multiline in content/default mode ----

    fn grep_input(
        path: &std::path::Path,
        pattern: &str,
        mode: &str,
        multiline: bool,
    ) -> GrepSearchInput {
        GrepSearchInput {
            pattern: pattern.to_string(),
            path: Some(path.to_string_lossy().into_owned()),
            glob: None,
            output_mode: Some(mode.to_string()),
            before: None,
            after: None,
            context_short: None,
            context: None,
            line_numbers: Some(true),
            case_insensitive: Some(false),
            file_type: None,
            head_limit: None,
            offset: None,
            multiline: Some(multiline),
        }
    }

    // A cross-line pattern with multiline=true must match every line the match
    // spans: `foo\nbar` over `foo\nbar\n` covers line 1 (foo) AND line 2 (bar).
    #[test]
    fn grep_multiline_content_matches_across_lines() {
        let path = temp_path("grep-ml-across.txt");
        write_file(path.to_string_lossy().as_ref(), "foo\nbar\n").expect("write should succeed");
        let out = grep_search(&grep_input(&path, "foo\nbar", "content", true))
            .expect("grep should succeed");
        assert_eq!(out.num_lines, Some(2), "match spans two lines");
        let content = out.content.unwrap_or_default();
        assert!(content.contains(":1:foo"), "expected line 1 foo, got: {content}");
        assert!(content.contains(":2:bar"), "expected line 2 bar, got: {content}");
    }

    // Off-by-one guard: `foo\n` matching `foo\n` ends right after the newline.
    // The END line must map to the LAST matched byte (the '\n' on line 1), NOT a
    // non-existent line 2. Behavior must be only line 1, with no panic.
    #[test]
    fn grep_multiline_trailing_newline_no_off_by_one() {
        let path = temp_path("grep-ml-trailing.txt");
        write_file(path.to_string_lossy().as_ref(), "foo\n").expect("write should succeed");
        let out =
            grep_search(&grep_input(&path, "foo\n", "content", true)).expect("grep should succeed");
        assert_eq!(out.num_lines, Some(1), "only line 1 exists/matches");
        let content = out.content.unwrap_or_default();
        assert!(content.contains(":1:foo"), "got: {content}");
        assert!(!content.contains(":2:"), "must not reference a second line: {content}");
    }

    // Discriminating off-by-one catch: `foo\n` over `foo\nbar\n` ends just past
    // line 1's newline. The naive `count_nl(m.end())` would map the END to line 2
    // and wrongly pull in "bar"; mapping to the LAST matched byte keeps it on line 1.
    #[test]
    fn grep_multiline_match_ending_at_newline_does_not_pull_next_line() {
        let path = temp_path("grep-ml-endnl.txt");
        write_file(path.to_string_lossy().as_ref(), "foo\nbar\n").expect("write should succeed");
        let out =
            grep_search(&grep_input(&path, "foo\n", "content", true)).expect("grep should succeed");
        assert_eq!(out.num_lines, Some(1), "only line 1 should match");
        let content = out.content.unwrap_or_default();
        assert!(content.contains(":1:foo"), "got: {content}");
        assert!(!content.contains("bar"), "off-by-one pulled in line 2: {content}");
    }

    // No trailing newline: `bar` over `foo\nbar` matches its line (line 2) without
    // any panic from byte/char-boundary arithmetic.
    #[test]
    fn grep_multiline_no_trailing_newline_no_panic() {
        let path = temp_path("grep-ml-notrail.txt");
        write_file(path.to_string_lossy().as_ref(), "foo\nbar").expect("write should succeed");
        let out =
            grep_search(&grep_input(&path, "bar", "content", true)).expect("grep should succeed");
        assert_eq!(out.num_lines, Some(1));
        let content = out.content.unwrap_or_default();
        assert!(content.contains(":2:bar"), "got: {content}");
    }

    // Empty file with multiline=true: no matches, no panic, and no bogus line 0.
    #[test]
    fn grep_multiline_empty_file_no_match() {
        let path = temp_path("grep-ml-empty.txt");
        write_file(path.to_string_lossy().as_ref(), "").expect("write should succeed");
        let out = grep_search(&grep_input(&path, "foo\nbar", "content", true))
            .expect("grep should succeed");
        assert_eq!(out.num_files, 0, "empty file must not match");
        assert_eq!(out.num_lines, Some(0), "no bogus line emitted");
        assert_eq!(out.content.unwrap_or_default(), "");
    }

    // Unchanged behavior: without multiline, a cross-line pattern cannot match a
    // single newline-free line, so `foo\nbar` over `foo\nbar` yields no match.
    #[test]
    fn grep_without_multiline_cross_line_pattern_no_match() {
        let path = temp_path("grep-nomulti.txt");
        write_file(path.to_string_lossy().as_ref(), "foo\nbar").expect("write should succeed");
        let out = grep_search(&grep_input(&path, "foo\nbar", "content", false))
            .expect("grep should succeed");
        assert_eq!(out.num_files, 0, "cross-line pattern must not match per-line");
        assert_eq!(out.num_lines, Some(0));
    }

    // multiline=true with a plain single-line pattern still matches normally.
    #[test]
    fn grep_multiline_single_line_pattern_still_matches() {
        let path = temp_path("grep-ml-single.txt");
        write_file(path.to_string_lossy().as_ref(), "foo\nbar\n").expect("write should succeed");
        let out =
            grep_search(&grep_input(&path, "bar", "content", true)).expect("grep should succeed");
        assert_eq!(out.num_lines, Some(1));
        let content = out.content.unwrap_or_default();
        assert!(content.contains(":2:bar"), "got: {content}");
    }
}
