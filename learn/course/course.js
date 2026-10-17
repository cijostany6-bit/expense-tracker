/* ══════════════════════════════════════════════════════════════════
   Expense Tracker — interactive course engine
   • renders the module map + progress on the landing page
   • renders the page pager on module pages
   • interactive sequence diagrams (step through a request)
   • hotspot architecture diagrams (click a service → its job)
   • quizzes with reveal + self-grade + progress saved in localStorage

   The engine is data-driven: to add a module, add one entry to MODULES
   and create its HTML file.  Everything else is automatic.
   ══════════════════════════════════════════════════════════════════ */
(function () {
  "use strict";

  /* ── the course map (single source of truth) ── */
  const MODULES = [
    { id:"m1",  n:1,  icon:"🏗️", title:"Architecture & the request lifecycle", desc:"The whole system on one page: components, the two request paths, and why serverless.", file:"module-01-architecture.html", soon:false },
    { id:"m2",  n:2,  icon:"🔐", title:"Cognito & the JWT", desc:"How sign-in works, what a JWT really is, and how API Gateway verifies it with no secret.", file:"module-02-cognito.html", soon:true },
    { id:"m3",  n:3,  icon:"🚪", title:"API Gateway (HTTP API)", desc:"The bouncer: routes, the JWT authorizer, AWS_PROXY, and HTTP vs REST API.", file:"module-03-api-gateway.html", soon:true },
    { id:"m4",  n:4,  icon:"⚡", title:"Lambda", desc:"Compute: events, cold starts, concurrency (the 503s we hit), and the execution role.", file:"module-04-lambda.html", soon:true },
    { id:"m5",  n:5,  icon:"🗄️", title:"DynamoDB", desc:"Single-table design, PK/SK, why the partition key is the tenant boundary.", file:"module-05-dynamodb.html", soon:true },
    { id:"m6",  n:6,  icon:"📦", title:"S3 & presigned URLs", desc:"Two buckets, private objects, and how a signed URL is really a permission slip.", file:"module-06-s3.html", soon:true },
    { id:"m7",  n:7,  icon:"🪪", title:"IAM", desc:"Trust policy vs permission policy, least privilege, and roles vs users.", file:"module-07-iam.html", soon:true },
    { id:"m8",  n:8,  icon:"🌐", title:"CloudFront", desc:"The HTTPS front door: caching, origins, and why S3 alone wasn't enough.", file:"module-08-cloudfront.html", soon:true },
    { id:"m9",  n:9,  icon:"🧭", title:"Route 53 + ACM", desc:"A real domain: hosted zones, NS delegation, alias records, and the us-east-1 rule.", file:"module-09-dns.html", soon:true },
    { id:"m10", n:10, icon:"🤖", title:"Bedrock & the OCR pipeline", desc:"Vision models, the Converse API, prompt design, and grounded extraction.", file:"module-10-bedrock.html", soon:true },
    { id:"m11", n:11, icon:"🔀", title:"Event-driven design", desc:"S3 events, decoupling, idempotency, and async failure handling.", file:"module-11-event-driven.html", soon:true },
    { id:"m12", n:12, icon:"🧾", title:"Infrastructure as Code", desc:"The whole stack as CloudFormation — parameters, conditions, dependencies.", file:"module-12-iac.html", soon:true },
    { id:"m13", n:13, icon:"🧪", title:"Testing & CI", desc:"36 offline tests with pytest + moto, and a green pipeline on every push.", file:"module-13-testing.html", soon:true },
    { id:"m14", n:14, icon:"🛡️", title:"Security & multi-tenancy", desc:"The threat model: authN vs authZ, IDOR, least privilege, and data residency.", file:"module-14-security.html", soon:true },
    { id:"m15", n:15, icon:"💸", title:"Cost & FinOps", desc:"Why this is ~free, the free-tier map, and where cost would grow.", file:"module-15-cost.html", soon:true },
    { id:"m16", n:16, icon:"📈", title:"Production gaps & scaling", desc:"What's missing for real production, and what breaks at 1000×.", file:"module-16-production.html", soon:true },
    { id:"m17", n:17, icon:"🔥", title:"War stories", desc:"The bugs and the mistakes — your best interview material.", file:"module-17-war-stories.html", soon:true },
    { id:"m18", n:18, icon:"🎤", title:"Mock interview", desc:"Talk through the project, then survive the follow-up questions.", file:"module-18-mock-interview.html", soon:true },
  ];

  /* ── tiny storage ── */
  const KEY = "et-course-v1";
  let store = {};
  try { store = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { store = {}; }
  const save = () => { try { localStorage.setItem(KEY, JSON.stringify(store)); } catch (e) {} };
  const mod = (id) => (store[id] = store[id] || {});
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]));

  /* ══════════════ landing page ══════════════ */
  function initLanding() {
    const grid = document.getElementById("modgrid");
    if (!grid) return;

    const live = MODULES.filter((m) => !m.soon);
    const done = live.filter((m) => mod(m.id).pct >= 1).length;

    grid.innerHTML = MODULES.map((m) => {
      const pct = Math.round((mod(m.id).pct || 0) * 100);
      const isDone = pct >= 100;
      const body = `
        <div class="num">${m.n}</div>
        <div class="body">
          <div class="t">${m.icon} ${esc(m.title)}</div>
          <div class="d">${esc(m.desc)}</div>
          <div class="minibar"><span style="width:${pct}%"></span></div>
        </div>
        <div class="tag">${m.soon ? "soon" : isDone ? "done" : "module"}</div>`;
      return m.soon
        ? `<div class="modcard soon">${body}</div>`
        : `<a class="modcard${isDone ? " done" : ""}" href="${m.file}">${body}</a>`;
    }).join("");

    const g = document.getElementById("gbar");
    if (g) g.style.width = (live.length ? (done / live.length) * 100 : 0) + "%";
    const gs = document.getElementById("gstat");
    if (gs) gs.textContent = `${done} / ${live.length} modules complete`;
  }

  /* ══════════════ module page ══════════════ */
  function initModule() {
    const id = document.body.dataset.module;
    if (!id) return;
    const idx = MODULES.findIndex((m) => m.id === id);
    const me = MODULES[idx];

    mod(id).visited = true;
    save();

    // title / crumb
    if (me) {
      document.title = `M${me.n} · ${me.title} — Expense Tracker course`;
      const t = document.getElementById("mtitle");
      if (t) t.textContent = me.title;
      const c = document.getElementById("mcrumb");
      if (c) c.textContent = `Module ${me.n} of ${MODULES.length}`;
    }

    // pager
    const prev = MODULES[idx - 1];
    const next = MODULES[idx + 1];
    const pager = document.getElementById("pager");
    if (pager) {
      const link = (m, cls, lbl) => (m && !m.soon)
        ? `<a class="${cls}" href="${m.file}"><span class="lbl">${lbl}</span>${m.icon} ${esc(m.title)}</a>`
        : `<a class="${cls} empty" href="#"></a>`;
      pager.innerHTML = link(prev, "prev", "← Previous") + link(next, "next", "Next →");
    }

    initQuizzes(id);
    initSequences();
    initDiagrams();
    updateTopProgress();
  }

  function updateTopProgress() {
    const bar = document.querySelector(".globar span");
    if (!bar) return;
    const live = MODULES.filter((m) => !m.soon);
    const done = live.filter((m) => mod(m.id).pct >= 1).length;
    bar.style.width = (live.length ? (done / live.length) * 100 : 0) + "%";
  }

  /* ══════════════ quizzes ══════════════ */
  function initQuizzes(moduleId) {
    document.querySelectorAll(".quiz").forEach((quiz) => {
      const qs = Array.from(quiz.querySelectorAll("li.q"));
      const scoreEl = quiz.querySelector(".score");
      const barEl = quiz.querySelector(".pbar span");

      const render = () => {
        const answers = mod(moduleId).quiz || {};
        let graded = 0, pts = 0;
        qs.forEach((q, i) => {
          const g = answers[i];
          q.classList.remove("got", "part", "miss", "graded");
          if (g) {
            graded++;
            q.classList.add("graded", g);
            pts += g === "got" ? 1 : g === "part" ? 0.5 : 0;
            q.querySelectorAll(".grade button").forEach((b) =>
              b.classList.toggle("on", b.dataset.g === g));
          }
        });
        if (scoreEl) scoreEl.textContent = `Graded ${graded} / ${qs.length} · Score ${pts} / ${qs.length}`;
        if (barEl) barEl.style.width = (qs.length ? (graded / qs.length) * 100 : 0) + "%";
        const m = mod(moduleId);
        m.pct = qs.length ? graded / qs.length : 0;
        save();
        updateTopProgress();
      };

      qs.forEach((q, i) => {
        const rev = q.querySelector(".reveal");
        const ans = q.querySelector(".answer");
        if (rev && ans) rev.addEventListener("click", () => {
          ans.classList.toggle("open");
          rev.textContent = ans.classList.contains("open") ? "Hide model answer" : "Reveal model answer";
        });
        q.querySelectorAll(".grade button").forEach((btn) =>
          btn.addEventListener("click", () => {
            const answers = mod(moduleId).quiz || (mod(moduleId).quiz = {});
            answers[i] = (answers[i] === btn.dataset.g) ? undefined : btn.dataset.g;
            if (!answers[i]) delete answers[i];
            save();
            render();
          }));
      });

      const reset = quiz.querySelector(".reset");
      if (reset) reset.addEventListener("click", () => {
        mod(moduleId).quiz = {};
        save();
        qs.forEach((q) => {
          q.querySelector(".answer")?.classList.remove("open");
          const rev = q.querySelector(".reveal");
          if (rev) rev.textContent = "Reveal model answer";
        });
        render();
      });

      render();
    });
  }

  /* ══════════════ interactive sequence diagrams ══════════════ */
  function initSequences() {
    document.querySelectorAll("figure.seq").forEach((fig) => {
      const holder = fig.querySelector('script[type="application/json"]');
      if (!holder) return;
      let spec;
      try { spec = JSON.parse(holder.textContent); } catch (e) { return; }

      const actors = spec.actors || [];
      const steps = spec.steps || [];
      const n = actors.length, colw = 176, pad = 80;
      const cx = (i) => pad + i * colw;              // lifeline x
      const width = pad * 2 + Math.max(n - 1, 1) * colw;
      const boxW = 138, boxH = 36, boxY = 12;
      const y0 = 104, rowH = 54;
      const height = y0 + steps.length * rowH + 8;
      const lineX = (i) => cx(i);

      let svg = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="sequence diagram">
        <defs>
          <marker id="ah" markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L7,3 L0,6 z" fill="#22d3ee"/></marker>
          <marker id="ahg" markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L7,3 L0,6 z" fill="#34d399"/></marker>
        </defs>`;

      // actor boxes + lifelines
      actors.forEach((a, i) => {
        svg += `<g class="actor">
          <rect x="${cx(i) - boxW / 2}" y="${boxY}" width="${boxW}" height="${boxH}" rx="10"/>
          <text x="${cx(i)}" y="${boxY + 23}" text-anchor="middle">${esc(a)}</text>
        </g>`;
        svg += `<line class="lifeline" x1="${cx(i)}" y1="${boxY + boxH}" x2="${cx(i)}" y2="${height - 12}"/>`;
      });

      // messages
      steps.forEach((s, i) => {
        const y = y0 + i * rowH;
        const cls = "mstep" + (s.ret ? " ret" : "");
        if (s.self) {
          const x = lineX(s.f);
          svg += `<g class="${cls}" data-i="${i}">
            <path d="M ${x} ${y - 8} h 48 v 18 h -46" marker-end="url(#${s.ret ? "ahg" : "ah"})"/>
            <text x="${x + 58}" y="${y + 4}" text-anchor="start">${esc(s.m)}</text>
          </g>`;
        } else {
          const x1 = lineX(s.f), x2 = lineX(s.t);
          const mid = (x1 + x2) / 2;
          svg += `<g class="${cls}" data-i="${i}">
            <line x1="${x1}" y1="${y}" x2="${x2}" y2="${y}" marker-end="url(#${s.ret ? "ahg" : "ah"})"/>
            <text x="${mid}" y="${y - 8}" text-anchor="middle">${esc(s.m)}</text>
          </g>`;
        }
      });
      svg += `</svg>`;

      const label = spec.actors ? "" : "";
      fig.insertAdjacentHTML("beforeend",
        `<div class="seq-svg">${svg}</div>
         <div class="seq-controls">
           <button class="prev" type="button">← Prev</button>
           <button class="next" type="button">Next →</button>
           <span class="counter"></span>
         </div>
         <div class="seq-note"></div>`);

      const groups = Array.from(fig.querySelectorAll(".mstep"));
      const counter = fig.querySelector(".counter");
      const note = fig.querySelector(".seq-note");
      const prevB = fig.querySelector(".prev");
      const nextB = fig.querySelector(".next");
      let cur = -1;

      const show = (i) => {
        cur = Math.max(-1, Math.min(steps.length - 1, i));
        groups.forEach((g, k) => {
          g.classList.toggle("active", k === cur);
          g.classList.toggle("dim", cur !== -1 && k !== cur);
        });
        const s = steps[cur];
        note.innerHTML = s ? `<b>Step ${cur + 1}/${steps.length}:</b> ${s.note || ""}` : `<b>Click “Next”</b> to walk through this request.`;
        counter.textContent = cur === -1 ? `0 / ${steps.length}` : `${cur + 1} / ${steps.length}`;
        prevB.disabled = cur <= -1;
        nextB.disabled = cur >= steps.length - 1;
      };

      prevB.addEventListener("click", () => show(cur - 1));
      nextB.addEventListener("click", () => show(cur + 1));
      groups.forEach((g) => g.addEventListener("click", () => show(Number(g.dataset.i))));
      show(spec.start === undefined ? -1 : spec.start);
      // auto-advance to step 1 on first view so the diagram is "one click in"
      if (cur === -1 && steps.length) { /* keep at 0-based start */ }
    });
  }

  /* ══════════════ hotspot diagrams ══════════════ */
  function initDiagrams() {
    document.querySelectorAll("figure.diagram").forEach((fig) => {
      const note = fig.querySelector(".diagram-note");
      fig.querySelectorAll(".hotspot").forEach((hs) => {
        hs.addEventListener("click", () => {
          fig.querySelectorAll(".hotspot").forEach((x) => x.classList.remove("on"));
          hs.classList.add("on");
          if (note) note.innerHTML = `<b>${esc(hs.dataset.name || "")}</b> ${hs.dataset.note || ""}`;
        });
      });
    });
  }

  /* ── exposed so the PDF/print builder can render diagrams on injected content ── */
  window.ETCourse = { render() { initSequences(); initDiagrams(); }, modules: MODULES };

  /* ── boot ── */
  const boot = () => { initLanding(); initModule(); };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
