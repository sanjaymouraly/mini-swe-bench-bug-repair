/* Mini SWE-Bench Dashboard Client */

const state = {
  overview: null,
  tasks: [],
  selectedTask: null,
  runs: [],
  selectedRunId: null,
  selectedRun: null,
  activePollTimer: null,
  providers: [],
};

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function statusBadgeHtml(status) {
  const s = String(status || "").toUpperCase();
  if (s === "RESOLVED" || s === "PASSED" || s === "COMPLETED") {
    return `<span class="badge badge-pass">${escapeHtml(s)}</span>`;
  }
  if (s === "REGRESSION" || s === "INTEGRITY_VIOLATION" || s === "EXECUTION_FAILURE" || s === "FAILED") {
    return `<span class="badge badge-fail">${escapeHtml(s)}</span>`;
  }
  return `<span class="badge badge-warn">${escapeHtml(s || "UNRESOLVED")}</span>`;
}

function difficultyBadgeHtml(diff) {
  const d = String(diff || "medium").toLowerCase();
  return `<span class="badge badge-${escapeHtml(d)}">${escapeHtml(d)}</span>`;
}

function renderUnifiedDiff(diffText) {
  if (!diffText || !diffText.trim()) {
    return `<div class="diff-viewer muted">No patch diff (empty submission).</div>`;
  }
  const lines = diffText.replace(/\r\n/g, "\n").split("\n");
  const formatted = lines
    .map((line) => {
      if (line.startsWith("+++") || line.startsWith("---") || line.startsWith("@@") || line.startsWith("diff --git")) {
        return `<span class="diff-line-hdr">${escapeHtml(line)}</span>`;
      }
      if (line.startsWith("+")) {
        return `<span class="diff-line-add">${escapeHtml(line)}</span>`;
      }
      if (line.startsWith("-")) {
        return `<span class="diff-line-del">${escapeHtml(line)}</span>`;
      }
      return `<span>${escapeHtml(line)}</span>`;
    })
    .join("\n");
  return `<pre class="diff-viewer">${formatted}</pre>`;
}

function switchTab(tabName) {
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === tabName);
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `tab-${tabName}`);
  });
  if (tabName === "overview") loadOverview();
  if (tabName === "tasks") loadTasks();
  if (tabName === "results") loadRunsForResults();
  if (tabName === "comparison") loadComparisonView();
  if (tabName === "providers") loadProviders();
}

async function fetchJson(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`HTTP ${res.status}: ${errText}`);
  }
  return res.json();
}

async function loadOverview() {
  try {
    const data = await fetchJson("/api/overview");
    state.overview = data;
    document.getElementById("kpi-total-tasks").textContent = data.total_tasks;
    const dc = data.difficulty_counts || {};
    document.getElementById("kpi-difficulty-split").textContent =
      `${dc.easy || 0} Easy · ${dc.medium || 0} Medium · ${dc.hard || 0} Hard`;
    document.getElementById("kpi-total-runs").textContent = data.total_runs;
    document.getElementById("kpi-sandbox-mode").textContent = data.sandbox_mode;

    const navTasks = document.getElementById("nav-tasks");
    if (navTasks) navTasks.textContent = `Task Library (${data.total_tasks})`;

    // Populate Recent Runs table
    const tbody = document.getElementById("overview-runs-tbody");
    const runs = data.recent_runs || [];
    if (runs.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" class="empty-cell muted">No evaluation runs recorded yet. Click "Run Reference Oracle" or "Run No-Op Baseline" above.</td></tr>`;
    } else {
      const bestRate = Math.max(...runs.map((r) => r.resolved_rate || 0));
      document.getElementById("kpi-best-rate").textContent = `Peak Resolved Rate: ${bestRate.toFixed(1)}%`;
      tbody.innerHTML = runs
        .map(
          (r) => `
        <tr data-run-id="${escapeHtml(r.run_id)}">
          <td><strong>${escapeHtml(r.run_name)}</strong><br/><span class="muted">${escapeHtml(r.run_id)}</span></td>
          <td><code>${escapeHtml(r.agent_id)}</code></td>
          <td><strong>${r.resolved_count}/${r.total_tasks}</strong> (${r.resolved_rate}%)</td>
          <td>${r.issue_fix_count}/${r.total_tasks} (${r.issue_fix_rate}%)</td>
          <td>${r.regression_count > 0 ? `<span class="status-text-fail">${r.regression_count} regression(s)</span>` : `<span class="status-text-pass">0 (100% safe)</span>`}</td>
          <td>${statusBadgeHtml(r.status)}</td>
          <td><button class="btn btn-secondary btn-inspect-run" data-run-id="${escapeHtml(r.run_id)}">View</button></td>
        </tr>`
        )
        .join("");

      tbody.querySelectorAll(".btn-inspect-run").forEach((btn) => {
        btn.addEventListener("click", (e) => {
          e.stopPropagation();
          state.selectedRunId = btn.dataset.runId;
          switchTab("results");
        });
      });
    }

    // Populate Validation box
    const valBox = document.getElementById("validation-summary-box");
    const val = data.latest_validation;
    if (!val) {
      valBox.innerHTML = `<p class="muted">No validation report stored yet. Run <code>bugbench validate</code> or click below.</p>`;
    } else {
      const statusEl = document.getElementById("kpi-validation-status");
      statusEl.textContent = val.all_passed ? `100% Valid (${val.valid_tasks}/${val.total_tasks})` : `Failed (${val.invalid_tasks})`;
      statusEl.className = `kpi-value ${val.all_passed ? "status-text-pass" : "status-text-fail"}`;
      const rowsHtml = (val.task_reports || [])
        .map(
          (tr) => `
          <tr>
            <td><code>${escapeHtml(tr.task_id)}</code></td>
            <td>${difficultyBadgeHtml(tr.difficulty)}</td>
            <td>${tr.passed ? `<span class="badge badge-pass">8/8 GATES PASS</span>` : `<span class="badge badge-fail">FAILED</span>`}</td>
            <td><code>${escapeHtml((tr.base_revision || "").slice(0, 10))}</code></td>
            <td>${tr.duration_ms.toFixed(0)} ms</td>
          </tr>`
        )
        .join("");
      valBox.innerHTML = `
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr><th>Task ID</th><th>Difficulty</th><th>Quality Gates</th><th>Base SHA</th><th>Time</th></tr>
            </thead>
            <tbody>${rowsHtml}</tbody>
          </table>
        </div>`;
    }
  } catch (err) {
    console.error("Failed to load overview:", err);
  }
}

