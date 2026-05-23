"""End-to-end integration test: simulates a real ARIS skill calling manual-review MCP.

This test:
1. Starts the MCP server as a subprocess (exactly how Claude Code would)
2. Sends a realistic review prompt (same format as /research-review sends to Codex)
3. Simulates a user submitting a response via the HTTP endpoint
4. Verifies the MCP returns the correct format that skills expect
5. Tests review_reply (multi-round) with threadId continuity
"""

import json
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path

SERVER_PATH = Path(__file__).parent.parent / "mcp-servers" / "manual-review" / "server.py"

# A realistic review prompt (shortened version of what /research-review sends to Codex)
REALISTIC_PROMPT = """You are reviewing a NeurIPS paper. Please provide a detailed, structured review.

## Paper Title: Factorized Discrete Diffusion for Efficient Text Generation

## Abstract:
We propose FDD, a factorized approach to discrete diffusion language models that
decomposes the joint denoising distribution into independent per-token factors...

## Method Summary:
The key insight is that standard discrete diffusion models parameterize a joint
distribution over all tokens, which is computationally expensive...

## Results:
- Perplexity: 12.3 (baseline: 14.1, improvement: -12.7%)
- Generation speed: 3.2x faster than AR baseline
- Human eval: 4.2/5 fluency (baseline: 4.0/5)

## Review Instructions
Please act as a senior ML reviewer (NeurIPS level). Provide:
1. **Overall Score** (1-10, where 6 = weak accept, 7 = accept)
2. **Summary** (2-3 sentences)
3. **Strengths** (bullet list, ranked)
4. **Weaknesses** (bullet list, ranked: CRITICAL > MAJOR > MINOR)
5. **For each CRITICAL/MAJOR weakness**: A specific, actionable fix
6. **Verdict**: Ready for submission? Yes / Almost / No

Focus on: theoretical rigor, claims vs evidence alignment, writing clarity.
"""

# A realistic review response (what a model like GPT-5.5 would return)
REALISTIC_RESPONSE = """## Overall Score: 6/10

## Summary
The paper presents FDD, a factorized discrete diffusion approach that achieves meaningful speedups over standard discrete diffusion LMs while maintaining competitive perplexity. The core factorization idea is sound but the experimental evaluation has gaps.

## Strengths
- Clear and well-motivated factorization of the joint denoising distribution
- Significant speedup (3.2x) with modest perplexity degradation
- Solid theoretical grounding in the independence assumption analysis (Section 3.2)

## Weaknesses

### CRITICAL
1. **Missing ablation on factorization granularity** — The paper only tests full per-token independence. What about block-level factorization (e.g., 4-token blocks)? This is the most natural middle ground and its absence weakens the contribution claim.
   - **Fix**: Add experiments with block sizes {2, 4, 8, 16} and show the perplexity-speed Pareto frontier.

### MAJOR
2. **Human eval sample size too small** — 4.2/5 vs 4.0/5 on fluency is not statistically significant without knowing N and confidence intervals.
   - **Fix**: Report N, compute bootstrap CIs, run significance test (paired t-test or Wilcoxon).

3. **No comparison with recent semi-autoregressive baselines** — SUNDAE (Savinov et al., 2022) and DiffusionBERT achieve similar speedups with different trade-offs.
   - **Fix**: Add these baselines to Table 1.

### MINOR
4. Notation inconsistency: q(x_t | x_0) vs q_t(x | x_0) used interchangeably in Sections 2 and 3.

## Verdict: Almost

The core idea is solid and the speedup is real, but the missing ablation (CRITICAL #1) and weak human eval (MAJOR #2) need to be addressed before submission. Fixable in 1-2 weeks.
"""


def send_jsonrpc(proc, method, params=None, req_id=1):
    msg = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params:
        msg["params"] = params
    payload = json.dumps(msg).encode("utf-8")
    header = f"Content-Length: {len(payload)}\r\n\r\n".encode("utf-8")
    proc.stdin.write(header + payload)
    proc.stdin.flush()


def read_response(proc, timeout=15):
    deadline = time.monotonic() + timeout
    header = b""
    while time.monotonic() < deadline:
        byte = proc.stdout.read(1)
        if not byte:
            break
        header += byte
        if header.endswith(b"\r\n\r\n"):
            break
    content_length = 0
    for line in header.decode("utf-8", errors="replace").split("\r\n"):
        if line.lower().startswith("content-length:"):
            content_length = int(line.split(":", 1)[1].strip())
    if content_length == 0:
        return None
    body = proc.stdout.read(content_length)
    return json.loads(body.decode("utf-8"))


