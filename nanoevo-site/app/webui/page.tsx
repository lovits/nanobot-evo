import type { Metadata } from "next";
import Link from "next/link";
import "./webui.css";

export const metadata: Metadata = {
  title: "NanoEvo WebUI Demo",
  description:
    "A read-only public demonstration of NanoEvo Skill evolution management in the nanobot WebUI.",
};

const skills = [
  { name: "chinese-writing-polish", meta: "1 proposal pending", state: "pending" },
  { name: "repo-analysis", meta: "Collecting 0/5", state: "evolvable" },
  { name: "writing-polish", meta: "Collecting 0/5", state: "evolvable" },
  { name: "clawhub", meta: "Built-in · protected", state: "protected" },
  { name: "cron", meta: "Built-in · protected", state: "protected" },
  { name: "github", meta: "Built-in · protected", state: "protected" },
  { name: "image-generation", meta: "Built-in · protected", state: "protected" },
  { name: "memory", meta: "Built-in · protected", state: "protected" },
];

const gates = [
  { label: "1 / 2 independent turns", pass: false },
  { label: "Project independence is not required for these traces", pass: true },
  { label: "Explicit user feedback exception is recorded", pass: true },
  { label: "Deterministic evidence policy is satisfied", pass: true },
];

function RailIcon({ children }: { children: React.ReactNode }) {
  return <span className="rail-icon" aria-hidden="true">{children}</span>;
}

