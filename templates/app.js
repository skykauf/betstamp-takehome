(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  let threadId = null;
  const chatMessages = [];
  let briefingUpdatedAtMs = null;
  let briefingUpdatedTicker = null;

  function asArray(x) {
    return Array.isArray(x) ? x : [];
  }

  function addChatMessage(role, text, tools) {
    chatMessages.push({
      role: role || "agent",
      text: text == null ? "" : String(text),
      tools: Array.isArray(tools) ? tools : null,
    });
    renderChatLog();
  }

  function updateLastAgentMessage(text, tools) {
    if (!chatMessages.length || chatMessages[chatMessages.length - 1].role !== "agent") {
      addChatMessage("agent", text, tools);
      return;
    }
    const idx = chatMessages.length - 1;
    chatMessages[idx].text = text == null ? "" : String(text);
    chatMessages[idx].tools = Array.isArray(tools) ? tools : null;
    renderChatLog();
  }

  function relativeAge(ms) {
    if (ms == null) return "—";
    const deltaSec = Math.max(0, Math.floor((Date.now() - ms) / 1000));
    if (deltaSec < 10) return "just now";
    if (deltaSec < 60) return deltaSec + "s ago";
    const mins = Math.floor(deltaSec / 60);
    if (mins < 60) return mins + "m ago";
    const hours = Math.floor(mins / 60);
    if (hours < 24) return hours + "h ago";
    const days = Math.floor(hours / 24);
    return days + "d ago";
  }

  function renderBriefingUpdatedLabel() {
    $("briefing-last-updated").textContent = "Last updated: " + relativeAge(briefingUpdatedAtMs);
  }

  function startBriefingUpdatedTicker() {
    if (briefingUpdatedTicker != null) window.clearInterval(briefingUpdatedTicker);
    renderBriefingUpdatedLabel();
    briefingUpdatedTicker = window.setInterval(renderBriefingUpdatedLabel, 1000);
  }

  function renderChatLog() {
    const root = $("chat-log");
    while (root.firstChild) root.removeChild(root.firstChild);
    if (!chatMessages.length) {
      root.textContent = "—";
      return;
    }
    chatMessages.forEach((m, idx) => {
      const item = document.createElement("div");
      item.className = "chat-msg";

      const head = document.createElement("div");
      head.className = "chat-msg-head";

      const role = document.createElement("span");
      role.className = "chat-msg-role";
      role.textContent = m.role === "user" ? "You" : "Agent";
      head.appendChild(role);

      if (m.role === "agent") {
        const copyBtn = document.createElement("button");
        copyBtn.type = "button";
        copyBtn.className = "chat-msg-copy";
        copyBtn.textContent = "Copy";
        copyBtn.onclick = async () => {
          try {
            await navigator.clipboard.writeText(m.text || "");
            copyBtn.textContent = "Copied";
            window.setTimeout(() => {
              copyBtn.textContent = "Copy";
            }, 1200);
          } catch (_) {
            copyBtn.textContent = "Failed";
            window.setTimeout(() => {
              copyBtn.textContent = "Copy";
            }, 1200);
          }
        };
        head.appendChild(copyBtn);
      } else {
        const spacer = document.createElement("span");
        spacer.textContent = " ";
        head.appendChild(spacer);
      }
      item.appendChild(head);

      const body = document.createElement("p");
      body.className = "chat-msg-body";
      body.textContent = m.text || "";
      item.appendChild(body);

      if (m.role === "agent" && m.tools && m.tools.length) {
        const tools = document.createElement("div");
        tools.className = "chat-msg-tools";
        tools.textContent = "tools: " + JSON.stringify(m.tools);
        item.appendChild(tools);
      }

      root.appendChild(item);
    });
    root.scrollTop = root.scrollHeight;
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
    $("refresh-dk-now").disabled = b || !threadId;
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
    $("chat-input").value = "";
    addChatMessage("user", t);
    addChatMessage("agent", "…");
    let agentText = "";
    const toolsRunning = [];
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
          const toolTrace = toolsRunning.map((name) => ({ name: name, state: "running" }));
          updateLastAgentMessage(agentText, toolTrace);
        } else if (evt.event === "tool" && evt.name) {
          toolsRunning.push(evt.name);
          const textNow = agentText || "…";
          const toolTrace = toolsRunning.map((name) => ({ name: name, state: "running" }));
          updateLastAgentMessage(textNow, toolTrace);
        } else if (evt.event === "done") {
          agentText = evt.reply != null ? String(evt.reply) : agentText;
          updateLastAgentMessage(agentText, evt.tool_trace || []);
        }
      });
    } catch (e) {
      updateLastAgentMessage("Error: " + e.message, null);
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
    briefingUpdatedAtMs = null;
    renderBriefingUpdatedLabel();
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
          chatMessages.length = 0;
          renderChatLog();
          briefingUpdatedAtMs = Date.now();
          startBriefingUpdatedTicker();
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
  $("refresh-dk-now").onclick = () =>
    sendChatMessage(
      "Please call refresh_draftkings_nba_odds now, then confirm dataset source and record count."
    );

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
  renderBriefingUpdatedLabel();
  renderChatLog();
})();
