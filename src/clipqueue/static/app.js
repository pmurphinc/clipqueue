// Small bits of interactivity. No framework, no build step.
(function () {
  "use strict";

  async function post(url, data) {
    const body = new FormData();
    Object.entries(data || {}).forEach(([k, v]) => body.append(k, v));
    const r = await fetch(url, { method: "POST", body });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  }

  // Folder scan progress.
  function pollScan() {
    const box = document.getElementById("scan-status");
    if (!box || box.dataset.poll !== "1") return;
    const tick = async () => {
      const s = await (await fetch("/api/scan")).json();
      const bar = box.querySelector(".bar span");
      if (bar) bar.style.width = (s.total ? (100 * s.done) / s.total : 0) + "%";
      box.querySelector(".scan-msg").textContent = s.message;
      if (s.running) setTimeout(tick, 700);
      else location.replace(location.pathname + location.hash); // drop the "Scanning..." banner
    };
    tick();
  }

  // Limit "pick up to N" checkbox groups.
  function limitChecks() {
    document.querySelectorAll("[data-max]").forEach((group) => {
      const max = +group.dataset.max;
      group.addEventListener("change", (e) => {
        const checked = group.querySelectorAll("input:checked");
        if (checked.length > max) e.target.checked = false;
      });
    });
  }

  // Confirm dangerous buttons.
  function confirms() {
    document.querySelectorAll("button[data-confirm]").forEach((b) =>
      b.addEventListener("click", (e) => {
        if (!confirm(b.dataset.confirm)) e.preventDefault();
      })
    );
  }

  function editor(clipId) {
    const title = document.getElementById("title");
    const count = document.getElementById("title-count");
    const desc = document.getElementById("description");
    const tags = document.getElementById("tags");
    const box = document.getElementById("options");
    const note = document.querySelector("input[name=note]");
    const status = document.getElementById("suggest-note");
    if (title && count) title.addEventListener("input", () => (count.textContent = title.value.length));

    async function suggest(ai, btn) {
      btn.disabled = true;
      status.textContent = ai ? "Asking Claude… (can take up to a minute)" : "Thinking…";
      try {
        const res = await post(`/api/clip/${clipId}/suggest`, { ai: ai ? "1" : "0", note: note ? note.value : "" });
        status.textContent = res.source === "claude" ? "From Claude" : res.source.startsWith("offline (") ? res.source : "";
        box.replaceChildren();
        res.options.forEach((o) => {
          const el = document.createElement("button");
          el.type = "button";
          el.className = "option";
          const t = document.createElement("div");
          t.className = "t";
          t.textContent = o.title;
          const h = document.createElement("div");
          h.className = "h";
          h.textContent = o.hashtags.join(" ");
          el.append(t, h);
          el.addEventListener("click", () => {
            title.value = o.title;
            count.textContent = o.title.length;
            desc.value = o.description;
            if (o.tags) tags.value = o.tags.join(", ");
            box.querySelectorAll(".option").forEach((x) => (x.style.borderColor = ""));
            el.style.borderColor = "var(--accent)";
            if (o.style && o.style !== "ai") post("/api/style-pick", { style: o.style }).catch(() => {});
          });
          box.append(el);
        });
      } catch (e) {
        status.textContent = "Couldn't get suggestions.";
      } finally {
        btn.disabled = false;
      }
    }
    ["suggest", "suggest-ai"].forEach((id) => {
      const b = document.getElementById(id);
      if (b) b.addEventListener("click", () => suggest(b.dataset.ai === "1", b));
    });

    const up = document.getElementById("upload-status");
    if (up) {
      const tick = async () => {
        const s = await (await fetch("/api/uploader")).json();
        if (s.clip_id == clipId) {
          up.querySelector(".bar span").style.width = Math.round(s.progress * 100) + "%";
          setTimeout(tick, 1500);
        } else location.reload();
      };
      tick();
    }
  }

  function schedulePage() {
    const msg = document.getElementById("uploader-msg");
    const pct = document.getElementById("pct");
    let wasBusy = false;
    const tick = async () => {
      try {
        const s = await (await fetch("/api/uploader")).json();
        msg.textContent = s.message;
        if (pct && s.clip_id) pct.textContent = Math.round(s.progress * 100) + "%";
        if (wasBusy && !s.clip_id) return location.reload();
        wasBusy = !!s.clip_id;
      } catch (e) {}
      setTimeout(tick, 2000);
    };
    tick();
    const run = document.getElementById("run-now");
    if (run) run.addEventListener("click", () => post("/api/uploader/run").then(() => setTimeout(tick, 800)));
  }

  document.addEventListener("DOMContentLoaded", () => {
    pollScan();
    limitChecks();
    confirms();
  });
  window.ClipQueue = { editor, schedulePage };
})();
