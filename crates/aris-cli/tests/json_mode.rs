//! v0.4.22 (C3, design-mandated wiring test): `--output-format json` must
//! NEVER prompt. End-to-end against the real `aris` binary with a local mock
//! Anthropic SSE server: the model "asks" for a DangerFullAccess tool (bash)
//! under `--permission-mode workspace-write`, the permission engine takes the
//! structured-deny path (prompter is None on the JSON path), a second turn
//! completes normally — and stdout is exactly ONE valid JSON document with no
//! approval text and no stdin read (stdin is closed).

use std::io::{Read, Write};
use std::net::TcpListener;
use std::process::{Command, Stdio};
use std::thread;
use std::time::{Duration, Instant};

/// Minimal HTTP/1.1 responder: accepts `count` sequential connections, reads
/// the request until the header terminator (plus best-effort body), answers
/// with the queued response, closes. Mirrors the api crate's integration
/// harness in spirit; std-only here because this is a binary-crate test.
fn spawn_mock_anthropic(responses: Vec<String>) -> (String, thread::JoinHandle<()>) {
    let listener = TcpListener::bind("127.0.0.1:0").expect("bind mock server");
    let addr = listener.local_addr().expect("mock server addr");
    let handle = thread::spawn(move || {
        for body in responses {
            let (mut socket, _) = match listener.accept() {
                Ok(pair) => pair,
                Err(_) => return,
            };
            socket
                .set_read_timeout(Some(Duration::from_secs(10)))
                .ok();
            // Read request headers (and drain what we can of the body).
            let mut buf = Vec::new();
            let mut chunk = [0u8; 4096];
            while !buf.windows(4).any(|w| w == b"\r\n\r\n") {
                match socket.read(&mut chunk) {
                    Ok(0) => break,
                    Ok(n) => buf.extend_from_slice(&chunk[..n]),
                    Err(_) => break,
                }
            }
            let response = format!(
                "HTTP/1.1 200 OK\r\ncontent-type: text/event-stream\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{}",
                body.len(),
                body
            );
            let _ = socket.write_all(response.as_bytes());
            let _ = socket.flush();
        }
    });
    (format!("http://{addr}"), handle)
}

fn sse_tool_use_turn() -> String {
    concat!(
        "event: message_start\n",
        "data: {\"type\":\"message_start\",\"message\":{\"id\":\"msg_1\",\"type\":\"message\",\"role\":\"assistant\",\"content\":[],\"model\":\"claude-opus-4-8\",\"stop_reason\":null,\"stop_sequence\":null,\"usage\":{\"input_tokens\":10,\"output_tokens\":1}}}\n\n",
        "event: content_block_start\n",
        "data: {\"type\":\"content_block_start\",\"index\":0,\"content_block\":{\"type\":\"tool_use\",\"id\":\"toolu_1\",\"name\":\"bash\",\"input\":{}}}\n\n",
        "event: content_block_delta\n",
        "data: {\"type\":\"content_block_delta\",\"index\":0,\"delta\":{\"type\":\"input_json_delta\",\"partial_json\":\"{\\\"command\\\":\\\"pwd\\\"}\"}}\n\n",
        "event: content_block_stop\n",
        "data: {\"type\":\"content_block_stop\",\"index\":0}\n\n",
        "event: message_delta\n",
        "data: {\"type\":\"message_delta\",\"delta\":{\"stop_reason\":\"tool_use\",\"stop_sequence\":null},\"usage\":{\"input_tokens\":10,\"output_tokens\":5}}\n\n",
        "event: message_stop\n",
        "data: {\"type\":\"message_stop\"}\n\n",
    )
    .to_string()
}

