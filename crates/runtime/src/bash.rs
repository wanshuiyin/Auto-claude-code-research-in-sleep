use std::env;
use std::io;
use std::process::{Command, Stdio};
use std::time::Duration;

use serde::{Deserialize, Serialize};
use tokio::process::Command as TokioCommand;
use tokio::runtime::Builder;
use tokio::time::timeout;

use crate::sandbox::{
    build_linux_sandbox_command, resolve_sandbox_status_for_request, FilesystemIsolationMode,
    SandboxConfig, SandboxStatus,
};
use crate::ConfigLoader;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct BashCommandInput {
    pub command: String,
    pub timeout: Option<u64>,
    pub description: Option<String>,
    #[serde(rename = "run_in_background")]
    pub run_in_background: Option<bool>,
    #[serde(rename = "dangerouslyDisableSandbox")]
    pub dangerously_disable_sandbox: Option<bool>,
    #[serde(rename = "namespaceRestrictions")]
    pub namespace_restrictions: Option<bool>,
    #[serde(rename = "isolateNetwork")]
    pub isolate_network: Option<bool>,
    #[serde(rename = "filesystemMode")]
    pub filesystem_mode: Option<FilesystemIsolationMode>,
    #[serde(rename = "allowedMounts")]
    pub allowed_mounts: Option<Vec<String>>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct BashCommandOutput {
    pub stdout: String,
    pub stderr: String,
    #[serde(rename = "rawOutputPath")]
    pub raw_output_path: Option<String>,
    pub interrupted: bool,
    #[serde(rename = "isImage")]
    pub is_image: Option<bool>,
    #[serde(rename = "backgroundTaskId")]
    pub background_task_id: Option<String>,
    #[serde(rename = "backgroundedByUser")]
    pub backgrounded_by_user: Option<bool>,
    #[serde(rename = "assistantAutoBackgrounded")]
    pub assistant_auto_backgrounded: Option<bool>,
    #[serde(rename = "dangerouslyDisableSandbox")]
    pub dangerously_disable_sandbox: Option<bool>,
    #[serde(rename = "returnCodeInterpretation")]
    pub return_code_interpretation: Option<String>,
    #[serde(rename = "noOutputExpected")]
    pub no_output_expected: Option<bool>,
    #[serde(rename = "structuredContent")]
    pub structured_content: Option<Vec<serde_json::Value>>,
    #[serde(rename = "persistedOutputPath")]
    pub persisted_output_path: Option<String>,
    #[serde(rename = "persistedOutputSize")]
    pub persisted_output_size: Option<u64>,
    #[serde(rename = "sandboxStatus")]
    pub sandbox_status: Option<SandboxStatus>,
}

pub fn execute_bash(input: BashCommandInput) -> io::Result<BashCommandOutput> {
    // Pre-execution safety check
    if let Some(rejection) = check_dangerous_command(&input.command) {
        return Err(io::Error::new(io::ErrorKind::PermissionDenied, rejection));
    }

    let cwd = env::current_dir()?;
    let sandbox_status = sandbox_status_for_input(&input, &cwd);

    if input.run_in_background.unwrap_or(false) {
        let mut child = prepare_command(&input.command, &cwd, &sandbox_status, false);
        let child = child
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()?;

        return Ok(BashCommandOutput {
            stdout: String::new(),
            stderr: String::new(),
            raw_output_path: None,
            interrupted: false,
            is_image: None,
            background_task_id: Some(child.id().to_string()),
            backgrounded_by_user: Some(false),
            assistant_auto_backgrounded: Some(false),
            dangerously_disable_sandbox: input.dangerously_disable_sandbox,
            return_code_interpretation: None,
            no_output_expected: Some(true),
            structured_content: None,
            persisted_output_path: None,
            persisted_output_size: None,
            sandbox_status: Some(sandbox_status),
        });
    }

    let runtime = Builder::new_current_thread().enable_all().build()?;
    runtime.block_on(execute_bash_async(input, sandbox_status, cwd))
}

async fn execute_bash_async(
    input: BashCommandInput,
    sandbox_status: SandboxStatus,
    cwd: std::path::PathBuf,
) -> io::Result<BashCommandOutput> {
    let mut command = prepare_tokio_command(&input.command, &cwd, &sandbox_status, true);
    // v0.4.23 (B2): a timed-out `output()` future is DROPPED — without
    // kill_on_drop the child keeps running and its side effects land AFTER we
    // reported `interrupted: true` (the tool contract lied). kill_on_drop
    // SIGKILLs the immediate child on drop; process-group kill is explicitly
    // out of scope. Escape hatch: ARIS_BASH_KILL_ON_TIMEOUT=0 restores the old
    // let-it-run behavior. Successful completions reap before drop → no-op;
    // the background path uses std spawn and is untouched.
    if bash_kill_on_timeout_enabled(std::env::var("ARIS_BASH_KILL_ON_TIMEOUT").ok().as_deref()) {
        command.kill_on_drop(true);
    }

    let output_result = if let Some(timeout_ms) = input.timeout {
        match timeout(Duration::from_millis(timeout_ms), command.output()).await {
            Ok(result) => (result?, false),
            Err(_) => {
                return Ok(BashCommandOutput {
                    stdout: String::new(),
                    stderr: format!("Command exceeded timeout of {timeout_ms} ms"),
                    raw_output_path: None,
                    interrupted: true,
                    is_image: None,
                    background_task_id: None,
                    backgrounded_by_user: None,
                    assistant_auto_backgrounded: None,
                    dangerously_disable_sandbox: input.dangerously_disable_sandbox,
                    return_code_interpretation: Some(String::from("timeout")),
                    no_output_expected: Some(true),
                    structured_content: None,
                    persisted_output_path: None,
                    persisted_output_size: None,
                    sandbox_status: Some(sandbox_status),
                });
            }
        }
    } else {
        (command.output().await?, false)
    };

    let (output, interrupted) = output_result;
    let stdout = String::from_utf8_lossy(&output.stdout).into_owned();
    let stderr = String::from_utf8_lossy(&output.stderr).into_owned();
    let no_output_expected = Some(stdout.trim().is_empty() && stderr.trim().is_empty());
    let return_code_interpretation = output.status.code().and_then(|code| {
        if code == 0 {
            None
        } else {
            Some(format!("exit_code:{code}"))
        }
    });

    Ok(BashCommandOutput {
        stdout,
        stderr,
        raw_output_path: None,
        interrupted,
        is_image: None,
        background_task_id: None,
        backgrounded_by_user: None,
        assistant_auto_backgrounded: None,
        dangerously_disable_sandbox: input.dangerously_disable_sandbox,
        return_code_interpretation,
        no_output_expected,
        structured_content: None,
        persisted_output_path: None,
        persisted_output_size: None,
        sandbox_status: Some(sandbox_status),
    })
}

fn sandbox_status_for_input(input: &BashCommandInput, cwd: &std::path::Path) -> SandboxStatus {
    let config = ConfigLoader::default_for(cwd).load().map_or_else(
        |_| SandboxConfig::default(),
        |runtime_config| runtime_config.sandbox().clone(),
    );

    // v0.4.12 #238 — when the user has set `sandbox.strictMode: true` in
    // their config and the LLM tool call nonetheless requests
    // `dangerouslyDisableSandbox: true` (or any other override that
    // contradicts strict policy), emit a one-shot per-process warning
    // so the user can see their config is being honoured. The actual
    // request is resolved below by SandboxConfig::resolve_request which
    // already drops all LLM overrides in strict mode.
    if config.is_strict() && input_attempts_to_relax_sandbox(input) {
        warn_strict_sandbox_override();
    }

    let request = config.resolve_request(
        input.dangerously_disable_sandbox.map(|disabled| !disabled),
        input.namespace_restrictions,
        input.isolate_network,
        input.filesystem_mode,
        input.allowed_mounts.clone(),
    );
    resolve_sandbox_status_for_request(&request, cwd)
}

/// v0.4.12 #238 — `true` when the bash tool call carries any sandbox
/// override the LLM might use to relax policy. Used to gate the
/// strictMode warning so we only complain when there's an actual
/// conflict to flag.
fn input_attempts_to_relax_sandbox(input: &BashCommandInput) -> bool {
    input.dangerously_disable_sandbox == Some(true)
        || input.namespace_restrictions == Some(false)
        || input.isolate_network == Some(false)
        || input.filesystem_mode.is_some()
        || input.allowed_mounts.is_some()
}

/// v0.4.12 #238 — one-shot per-process stderr warning when strict
/// sandbox policy silently overrides a LLM tool-call override. Per-process
/// not per-session so a long-running REPL doesn't spam the user.
fn warn_strict_sandbox_override() {
    static WARNED: std::sync::OnceLock<()> = std::sync::OnceLock::new();
    WARNED.get_or_init(|| {
        eprintln!(
            "\x1b[33mwarning:\x1b[0m sandbox.strictMode is enabled; \
             LLM-requested sandbox override (e.g. `dangerouslyDisableSandbox: true`) \
             is being ignored. Set `sandbox.strictMode: false` (or remove the field) \
             in your config to allow LLM overrides."
        );
    });
}

fn prepare_command(
    command: &str,
    cwd: &std::path::Path,
    sandbox_status: &SandboxStatus,
    create_dirs: bool,
) -> Command {
    if create_dirs {
        prepare_sandbox_dirs(cwd);
    }

    if let Some(launcher) = build_linux_sandbox_command(command, cwd, sandbox_status) {
        let mut prepared = Command::new(launcher.program);
        prepared.args(launcher.args);
        prepared.current_dir(cwd);
        prepared.envs(launcher.env);
        return prepared;
    }

    if cfg!(windows) {
        let mut prepared = Command::new("cmd");
        prepared.arg("/C").arg(command).current_dir(cwd);
        return prepared;
    }

    let mut prepared = Command::new("sh");
    prepared.arg("-lc").arg(command).current_dir(cwd);
    if sandbox_status.filesystem_active {
        prepared.env("HOME", cwd.join(".sandbox-home"));
        prepared.env("TMPDIR", cwd.join(".sandbox-tmp"));
    }
    prepared
}

/// v0.4.23 (B2): only the exact opt-out `"0"` disables the timeout kill;
/// unset or any other value keeps it on (pure for the truth-table test).
fn bash_kill_on_timeout_enabled(env_value: Option<&str>) -> bool {
    env_value != Some("0")
}

fn prepare_tokio_command(
    command: &str,
    cwd: &std::path::Path,
    sandbox_status: &SandboxStatus,
    create_dirs: bool,
) -> TokioCommand {
    if create_dirs {
        prepare_sandbox_dirs(cwd);
    }

    if let Some(launcher) = build_linux_sandbox_command(command, cwd, sandbox_status) {
        let mut prepared = TokioCommand::new(launcher.program);
        prepared.args(launcher.args);
        prepared.current_dir(cwd);
        prepared.envs(launcher.env);
        return prepared;
    }

    if cfg!(windows) {
        let mut prepared = TokioCommand::new("cmd");
        prepared.arg("/C").arg(command).current_dir(cwd);
        return prepared;
    }

    let mut prepared = TokioCommand::new("sh");
    prepared.arg("-lc").arg(command).current_dir(cwd);
    if sandbox_status.filesystem_active {
        prepared.env("HOME", cwd.join(".sandbox-home"));
        prepared.env("TMPDIR", cwd.join(".sandbox-tmp"));
    }
    prepared
}

fn prepare_sandbox_dirs(cwd: &std::path::Path) {
    let _ = std::fs::create_dir_all(cwd.join(".sandbox-home"));
    let _ = std::fs::create_dir_all(cwd.join(".sandbox-tmp"));
}

/// Check for dangerous bash command patterns. Returns rejection reason or None.
fn check_dangerous_command(command: &str) -> Option<String> {
    let normalized = command.to_ascii_lowercase();
    let tokens: Vec<&str> = normalized.split_whitespace().collect();

    // Patterns that are always dangerous
    const DANGEROUS_PATTERNS: &[(&str, &str)] = &[
        ("rm -rf /", "recursive deletion of root filesystem"),
        ("rm -rf /*", "recursive deletion of root filesystem"),
        ("rm -rf ~", "recursive deletion of home directory"),
        ("mkfs", "filesystem formatting"),
        ("dd if=/dev/zero", "disk overwrite"),
        ("dd if=/dev/random", "disk overwrite"),
        (":(){:|:&};:", "fork bomb"),
        ("chmod -r 777 /", "recursive permission change on root"),
        ("chown -r", "recursive ownership change"),
    ];

    for (pattern, reason) in DANGEROUS_PATTERNS {
        if normalized.contains(pattern) {
            return Some(format!(
                "Blocked: command matches dangerous pattern ({reason}): {pattern}"
            ));
        }
    }

    // Check for sudo + destructive commands
    if tokens.first() == Some(&"sudo") || normalized.contains("| sudo") {
        let after_sudo = if tokens.first() == Some(&"sudo") {
            tokens.get(1).copied().unwrap_or("")
        } else {
            // Find command after "| sudo"
            normalized
                .split("| sudo")
                .nth(1)
                .and_then(|s| s.split_whitespace().next())
                .unwrap_or("")
        };
        const SUDO_BLOCKED: &[&str] = &["rm", "mkfs", "dd", "chmod", "chown", "fdisk", "parted"];
        if SUDO_BLOCKED.iter().any(|cmd| after_sudo == *cmd) {
            return Some(format!(
                "Blocked: sudo with destructive command '{after_sudo}'"
            ));
        }
    }

    None
}

#[cfg(test)]
mod tests {
    use super::{execute_bash, BashCommandInput};
    use crate::sandbox::FilesystemIsolationMode;

    #[test]
    fn executes_simple_command() {
        let output = execute_bash(BashCommandInput {
            command: String::from("printf 'hello'"),
            timeout: Some(1_000),
            description: None,
            run_in_background: Some(false),
            dangerously_disable_sandbox: Some(false),
            namespace_restrictions: Some(false),
            isolate_network: Some(false),
            filesystem_mode: Some(FilesystemIsolationMode::WorkspaceOnly),
            allowed_mounts: None,
        })
        .expect("bash command should execute");

        assert_eq!(output.stdout, "hello");
        assert!(!output.interrupted);
        assert!(output.sandbox_status.is_some());
    }

    #[test]
    fn disables_sandbox_when_requested() {
        let output = execute_bash(BashCommandInput {
            command: String::from("printf 'hello'"),
            timeout: Some(1_000),
            description: None,
            run_in_background: Some(false),
            dangerously_disable_sandbox: Some(true),
            namespace_restrictions: None,
            isolate_network: None,
            filesystem_mode: None,
            allowed_mounts: None,
        })
        .expect("bash command should execute");

        assert!(!output.sandbox_status.expect("sandbox status").enabled);
    }

    /// v0.4.23 (B2): only the exact "0" opts out of the timeout kill.
    #[test]
    fn bash_kill_on_timeout_gate_truth_table() {
        use super::bash_kill_on_timeout_enabled;
        assert!(bash_kill_on_timeout_enabled(None));
        assert!(bash_kill_on_timeout_enabled(Some("1")));
        assert!(bash_kill_on_timeout_enabled(Some("")));
        assert!(bash_kill_on_timeout_enabled(Some("true")));
        assert!(!bash_kill_on_timeout_enabled(Some("0")));
    }

    /// v0.4.23 (B2): the REAL behavioral lock — a timed-out command's side
    /// effects must NOT land after the tool reported `interrupted: true`.
    /// Pre-B2 the dropped `output()` future left the child running and the
    /// marker file appeared ~1s later.
    #[cfg(unix)]
    #[test]
    fn bash_timeout_kills_child_process() {
        // Gate round-2 hermeticity: (a) a legitimately-set escape hatch in
        // the developer's shell must not fail the CORRECT implementation —
        // isolate it; (b) a strict sandbox config could block the marker
        // write entirely and green-wash the OLD defect — prove writability
        // with a control run first and skip when the env can't write.
        std::env::remove_var("ARIS_BASH_KILL_ON_TIMEOUT");
        let marker = std::env::temp_dir().join(format!(
            "aris-b2-marker-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .expect("time")
                .as_nanos()
        ));
        let marker_str = marker.display().to_string();
        let control = execute_bash(BashCommandInput {
            command: format!("touch '{marker_str}.control'"),
            timeout: Some(5_000),
            description: None,
            run_in_background: Some(false),
            dangerously_disable_sandbox: Some(true),
            namespace_restrictions: None,
            isolate_network: None,
            filesystem_mode: None,
            allowed_mounts: None,
        })
        .expect("control bash command should execute");
        let control_marker = std::path::PathBuf::from(format!("{marker_str}.control"));
        if control.interrupted || !control_marker.exists() {
            // Environment (e.g. strict sandbox) can't write the marker at all
            // — the assertion below would be meaningless; skip honestly.
            eprintln!("skipping bash_timeout_kills_child_process: env cannot write markers");
            let _ = std::fs::remove_file(&control_marker);
            return;
        }
        let _ = std::fs::remove_file(&control_marker);
        let output = execute_bash(BashCommandInput {
            command: format!("sleep 1 && touch '{marker_str}'"),
            timeout: Some(120),
            description: None,
            run_in_background: Some(false),
            dangerously_disable_sandbox: Some(true),
            namespace_restrictions: None,
            isolate_network: None,
            filesystem_mode: None,
            allowed_mounts: None,
        })
        .expect("bash command should execute");
        assert!(output.interrupted, "the 120ms timeout must fire");
        // Give a surviving child ample time to prove it survived (pre-B2 it
        // touched the marker at ~1s).
        std::thread::sleep(std::time::Duration::from_millis(1_800));
        assert!(
            !marker.exists(),
            "child survived the timeout and touched the marker — kill_on_drop regressed"
        );
        let _ = std::fs::remove_file(&marker);
    }
}
