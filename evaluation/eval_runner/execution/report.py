# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""HTML report generator for eval results.

Reads ``eval-results/*/result.json`` files and produces a self-contained
``report.html`` dashboard with summary grid + per-scenario detail views.

Standalone from the eval runner — only needs the JSON result files on disk.

Usage::

    # Via CLI:
    ./run-eval.sh report
    ./run-eval.sh report --results-dir /path/to/eval-results

    # Via Python:
    from eval_runner.execution.report import generate_dashboard
    generate_dashboard()
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def generate_dashboard(results_dir: Path | None = None) -> str:
    """Generate a combined HTML dashboard from all result JSON files.

    Scans ``results_dir`` for ``*/result.json`` files and produces a single
    self-contained ``report.html``.

    Args:
        results_dir: Root eval-results directory. Defaults to ``./eval-results/``.

    Returns:
        Absolute path to the generated HTML file.
    """
    if results_dir is None:
        results_dir = Path.cwd() / "eval-results"

    # Collect timestamped result files (result_YYYYMMDD_HHMMSS.json).
    # When multiple results exist for a scenario, keep only the latest.
    # Legacy result.json (no timestamp) is ignored — use `clean` to purge.
    latest_per_scenario: dict[str, tuple[str, Path]] = {}
    for json_path in results_dir.glob("*/result_*.json"):
        scenario_id = json_path.parent.name
        # Timestamped filenames sort chronologically
        sort_key = json_path.name
        prev_key, _ = latest_per_scenario.get(scenario_id, ("", json_path))
        if sort_key >= prev_key:
            latest_per_scenario[scenario_id] = (sort_key, json_path)

    results: list[dict[str, Any]] = []
    for _scenario_id, (_key, json_path) in sorted(latest_per_scenario.items()):
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            results.append(data)
        except (json.JSONDecodeError, OSError):
            continue

    embedded_json = json.dumps(results).replace("</", "<\\/")

    html_content = _TEMPLATE.replace("__DATA_PLACEHOLDER__", embedded_json)

    out_path = results_dir / "report.html"
    out_path.write_text(html_content, encoding="utf-8")
    return str(out_path)


# ---------------------------------------------------------------------------
# Self-contained HTML template
# ---------------------------------------------------------------------------
# Uses {{ / }} for literal braces in CSS/JS since this is NOT an f-string.

_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Agent — Eval Dashboard</title>
<style>
/* ── Reset & Theme ──────────────────────────────────────────────── */
:root {
  --bg: #1a1a2e;
  --surface: #22223a;
  --surface-hover: #2a2a45;
  --border: #333355;
  --border-light: #444466;
  --text: #e8e8f0;
  --text-muted: #9090aa;
  --text-dim: #6a6a88;
  --green: #4ade80;
  --green-bg: rgba(74,222,128,0.08);
  --green-border: rgba(74,222,128,0.25);
  --red: #f87171;
  --red-bg: rgba(248,113,113,0.08);
  --red-border: rgba(248,113,113,0.25);
  --yellow: #fbbf24;
  --yellow-bg: rgba(251,191,36,0.08);
  --blue: #60a5fa;
  --purple: #a78bfa;
  --purple-bg: rgba(167,139,250,0.06);
  --purple-border: rgba(167,139,250,0.2);
  --human-bubble: #2d2b55;
  --agent-avatar: #a78bfa;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.6;
}

/* ── Layout ─────────────────────────────────────────────────────── */
.app { display: flex; height: 100vh; }
.sidebar {
  width: 300px; min-width: 300px; background: var(--surface);
  border-right: 1px solid var(--border); display: flex; flex-direction: column;
  overflow: hidden;
}
.sidebar-header {
  padding: 20px; border-bottom: 1px solid var(--border);
}
.sidebar-header h1 { font-size: 1rem; font-weight: 700; letter-spacing: -0.02em; }
.sidebar-header .subtitle { font-size: 0.78rem; color: var(--text-muted); margin-top: 2px; }
.scenario-list { flex: 1; overflow-y: auto; padding: 8px; }
.main-content { flex: 1; overflow-y: auto; }

/* ── Summary Cards ──────────────────────────────────────────────── */
.summary-bar {
  display: flex; gap: 12px; padding: 12px 20px;
  border-bottom: 1px solid var(--border); flex-wrap: wrap;
}
.summary-stat {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 8px; padding: 8px 16px; min-width: 80px;
}
.summary-stat .label { font-size: 0.68rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.06em; }
.summary-stat .value { font-size: 1.2rem; font-weight: 700; }
.summary-stat .value.green { color: var(--green); }
.summary-stat .value.red { color: var(--red); }

/* ── Scenario List Items ────────────────────────────────────────── */
.scenario-item {
  padding: 10px 12px; border-radius: 8px; cursor: pointer;
  margin-bottom: 2px; transition: background 0.1s;
}
.scenario-item:hover { background: var(--surface-hover); }
.scenario-item.active { background: var(--purple-bg); border: 1px solid var(--purple-border); }
.scenario-item .name {
  font-size: 0.85rem; font-weight: 600; display: flex; align-items: center; gap: 8px;
}
.scenario-item .name .dot {
  width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
}
.scenario-item .name .dot.pass { background: var(--green); }
.scenario-item .name .dot.fail { background: var(--red); }
.scenario-item .meta-line {
  font-size: 0.73rem; color: var(--text-muted); margin-top: 2px; padding-left: 16px;
}
.scenario-item .grade {
  font-size: 0.75rem; font-weight: 700; padding-left: 16px; margin-top: 1px;
}
.scenario-item .grade.green { color: var(--green); }
.scenario-item .grade.yellow { color: var(--yellow); }
.scenario-item .grade.red { color: var(--red); }
.scenario-item .grade-bar {
  height: 3px; border-radius: 2px; margin: 4px 0 0 16px; background: var(--border);
  overflow: hidden; display: flex;
}
.scenario-item .grade-bar .g-pass { background: var(--green); }
.scenario-item .grade-bar .g-fail { background: var(--red); }
.scenario-item .grade-bar .g-review { background: var(--yellow); }
.tag {
  display: inline-block; background: rgba(96,165,250,0.1); color: var(--blue);
  padding: 1px 7px; border-radius: 8px; font-size: 0.7rem; margin-right: 3px;
}

/* ── Scenario Detail Panel ──────────────────────────────────────── */
.detail-panel { padding: 0; }
.detail-header {
  padding: 20px 28px; border-bottom: 1px solid var(--border);
  background: var(--surface);
}
.detail-header h2 { font-size: 1.15rem; font-weight: 700; margin-bottom: 2px; }
.detail-header .desc { font-size: 0.85rem; color: var(--text-muted); }
.badge {
  display: inline-block; padding: 2px 10px; border-radius: 12px;
  font-size: 0.75rem; font-weight: 600; margin-left: 10px;
}
.badge.passed { background: var(--green-bg); color: var(--green); border: 1px solid var(--green-border); }
.badge.failed { background: var(--red-bg); color: var(--red); border: 1px solid var(--red-border); }

.detail-meta {
  display: flex; gap: 20px; padding: 12px 28px; border-bottom: 1px solid var(--border);
  font-size: 0.82rem; color: var(--text-muted); flex-wrap: wrap;
}
.detail-meta span { white-space: nowrap; }
.detail-meta strong { color: var(--text); font-weight: 600; }

/* ── Tabs ───────────────────────────────────────────────────────── */
.tabs {
  display: flex; gap: 0; padding: 0 28px;
  border-bottom: 1px solid var(--border); background: var(--surface);
}
.tab-btn {
  padding: 10px 18px; cursor: pointer; color: var(--text-muted);
  border-bottom: 2px solid transparent; margin-bottom: -1px;
  font-size: 0.85rem; font-weight: 500; transition: all 0.1s;
  background: none; border-top: none; border-left: none; border-right: none;
}
.tab-btn:hover { color: var(--text); }
.tab-btn.active { color: var(--purple); border-bottom-color: var(--purple); }
.tab-panel { display: none; }
.tab-panel.active { display: block; }

/* ── Transcript (Kiro-style) ────────────────────────────────────── */
.transcript { padding: 16px 24px; max-width: 850px; }

/* Human message — right-aligned compact bubble */
.t-human {
  display: flex; justify-content: flex-end; margin: 12px 0 4px;
}
.t-human-bubble {
  background: #302d50; border-radius: 12px 12px 4px 12px;
  padding: 8px 14px; max-width: 70%; font-size: 0.88rem;
  color: var(--text); line-height: 1.5;
}

/* Agent header — matches Kiro's avatar + name row */
.t-agent-header {
  display: flex; align-items: center; gap: 8px; margin: 14px 0 4px;
}
.t-agent-avatar {
  width: 26px; height: 26px; border-radius: 50%; background: #555;
  display: flex; align-items: center; justify-content: center;
  font-size: 0.65rem; font-weight: 700; color: #fff; flex-shrink: 0;
}
.t-agent-name { font-size: 0.88rem; font-weight: 600; }

/* Agent text — plain text, no bubble, flows like Kiro */
.t-agent-text {
  padding-left: 34px; font-size: 0.88rem; line-height: 1.65;
  margin-bottom: 2px; white-space: pre-wrap; word-break: break-word;
  color: var(--text);
}

/* Tool call card — flat, single-line, matching Kiro's collapsible style */
.t-tool {
  margin: 4px 0 4px 34px; border: 1px solid var(--border);
  border-radius: 8px; overflow: hidden; max-width: 620px;
}
.t-tool-header {
  display: flex; align-items: center; gap: 7px; padding: 5px 10px;
  background: rgba(255,255,255,0.02); cursor: pointer; font-size: 0.82rem;
  user-select: none;
}
.t-tool-header:hover { background: rgba(255,255,255,0.04); }
.t-tool-chevron {
  font-size: 0.65rem; color: var(--text-dim); transition: transform 0.15s;
  width: 12px; text-align: center;
}
.t-tool-chevron.open { transform: rotate(90deg); }
.t-tool-icon { font-size: 0.82rem; }
.t-tool-label { color: var(--text-muted); font-size: 0.8rem; }
.t-tool-name {
  background: rgba(167,139,250,0.1); color: var(--purple);
  padding: 1px 7px; border-radius: 4px; font-size: 0.76rem; font-family: 'SF Mono', Menlo, monospace;
}
.t-tool-status-ok { color: var(--green); font-size: 0.72rem; margin-left: auto; }
.t-tool-status-fail { color: var(--red); font-size: 0.72rem; margin-left: auto; }
.t-tool-body {
  display: none; padding: 8px 10px; border-top: 1px solid var(--border);
  font-size: 0.8rem; color: var(--text-muted); font-family: 'SF Mono', Menlo, monospace;
  white-space: pre-wrap; word-break: break-all; background: rgba(0,0,0,0.12);
}
.t-tool-body.open { display: block; }

/* Turn divider — subtle dashed line like Kiro's checkpoint */
.t-turn-divider {
  display: flex; align-items: center; gap: 10px; margin: 16px 0 8px;
  color: var(--text-dim); font-size: 0.7rem; letter-spacing: 0.05em;
}
.t-turn-divider::before, .t-turn-divider::after {
  content: ''; flex: 1; height: 1px; border-top: 1px dashed var(--border);
}

/* ── Assertions Panel ───────────────────────────────────────────── */
.assertions-panel { padding: 20px 28px; }
.assertion-card {
  border: 1px solid var(--border); border-radius: 10px;
  margin-bottom: 10px; overflow: hidden;
}
.assertion-card.pass { border-left: 3px solid var(--green); }
.assertion-card.fail { border-left: 3px solid var(--red); }
.assertion-card.needs_review { border-left: 3px solid var(--yellow); }
.assertion-header {
  display: flex; align-items: center; gap: 10px; padding: 10px 14px;
}
.assertion-icon { font-size: 1rem; width: 20px; text-align: center; }
.assertion-card.pass .assertion-icon { color: var(--green); }
.assertion-card.fail .assertion-icon { color: var(--red); }
.assertion-card.needs_review .assertion-icon { color: var(--yellow); }
.assertion-name { font-weight: 600; font-size: 0.88rem; flex: 1; }
.assertion-type {
  font-size: 0.75rem; color: var(--text-muted); font-family: monospace;
  background: var(--surface); padding: 2px 8px; border-radius: 6px;
}
.assertion-result {
  font-size: 0.8rem; font-weight: 600; padding: 2px 10px; border-radius: 10px;
}
.assertion-card.pass .assertion-result { color: var(--green); background: var(--green-bg); }
.assertion-card.fail .assertion-result { color: var(--red); background: var(--red-bg); }
.assertion-card.needs_review .assertion-result { color: var(--yellow); background: var(--yellow-bg); }
.assertion-details {
  padding: 0 14px 12px 44px; font-size: 0.82rem; color: var(--text-muted);
  line-height: 1.5;
}
.assertion-evidence {
  margin-top: 6px; padding: 8px 12px; background: rgba(0,0,0,0.15);
  border-radius: 6px; font-size: 0.8rem; white-space: pre-wrap; word-break: break-word;
}

/* ── Details Panel ──────────────────────────────────────────────── */
.details-panel { padding: 20px 28px; }
.details-panel dl { margin: 0; }
.details-panel dt {
  font-size: 0.78rem; color: var(--text-muted); text-transform: uppercase;
  letter-spacing: 0.05em; margin-top: 14px;
}
.details-panel dd { margin: 2px 0 0; font-size: 0.9rem; }
.details-panel dd code {
  background: var(--surface); padding: 2px 6px; border-radius: 4px;
  font-size: 0.85rem;
}
.token-grid {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-top: 12px;
}
.token-item {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 8px; padding: 10px 14px;
}
.token-item .label { font-size: 0.68rem; color: var(--text-muted); text-transform: uppercase; }
.token-item .value { font-size: 1.1rem; font-weight: 700; }

/* ── Grading Panel ──────────────────────────────────────────────── */
.grading-panel { padding: 20px 28px; max-width: 820px; }
.grading-section {
  margin-bottom: 20px;
}
.grading-section-title {
  font-size: 0.78rem; color: var(--text-muted); text-transform: uppercase;
  letter-spacing: 0.05em; margin-bottom: 8px; display: flex; align-items: center; gap: 8px;
}
.grading-section-title::after {
  content: ''; flex: 1; height: 1px; background: var(--border);
}
.grading-block {
  background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
  padding: 14px 16px; font-size: 0.85rem; line-height: 1.6;
  white-space: pre-wrap; word-break: break-word; font-family: monospace;
  max-height: 400px; overflow-y: auto;
}
.grading-block.response {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
}
.grading-judge-header {
  display: flex; align-items: center; gap: 8px; margin-bottom: 10px;
}
.grading-judge-avatar {
  width: 28px; height: 28px; border-radius: 50%; background: var(--yellow);
  display: flex; align-items: center; justify-content: center;
  font-size: 0.75rem; font-weight: 700; color: #1a1a2e; flex-shrink: 0;
}
.grading-judge-name { font-size: 0.85rem; font-weight: 600; }

/* ── Empty / Welcome ────────────────────────────────────────────── */
.welcome {
  display: flex; align-items: center; justify-content: center;
  height: 100%; color: var(--text-muted); font-size: 0.95rem;
}

/* ── Scrollbar ──────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--border-light); }
</style>
</head>
<body>

<div class="app">
  <!-- Sidebar -->
  <div class="sidebar">
    <div class="sidebar-header">
      <h1>Eval Dashboard</h1>
      <div class="subtitle">Agent</div>
    </div>
    <div class="summary-bar" id="summary-bar"></div>
    <div class="scenario-list" id="scenario-list"></div>
  </div>

  <!-- Main content -->
  <div class="main-content" id="main-content">
    <div class="welcome" id="welcome">Select a scenario from the sidebar</div>
    <div class="detail-panel" id="detail-panel" style="display:none;"></div>
  </div>
</div>

<script>
// ── Embedded data ──────────────────────────────────────────────────
const DATA = __DATA_PLACEHOLDER__;

// ── Helpers ────────────────────────────────────────────────────────
function esc(s) {
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function nl2br(s) { return esc(s).replace(/\n/g, '<br>'); }

// Parse tool_call content: "tool_call: get_status (kind=other, status=completed)"
function parseToolCall(content) {
  const m = content.match(/^tool_call:\s*(\S+)\s*\(kind=([^,]*),\s*status=([^)]*)\)/);
  if (m) return { tool: m[1], kind: m[2], status: m[3] };
  return { tool: content, kind: '', status: '' };
}

// ── Render summary bar ─────────────────────────────────────────────
function renderSummary() {
  const total = DATA.length;
  const passed = DATA.filter(d => d.passed).length;
  const failed = total - passed;
  const totalTime = DATA.reduce((s, d) => s + d.duration_seconds, 0);
  const totalTokens = DATA.reduce((s, d) => s + (d.token_usage?.total_tokens || 0), 0);

  document.getElementById('summary-bar').innerHTML = `
    <div class="summary-stat">
      <div class="label">Total</div>
      <div class="value">${total}</div>
    </div>
    <div class="summary-stat">
      <div class="label">Passed</div>
      <div class="value green">${passed}</div>
    </div>
    <div class="summary-stat">
      <div class="label">Failed</div>
      <div class="value ${failed > 0 ? 'red' : ''}">${failed}</div>
    </div>
    <div class="summary-stat">
      <div class="label">Time</div>
      <div class="value">${totalTime.toFixed(0)}s</div>
    </div>
  `;
}

// ── Render scenario list ───────────────────────────────────────────
function renderScenarioList() {
  const list = document.getElementById('scenario-list');
  list.innerHTML = DATA.map((d, i) => {
    const s = d.scenario || {};
    const passCount = d.assertions.filter(a => a.result === 'pass').length;
    const failCount = d.assertions.filter(a => a.result === 'fail').length;
    const reviewCount = d.assertions.filter(a => a.result === 'needs_review').length;
    const totalCount = d.assertions.length;
    const pct = totalCount > 0 ? Math.round((passCount / totalCount) * 100) : 0;
    const gradeColor = pct === 100 ? 'green' : pct >= 50 ? 'yellow' : 'red';
    const tags = (s.tags || []).map(t => `<span class="tag">${esc(t)}</span>`).join('');
    return `
      <div class="scenario-item" data-idx="${i}" onclick="selectScenario(${i})">
        <div class="name">
          <span class="dot ${d.passed ? 'pass' : 'fail'}"></span>
          ${esc(s.name || d.eval_id)}
        </div>
        <div class="meta-line" style="font-family:monospace;opacity:0.7;">${esc(d.eval_id)}</div>
        <div class="grade ${gradeColor}">${pct}% &mdash; ${passCount}/${totalCount} passed</div>
        <div class="grade-bar">
          <div class="g-pass" style="width:${totalCount ? (passCount/totalCount)*100 : 0}%"></div>
          <div class="g-fail" style="width:${totalCount ? (failCount/totalCount)*100 : 0}%"></div>
          <div class="g-review" style="width:${totalCount ? (reviewCount/totalCount)*100 : 0}%"></div>
        </div>
        <div class="meta-line">
          ${d.turn_count} turns &middot; ${d.duration_seconds.toFixed(0)}s
          ${tags ? ' &middot; ' + tags : ''}
        </div>
      </div>
    `;
  }).join('');
}

// ── Render detail panel ────────────────────────────────────────────
function selectScenario(idx) {
  // Update sidebar active state
  document.querySelectorAll('.scenario-item').forEach(el => el.classList.remove('active'));
  const activeItem = document.querySelector(`.scenario-item[data-idx="${idx}"]`);
  if (activeItem) activeItem.classList.add('active');

  document.getElementById('welcome').style.display = 'none';
  const panel = document.getElementById('detail-panel');
  panel.style.display = 'block';

  const d = DATA[idx];
  const s = d.scenario || {};
  const passCount = d.assertions.filter(a => a.result === 'pass').length;
  const totalCount = d.assertions.length;
  const tok = d.token_usage || {};

  panel.innerHTML = `
    <div class="detail-header">
      <h2>${esc(s.name || d.eval_id)}
        <span class="badge ${d.passed ? 'passed' : 'failed'}">${d.passed ? 'PASSED' : 'FAILED'}</span>
      </h2>
      <div class="desc">${esc(s.description || '')}</div>
    </div>
    <div class="detail-meta">
      <span><strong>${passCount}/${totalCount}</strong> assertions</span>
      <span><strong>${d.turn_count}</strong> turns</span>
      <span><strong>${d.duration_seconds.toFixed(1)}s</strong> duration</span>
      <span><strong>${(tok.total_tokens || 0).toLocaleString()}</strong> tokens</span>
    </div>
    <div class="tabs">
      <button class="tab-btn active" data-panel="tab-transcript-${idx}">Transcript</button>
      <button class="tab-btn" data-panel="tab-assertions-${idx}">Assertions</button>
      <button class="tab-btn" data-panel="tab-details-${idx}">Details</button>
      <button class="tab-btn" data-panel="tab-grading-${idx}">Grading</button>
    </div>
    <div class="tab-panel active" id="tab-transcript-${idx}">
      ${renderTranscript(d)}
    </div>
    <div class="tab-panel" id="tab-assertions-${idx}">
      ${renderAssertions(d)}
    </div>
    <div class="tab-panel" id="tab-details-${idx}">
      ${renderDetails(d)}
    </div>
    <div class="tab-panel" id="tab-grading-${idx}">
      ${renderGrading(d)}
    </div>
  `;

  // Wire tabs
  panel.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      panel.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      panel.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(btn.dataset.panel).classList.add('active');
    });
  });

  // Wire tool card toggles
  panel.querySelectorAll('.t-tool-header').forEach(hdr => {
    hdr.addEventListener('click', () => {
      const chev = hdr.querySelector('.t-tool-chevron');
      const body = hdr.nextElementSibling;
      chev.classList.toggle('open');
      body.classList.toggle('open');
    });
  });

  // Scroll to top
  document.getElementById('main-content').scrollTop = 0;
}

// ── Transcript renderer (Kiro-style) ──────────────────────────────
function renderTranscript(d) {
  const entries = d.transcript || [];
  if (!entries.length) return '<div class="transcript"><p style="color:var(--text-muted);font-style:italic;">No transcript recorded.</p></div>';

  let html = '<div class="transcript">';
  let lastTurn = -1;
  let agentHeaderShown = false;

  for (const entry of entries) {
    // Turn divider
    if (entry.turn !== lastTurn && entry.turn > 0) {
      lastTurn = entry.turn;
      html += `<div class="t-turn-divider">Turn ${entry.turn}</div>`;
      agentHeaderShown = false;
    }

    if (entry.role === 'human') {
      agentHeaderShown = false;
      html += `
        <div class="t-human">
          <div class="t-human-bubble">${nl2br(entry.content)}</div>
        </div>
      `;
    } else if (entry.role === 'tool_call') {
      const tc = parseToolCall(entry.content);
      const isMcp = tc.tool.includes('/') || tc.kind === 'other';
      const icon = isMcp ? '🔧' : '⚡';
      const label = isMcp ? 'Called MCP tool' : 'Called tool';
      const statusOk = tc.status === 'completed' || tc.status === '';
      const statusHtml = statusOk
        ? '<span class="t-tool-status-ok">&#10004;</span>'
        : '<span class="t-tool-status-fail">&#9888; ' + esc(tc.status) + '</span>';

      html += `
        <div class="t-tool">
          <div class="t-tool-header">
            <span class="t-tool-chevron">&#9656;</span>
            <span class="t-tool-icon">${icon}</span>
            <span class="t-tool-label">${label}</span>
            <span class="t-tool-name">${esc(tc.tool)}</span>
            ${statusHtml}
          </div>
          <div class="t-tool-body">kind: ${esc(tc.kind)}\nstatus: ${esc(tc.status)}</div>
        </div>
      `;
    } else if (entry.role === 'agent') {
      if (!agentHeaderShown) {
        html += `
          <div class="t-agent-header">
            <div class="t-agent-avatar">K</div>
            <div class="t-agent-name">Agent</div>
          </div>
        `;
        agentHeaderShown = true;
      }
      html += `<div class="t-agent-text">${nl2br(entry.content)}</div>`;
    } else {
      // thought, permission, tool_progress — muted
      html += `
        <div class="t-tool" style="opacity:0.6;">
          <div class="t-tool-header">
            <span class="t-tool-chevron">&#9656;</span>
            <span class="t-tool-icon">&#128172;</span>
            <span class="t-tool-label">${esc(entry.role)}</span>
          </div>
          <div class="t-tool-body">${esc(entry.content)}</div>
        </div>
      `;
    }
  }

  html += '</div>';
  return html;
}

// ── Assertions renderer ───────────────────────────────────────────
function renderAssertions(d) {
  const assertions = d.assertions || [];
  const scenarioAssertions = (d.scenario?.assertions || []);
  const defMap = {};
  scenarioAssertions.forEach(a => { defMap[a.name] = a; });

  let html = '<div class="assertions-panel">';
  for (const a of assertions) {
    const def = defMap[a.name] || {};
    const css = a.result;
    const icon = a.result === 'pass' ? '&#10004;' : a.result === 'fail' ? '&#10008;' : '?';
    const check = Array.isArray(def.check) ? def.check.join(', ') : (def.check || '');

    html += `
      <div class="assertion-card ${css}">
        <div class="assertion-header">
          <span class="assertion-icon">${icon}</span>
          <span class="assertion-name">${esc(a.name)}</span>
          <span class="assertion-type">${esc(def.type || '')}</span>
          <span class="assertion-result">${esc(a.result)}</span>
        </div>
        <div class="assertion-details">
          ${def.description ? '<div>' + esc(def.description) + '</div>' : ''}
          ${check ? '<div style="margin-top:4px;"><strong>Check:</strong> <code>' + esc(check) + '</code></div>' : ''}
          ${a.evidence ? (def.type === 'llm_judge' ? '<div style="margin-top:8px;display:flex;align-items:center;gap:6px;"><span style="width:18px;height:18px;border-radius:50%;background:var(--yellow);display:inline-flex;align-items:center;justify-content:center;font-size:0.6rem;font-weight:700;color:#1a1a2e;flex-shrink:0;">J</span><span style="font-size:0.78rem;font-weight:600;color:var(--yellow);">LLM Judge</span></div>' : '') + '<div class="assertion-evidence">' + esc(a.evidence) + '</div>' : ''}
        </div>
      </div>
    `;
  }
  html += '</div>';
  return html;
}

// ── Details renderer ──────────────────────────────────────────────
function renderDetails(d) {
  const s = d.scenario || {};
  const tok = d.token_usage || {};

  let html = '<div class="details-panel"><dl>';
  html += `<dt>Initial Prompt</dt><dd>${nl2br(s.prompt || '(none)')}</dd>`;
  html += `<dt>Human Guidance</dt><dd>${nl2br(s.simulated_human_guidance || '(none)')}</dd>`;
  html += `<dt>Max Turns</dt><dd>${s.max_turns || '—'}</dd>`;
  html += `<dt>Timeout</dt><dd>${s.timeout_seconds || '—'}s</dd>`;
  html += `<dt>Work Directory</dt><dd><code>${esc(d.work_dir || '(none)')}</code></dd>`;
  html += '</dl>';

  html += '<dt style="margin-top:20px;font-size:0.78rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.05em;">Token Usage</dt>';
  html += `<div class="token-grid">
    <div class="token-item"><div class="label">Input</div><div class="value">${(tok.input_tokens || 0).toLocaleString()}</div></div>
    <div class="token-item"><div class="label">Output</div><div class="value">${(tok.output_tokens || 0).toLocaleString()}</div></div>
    <div class="token-item"><div class="label">Cached</div><div class="value">${(tok.cached_read_tokens || 0).toLocaleString()}</div></div>
    <div class="token-item"><div class="label">Total</div><div class="value">${(tok.total_tokens || 0).toLocaleString()}</div></div>
  </div>`;

  if (d.log_files && d.log_files.length) {
    html += '<dt style="margin-top:20px;font-size:0.78rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.05em;">Log Files</dt>';
    html += '<dd><ul style="list-style:none;padding:0;">';
    for (const lf of d.log_files) {
      const name = lf.split('/').pop();
      html += `<li style="margin:3px 0;"><code style="font-size:0.8rem;">${esc(name)}</code></li>`;
    }
    html += '</ul></dd>';
  }

  html += '</div>';
  return html;
}

// ── Grading renderer ──────────────────────────────────────────────
function renderGrading(d) {
  const transcript = d.transcript || [];
  const assertions = d.assertions || [];
  const scenarioAssertions = d.scenario?.assertions || [];

  if (!assertions.length) {
    return '<div class="grading-panel"><p style="color:var(--text-muted);font-style:italic;">No grading data available.</p></div>';
  }

  const passed = assertions.filter(a => a.result === 'pass').length;
  const failed = assertions.filter(a => a.result === 'fail').length;
  const review = assertions.filter(a => a.result === 'needs_review').length;
  const total = assertions.length;
  const pct = total > 0 ? Math.round((passed / total) * 100) : 0;

  let html = '<div class="grading-panel">';

  // Judge header
  html += `
    <div class="grading-judge-header">
      <div class="grading-judge-avatar">J</div>
      <div class="grading-judge-name">Eval Judge</div>
    </div>
  `;

  // Score
  const scoreColor = pct === 100 ? 'var(--green)' : pct >= 50 ? 'var(--yellow)' : 'var(--red)';
  html += `
    <div class="grading-section">
      <div style="display:flex;align-items:baseline;gap:16px;margin-bottom:16px;">
        <span style="font-size:2.4rem;font-weight:800;color:${scoreColor};">${pct}%</span>
        <span style="font-size:0.9rem;color:var(--text-muted);">
          <span style="color:var(--green);font-weight:600;">${passed}</span> passed
          ${failed ? ' &middot; <span style="color:var(--red);font-weight:600;">' + failed + '</span> failed' : ''}
          ${review ? ' &middot; <span style="color:var(--yellow);font-weight:600;">' + review + '</span> needs review' : ''}
          &middot; ${total} total
        </span>
      </div>
      <div style="height:6px;background:var(--surface);border-radius:3px;overflow:hidden;margin-bottom:20px;">
        <div style="display:flex;height:100%;">
          <div style="width:${(passed/total)*100}%;background:var(--green);"></div>
          <div style="width:${(failed/total)*100}%;background:var(--red);"></div>
          <div style="width:${(review/total)*100}%;background:var(--yellow);"></div>
        </div>
      </div>
    </div>
  `;

  // Transcript the judge graded (the raw text format, not the Kiro-style view)
  if (transcript.length) {
    const transcriptText = transcript
      .map(e => '[Turn ' + e.turn + '] ' + e.role.toUpperCase() + ': ' + e.content)
      .join('\n');
    html += `
      <div class="grading-section">
        <div class="grading-section-title">Transcript sent to judge</div>
        <div class="grading-block">${esc(transcriptText)}</div>
      </div>
    `;
  }

  // Assertions sent to judge
  html += `
    <div class="grading-section">
      <div class="grading-section-title">Assertions sent to judge</div>
      <div class="grading-block">${esc(JSON.stringify(scenarioAssertions, null, 2))}</div>
    </div>
  `;

  html += '</div>';
  return html;
}

// ── Init ──────────────────────────────────────────────────────────
renderSummary();
renderScenarioList();
if (DATA.length === 1) selectScenario(0);
</script>
</body>
</html>"""