fn sse_final_text_turn() -> String {
    concat!(
        "event: message_start\n",
        "data: {\"type\":\"message_start\",\"message\":{\"id\":\"msg_2\",\"type\":\"message\",\"role\":\"assistant\",\"content\":[],\"model\":\"claude-opus-4-8\",\"stop_reason\":null,\"stop_sequence\":null,\"usage\":{\"input_tokens\":20,\"output_tokens\":1}}}\n\n",
        "event: content_block_start\n",
        "data: {\"type\":\"content_block_start\",\"index\":0,\"content_block\":{\"type\":\"text\",\"text\":\"\"}}\n\n",
        "event: content_block_delta\n",
        "data: {\"type\":\"content_block_delta\",\"index\":0,\"delta\":{\"type\":\"text_delta\",\"text\":\"the tool was denied, done\"}}\n\n",
        "event: content_block_stop\n",
        "data: {\"type\":\"content_block_stop\",\"index\":0}\n\n",
        "event: message_delta\n",
        "data: {\"type\":\"message_delta\",\"delta\":{\"stop_reason\":\"end_turn\",\"stop_sequence\":null},\"usage\":{\"input_tokens\":20,\"output_tokens\":6}}\n\n",
        "event: message_stop\n",
        "data: {\"type\":\"message_stop\"}\n\n",
    )
    .to_string()
}

#[test]
fn json_mode_denies_escalation_without_prompting_and_emits_single_json_doc() {
    let (base_url, _server) = spawn_mock_anthropic(vec![sse_tool_use_turn(), sse_final_text_turn()]);

    let home = std::env::temp_dir().join(format!("aris-json-mode-{}", std::process::id()));
    std::fs::create_dir_all(&home).expect("temp home");

    let mut child = Command::new(env!("CARGO_BIN_EXE_aris"))
        .args([
            "--output-format",
            "json",
            "--permission-mode",
            "workspace-write",
            "--allowedTools",
            "bash",
            "run pwd via bash",
        ])
        // Isolated home: no user config/settings/mcpServers/sessions leak in.
        .env("HOME", &home)
        .env("CLAUDE_CONFIG_HOME", home.join("claude"))
        .env("XDG_CONFIG_HOME", home.join("xdg"))
        .env("ANTHROPIC_API_KEY", "test-key-json-mode")
        .env("ANTHROPIC_BASE_URL", &base_url)
        .env("ARIS_DISABLE_KEYCHAIN", "1")
        .env("ARIS_NO_HISTORY", "1")
        .env_remove("EXECUTOR_PROVIDER")
        .env_remove("ANTHROPIC_AUTH_TOKEN")
        // A developer shell with http(s)_proxy set would route the child's
        // 127.0.0.1 mock-server requests through the proxy (502s) — scrub.
        .env_remove("http_proxy")
        .env_remove("https_proxy")
        .env_remove("HTTP_PROXY")
        .env_remove("HTTPS_PROXY")
        .env_remove("all_proxy")
        .env_remove("ALL_PROXY")
        .env("NO_PROXY", "127.0.0.1,localhost")
        .current_dir(&home)
        // THE point of the test: stdin is CLOSED. A prompting JSON path would
        // block (pre-v0.4.22 behavior printed "Permission approval required"
        // and read stdin); the fixed path must complete without it.
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("spawn aris binary");

    // Hard timeout so a regression (stdin block) fails fast instead of hanging.
    let deadline = Instant::now() + Duration::from_secs(60);
    let status = loop {
        match child.try_wait().expect("try_wait") {
            Some(status) => break status,
            None if Instant::now() > deadline => {
                let _ = child.kill();
                panic!("aris --output-format json hung (>60s) — prompting/stdin-block regression?");
            }
            None => thread::sleep(Duration::from_millis(100)),
        }
    };

    let mut stdout = String::new();
    child
        .stdout
        .take()
        .expect("stdout piped")
        .read_to_string(&mut stdout)
        .expect("read stdout");
    let mut stderr = String::new();
    child
        .stderr
        .take()
        .expect("stderr piped")
        .read_to_string(&mut stderr)
        .expect("read stderr");

    assert!(
        status.success(),
        "aris exited with {status:?}\nstdout:\n{stdout}\nstderr:\n{stderr}"
    );
    // No approval prompt anywhere near stdout (the single-JSON contract).
    assert!(
        !stdout.contains("Permission approval required") && !stdout.contains("Approve"),
        "JSON stdout was polluted by an approval prompt:\n{stdout}"
    );
    // stdout parses as exactly ONE JSON document.
    let doc: serde_json::Value = serde_json::from_str(stdout.trim())
        .unwrap_or_else(|e| panic!("stdout is not a single JSON document ({e}):\n{stdout}"));
    // The DangerFullAccess bash call under workspace-write took the
    // structured-deny path (prompter is None on the JSON path).
    let tool_results = doc
        .get("tool_results")
        .and_then(serde_json::Value::as_array)
        .unwrap_or_else(|| panic!("missing tool_results in {doc}"));
    let denied = tool_results.iter().any(|r| {
        r.to_string().contains("requires approval")
            || r.to_string().to_lowercase().contains("denied")
    });
    assert!(
        denied,
        "expected the bash escalation to be structurally denied, got: {doc}"
    );

    let _ = std::fs::remove_dir_all(&home);
}

