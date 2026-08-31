const SECTION_ORDER = [
  ["problem_diagnosis", "Problem diagnosis"],
  ["automation_potential", "Automation potential"],
  ["recommended_solution", "Recommended AI or automation solution"],
  ["solution_architecture", "Suggested solution architecture"],
  ["expected_business_impact", "Expected business impact"],
  ["implementation_complexity", "Implementation complexity"],
  ["key_risks", "Key risks"],
  ["recommended_mvp_scope", "Recommended MVP scope"],
  ["next_implementation_steps", "Next implementation steps"],
];

const state = { assessmentId: null, examples: [] };

function $(id) {
  return document.getElementById(id);
}

function fieldValue(id) {
  return $(id).value.trim();
}

async function loadHealth() {
  const el = $("health");
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    if (!data.ok) {
      el.className = "health bad";
      el.textContent = "Ollama is not reachable. Start Ollama before running an assessment.";
      return;
    }
    el.className = "health ok";
    const present = data.model_present
      ? `Model ${data.model} is available.`
      : `Ollama is up. Pull a model if needed: ollama pull ${data.model}`;
    el.textContent = present;
  } catch {
    el.className = "health bad";
    el.textContent = "Cannot reach the local API.";
  }
}

async function loadExamples() {
  const res = await fetch("/api/examples");
  state.examples = await res.json();
  const box = $("examples");
  box.innerHTML = "";
  state.examples.forEach((ex) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.innerHTML = `<strong>${ex.title}</strong><br><span>${ex.blurb}</span>`;
    btn.addEventListener("click", () => {
      box.querySelectorAll("button").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      $("process_text").value = ex.process_text;
      $("industry").value = ex.industry || "";
      $("volume_note").value = ex.volume_note || "";
      $("tools_note").value = ex.tools_note || "";
      $("data_shape").value = ex.data_shape || "unknown";
      $("judgment_level").value = ex.judgment_level || "unknown";
    });
    box.appendChild(btn);
  });
}

function renderList(items) {
  const ul = document.createElement("ul");
  (items || []).forEach((item) => {
    const li = document.createElement("li");
    li.textContent = item;
    ul.appendChild(li);
  });
  return ul;
}

function renderReport(payload) {
  const report = payload.report;
  const rubric = payload.rubric;
  $("result").hidden = false;
  $("class-title").textContent = `Classification: ${report.classification}`;
  const badges = $("badges");
  badges.innerHTML = "";
  const b1 = document.createElement("span");
  b1.className = `badge ${report.classification}`;
  b1.textContent = report.classification;
  const b2 = document.createElement("span");
  b2.className = "badge";
  b2.textContent = rubric.authoritative
    ? `rubric ${rubric.confidence} · authoritative`
    : `rubric ${rubric.confidence}`;
  badges.append(b1, b2);

  const banner = $("memory-banner");
  const mem = payload.memory;
  if (mem && mem.used) {
    banner.hidden = false;
    banner.className = "memory-banner" + (mem.conflict ? " conflict" : "");
    const lessons = (mem.lessons || [])
      .map(
        (l) =>
          `<li><strong>${l.outcome.replaceAll("_", " ")}</strong> — ${escapeHtml(
            l.implemented_what
          )} <button type="button" class="link" data-discard="${l.id}">Not relevant</button></li>`
      )
      .join("");
    banner.innerHTML = `<p><strong>${escapeHtml(mem.attribution)}</strong> This is retrieved past feedback, not model training.</p>
      ${mem.conflict && mem.conflict_note ? `<p>${escapeHtml(mem.conflict_note)}</p>` : ""}
      <ul>${lessons}</ul>`;
    banner.querySelectorAll("[data-discard]").forEach((btn) => {
      btn.addEventListener("click", () => discardLesson(btn.getAttribute("data-discard"), btn));
    });
  } else {
    banner.hidden = true;
    banner.innerHTML = "";
  }

  const ol = $("sections");
  ol.innerHTML = "";
  const extra = {
    implementation_complexity: report.implementation_complexity_band
      ? `Band: ${report.implementation_complexity_band}\n\n${report.implementation_complexity}`
      : report.implementation_complexity,
  };
  SECTION_ORDER.forEach(([key, title]) => {
    const li = document.createElement("li");
    const h = document.createElement("h3");
    h.textContent = title;
    li.appendChild(h);
    const value = extra[key] || report[key];
    if (Array.isArray(value)) {
      li.appendChild(renderList(value));
    } else {
      const p = document.createElement("p");
      p.textContent = value || "";
      li.appendChild(p);
    }
    ol.appendChild(li);
  });

  const rationale = document.createElement("li");
  rationale.innerHTML = `<h3>Classification rationale</h3>`;
  const p = document.createElement("p");
  p.textContent = report.classification_rationale || "";
  rationale.appendChild(p);
  ol.appendChild(rationale);

  $("feedback-form").hidden = true;
  $("feedback-msg").hidden = true;
  document.querySelectorAll(".outcomes button").forEach((b) => b.classList.remove("active"));
}

function escapeHtml(s) {
  return String(s || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

async function discardLesson(id, btn) {
  const res = await fetch(`/api/lessons/${id}/not-relevant`, { method: "POST" });
  if (res.ok) {
    btn.textContent = "Discarded";
    btn.disabled = true;
  }
}

$("assess-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const err = $("form-error");
  err.hidden = true;
  $("result").hidden = true;
  const status = $("status");
  status.hidden = false;
  status.textContent = "Running the local model. First CPU runs can take a minute.";
  $("submit-btn").disabled = true;
  const body = {
    process_text: fieldValue("process_text"),
    industry: fieldValue("industry") || null,
    volume_note: fieldValue("volume_note") || null,
    tools_note: fieldValue("tools_note") || null,
    data_shape: $("data_shape").value,
    judgment_level: $("judgment_level").value,
  };
  try {
    const res = await fetch("/api/assess", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Assessment failed");
    }
    state.assessmentId = data.assessment_id;
    status.hidden = true;
    renderReport(data);
    $("result").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (e) {
    err.hidden = false;
    err.textContent = e.message || String(e);
    status.hidden = true;
  } finally {
    $("submit-btn").disabled = false;
  }
});

document.querySelectorAll(".outcomes button").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".outcomes button").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    $("outcome").value = btn.getAttribute("data-outcome");
    $("feedback-form").hidden = false;
  });
});

$("feedback-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const msg = $("feedback-msg");
  if (!state.assessmentId) {
    msg.hidden = false;
    msg.textContent = "Run an assessment first.";
    return;
  }
  const body = {
    assessment_id: state.assessmentId,
    outcome: $("outcome").value,
    implemented_what: fieldValue("implemented_what"),
    what_worked: fieldValue("what_worked"),
    what_failed: fieldValue("what_failed"),
    why: fieldValue("why"),
    alternative: fieldValue("alternative"),
    company_specific: $("company_specific").checked,
  };
  const res = await fetch("/api/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  msg.hidden = false;
  msg.textContent = data.message || data.detail || "Saved.";
});

loadHealth();
loadExamples();