async function loadTasks() {
  const search = document.getElementById("task-search").value.trim();
  const difficulty = document.getElementById("task-difficulty-filter").value;
  const category = document.getElementById("task-category-filter").value;
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  if (difficulty) params.set("difficulty", difficulty);
  if (category) params.set("category", category);

  try {
    const data = await fetchJson(`/api/tasks?${params.toString()}`);
    state.tasks = data.tasks || [];
    const container = document.getElementById("task-list-container");

    // Also populate task selector on Evaluate tab
    const evalSelect = document.getElementById("eval-task-filter");
    if (evalSelect && evalSelect.options.length <= 1 && state.tasks.length > 0) {
      state.tasks.forEach((t) => {
        const opt = document.createElement("option");
        opt.value = t.task_id;
        opt.textContent = `${t.task_id} — ${t.title} (${t.difficulty})`;
        evalSelect.appendChild(opt);
      });
    }

    if (state.tasks.length === 0) {
      container.innerHTML = `<div class="card muted">No tasks match the current filter criteria.</div>`;
      return;
    }

    container.innerHTML = state.tasks
      .map(
        (t) => `
      <div class="task-item-card ${state.selectedTask && state.selectedTask.task_id === t.task_id ? "active" : ""}" data-task-id="${escapeHtml(t.task_id)}">
        <div class="task-item-header">
          <span class="task-id-code">${escapeHtml(t.task_id)}</span>
          ${difficultyBadgeHtml(t.difficulty)}
        </div>
        <div class="task-item-title">${escapeHtml(t.title)}</div>
        <div class="task-item-meta">
          <span>Pkg: <code>${escapeHtml(t.package_name)}</code></span>
          <span>Category: <code>${escapeHtml(t.category)}</code></span>
          <span>SHA: <code>${escapeHtml((t.base_revision || "").slice(0, 8))}</code></span>
        </div>
      </div>`
      )
      .join("");

    container.querySelectorAll(".task-item-card").forEach((card) => {
      card.addEventListener("click", () => inspectTask(card.dataset.taskId));
    });

    if (!state.selectedTask && state.tasks.length > 0) {
      inspectTask(state.tasks[0].task_id);
    }
  } catch (err) {
    console.error("Failed to load tasks:", err);
  }
}