/// v0.4.23 (A, codex-mandated sentinel): Anthropic thinking deltas must NEVER
/// reach stdout in text mode. (We deliberately do NOT assert on the word
/// "Thinking" — the spinner legitimately prints "Thinking...".)
fn sse_thinking_then_text_turn() -> String {
    concat!(
        "event: message_start\n",
        "data: {\"type\":\"message_start\",\"message\":{\"id\":\"msg_t\",\"type\":\"message\",\"role\":\"assistant\",\"content\":[],\"model\":\"claude-opus-4-8\",\"stop_reason\":null,\"stop_sequence\":null,\"usage\":{\"input_tokens\":5,\"output_tokens\":1}}}\n\n",
        "event: content_block_start\n",
        "data: {\"type\":\"content_block_start\",\"index\":0,\"content_block\":{\"type\":\"thinking\",\"thinking\":\"\",\"signature\":\"\"}}\n\n",
        "event: content_block_delta\n",
        "data: {\"type\":\"content_block_delta\",\"index\":0,\"delta\":{\"type\":\"thinking_delta\",\"thinking\":\"ARIS_THINKING_SENTINEL_XK9\"}}\n\n",
        "event: content_block_stop\n",
        "data: {\"type\":\"content_block_stop\",\"index\":0}\n\n",
        "event: content_block_start\n",
        "data: {\"type\":\"content_block_start\",\"index\":1,\"content_block\":{\"type\":\"text\",\"text\":\"\"}}\n\n",
        "event: content_block_delta\n",
        "data: {\"type\":\"content_block_delta\",\"index\":1,\"delta\":{\"type\":\"text_delta\",\"text\":\"visible reply body\"}}\n\n",
        "event: content_block_stop\n",
        "data: {\"type\":\"content_block_stop\",\"index\":1}\n\n",
        "event: message_delta\n",
        "data: {\"type\":\"message_delta\",\"delta\":{\"stop_reason\":\"end_turn\",\"stop_sequence\":null},\"usage\":{\"input_tokens\":5,\"output_tokens\":4}}\n\n",
        "event: message_stop\n",
        "data: {\"type\":\"message_stop\"}\n\n",
    )
    .to_string()
}

fn isolated_aris(home: &std::path::Path, base_url: &str) -> Command {
    let mut cmd = Command::new(env!("CARGO_BIN_EXE_aris"));
    cmd.env("HOME", home)
        .env("CLAUDE_CONFIG_HOME", home.join("claude"))
        .env("XDG_CONFIG_HOME", home.join("xdg"))
        .env("ANTHROPIC_BASE_URL", base_url)
        .env("ARIS_DISABLE_KEYCHAIN", "1")
        .env("ARIS_NO_HISTORY", "1")
        .env_remove("EXECUTOR_PROVIDER")
        .env_remove("EXECUTOR_API_KEY")
        .env_remove("EXECUTOR_BASE_URL")
        .env_remove("ANTHROPIC_AUTH_TOKEN")
        .env_remove("http_proxy")
        .env_remove("https_proxy")
        .env_remove("HTTP_PROXY")
        .env_remove("HTTPS_PROXY")
        .env_remove("all_proxy")
        .env_remove("ALL_PROXY")
        .env("NO_PROXY", "127.0.0.1,localhost")
        .current_dir(home)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    cmd
}

