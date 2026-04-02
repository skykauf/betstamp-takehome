(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  let threadId = null;

  function asArray(x) {
    return Array.isArray(x) ? x : [];
  }

  function clearBriefing(el) {
    while (el.firstChild) el.removeChild(el.firstChild);
  }

  function addHeading(parent, text) {
    const h = document.createElement("h2");
    h.textContent = text;
    parent.appendChild(h);
  }

  function addParagraph(parent, text) {
    const p = document.createElement("p");
    p.textContent = text == null ? "" : String(text);
    parent.appendChild(p);
  }

  function addMetaLine(parent, parts) {
    const bits = parts.filter(Boolean);
    if (!bits.length) return;
    const span = document.createElement("span");
    span.className = "item-meta";
    span.textContent = bits.join(" · ");
    parent.appendChild(span);
  }

  const CONF_LEVELS = new Set(["high", "medium", "low"]);

  function appendConfidence(parent, level, basis) {
    const norm = level == null ? "" : String(level).toLowerCase().trim();
    const b = basis == null ? "" : String(basis).trim();
    if (!CONF_LEVELS.has(norm) && !b) return;
    const wrap = document.createElement("div");
    wrap.className = "confidence";
    if (CONF_LEVELS.has(norm)) {
      const strong = document.createElement("strong");
      strong.textContent = "Confidence: " + norm;
      wrap.appendChild(strong);
    }
    if (b) {
      const rest = document.createElement("span");
      rest.textContent = (CONF_LEVELS.has(norm) ? " — " : "") + b;
      wrap.appendChild(rest);
    }
    parent.appendChild(wrap);
  }

  function renderBriefing(data) {
    const el = $("briefing");
    clearBriefing(el);

    const rawOnly =
      data &&
      typeof data.raw_markdown === "string" &&
      data.raw_markdown.length > 0 &&
      typeof data.market_overview !== "string";

    if (rawOnly) {
      addHeading(el, "Briefing (unparsed)");
      const pre = document.createElement("pre");
      pre.className = "trace";
      pre.style.marginTop = "0.5rem";
      pre.textContent = data.raw_markdown;
      el.appendChild(pre);
      const hint = document.createElement("p");
      hint.className = "muted";
      hint.style.marginTop = "0.75rem";
      hint.textContent =
        "The model did not return pure JSON; showing raw text. You can still ask follow-ups.";
      el.appendChild(hint);
      return;
    }

    const overview = typeof data.market_overview === "string" ? data.market_overview : "";
    const anomalies = asArray(data.anomalies);
    const values = asArray(data.value_opportunities);
    let books = asArray(data.sportsbook_quality);
    books = [...books].sort((a, b) => (Number(a.rank) || 0) - (Number(b.rank) || 0));

    addHeading(el, "Market overview");
    addParagraph(el, overview || "—");
    appendConfidence(
      el,
      data.market_overview_confidence,
      data.market_overview_confidence_basis
    );

    addHeading(el, "Flagged anomalies");
    if (!anomalies.length) {
      addParagraph(el, "None called out.");
    } else {
      const ul = document.createElement("ul");
      anomalies.forEach((a) => {
        const li = document.createElement("li");
        const title = document.createElement("span");
        title.className = "item-title";
        title.textContent = a.summary || "Anomaly";
        li.appendChild(title);
        addMetaLine(li, [a.game_id, a.sportsbook].filter((x) => x != null && x !== ""));
        if (a.detail) {
          const d = document.createElement("span");
          d.className = "item-detail";
          d.textContent = a.detail;
          li.appendChild(d);
        }
        appendConfidence(li, a.confidence, a.confidence_basis);
        ul.appendChild(li);
      });
      el.appendChild(ul);
    }

    addHeading(el, "Value opportunities");
    if (!values.length) {
      addParagraph(el, "None highlighted.");
    } else {
      const ul = document.createElement("ul");
      values.forEach((v) => {
        const li = document.createElement("li");
        const title = document.createElement("span");
        title.className = "item-title";
        title.textContent = v.summary || "Opportunity";
        li.appendChild(title);
        addMetaLine(li, [v.game_id, v.market].filter((x) => x != null && x !== ""));
        if (v.math) {
          const d = document.createElement("span");
          d.className = "item-detail";
          d.textContent = v.math;
          li.appendChild(d);
        }
        appendConfidence(li, v.confidence, v.confidence_basis);
        ul.appendChild(li);
      });
      el.appendChild(ul);
    }

    addHeading(el, "Sportsbook quality");
    if (!books.length) {
      addParagraph(el, "No ranking returned.");
    } else {
      const ol = document.createElement("ol");
      books.forEach((b) => {
        const li = document.createElement("li");
        const title = document.createElement("span");
        title.className = "item-title";
        title.textContent = b.sportsbook || "Book";
        li.appendChild(title);
        if (b.rationale) {
          const d = document.createElement("span");
          d.className = "item-detail";
          d.textContent = b.rationale;
          li.appendChild(d);
        }
        appendConfidence(li, b.confidence, b.confidence_basis);
        ol.appendChild(li);
      });
      el.appendChild(ol);
    }
  }

  function setDemoPromptsEnabled(on) {
    document.querySelectorAll(".demo-q").forEach((btn) => {
      btn.disabled = !on;
    });
  }

  function resetBriefingActivityPanel() {
    const sec = $("briefing-activity-section");
    sec.classList.add("is-live");
    $("briefing-tools-live").textContent = "";
    $("briefing-draft").textContent = "";
    $("briefing-draft").style.display = "none";
    $("briefing-draft-label").style.display = "none";
  }

  function hideBriefingActivityPanel() {
    $("briefing-activity-section").classList.remove("is-live");
  }

  function appendBriefingToolLine(name, args) {
    const ul = $("briefing-tools-live");
    const li = document.createElement("li");
    let line = name || "tool";
    if (args && typeof args === "object" && Object.keys(args).length) {
      const s = JSON.stringify(args);
      line += s.length > 120 ? " " + s.slice(0, 117) + "…" : " " + s;
    }
    li.textContent = line;
    ul.appendChild(li);
  }

  async function readFetchErrorBody(r) {
    const errBody = await r.text();
    let msg = errBody;
    try {
      const j = JSON.parse(errBody);
      if (j.detail) msg = Array.isArray(j.detail) ? JSON.stringify(j.detail) : j.detail;
    } catch (_) {}
    return String(msg).slice(0, 400);
  }

  function setBusy(b) {
    $("run-brief").disabled = b;
    $("send-chat").disabled = b || !threadId;
    $("chat-input").disabled = b || !threadId;
    if (threadId && !b) setDemoPromptsEnabled(true);
    else if (!threadId || b) setDemoPromptsEnabled(false);
  }

  async function readSseEvents(response, onEvent) {
    const reader = response.body.getReader();
    const dec = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += dec.decode(value, { stream: true });
      for (;;) {
        const idx = buffer.indexOf("\n\n");
        if (idx === -1) break;
        const block = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        for (const raw of block.split("\n")) {
          const line = raw.replace(/\r$/, "");
          if (!line.startsWith("data: ")) continue;
          const payload = line.slice(6).trim();
          if (!payload) continue;
          let evt;
          try {
            evt = JSON.parse(payload);
          } catch (_) {
            continue;
          }
          onEvent(evt);
        }
      }
    }
  }

  async function sendChatMessage(text) {
    const t = (text || "").trim();
    if (!t || !threadId) return;
    setBusy(true);
    const prev = $("chat-log").textContent;
    const header =
      (prev && prev !== "—" ? prev + "\n\n---\n\n" : "") + "You: " + t + "\n\nAgent: ";
    $("chat-input").value = "";
    let agentText = "";
    const toolsRunning = [];
    $("chat-log").textContent = header + "…";
    try {
      const r = await fetch("/api/chat/stream", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify({ thread_id: threadId, message: t }),
      });
      if (!r.ok) throw new Error(await readFetchErrorBody(r));
      await readSseEvents(r, (evt) => {
        if (evt.event === "error") {
          throw new Error(evt.message || "Stream error");
        }
        if (evt.event === "delta" && evt.text) {
          agentText += evt.text;
          const toolLine =
            toolsRunning.length > 0
              ? "\n\n(tools running: " + toolsRunning.join(", ") + ")"
              : "";
          $("chat-log").textContent = header + agentText + toolLine;
        } else if (evt.event === "tool" && evt.name) {
          toolsRunning.push(evt.name);
          $("chat-log").textContent =
            header +
            agentText +
            "\n\n(tools running: " +
            toolsRunning.join(", ") +
            ")";
        } else if (evt.event === "done") {
          agentText = evt.reply != null ? String(evt.reply) : agentText;
          $("chat-log").textContent =
            header +
            agentText +
            "\n\n(tools: " +
            JSON.stringify(evt.tool_trace || []) +
            ")";
        }
      });
    } catch (e) {
      $("chat-log").textContent = prev + "\n\nError: " + e.message;
    } finally {
      setBusy(false);
    }
  }

  $("run-brief").onclick = async () => {
    setBusy(true);
    threadId = null;
    setDemoPromptsEnabled(false);
    clearBriefing($("briefing"));
    const waitP = document.createElement("p");
    waitP.className = "muted";
    waitP.style.margin = "0";
    waitP.textContent = "Waiting for structured briefing…";
    $("briefing").appendChild(waitP);
    $("trace").textContent = "—";
    $("thread-label").textContent = "Generating briefing…";
    resetBriefingActivityPanel();
    let gotBriefDone = false;
    try {
      const r = await fetch("/api/brief/stream", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: "{}",
      });
      if (!r.ok) throw new Error(await readFetchErrorBody(r));
      await readSseEvents(r, (evt) => {
        if (evt.event === "error") {
          throw new Error(evt.message || "Briefing stream error");
        }
        if (evt.event === "tool" && evt.name) {
          appendBriefingToolLine(evt.name, evt.arguments);
        }
        if (evt.event === "delta" && evt.text) {
          const pre = $("briefing-draft");
          const lab = $("briefing-draft-label");
          pre.style.display = "block";
          lab.style.display = "block";
          pre.textContent += evt.text;
        }
        if (evt.event === "brief_done") {
          gotBriefDone = true;
          threadId = evt.thread_id;
          $("thread-label").textContent = "thread: " + threadId;
          renderBriefing(evt.briefing || {});
          $("trace").textContent = JSON.stringify(evt.tool_trace || [], null, 2);
          $("trace-wrap").open = true;
          $("chat-log").textContent = "—";
          hideBriefingActivityPanel();
        }
      });
      if (!gotBriefDone) {
        throw new Error("Stream ended before briefing completed.");
      }
    } catch (e) {
      hideBriefingActivityPanel();
      clearBriefing($("briefing"));
      const p = document.createElement("p");
      p.className = "muted";
      p.textContent = "Error: " + e.message;
      $("briefing").appendChild(p);
      $("thread-label").textContent = "";
    } finally {
      setBusy(false);
    }
  };

  $("send-chat").onclick = () => sendChatMessage($("chat-input").value);

  $("chat-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendChatMessage($("chat-input").value);
    }
  });

  document.getElementById("demo-prompts").addEventListener("click", (e) => {
    const btn = e.target.closest(".demo-q");
    if (!btn || btn.disabled) return;
    const q = btn.getAttribute("data-q");
    if (!q) return;
    $("chat-input").value = q;
    sendChatMessage(q);
  });
})();