async function inspectTask(taskId) {
  try {
    const detail = await fetchJson(`/api/tasks/${encodeURIComponent(taskId)}`);
    const t = detail.task;
    state.selectedTask = t;

    document.querySelectorAll(".task-item-card").forEach((c) => {
      c.classList.toggle("active", c.dataset.taskId === taskId);
    });

    const srcEntries = Object.entries(detail.source_files || {});
    const srcHtml = srcEntries
      .map(
        ([path, code]) => `
        <div style="margin-top: 10px;">
          <div class="muted" style="margin-bottom:4px;">File: <code>${escapeHtml(path)}</code></div>
          <pre class="code-block">${escapeHtml(code)}</pre>
        </div>`
      )
      .join("");

    const panel = document.getElementById("task-detail-panel");
    panel.innerHTML = `
      <div class="section-header" style="margin-bottom:10px;">
        <div>
          <h3><code>${escapeHtml(t.task_id)}</code> — ${escapeHtml(t.title)}</h3>
          <p class="muted">${escapeHtml(t.summary)}</p>
        </div>
        <div class="action-group">
          ${difficultyBadgeHtml(t.difficulty)}
          <span class="badge badge-neutral">${escapeHtml(t.category)}</span>
        </div>
      </div>

      <div class="meta-kv-grid">
        <div class="meta-kv"><span>Package Name</span><code>${escapeHtml(t.package_name)}</code></div>
        <div class="meta-kv"><span>Base Git Revision</span><code>${escapeHtml((t.base_revision || "").slice(0, 12))}</code></div>
        <div class="meta-kv"><span>Allowed Modifiable Files</span><code>${escapeHtml((t.allowed_files || []).join(", "))}</code></div>
        <div class="meta-kv"><span>Test Suite Hash</span><code>${escapeHtml((t.test_suite_hash || "").slice(0, 12))}</code></div>
      </div>

      <h3 style="margin-top:14px;">Issue Report</h3>
      <pre class="code-block">${escapeHtml(t.issue_description)}</pre>

      <h3 style="margin-top:14px;">Controlled Reproduction Guidance</h3>
      <pre class="code-block">${escapeHtml(t.reproduction_instructions)}</pre>

      <h3 style="margin-top:14px;">Repository Source Code (Buggy Revision)</h3>
      ${srcHtml}
    `;
  } catch (err) {
    console.error("Failed to inspect task:", err);
  }
}

async function loadRunsForResults() {
  try {
    const data = await fetchJson("/api/runs?limit=50&include_tasks=true");
    state.runs = data.runs || [];
    const sel = document.getElementById("results-run-select");
    if (state.runs.length === 0) {
      sel.innerHTML = `<option value="">No runs available</option>`;
      document.getElementById("selected-run-summary-bar").innerHTML = "";
      document.getElementById("run-tasks-tbody").innerHTML =
        `<tr><td colspan="8" class="muted">No runs recorded yet. Launch a run first.</td></tr>`;
      return;
    }

    if (!state.selectedRunId || !state.runs.some((r) => r.run_id === state.selectedRunId)) {
      // Prefer the most recent run that actually has task results. A run that
      // was just launched has none yet, and defaulting to it would show an
      // empty table with no explanation.
      const withResults = state.runs.find((r) => (r.task_results || []).length > 0);
      state.selectedRunId = (withResults || state.runs[0]).run_id;
    }

    sel.innerHTML = state.runs
      .map(
        (r) =>
          `<option value="${escapeHtml(r.run_id)}" ${r.run_id === state.selectedRunId ? "selected" : ""}>${escapeHtml(r.run_name)} — ${escapeHtml(r.agent_id)} (${r.resolved_count}/${r.total_tasks} resolved)</option>`
      )
      .join("");

    await displaySelectedRun(state.selectedRunId);
  } catch (err) {
    console.error("Failed to load runs:", err);
  }
}