export default function WebUIDemo() {
  return (
    <main className="webui-demo">
      <header className="demo-banner">
        <div>
          <span className="demo-live"><i /> PUBLIC DEMO</span>
          <p>只读展示，不连接你的本地 Gateway、对话、密钥或工作区数据。</p>
        </div>
        <Link href="/">返回 NanoEvo 官网 <span aria-hidden="true">↗</span></Link>
      </header>

      <div className="app-shell">
        <aside className="app-rail" aria-label="WebUI navigation preview">
          <div className="app-logo">n</div>
          <nav>
            <a href="#workspace"><RailIcon>⌁</RailIcon><span>New thread</span></a>
            <a href="#workspace"><RailIcon>⌕</RailIcon><span>Search</span></a>
            <a href="#workspace"><RailIcon>◫</RailIcon><span>Files</span></a>
            <a href="#workspace"><RailIcon>◷</RailIcon><span>Automations</span></a>
          </nav>
          <div className="rail-section">
            <span>RECENT</span>
            <a href="#workspace" className="recent-thread">NanoEvo evidence review</a>
            <a href="#workspace" className="recent-thread">Skill quality experiment</a>
          </div>
          <a className="settings-link" href="#workspace"><RailIcon>⚙</RailIcon><span>Settings</span></a>
        </aside>

        <section className="settings-canvas" id="workspace">
          <header className="settings-header">
            <div>
              <p>Settings / Skills</p>
              <h1>Skills</h1>
            </div>
            <div className="header-actions">
              <span className="gateway-state"><i /> Gateway connected</span>
              <button type="button" aria-disabled="true">Install Skill</button>
            </div>
          </header>

          <div className="settings-grid">
            <nav className="settings-nav" aria-label="Settings sections">
              <a href="#workspace">General</a>
              <a href="#workspace">Models</a>
              <a href="#workspace">Channels</a>
              <a href="#workspace" className="active">Skills</a>
              <a href="#workspace">Tools & MCP</a>
              <a href="#workspace">Security</a>
            </nav>

            <section className="catalog-preview">
              <div className="catalog-heading">
                <div>
                  <h2>Workspace Skills</h2>
                  <p>Reusable operating knowledge available to your agent.</p>
                </div>
                <span className="runtime-pill"><i /> Evolution active</span>
              </div>
              <div className="catalog-card">
                <div className="catalog-row selected">
                  <div className="skill-glyph">技</div>
                  <div><b>chinese-writing-polish</b><span>Professional Chinese writing refinement</span></div>
                  <em>Pending review</em>
                </div>
                <div className="catalog-row">
                  <div className="skill-glyph">代</div>
                  <div><b>repo-analysis</b><span>Repository structure and code reasoning</span></div>
                  <em className="neutral">Evolvable</em>
                </div>
                <div className="catalog-row">
                  <div className="skill-glyph">写</div>
                  <div><b>writing-polish</b><span>Clear, concise professional prose</span></div>
                  <em className="neutral">Evolvable</em>
                </div>
              </div>
              <div className="catalog-info">
                <span>Evolution management</span>
                <p>Review evidence, inspect proposed changes, and control every applied version.</p>
                <button type="button" aria-disabled="true">Open management</button>
              </div>
            </section>
          </div>
        </section>

        <section className="evolution-sheet" aria-label="Skill evolution management preview">
          <header className="sheet-heading">
            <div className="sheet-icon">⌬</div>
            <div>
              <span className="sheet-overline">NANOEVO CONTROL PLANE</span>
              <h2>Skill evolution management</h2>
              <p>Improve existing Workspace Skills from redacted execution evidence.</p>
            </div>
            <span className="sheet-close" aria-hidden="true">×</span>
          </header>

          <section className="config-strip">
            <div><span>Review schedule</span><b>5 / 10 / 20 / 100</b></div>
            <div><span>Current threshold</span><b>10 trajectories</b></div>
            <div><span>Runtime policy</span><b>Human approval</b></div>
            <button type="button" aria-disabled="true">▣ Save configuration</button>
          </section>

          <div className="stats-row">
            <div><span>Evolvable</span><b>3</b></div>
            <div><span>Protected</span><b>11</b></div>
            <div><span>Pending</span><b className="pending-number">1</b></div>
          </div>

          <div className="evolution-workspace">
            <aside className="skill-list">
              <div className="skill-filters"><span className="active">All</span><span>Evolvable</span><span>Pending</span></div>
              {skills.map((skill) => (
                <article className={skill.name === "chinese-writing-polish" ? "active" : ""} key={skill.name}>
                  <span className={`skill-state-icon ${skill.state}`}>{skill.state === "protected" ? "▣" : "⌬"}</span>
                  <div><b>{skill.name}</b><small>{skill.meta}</small></div>
                </article>
              ))}
            </aside>

            <section className="proposal-panel">
              <header className="proposal-heading">
                <div>
                  <h3>chinese-writing-polish</h3>
                  <p>专业的中文写作润色工具，优化表达、修正语法、提升文采。</p>
                </div>
                <span>Pending review</span>
              </header>

              <nav className="proposal-tabs" aria-label="Evolution detail tabs">
                <a href="#overview">Overview</a>
                <a href="#proposal" className="active">Proposal 1</a>
                <a href="#versions">Versions 3</a>
              </nav>

              <section className="proposal-copy" id="proposal">
                <h4>Why this change</h4>
                <p>
                  Repeated evidence shows duplicate “准确性” guidance and overlapping wording.
                  The proposed replacement removes semantic confusion while keeping the original
                  quality intent intact.
                </p>
              </section>

              <section className="gate-section">
                <h4>Evidence gates</h4>
                {gates.map((gate) => (
                  <div key={gate.label} className={gate.pass ? "pass" : "waiting"}>
                    <i>{gate.pass ? "✓" : "!"}</i><span>{gate.label}</span>
                  </div>
                ))}
              </section>

              <section className="diff-section">
                <h4>Local text replacement</h4>
                <div className="diff-block remove">
                  <span>− Before</span>
                  <pre>{`## 润色维度

1. **准确性** — 修正错别字、语法错误
2. **流畅性** — 优化句子连接
3. **准确性** — 用词更贴切
4. **风格统一** — 保持整体风格一致`}</pre>
                </div>
                <div className="diff-block add">
                  <span>+ After</span>
                  <pre>{`## 润色维度

1. **准确性** — 修正错别字、语法错误
2. **流畅性** — 优化句子连接
3. **用词精准** — 用词更贴切、符合语境
4. **风格统一** — 保持整体风格一致`}</pre>
                </div>
              </section>

              <div className="decision-bar">
                <p><i /> Base hash verified · backup ready</p>
                <div><button className="reject" type="button" aria-disabled="true">Reject</button><button type="button" aria-disabled="true">Approve and apply</button></div>
              </div>
            </section>
          </div>
        </section>
      </div>
    </main>
  );
}