fn wait_with_timeout(child: &mut std::process::Child, secs: u64) -> std::process::ExitStatus {
    let deadline = Instant::now() + Duration::from_secs(secs);
    loop {
        match child.try_wait().expect("try_wait") {
            Some(status) => return status,
            None if Instant::now() > deadline => {
                let _ = child.kill();
                panic!("aris hung (>{secs}s)");
            }
            None => thread::sleep(Duration::from_millis(100)),
        }
    }
}

#[test]
fn text_mode_never_prints_anthropic_thinking() {
    let (base_url, _server) = spawn_mock_anthropic(vec![sse_thinking_then_text_turn()]);
    let home = std::env::temp_dir().join(format!("aris-think-{}", std::process::id()));
    std::fs::create_dir_all(&home).expect("temp home");

    let mut child = isolated_aris(&home, &base_url);
    child
        .args(["--print", "say something"])
        .env("ANTHROPIC_API_KEY", "test-key-thinking");
    let mut child = child.spawn().expect("spawn aris");
    let status = wait_with_timeout(&mut child, 60);

    let mut stdout = String::new();
    child.stdout.take().unwrap().read_to_string(&mut stdout).unwrap();
    let mut stderr = String::new();
    child.stderr.take().unwrap().read_to_string(&mut stderr).unwrap();

    assert!(status.success(), "exit {status:?}\nstdout:\n{stdout}\nstderr:\n{stderr}");
    assert!(
        stdout.contains("visible reply"),
        "the visible text must render: {stdout}"
    );
    assert!(
        !stdout.contains("ARIS_THINKING_SENTINEL_XK9")
            && !stderr.contains("ARIS_THINKING_SENTINEL_XK9"),
        "thinking content leaked to the terminal:\nstdout:\n{stdout}\nstderr:\n{stderr}"
    );

    let _ = std::fs::remove_dir_all(&home);
}

/// v0.4.23 (A, codex-mandated sentinel): Kimi-family `reasoning_content` must
/// never reach the terminal either (it only feeds the replay cache).
#[test]
fn text_mode_never_prints_kimi_reasoning() {
    let openai_sse = concat!(
        "data: {\"choices\":[{\"delta\":{\"reasoning_content\":\"ARIS_KIMI_REASONING_SENTINEL_QZ7\"}}]}\n\n",
        "data: {\"choices\":[{\"delta\":{\"content\":\"kimi visible answer\"}}]}\n\n",
        "data: {\"choices\":[{\"finish_reason\":\"stop\"}]}\n\n",
        "data: [DONE]\n\n",
    )
    .to_string();
    let (base_url, _server) = spawn_mock_anthropic(vec![openai_sse]);
    let home = std::env::temp_dir().join(format!("aris-kimi-{}", std::process::id()));
    std::fs::create_dir_all(&home).expect("temp home");

    let mut child = isolated_aris(&home, &base_url);
    child
        .args(["--model", "kimi-k2.5", "--print", "say something"])
        .env("EXECUTOR_PROVIDER", "openai")
        .env("EXECUTOR_API_KEY", "test-key-kimi")
        .env("EXECUTOR_BASE_URL", &base_url);
    let mut child = child.spawn().expect("spawn aris");
    let status = wait_with_timeout(&mut child, 60);

    let mut stdout = String::new();
    child.stdout.take().unwrap().read_to_string(&mut stdout).unwrap();
    let mut stderr = String::new();
    child.stderr.take().unwrap().read_to_string(&mut stderr).unwrap();

    assert!(status.success(), "exit {status:?}\nstdout:\n{stdout}\nstderr:\n{stderr}");
    assert!(
        stdout.contains("kimi visible answer"),
        "the visible text must render: {stdout}"
    );
    assert!(
        !stdout.contains("ARIS_KIMI_REASONING_SENTINEL_QZ7")
            && !stderr.contains("ARIS_KIMI_REASONING_SENTINEL_QZ7"),
        "reasoning_content leaked to the terminal:\nstdout:\n{stdout}\nstderr:\n{stderr}"
    );

    let _ = std::fs::remove_dir_all(&home);
}