async function displaySelectedRun(runId) {
  if (!runId) return;
  try {
    const run = await fetchJson(`/api/runs/${encodeURIComponent(runId)}`);
    state.selectedRun = run;

    const summaryBar = document.getElementById("selected-run-summary-bar");
    summaryBar.innerHTML = `
      <div class="kpi-card">
        <span class="kpi-label">Resolved Tasks</span>
        <strong class="kpi-value ${run.resolved_count === run.total_tasks ? "status-text-pass" : ""}">${run.resolved_count} / ${run.total_tasks} (${run.resolved_rate}%)</strong>
        <span class="kpi-sub">Agent: <code>${escapeHtml(run.agent_id)}</code></span>
      </div>
      <div class="kpi-card">
        <span class="kpi-label">Issue-Fix Rate</span>
        <strong class="kpi-value">${run.issue_fix_count} / ${run.total_tasks} (${run.issue_fix_rate}%)</strong>
        <span class="kpi-sub">FAIL_TO_PASS + Private Suites</span>
      </div>
      <div class="kpi-card">
        <span class="kpi-label">Regression-Free Rate</span>
        <strong class="kpi-value ${run.regression_count > 0 ? "status-text-fail" : "status-text-pass"}">${run.regression_free_rate}%</strong>
        <span class="kpi-sub">${run.regression_count} task(s) with PASS_TO_PASS regressions</span>
      </div>
      <div class="kpi-card">
        <span class="kpi-label">Patch Applicability</span>
        <strong class="kpi-value">${run.patch_valid_rate}%</strong>
        <span class="kpi-sub">Duration: ${(run.total_duration_ms / 1000).toFixed(2)}s · Sandbox: ${escapeHtml(run.sandbox_mode)}</span>
      </div>
    `;

    const tbody = document.getElementById("run-tasks-tbody");
    const results = run.task_results || [];
    if (results.length === 0) {
      const status = run.status || "UNKNOWN";
      tbody.innerHTML =
        `<tr><td colspan="8" class="muted">` +
        (status === "RUNNING"
          ? `This run is still in progress — no task results have been recorded yet. ` +
            `Open the <em>Run Evaluation</em> tab to watch it live, or select a completed run.`
          : `This run has no recorded task results (status: ${escapeHtml(status)}). ` +
            `Select another run from the dropdown above.`) +
        `</td></tr>`;
      const inspector = document.getElementById("task-result-inspector");
      if (inspector) {
        inspector.innerHTML = `<div class="diff-viewer muted">No task result selected.</div>`;
      }
      return;
    }
    tbody.innerHTML = results
      .map((tr) => {
        const f2p = tr.fail_to_pass ? `${tr.fail_to_pass.passed_count}/${tr.fail_to_pass.total_count}` : "—";
        const p2p = tr.pass_to_pass ? `${tr.pass_to_pass.passed_count}/${tr.pass_to_pass.total_count}` : "—";
        const priv = tr.private_tests ? `${tr.private_tests.passed_count}/${tr.private_tests.total_count}` : "—";
        return `
          <tr data-task-id="${escapeHtml(tr.task_id)}">
            <td><code>${escapeHtml(tr.task_id)}</code><br/><span class="muted">${escapeHtml(tr.title)}</span></td>
            <td>${difficultyBadgeHtml(tr.difficulty)}</td>
            <td>${statusBadgeHtml(tr.resolution_status)}</td>
            <td><code>${f2p}</code></td>
            <td><code>${p2p}</code></td>
            <td><code>${priv}</code></td>
            <td>${tr.has_regression ? `<span class="badge badge-fail">REGRESSION</span>` : `<span class="badge badge-pass">SAFE</span>`}</td>
            <td>${tr.duration_ms.toFixed(0)} ms</td>
          </tr>`;
      })
      .join("");

    tbody.querySelectorAll("tr").forEach((row) => {
      row.addEventListener("click", () => {
        const tid = row.dataset.taskId;
        const found = results.find((x) => x.task_id === tid);
        if (found) renderTaskEvaluationInspector(found);
      });
    });

    if (results.length > 0) {
      renderTaskEvaluationInspector(results[0]);
    }
  } catch (err) {
    console.error("Failed to display run:", err);
  }
}

