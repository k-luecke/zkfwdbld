const state = {
  packet: null,
  selectedView: "overview",
  rawMode: false
};

async function loadPacket() {
  const sources = ["/generated/packet.json", "/api/packet"];

  for (const source of sources) {
    try {
      const response = await fetch(source);
      if (!response.ok) {
        continue;
      }

      const payload = await response.json();
      state.packet = payload.packet || payload;
      if (state.packet) {
        return;
      }
    } catch (_error) {
      continue;
    }
  }

  throw new Error("Failed to load packet from generated snapshot or local API.");
}

function escapeHtml(text) {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function inlineMarkdown(text) {
  return escapeHtml(text)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
}

function renderMarkdown(mdText) {
  const lines = mdText.replace(/\r/g, "").split("\n");
  const blocks = [];
  let listBuffer = null;
  let codeBuffer = null;
  let paragraph = [];

  function flushParagraph() {
    if (paragraph.length) {
      blocks.push(`<p>${inlineMarkdown(paragraph.join(" "))}</p>`);
      paragraph = [];
    }
  }

  function flushList() {
    if (listBuffer) {
      const tag = listBuffer.type === "ol" ? "ol" : "ul";
      const items = listBuffer.items.map((item) => `<li>${inlineMarkdown(item)}</li>`).join("");
      blocks.push(`<${tag}>${items}</${tag}>`);
      listBuffer = null;
    }
  }

  function flushCode() {
    if (codeBuffer) {
      blocks.push(`<pre><code>${escapeHtml(codeBuffer.join("\n"))}</code></pre>`);
      codeBuffer = null;
    }
  }

  for (const line of lines) {
    if (line.startsWith("```")) {
      flushParagraph();
      flushList();
      if (codeBuffer) {
        flushCode();
      } else {
        codeBuffer = [];
      }
      continue;
    }

    if (codeBuffer) {
      codeBuffer.push(line);
      continue;
    }

    if (!line.trim()) {
      flushParagraph();
      flushList();
      continue;
    }

    const headingMatch = line.match(/^(#{1,3})\s+(.*)$/);
    if (headingMatch) {
      flushParagraph();
      flushList();
      const level = headingMatch[1].length;
      blocks.push(`<h${level}>${inlineMarkdown(headingMatch[2])}</h${level}>`);
      continue;
    }

    const orderedMatch = line.match(/^\d+\.\s+(.*)$/);
    if (orderedMatch) {
      flushParagraph();
      if (!listBuffer || listBuffer.type !== "ol") {
        flushList();
        listBuffer = { type: "ol", items: [] };
      }
      listBuffer.items.push(orderedMatch[1]);
      continue;
    }

    const bulletMatch = line.match(/^-\s+(.*)$/);
    if (bulletMatch) {
      flushParagraph();
      if (!listBuffer || listBuffer.type !== "ul") {
        flushList();
        listBuffer = { type: "ul", items: [] };
      }
      listBuffer.items.push(bulletMatch[1]);
      continue;
    }

    paragraph.push(line.trim());
  }

  flushParagraph();
  flushList();
  flushCode();
  return blocks.join("");
}

function bundleLabel(name) {
  const labels = {
    harness: "Harness Findings",
    scanner: "Scanner Findings",
    messages: "Ops Loop Actions"
  };
  return labels[name] || name;
}

function renderNav() {
  const nav = document.getElementById("nav");
  const buttons = [
    { key: "overview", title: "Overview", meta: "Packet summary and bundle snapshot" },
    { key: "talk-track", title: "Talk Track", meta: "Short walkthrough for demos" },
    ...state.packet.bundles.map((bundle) => ({
      key: `bundle:${bundle.name}`,
      title: bundleLabel(bundle.name),
      meta: bundle.summary.handoff_readiness
    }))
  ];

  nav.innerHTML = buttons
    .map(
      (button) => `
        <button class="${state.selectedView === button.key ? "active" : ""}" data-view="${button.key}">
          <span class="title">${button.title}</span>
          <span class="meta">${button.meta}</span>
        </button>
      `
    )
    .join("");

  nav.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedView = button.dataset.view;
      render();
    });
  });
}

function renderPacketMeta() {
  const meta = document.getElementById("packet-meta");
  meta.innerHTML = `
    <div><strong>Type:</strong> ${state.packet.packet_type}</div>
    <div><strong>Generated:</strong> ${new Date(state.packet.generated_at).toLocaleString()}</div>
    <div><strong>Packet dir:</strong> <code>${state.packet.packet_dir}</code></div>
  `;
}

