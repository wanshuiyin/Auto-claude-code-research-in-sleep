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