function renderTaskEvaluationInspector(tr) {
  const inspector = document.getElementById("task-result-inspector");
  const pv = tr.patch_validation || {};

  const allCases = [
    ...((tr.fail_to_pass && tr.fail_to_pass.test_cases) || []),
    ...((tr.pass_to_pass && tr.pass_to_pass.test_cases) || []),
    ...((tr.private_tests && tr.private_tests.test_cases) || []),
  ];

  const casesHtml =
    allCases.length === 0
      ? `<p class="muted">No test cases executed for this submission.</p>`
      : `<div class="table-wrap"><table class="data-table">
          <thead><tr><th>Suite</th><th>Test Case</th><th>Outcome</th><th>Time</th></tr></thead>
          <tbody>
            ${allCases
              .map(
                (tc) => `
              <tr>
                <td><code>${escapeHtml(tc.suite)}</code></td>
                <td><code>${escapeHtml(tc.test_id)}</code>${tc.message ? `<br/><span class="muted">${escapeHtml(tc.message.slice(0, 160))}</span>` : ""}</td>
                <td>${tc.passed ? `<span class="badge badge-pass">PASS</span>` : `<span class="badge badge-fail">${escapeHtml(tc.outcome)}</span>`}</td>
                <td>${tc.duration_ms.toFixed(1)} ms</td>
              </tr>`
              )
              .join("")}
          </tbody>
        </table></div>`;

  // An empty patch has no integrity to judge, so report "N/A" rather than
  // "VIOLATION" -- an empty submission is not an integrity violation.
  const patchIsEmpty = Boolean(pv.is_empty);
  const integrityText = patchIsEmpty
    ? "N/A (no patch)"
    : pv.integrity_passed
    ? "PASSED"
    : "VIOLATION";
  const appliesText = patchIsEmpty
    ? "N/A (no patch)"
    : pv.applies_cleanly
    ? "Yes"
    : "No";

  inspector.innerHTML = `
    <div class="section-header" style="margin-bottom:10px;">
      <div>
        <h3><code>${escapeHtml(tr.task_id)}</code> — ${escapeHtml(tr.title)}</h3>
        <p class="muted">${escapeHtml(tr.explanation)}</p>
      </div>
      <div>${statusBadgeHtml(tr.resolution_status)}</div>
    </div>

    <div class="meta-kv-grid">
      <div class="meta-kv"><span>Classification</span><code>${escapeHtml(tr.failure_classification)}</code></div>
      <div class="meta-kv"><span>Patch Applies</span><code>${appliesText} (+${pv.added_lines || 0}/-${pv.removed_lines || 0})</code></div>
      <div class="meta-kv"><span>Patch Integrity</span><code>${integrityText}</code></div>
      <div class="meta-kv"><span>Base SHA</span><code>${escapeHtml((tr.base_revision || "").slice(0, 12))}</code></div>
    </div>

    <h3 style="margin-top:12px;">Submitted Unified Git Diff</h3>
    ${renderUnifiedDiff(tr.patch_diff)}

    <h3 style="margin-top:14px;">Per-Test Execution Breakdown (${allCases.length} tests)</h3>
    ${casesHtml}
  `;
}

async function loadComparisonView() {
  try {
    const data = await fetchJson("/api/compare");
    const runs = data.runs || [];
    const matrix = data.task_matrix || [];

    const summaryTbody = document.getElementById("comparison-summary-tbody");
    if (runs.length === 0) {
      summaryTbody.innerHTML = `<tr><td colspan="8" class="muted">No runs available for comparison.</td></tr>`;
      document.getElementById("comparison-chart-container").innerHTML = `<p class="muted">Run at least one evaluation to view comparison charts.</p>`;
      document.getElementById("comparison-matrix-wrap").innerHTML = "";
      return;
    }

    summaryTbody.innerHTML = runs
      .map(
        (r) => `
      <tr>
        <td><strong>${escapeHtml(r.run_name)}</strong></td>
        <td><code>${escapeHtml(r.agent_id)}</code></td>
        <td><code>${escapeHtml(r.sandbox_mode)}</code></td>
        <td><strong>${r.resolved_count}/${r.total_tasks} (${r.resolved_rate}%)</strong></td>
        <td>${r.issue_fix_count}/${r.total_tasks} (${r.issue_fix_rate}%)</td>
        <td>${r.regression_free_rate}% (${r.regression_count} reg)</td>
        <td>${r.patch_valid_rate}%</td>
        <td>${(r.total_duration_ms / 1000).toFixed(2)}s</td>
      </tr>`
      )
      .join("");

    // Render SVG comparison chart
    renderComparisonSvgChart(runs.slice(0, 6));

    // Render Per-Task Matrix
    const headerCols = runs
      .slice(0, 6)
      .map((r) => `<th>${escapeHtml(r.run_name)}<br/><span class="muted">${escapeHtml(r.agent_id)}</span></th>`)
      .join("");
    const bodyRows = matrix
      .map((row) => {
        const cells = runs
          .slice(0, 6)
          .map((r) => {
            const out = (row.outcomes || {})[r.run_id];
            if (!out) return `<td>—</td>`;
            return `<td>${statusBadgeHtml(out.resolution_status)}</td>`;
          })
          .join("");
        return `
          <tr>
            <td><code>${escapeHtml(row.task_id)}</code> — ${escapeHtml(row.title)}</td>
            <td>${difficultyBadgeHtml(row.difficulty)}</td>
            ${cells}
          </tr>`;
      })
      .join("");

    document.getElementById("comparison-matrix-wrap").innerHTML = `
      <table class="data-table">
        <thead>
          <tr><th>Task</th><th>Difficulty</th>${headerCols}</tr>
        </thead>
        <tbody>${bodyRows}</tbody>
      </table>`;
  } catch (err) {
    console.error("Failed to load comparison:", err);
  }
}