function renderBundleSummary() {
  const container = document.getElementById("bundle-summary");
  container.innerHTML = state.packet.bundles
    .map((bundle) => {
      const pills = Object.entries(bundle.summary.trust_states)
        .map(([key, value]) => `<span class="pill ${key}">${key}: ${value}</span>`)
        .join("");
      return `
        <article class="bundle-card">
          <div class="eyebrow">${bundleLabel(bundle.name)}</div>
          <h3>${bundle.summary.title}</h3>
          <p>${bundle.summary.handoff_readiness}</p>
          <div class="bundle-stats">${pills}</div>
        </article>
      `;
    })
    .join("");
}

function setDocument(title, subtitle, markdown, rawText) {
  document.getElementById("document-title").textContent = title;
  document.getElementById("view-subtitle").textContent = subtitle;
  document.getElementById("document-rendered").innerHTML = renderMarkdown(markdown);
  document.getElementById("document-raw").textContent = rawText;
}

function renderOverview() {
  document.getElementById("view-title").textContent = "Packet Overview";
  setDocument("Overview", "Product framing and walkthrough summary", state.packet.overview, state.packet.overview);
  document.getElementById("item-list").innerHTML =
    '<div class="empty-state">Choose a bundle from the left to open handoffs, reports, and artifacts.</div>';
}

function renderTalkTrack() {
  document.getElementById("view-title").textContent = "Demo Talk Track";
  setDocument("Talk Track", "Short guided narrative for live walkthroughs", state.packet.talk_track, state.packet.talk_track);
  document.getElementById("item-list").innerHTML =
    '<div class="empty-state">Open a bundle next if you want to move from the script into the actual artifacts.</div>';
}

function renderArtifactCard(bundle, item) {
  const trustState = item.artifact.verification?.trust_state || item.artifact.action?.status || "unknown";
  const title =
    item.artifact.claim?.title ||
    item.artifact.action?.type ||
    item.finding_id;

  return `
    <article class="artifact-card">
      <div class="item-header">
        <div>
          <div class="eyebrow">${bundleLabel(bundle.name)}</div>
          <h4>${title}</h4>
          <div class="item-meta">${item.finding_id}</div>
        </div>
        <span class="pill ${trustState}">${trustState}</span>
      </div>
      <div>${escapeHtml(item.artifact.summary || "No summary available.")}</div>
      <div class="actions">
        <button data-doc="report" data-bundle="${bundle.name}" data-id="${item.finding_id}">Open report</button>
        <button data-doc="artifact" data-bundle="${bundle.name}" data-id="${item.finding_id}">Open artifact</button>
      </div>
    </article>
  `;
}

function renderBundle(bundle) {
  document.getElementById("view-title").textContent = bundle.summary.title;
  setDocument(
    "Engineering Handoff",
    bundle.summary.handoff_readiness,
    bundle.handoff,
    bundle.handoff
  );

  const itemList = document.getElementById("item-list");
  itemList.innerHTML = bundle.items.map((item) => renderArtifactCard(bundle, item)).join("");
  itemList.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      const item = bundle.items.find((entry) => entry.finding_id === button.dataset.id);
      if (!item) return;
      if (button.dataset.doc === "report") {
        setDocument("Per-Item Report", `${item.finding_id}`, item.report, item.report);
      } else {
        const pretty = JSON.stringify(item.artifact, null, 2);
        setDocument("Artifact JSON", `${item.finding_id}`, `\`\`\`json\n${pretty}\n\`\`\``, pretty);
      }
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });
}

function syncTabState() {
  const rendered = document.getElementById("document-rendered");
  const raw = document.getElementById("document-raw");
  document.querySelectorAll(".tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === (state.rawMode ? "raw" : "rendered"));
  });
  rendered.classList.toggle("hidden", state.rawMode);
  raw.classList.toggle("hidden", !state.rawMode);
}

function render() {
  renderNav();
  renderPacketMeta();
  renderBundleSummary();

  if (state.selectedView === "overview") {
    renderOverview();
  } else if (state.selectedView === "talk-track") {
    renderTalkTrack();
  } else if (state.selectedView.startsWith("bundle:")) {
    const bundleName = state.selectedView.split(":")[1];
    const bundle = state.packet.bundles.find((entry) => entry.name === bundleName);
    if (bundle) {
      renderBundle(bundle);
    }
  }

  syncTabState();
}

async function bootstrap() {
  try {
    await loadPacket();
    render();
    document.querySelectorAll(".tab").forEach((button) => {
      button.addEventListener("click", () => {
        state.rawMode = button.dataset.tab === "raw";
        syncTabState();
      });
    });
  } catch (error) {
    document.body.innerHTML = `
      <main style="padding: 40px; font-family: Inter, sans-serif;">
        <h1>zkfwdbld Viewer</h1>
        <p>Could not load the packet.</p>
        <pre>${escapeHtml(error.message)}</pre>
      </main>
    `;
  }
}

bootstrap();