def simulate_user_submit(port, response_text, delay=1.0):
    """Simulate a user pasting a response after a short delay."""
    time.sleep(delay)
    data = json.dumps({"response": response_text}).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/submit",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=5)
        return True
    except Exception as e:
        print(f"  [submit error] {e}")
        return False


def find_server_port(pending_dir, timeout=8):
    """Read the port from the pending state file written by the server."""
    state_path = Path(pending_dir) / "pending_review.json"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if state_path.exists():
            try:
                data = json.loads(state_path.read_text(encoding="utf-8"))
                url = data.get("url", "")
                if url and ":" in url:
                    port = int(url.rsplit(":", 1)[1])
                    # Verify it's actually responding
                    try:
                        urllib.request.urlopen(f"http://127.0.0.1:{port}/api/context", timeout=1)
                        return port
                    except:
                        pass
            except (json.JSONDecodeError, ValueError, OSError):
                pass
        time.sleep(0.3)
    return None


def main():
    print("=" * 60)
    print("Integration Test: Manual Review MCP in ARIS Workflow")
    print("=" * 60)

    import os
    import tempfile
    tmpdir = tempfile.mkdtemp(prefix="aris_manual_review_test_")
    pending_dir = os.path.join(tmpdir, "pending_review")

    env = {
        **os.environ,
        "MANUAL_REVIEW_AUTO_OPEN": "false",
        "MANUAL_REVIEW_TIMEOUT_SEC": "30",
        "MANUAL_REVIEW_PENDING_DIR": pending_dir,
    }

    proc = subprocess.Popen(
        [sys.executable, str(SERVER_PATH)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    try:
        # --- Step 1: Initialize (same as Claude Code does on startup) ---
        print("\n[1] MCP Initialize...")
        send_jsonrpc(proc, "initialize", {}, req_id=1)
        resp = read_response(proc)
        assert resp and resp["result"]["serverInfo"]["name"] == "manual-review"
        print("    OK — server identified as 'manual-review'")

        # Notify initialized
        send_jsonrpc(proc, "notifications/initialized", {}, req_id=2)
        read_response(proc)

        # --- Step 2: Simulate /research-review calling review tool ---
        print("\n[2] Simulating /research-review skill calling mcp__manual_review__review...")
        print(f"    Prompt length: {len(REALISTIC_PROMPT)} chars")

        # We need to find the port after the tool call starts the HTTP server.
        # The tool call will block until user submits, so we send it and then
        # find the port in a separate thread.

        # Send the tool call
        send_jsonrpc(proc, "tools/call", {
            "name": "review",
            "arguments": {
                "prompt": REALISTIC_PROMPT,
                "config": {"model_reasoning_effort": "xhigh"},
            },
        }, req_id=3)

        # Give the HTTP server a moment to start
        time.sleep(1.5)

        # Find the port by reading the pending state file
        print("    Searching for HTTP server port...")
        port = find_server_port(pending_dir, timeout=8)
        if not port:
            print("    FAIL — could not find HTTP server port")
            return False

        print(f"    Found server at port {port}")

        # Verify /api/context returns the correct prompt
        ctx_resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/context")
        ctx = json.loads(ctx_resp.read().decode("utf-8"))
        # Compare stripped to handle platform line-ending differences
        assert ctx["prompt"].strip() == REALISTIC_PROMPT.strip(), \
            f"Prompt mismatch! Lengths: sent={len(REALISTIC_PROMPT)}, got={len(ctx['prompt'])}"
        assert ctx["config"]["model_reasoning_effort"] == "xhigh"
        print("    OK — /api/context returns correct prompt and config")

        # --- Step 3: Simulate user submitting the review response ---
        print("\n[3] Simulating user pasting review response...")
        print(f"    Response length: {len(REALISTIC_RESPONSE)} chars")

        submit_ok = simulate_user_submit(port, REALISTIC_RESPONSE, delay=0.5)
        assert submit_ok, "Submit failed!"
        print("    OK — response submitted via HTTP")

        # --- Step 4: Read the MCP tool result ---
        print("\n[4] Reading MCP tool result...")
        result = read_response(proc, timeout=10)
        assert result is not None, "No response from MCP server"
        assert "result" in result, f"Error response: {result}"

        content_text = result["result"]["content"][0]["text"]
        payload = json.loads(content_text)

        assert "threadId" in payload, f"Missing threadId: {payload}"
        assert "content" in payload, f"Missing content: {payload}"
        assert payload["content"].strip() == REALISTIC_RESPONSE.strip(), \
            f"Response mismatch! Lengths: sent={len(REALISTIC_RESPONSE)}, got={len(payload['content'])}"
        thread_id = payload["threadId"]
        print(f"    OK — threadId: {thread_id}")
        print(f"    OK — response matches (first 80 chars): {payload['content'][:80]}...")

        # --- Step 5: Verify skill can parse the response ---
        print("\n[5] Verifying skill-compatible parsing...")
        response_text = payload["content"]

        # Parse score (same regex pattern skills use)
        import re
        score_match = re.search(r"Score[:\s]*(\d+)/10", response_text)
        assert score_match, "Could not parse score from response"
        score = int(score_match.group(1))
        assert score == 6, f"Wrong score: {score}"
        print(f"    OK — Parsed score: {score}/10")

        # Parse verdict
        verdict_match = re.search(r"Verdict[:\s]*(.*)", response_text)
        assert verdict_match, "Could not parse verdict"
        verdict = verdict_match.group(1).strip()
        print(f"    OK — Parsed verdict: {verdict}")

        # --- Step 6: Test review_reply (multi-round) ---
        print("\n[6] Testing review_reply (Round 2 — multi-round continuity)...")

        round2_prompt = """Round 2/4 of autonomous review loop.

Since last review, we have:
- Added block-level factorization ablation (block sizes 2, 4, 8, 16)
- Expanded human eval to N=200 with bootstrap CIs
- Added SUNDAE and DiffusionBERT baselines to Table 1

Please re-score and re-assess. Has the paper improved?
"""
        send_jsonrpc(proc, "tools/call", {
            "name": "review_reply",
            "arguments": {
                "threadId": thread_id,
                "prompt": round2_prompt,
                "config": {"model_reasoning_effort": "xhigh"},
            },
        }, req_id=4)

        time.sleep(1.5)
        port2 = find_server_port(pending_dir, timeout=8)
        if not port2:
            print("    FAIL — could not find HTTP server for round 2")
            return False

        # Verify history is shown
        ctx2_resp = urllib.request.urlopen(f"http://127.0.0.1:{port2}/api/context")
        ctx2 = json.loads(ctx2_resp.read().decode("utf-8"))
        assert len(ctx2["history"]) >= 2, f"Expected history, got: {len(ctx2['history'])} items"
        assert ctx2["history"][0]["role"] == "user"
        assert ctx2["history"][0]["content"].strip() == REALISTIC_PROMPT.strip()
        print(f"    OK — Round 2 page shows {len(ctx2['history'])} history entries")

        # Submit round 2 response
        round2_response = "## Overall Score: 7/10\n\nThe paper has improved significantly. All three major issues addressed."
        simulate_user_submit(port2, round2_response, delay=0.5)

        result2 = read_response(proc, timeout=10)
        assert result2 is not None
        payload2 = json.loads(result2["result"]["content"][0]["text"])
        assert payload2["threadId"] == thread_id, "ThreadId should be preserved across rounds"
        assert "7/10" in payload2["content"]
        print(f"    OK — Round 2 response received, same threadId preserved")
        print(f"    OK — Score improved: 6/10 → 7/10")

        # --- Summary ---
        print("\n" + "=" * 60)
        print("ALL INTEGRATION TESTS PASSED")
        print("=" * 60)
        print("")
        print("Verified:")
        print("  [OK] MCP server starts and responds to initialize")
        print("  [OK] Realistic review prompt (%d chars) delivered correctly" % len(REALISTIC_PROMPT))
        print("  [OK] User submit via HTTP works")
        print("  [OK] Return format compatible (threadId + response)")
        print("  [OK] Skill-level parsing works (score extraction, verdict)")
        print("  [OK] Multi-round review_reply preserves threadId and shows history")
        print("  [OK] Full round-trip: skill -> MCP -> browser -> user -> MCP -> skill")
        print("")
        return True

    except Exception as e:
        print(f"\n  FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        proc.terminate()
        proc.wait(timeout=3)
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