function renderComparisonSvgChart(runs) {
  const container = document.getElementById("comparison-chart-container");
  const width = 920;
  const height = Math.max(220, runs.length * 56 + 60);
  const labelWidth = 240;
  const barMaxW = 540;

  let barsSvg = "";
  runs.forEach((r, idx) => {
    const y = 40 + idx * 52;
    const resW = Math.max(2, (r.resolved_rate / 100) * barMaxW);
    const regFreeW = Math.max(2, (r.regression_free_rate / 100) * barMaxW);
    barsSvg += `
      <text x="12" y="${y + 15}" fill="#f1f5f9" font-size="12" font-weight="600">${escapeHtml(r.run_name.slice(0, 30))}</text>
      <text x="12" y="${y + 31}" fill="#94a3b8" font-size="10.5">${escapeHtml(r.agent_id)}</text>
      <rect x="${labelWidth}" y="${y + 2}" width="${barMaxW}" height="14" rx="4" fill="#182032" />
      <rect x="${labelWidth}" y="${y + 2}" width="${resW}" height="14" rx="4" fill="#22c55e" />
      <text x="${labelWidth + barMaxW + 10}" y="${y + 13}" fill="#4ade80" font-size="11.5" font-weight="700">Resolved: ${r.resolved_rate}%</text>
      <rect x="${labelWidth}" y="${y + 20}" width="${barMaxW}" height="10" rx="3" fill="#182032" />
      <rect x="${labelWidth}" y="${y + 20}" width="${regFreeW}" height="10" rx="3" fill="#38bdf8" />
      <text x="${labelWidth + barMaxW + 10}" y="${y + 29}" fill="#38bdf8" font-size="11">Reg-Free: ${r.regression_free_rate}%</text>
    `;
  });

  container.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" width="100%" height="${height}" role="img" aria-label="Agent Performance Comparison Chart">
      <text x="${labelWidth}" y="22" fill="#94a3b8" font-size="11" font-weight="600">GREEN = RESOLVED RATE (%) · BLUE = REGRESSION-FREE SAFETY RATE (%)</text>
      ${barsSvg}
    </svg>`;
}

async function loadProviders() {
  try {
    const data = await fetchJson("/api/providers");
    state.providers = data.providers || [];
    const listEl = document.getElementById("providers-list-container");
    listEl.innerHTML = state.providers
      .map((p) => {
        const preset = p.preset || {};
        const inRate = p.input_cost_per_1k_tokens;
        const outRate = p.output_cost_per_1k_tokens;
        const priceLine =
          inRate !== null && inRate !== undefined
            ? `<span class="muted" style="margin-top:4px;font-size:11.5px;">Pricing: $${inRate}/1k in · $${outRate}/1k out <em>(${escapeHtml(p.pricing_source || "unknown")})</em></span>`
            : `<span class="muted" style="margin-top:4px;font-size:11.5px;">Pricing: <em>n/a</em> (unmeasured — not free)</span>`;
        return `
      <div class="provider-item">
        <div class="provider-item-top">
          <strong>${escapeHtml(p.name)} (<code>${escapeHtml(p.id)}</code>)</strong>
          ${
            !p.requires_api_key
              ? `<span class="badge badge-pass">OFFLINE / READY</span>`
              : p.has_api_key
              ? `<span class="badge badge-pass">KEY CONFIGURED</span>`
              : `<span class="badge badge-neutral">OPTIONAL API KEY</span>`
          }
          ${preset.cost_tier ? `<span class="badge badge-neutral">${escapeHtml(preset.cost_tier)}</span>` : ""}
        </div>
        <p class="muted">${escapeHtml(p.description)}</p>
        ${p.configured_base_url ? `<div class="muted" style="margin-top:4px;font-size:11.5px;">Endpoint: <code>${escapeHtml(p.configured_base_url)}</code> ${p.configured_model ? `· Model: <code>${escapeHtml(p.configured_model)}</code>` : ""}</div>` : ""}
        ${priceLine}
      </div>`;
      })
      .join("");

    // Easy-connect presets
    const presetEl = document.getElementById("provider-presets-container");
    const presets = data.presets || [];
    if (presetEl) {
      presetEl.innerHTML = presets
        .map(
          (p) => `
        <div class="preset-card" data-preset-provider="${escapeHtml(p.id)}">
          <div class="preset-card-top">
            <strong>${escapeHtml(p.label)}</strong>
            <span class="badge badge-${p.cost_tier === "free" ? "pass" : "neutral"}">${escapeHtml(p.cost_tier)}</span>
          </div>
          <div class="muted" style="font-size:11.5px;word-break:break-all;">${escapeHtml(p.default_base_url || "you provide the base URL")}</div>
          <div class="muted" style="font-size:11.5px;">Key: <code>${escapeHtml(p.api_key_env || "none required")}</code></div>
          <p class="muted" style="font-size:11.5px;">${escapeHtml(p.notes)}</p>
          <button type="button" class="btn btn-secondary btn-apply-preset" data-preset-provider="${escapeHtml(p.id)}">Use this provider</button>
        </div>`
        )
        .join("");

      presetEl.querySelectorAll(".btn-apply-preset").forEach((btn) => {
        btn.addEventListener("click", () => {
          const providerId = btn.dataset.presetProvider;
          const preset = presets.find((x) => x.id === providerId);
          const sel = document.getElementById("cfg-provider");
          if (sel && [...sel.options].some((o) => o.value === providerId)) {
            sel.value = providerId;
          }
          const baseUrlInput = document.getElementById("cfg-base-url");
          const keyInput = document.getElementById("cfg-api-key");
          if (preset) {
            baseUrlInput.value = preset.default_base_url || "";
            baseUrlInput.placeholder = "https://your-gateway.example/v1";
            keyInput.placeholder = preset.api_key_env
              ? `set ${preset.api_key_env} in your environment, or paste it here`
              : "not required";
            document.getElementById("provider-test-result").innerHTML =
              `<div class="info-callout"><strong>${escapeHtml(preset.label)}</strong> selected. ` +
              `${escapeHtml(preset.notes)} ` +
              (preset.api_key_env
                ? `Set <code>${escapeHtml(preset.api_key_env)}</code> in <code>.env</code> or paste the key above, then press <em>Test Connection</em>.`
                : "Press <em>Test Connection</em> to check reachability.") +
              `</div>`;
          }
          document.getElementById("cfg-model").focus();
        });
      });
    }
  } catch (err) {
    console.error("Failed to load providers:", err);
  }
}

async function triggerEvaluationRun(payload) {
  switchTab("evaluate");
  const logEl = document.getElementById("live-run-logs");
  const badgeEl = document.getElementById("live-run-status-badge");
  const barEl = document.getElementById("live-progress-bar");
  const cancelBtn = document.getElementById("btn-cancel-eval");

  logEl.textContent = "Initializing isolated evaluation run...\n";
  badgeEl.textContent = "RUNNING";
  badgeEl.className = "badge badge-warn";
  barEl.style.width = "10%";
  cancelBtn.style.display = "inline-block";

  try {
    const launchRes = await fetchJson("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...payload, async_exec: true }),
    });
    const runId = launchRes.run_id;
    state.selectedRunId = runId;

    cancelBtn.onclick = async () => {
      await fetchJson(`/api/runs/${encodeURIComponent(runId)}/cancel`, { method: "POST" });
    };

    if (state.activePollTimer) clearInterval(state.activePollTimer);
    state.activePollTimer = setInterval(async () => {
      try {
        const logData = await fetchJson(`/api/runs/${encodeURIComponent(runId)}/logs`);
        const lines = (logData.logs || []).map((l) => `${l.timestamp} [${l.level}] ${l.message}`);
        logEl.textContent = lines.join("\n") || "Running tasks...";
        logEl.scrollTop = logEl.scrollHeight;

        const pct = logData.total_tasks > 0 ? Math.round((logData.completed_tasks / logData.total_tasks) * 100) : 50;
        barEl.style.width = `${pct}%`;

        if (logData.status === "COMPLETED" || logData.status === "CANCELLED" || logData.status === "FAILED") {
          clearInterval(state.activePollTimer);
          state.activePollTimer = null;
          badgeEl.textContent = logData.status;
          badgeEl.className = logData.status === "COMPLETED" ? "badge badge-pass" : "badge badge-fail";
          barEl.style.width = "100%";
          cancelBtn.style.display = "none";
          loadOverview();
        }
      } catch (e) {
        console.error("Log poll error:", e);
      }
    }, 600);
  } catch (err) {
    badgeEl.textContent = "ERROR";
    badgeEl.className = "badge badge-fail";
    logEl.textContent += `\nError launching run: ${err.message}`;
    cancelBtn.style.display = "none";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  document.getElementById("task-search").addEventListener("input", () => loadTasks());
  document.getElementById("task-difficulty-filter").addEventListener("change", () => loadTasks());
  document.getElementById("task-category-filter").addEventListener("change", () => loadTasks());

  document.getElementById("eval-provider").addEventListener("change", (e) => {
    const isOffline = e.target.value === "offline";
    document.getElementById("offline-patch-group").style.display = isOffline ? "flex" : "none";
  });

  document.getElementById("launch-run-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const provider = document.getElementById("eval-provider").value;
    const runName = document.getElementById("eval-run-name").value.trim() || undefined;
    const taskFilter = document.getElementById("eval-task-filter").value;
    const difficulty = document.getElementById("eval-difficulty").value || undefined;
    const maxWorkers = parseInt(document.getElementById("eval-workers").value || "1", 10);
    const timeoutSeconds = parseInt(document.getElementById("eval-timeout").value || "60", 10);
    const patchText = provider === "offline" ? document.getElementById("eval-patch-text").value : undefined;

    triggerEvaluationRun({
      provider,
      run_name: runName,
      task_ids: taskFilter ? [taskFilter] : undefined,
      difficulty,
      max_workers: maxWorkers,
      timeout_seconds: timeoutSeconds,
      patch_text: patchText,
    });
  });

  document.getElementById("btn-quick-reference").addEventListener("click", () => {
    triggerEvaluationRun({
      provider: "reference",
      run_name: "Reference Oracle Evaluation (All 12 Tasks)",
      max_workers: 2,
    });
  });

  document.getElementById("btn-quick-noop").addEventListener("click", () => {
    triggerEvaluationRun({
      provider: "noop",
      run_name: "No-Op Baseline Evaluation (All 12 Tasks)",
      max_workers: 2,
    });
  });

  document.getElementById("results-run-select").addEventListener("change", (e) => {
    state.selectedRunId = e.target.value;
    displaySelectedRun(state.selectedRunId);
  });

  ["json", "jsonl", "csv"].forEach((fmt) => {
    document.getElementById(`btn-export-${fmt}`).addEventListener("click", () => {
      if (!state.selectedRunId) return;
      window.open(`/api/runs/${encodeURIComponent(state.selectedRunId)}/export?fmt=${fmt}`, "_blank");
    });
  });

  document.getElementById("provider-config-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const box = document.getElementById("provider-test-result");
    try {
      const inCostRaw = document.getElementById("cfg-input-cost").value.trim();
      const outCostRaw = document.getElementById("cfg-output-cost").value.trim();
      const payload = {
        provider: document.getElementById("cfg-provider").value,
        base_url: document.getElementById("cfg-base-url").value.trim(),
        api_key: document.getElementById("cfg-api-key").value.trim(),
        model: document.getElementById("cfg-model").value.trim(),
        temperature: parseFloat(document.getElementById("cfg-temp").value || "0.0"),
        max_tokens: parseInt(document.getElementById("cfg-max-tokens").value || "4096", 10),
        max_cost_usd: parseFloat(document.getElementById("cfg-max-cost").value || "0") || 0,
        input_cost_per_1k_tokens: inCostRaw === "" ? null : parseFloat(inCostRaw),
        output_cost_per_1k_tokens: outCostRaw === "" ? null : parseFloat(outCostRaw),
        allow_builtin_pricing_estimates:
          document.getElementById("cfg-use-builtin").value === "true",
      };
      await fetchJson("/api/providers/configure", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      box.innerHTML = `<span class="status-text-pass">Saved settings for provider <code>${escapeHtml(payload.provider)}</code>.</span>`;
      loadProviders();
    } catch (err) {
      box.innerHTML = `<span class="status-text-fail">Failed to save: ${escapeHtml(err.message)}</span>`;
    }
  });

  document.getElementById("btn-test-provider").addEventListener("click", async () => {
    const box = document.getElementById("provider-test-result");
    box.innerHTML = `<span class="muted">Testing connection and discovering models...</span>`;
    try {
      const payload = {
        provider: document.getElementById("cfg-provider").value,
        base_url: document.getElementById("cfg-base-url").value.trim() || undefined,
        api_key: document.getElementById("cfg-api-key").value.trim() || undefined,
        model: document.getElementById("cfg-model").value.trim() || undefined,
      };
      const res = await fetchJson("/api/providers/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (res.reachable && res.authenticated) {
        box.innerHTML = `<span class="status-text-pass">✓ ${escapeHtml(res.message)} (${res.latency_ms}ms)</span>`;
        if (res.selected_model && !document.getElementById("cfg-model").value) {
          document.getElementById("cfg-model").value = res.selected_model;
        }
      } else {
        box.innerHTML = `<span class="status-text-fail">✗ ${escapeHtml(res.message)}</span>`;
      }
    } catch (err) {
      box.innerHTML = `<span class="status-text-fail">Error: ${escapeHtml(err.message)}</span>`;
    }
  });

  loadOverview();
  loadTasks();
});
