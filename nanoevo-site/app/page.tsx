import Image from "next/image";

export default function Home() {
  return (
    <main>
      <nav className="nav" aria-label="主导航">
        <a className="brand" href="#top" aria-label="NanoEvo 首页">
          <span className="brand-mark" aria-hidden="true">N<span>E</span></span>
          <span>NanoEvo</span>
        </a>
        <div className="nav-links">
          <a href="#how">工作原理</a>
          <a href="#proof">产品界面</a>
          <a href="#safety">安全边界</a>
        </div>
        <a
          className="nav-cta"
          href="https://github.com/lovits/nanobot-evo"
          target="_blank"
          rel="noreferrer"
        >
          查看 GitHub <span aria-hidden="true">↗</span>
        </a>
      </nav>

      <section className="hero" id="top">
        <div className="hero-glow" aria-hidden="true" />
        <div className="eyebrow"><span className="pulse" /> Evidence-driven skill evolution</div>
        <h1>让 Skills 从真实工作中学习，<br /><em>但控制权始终在你手中。</em></h1>
        <p className="hero-copy">
          NanoEvo 是构建在 nanobot 之上的 Skill 演化控制层。它观察真实执行，
          将重复证据转化为聚焦的改进提案，并只在你批准后安全应用。
        </p>
        <div className="hero-actions">
          <a
            className="button button-primary"
            href="https://github.com/lovits/nanobot-evo"
            target="_blank"
            rel="noreferrer"
          >
            探索开源项目 <span aria-hidden="true">↗</span>
          </a>
          <a className="button button-ghost" href="#how">了解演化闭环 <span aria-hidden="true">↓</span></a>
        </div>
        <div className="hero-trust" aria-label="项目特性">
          <span><i>✓</i> Human approved</span>
          <span><i>✓</i> Patch only</span>
          <span><i>✓</i> Conflict safe</span>
          <span><i>✓</i> Fully reversible</span>
        </div>

        <div className="console-card" aria-label="NanoEvo 演化流程示意">
          <div className="console-top">
            <div className="console-dots" aria-hidden="true"><span /><span /><span /></div>
            <span>nanoevo / evolution trace</span>
            <span className="live"><i /> LIVE</span>
          </div>
          <div className="trace">
            <div className="trace-rail" aria-hidden="true"><span>01</span><span>02</span><span>03</span><span>04</span></div>
            <div className="trace-content">
              <div className="trace-row">
                <span className="trace-time">14:32:01</span>
                <span className="trace-tag cyan">OBSERVE</span>
                <span>Skill used successfully in a real task</span>
                <b className="ok">captured</b>
              </div>
              <div className="trace-row">
                <span className="trace-time">14:32:03</span>
                <span className="trace-tag violet">REVIEW</span>
                <span>Repeated friction found across evidence</span>
                <b className="ok">qualified</b>
              </div>
              <div className="trace-row selected">
                <span className="trace-time">14:32:04</span>
                <span className="trace-tag amber">PROPOSE</span>
                <span>Focused SKILL.md patch generated</span>
                <b className="pending">awaiting approval</b>
              </div>
              <div className="trace-row muted">
                <span className="trace-time">—</span>
                <span className="trace-tag green">APPLY</span>
                <span>Backup → atomic update → version history</span>
                <b>locked</b>
              </div>
            </div>
          </div>
          <div className="console-status">
            <span><i className="status-dot" /> MAIN TURN UNAFFECTED</span>
            <span>review failure isolation: ON</span>
          </div>
        </div>
      </section>

      <section className="manifesto">
        <p>不是让 Agent 随意重写自己。</p>
        <h2>是把“变得更好”变成一条<br /><em>可观察、可审查、可回滚</em>的工程路径。</h2>
      </section>

      <section className="section" id="how">
        <div className="section-heading">
          <div>
            <span className="section-index">01 / EVOLUTION LOOP</span>
            <h2>一条不打断主任务的<br />异步演化闭环</h2>
          </div>
          <p>正常回复照常完成。审查发生在回合之后，任何审查失败都不会影响用户已经得到的结果。</p>
        </div>

        <div className="loop-grid">
          <article className="loop-card">
            <span className="card-number">01</span>
            <div className="card-icon blue">◎</div>
            <h3>Observe</h3>
            <p>只记录真正成功使用过的 Workspace Skill，并生成脱敏的结构化轨迹。</p>
            <span className="card-meta">actual usage attribution</span>
          </article>
          <article className="loop-card">
            <span className="card-number">02</span>
            <div className="card-icon violet">⌁</div>
            <h3>Review</h3>
            <p>按 Skill 独立调度审查，从多次真实证据中寻找可复现的摩擦点。</p>
            <span className="card-meta">isolated review agent</span>
          </article>
          <article className="loop-card">
            <span className="card-number">03</span>
            <div className="card-icon amber">△</div>
            <h3>Propose</h3>
            <p>只产生聚焦的补丁提案；证据不足时，系统选择不修改。</p>
            <span className="card-meta">evidence-gated patch</span>
          </article>
          <article className="loop-card accent-card">
            <span className="card-number">04</span>
            <div className="card-icon green">✓</div>
            <h3>Approve & Apply</h3>
            <p>人工批准后才原子应用。冲突检测、备份和版本历史全程守护。</p>
            <span className="card-meta">human in the loop</span>
          </article>
        </div>
      </section>

      <section className="section product-section" id="proof">
        <div className="section-heading">
          <div>
            <span className="section-index">02 / CONTROL PLANE</span>
            <h2>证据、差异和决定，<br />都在一个视图里。</h2>
          </div>
          <p>演化管理直接集成在 WebUI 的 Settings → Skills 中，无需切换到另一个管理系统。</p>
        </div>

        <div className="product-frame">
          <div className="frame-bar">
            <div><span /><span /><span /></div>
            <span>Evolution management · proposal review</span>
            <span className="frame-secure">● LOCAL CONTROL</span>
          </div>
          <Image
            src="/evolution-diff.jpg"
            alt="NanoEvo Skill 演化管理界面，展示修改前后的差异与批准、拒绝操作"
            width={1280}
            height={720}
            sizes="(max-width: 1180px) 100vw, 1180px"
          />
        </div>
        <div className="product-points">
          <div><span>01</span><p><b>Evidence first</b>先看导致提案的真实轨迹，再决定是否接受。</p></div>
          <div><span>02</span><p><b>Diff before trust</b>精确查看 SKILL.md 每一处增删，不接受黑盒更新。</p></div>
          <div><span>03</span><p><b>Versioned control</b>比较历史版本、切换或恢复，所有改变都有来路。</p></div>
        </div>
      </section>

      <section className="section safety-section" id="safety">
        <div className="safety-copy">
          <span className="section-index">03 / BUILT-IN BOUNDARIES</span>
          <h2>演化能力越强，<br />边界越要清晰。</h2>
          <p>
            NanoEvo 改进的是显式的 Skill 操作知识，不训练模型参数，也不允许自由修改程序代码。
            Workspace Skills 可以演化；内置 Skills 永久受保护。
          </p>
          <a href="https://github.com/lovits/nanobot-evo" target="_blank" rel="noreferrer">
            在源码中查看设计边界 <span aria-hidden="true">↗</span>
          </a>
        </div>
        <div className="boundary-list">
          <article>
            <span className="boundary-icon">⌾</span>
            <div><h3>Human approval by default</h3><p>没有自动批准。每个提案都停留在待审状态，直到你明确决定。</p></div>
          </article>
          <article>
            <span className="boundary-icon">#</span>
            <div><h3>Base hash conflict detection</h3><p>如果底层 Skill 已变化，旧提案不会覆盖新内容。</p></div>
          </article>
          <article>
            <span className="boundary-icon">↶</span>
            <div><h3>Backup & atomic restore</h3><p>每次应用都先备份；更新原子完成，历史版本可以恢复。</p></div>
          </article>
          <article>
            <span className="boundary-icon">◇</span>
            <div><h3>Default-off compatibility</h3><p>关闭时不增加 Hook、模型调用或存储副作用，保持 nanobot 原有路径。</p></div>
          </article>
        </div>
      </section>

      <section className="evidence-section">
        <div className="evidence-kicker">A measured result, not a marketing promise</div>
        <div className="evidence-grid">
          <div>
            <span className="metric">+15.6<small>pp</small></span>
            <p>单个受控 held-out 案例中的路径引用准确率：77.8% → 93.3%</p>
          </div>
          <div className="evidence-note">
            <h3>我们也公开代价。</h3>
            <p>
              同一次实验中，required-info recall 从 100% 降至 83.3%，工具调用和 token 消耗也上升。
              这证明闭环可以工作——不是承诺每一次演化都必然更好。
            </p>
            <span>single model · single sample · real API · documented trade-offs</span>
          </div>
        </div>
      </section>

      <section className="cta-section">
        <div className="cta-orbit" aria-hidden="true"><span /><span /><span /></div>
        <span className="section-index">OPEN SOURCE · BUILT ON NANOBOT</span>
        <h2>把自我改进，从一句口号<br />变成可审计的系统能力。</h2>
        <p>阅读设计、检查实现，或把 NanoEvo 带进你的 nanobot 工作流。</p>
        <a
          className="button button-light"
          href="https://github.com/lovits/nanobot-evo"
          target="_blank"
          rel="noreferrer"
        >
          GitHub 上查看 NanoEvo <span aria-hidden="true">↗</span>
        </a>
      </section>

      <footer>
        <a className="brand footer-brand" href="#top">
          <span className="brand-mark" aria-hidden="true">N<span>E</span></span>
          <span>NanoEvo</span>
        </a>
        <p>Evidence-driven Skill evolution for nanobot.</p>
        <div>
          <a href="https://github.com/lovits/nanobot-evo" target="_blank" rel="noreferrer">GitHub ↗</a>
          <a href="https://github.com/HKUDS/nanobot" target="_blank" rel="noreferrer">nanobot ↗</a>
        </div>
      </footer>
    </main>
  );
}
