<script setup>
// Public landing page — what a signed-out visitor sees at `/`. Signed-in users
// are redirected to `/learn` by the router guard, and App.vue hides its own
// header/width constraint for this route so the sections run full-bleed.
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import logoUrl from '../assets/mentisq-logo.png'

// In-page nav with scroll-spy: the active link tracks whichever section is in
// view, and clicking one smooth-scrolls to it (no hash pushed to the URL).
const navLinks = [
  { id: 'features', label: 'Features' },
  { id: 'how', label: 'How it works' },
  { id: 'tutor', label: 'AI tutor' },
  { id: 'about', label: 'About' },
]
const activeSection = ref('')
let observer = null

function goTo(id) {
  activeSection.value = id
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

// The last section is the footer, which sits flush at the page bottom and may
// never reach the observer's band — highlight it once we're scrolled all the way.
function syncBottomEdge() {
  const atBottom =
    window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4
  if (atBottom) activeSection.value = navLinks[navLinks.length - 1].id
}

onMounted(() => {
  const sections = navLinks.map((l) => document.getElementById(l.id)).filter(Boolean)
  observer = new IntersectionObserver(
    (entries) => {
      const inView = entries
        .filter((e) => e.isIntersecting)
        .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
      if (inView.length) activeSection.value = inView[0].target.id
    },
    { rootMargin: '-15% 0px -80% 0px', threshold: 0 },
  )
  sections.forEach((s) => observer.observe(s))
  window.addEventListener('scroll', syncBottomEdge, { passive: true })
  syncBottomEdge()
})

onBeforeUnmount(() => {
  observer?.disconnect()
  window.removeEventListener('scroll', syncBottomEdge)
})
</script>

<template>
  <div class="landing">
    <!-- ============ HEADER ============ -->
    <header class="site-header">
      <div class="wrap">
        <RouterLink to="/" class="brand-pill" aria-label="mentisQ home">
          <img :src="logoUrl" alt="mentisQ" />
        </RouterLink>
        <nav class="site-nav">
          <a
            v-for="link in navLinks"
            :key="link.id"
            class="plain"
            :class="{ 'is-active': activeSection === link.id }"
            :href="`#${link.id}`"
            @click.prevent="goTo(link.id)"
          >{{ link.label }}</a>
          <RouterLink class="btn btn-on-dark-ghost" to="/login">Log in</RouterLink>
          <RouterLink class="btn btn-on-dark" to="/register">Register</RouterLink>
        </nav>
      </div>
    </header>

    <!-- ============ HERO ============ -->
    <section class="hero">
      <div class="wrap">
        <div>
          <p class="eyebrow">NSW high-school mathematics</p>
          <h1>Learn maths the <span class="hl">structured</span> way — with a tutor that never hands you the answer.</h1>
          <p class="lede">
            Guided lessons and animations, auto-graded practice, timed quizzes, and
            mentisQ — an AI tutor that walks you to the answer step by step.
          </p>
          <div class="hero-cta">
            <RouterLink class="btn btn-primary" to="/register">Start learning free</RouterLink>
            <RouterLink class="btn btn-ghost" to="/login">Log in</RouterLink>
          </div>
          <p class="hero-meta">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>
            Aligned to the NSW curriculum · Free while in pilot
          </p>
        </div>

        <div class="stage">
          <!-- Lesson / practice card -->
          <div class="card lesson-card">
            <span class="tab">Year 7 · Fractions · Practice</span>
            <h3>Which fraction is equivalent to
              <span class="frac"><span>2</span><span>3</span></span>?
            </h3>
            <div class="opts">
              <div class="opt"><span class="key">A</span><span class="frac"><span>3</span><span>4</span></span></div>
              <div class="opt correct">
                <span class="key">B</span>
                <span class="frac"><span>6</span><span>9</span></span>
                <span class="tick">Correct</span>
              </div>
              <div class="opt"><span class="key">C</span><span class="frac"><span>4</span><span>5</span></span></div>
            </div>
          </div>

          <!-- Tutor chat overlay -->
          <div class="card chat-card">
            <div class="who"><span class="dot">Q</span> mentisQ</div>
            <div class="bubble them">What do you have to do to the top and bottom of a fraction to keep it equivalent?</div>
            <div class="bubble you">multiply both by 3<span class="step-ok">✓ step checked · 2/3 = 6/9</span></div>
            <div class="bubble them">Exactly. So which option matches?</div>
          </div>
        </div>
      </div>
    </section>

    <!-- ============ TRUST STRIP ============ -->
    <div class="trust">
      <div class="wrap">
        <span><b>Year 7 Mathematics</b> live now</span>
        <span class="sep"></span>
        <span>Lessons · Animations · Practice</span>
        <span class="sep"></span>
        <span>Auto-graded: MCQ, numeric &amp; algebra</span>
        <span class="sep"></span>
        <span>More year levels rolling out</span>
      </div>
    </div>

    <!-- ============ FEATURES ============ -->
    <section class="block features" id="features">
      <div class="wrap">
        <div class="section-head center">
          <p class="eyebrow">Everything in one place</p>
          <h2>A full study loop, not just a question bank</h2>
          <p>Each topic gives you something to learn from, something to practise with, and someone to ask when you're stuck.</p>
        </div>

        <div class="feature-grid">
          <article class="feature">
            <div class="ico" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5h16M4 5v14M4 5 2 7m18-2 2 2M8 9h8M8 13h6"/></svg></div>
            <h3>Structured courses</h3>
            <p>Year → Subject → Unit → Topic, with prerequisites mapped. Work through it in order, or jump to what you need.</p>
          </article>

          <article class="feature">
            <div class="ico" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m10 8 6 4-6 4V8Z"/><rect x="3" y="4" width="18" height="16" rx="2"/></svg></div>
            <h3>Lessons &amp; animations</h3>
            <p>Clear written lessons with properly typeset maths, plus short explainer animations with captions and transcripts.</p>
          </article>

          <article class="feature">
            <div class="ico" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg></div>
            <h3>Auto-graded practice</h3>
            <p>Multiple choice, numeric, multi-part and algebra questions. Algebra is checked for real equivalence — not string matching.</p>
          </article>

          <article class="feature">
            <div class="ico" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3a7 7 0 0 1 7 7c0 2.5-1.5 4-2.5 5S15 24 15 24H9s.5-3-1.5-5S5 12.5 5 10a7 7 0 0 1 7-7Z"/><path d="M9 24h6"/></svg></div>
            <h3>mentisQ AI tutor</h3>
            <p>A guided conversation that names your wrong step, checks your working, and stays strictly on maths.</p>
          </article>

          <article class="feature">
            <div class="ico" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="13" r="8"/><path d="M12 13V9M12 3h0M9 3h6M18 6l1.5-1.5"/></svg></div>
            <h3>Timed quizzes</h3>
            <p>Sit a whole unit against the clock. The countdown is server-side, so closing the tab still gives you a full review.</p>
          </article>

          <article class="feature">
            <div class="ico" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="M7 14l3-4 3 3 5-7"/></svg></div>
            <h3>Mixed adaptive practice</h3>
            <p>A spaced mix across a unit or year, weighted toward the skills your history says you're weakest on.</p>
          </article>
        </div>
      </div>
    </section>

    <!-- ============ HOW IT WORKS ============ -->
    <section class="block" id="how">
      <div class="wrap">
        <div class="section-head">
          <p class="eyebrow">How it works</p>
          <h2>Learn it, practise it, get unstuck</h2>
        </div>
        <div class="steps">
          <div class="step">
            <h3>Learn the topic</h3>
            <p>Read the lesson and watch the animation. Every symbol is typeset properly, so it reads like a textbook, not a chat log.</p>
          </div>
          <div class="step">
            <h3>Practise until it sticks</h3>
            <p>Work the topic's questions, then a mixed or timed set. Instant marking, worked solutions when you've had a genuine go.</p>
          </div>
          <div class="step">
            <h3>Ask mentisQ when stuck</h3>
            <p>Open the tutor from any question. It nudges you forward one step at a time — and only shows the full solution if you ask.</p>
          </div>
        </div>
      </div>
    </section>

    <!-- ============ TUTOR SPOTLIGHT ============ -->
    <section class="block spotlight" id="tutor">
      <div class="wrap">
        <div>
          <p class="eyebrow">Meet mentisQ</p>
          <h2>A tutor that makes you do the thinking</h2>
          <p class="spotlight-lede">
            mentisQ is built to teach, not to answer. It knows the question you're on
            and the correct solution — and deliberately won't just read it out.
          </p>
          <ul class="checklist">
            <li><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg><span><b>No answer on the first reply.</b> It asks a question back and gets you moving.</span></li>
            <li><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg><span><b>It checks your algebra.</b> Paste your working and it verifies each step, flagging the exact line that breaks.</span></li>
            <li><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg><span><b>It stays on maths.</b> No essay help, no off-topic detours.</span></li>
            <li><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg><span><b>Full worked solution on request</b> — once you've actually tried.</span></li>
          </ul>
        </div>

        <div class="card transcript">
          <div class="who"><span class="dot">Q</span> mentisQ · Solving 3x + 5 = 20</div>
          <div class="bubble them">Where would you start to get <em>x</em> on its own?</div>
          <div class="bubble you">3x + 5 = 20<br/>3x = 25</div>
          <div class="bubble them">Careful — check that line. What did you do to both sides, and does 20 − 5 give 25?</div>
          <div class="bubble you">oops. 3x = 15, so x = 5</div>
          <div class="bubble them">That's it. Both steps check out. Want to try the next one yourself?</div>
          <p class="muted">Working verified step by step with a computer-algebra check</p>
        </div>
      </div>
    </section>

    <!-- ============ PROGRESS SPOTLIGHT ============ -->
    <section class="block" id="progress">
      <div class="wrap spotlight-wrap">
        <div class="card progress-vis">
          <h3>Your mastery · Year 7 Number</h3>
          <div class="mastery-row">
            <div class="lab"><span>Equivalent fractions</span><span class="val">88%</span></div>
            <div class="bar"><span style="width: 88%"></span></div>
            <span class="trend"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 17 10 11l4 4 6-7"/></svg> improving</span>
          </div>
          <div class="mastery-row">
            <div class="lab"><span>Adding &amp; subtracting fractions</span><span class="val">64%</span></div>
            <div class="bar"><span style="width: 64%"></span></div>
            <span class="trend"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/></svg> holding steady</span>
          </div>
          <div class="mastery-row">
            <div class="lab"><span>Percentages</span><span class="val">41%</span></div>
            <div class="bar"><span style="width: 41%"></span></div>
            <span class="trend"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7 10 13l4-4 6 7"/></svg> needs work — next in your mix</span>
          </div>
        </div>

        <div>
          <p class="eyebrow">Progress you can see</p>
          <h2>Know exactly where you stand</h2>
          <p class="spotlight-lede">
            Every attempt feeds a mastery score for each topic and each underlying
            skill, weighted so recent work counts most. You see what's solid, what's
            slipping, and what practice to do next — and mixed practice targets the
            gaps automatically.
          </p>
        </div>
      </div>
    </section>

    <!-- ============ CTA BAND ============ -->
    <section class="block cta-band">
      <div class="wrap">
        <h2>Start with Year 7 Mathematics today</h2>
        <p>Create a free account and work through your first topic — lesson, practice, and the tutor included.</p>
        <div class="hero-cta">
          <RouterLink class="btn btn-on-dark" to="/register">Create free account</RouterLink>
          <RouterLink class="btn btn-on-dark-ghost" to="/login">Log in</RouterLink>
        </div>
      </div>
    </section>

    <!-- ============ FOOTER ============ -->
    <footer class="site-footer" id="about">
      <div class="wrap">
        <img :src="logoUrl" alt="mentisQ" />
        <nav>
          <a href="#features">Features</a>
          <a href="#how">How it works</a>
          <a href="#tutor">AI tutor</a>
          <RouterLink to="/login">Log in</RouterLink>
          <RouterLink to="/register">Register</RouterLink>
        </nav>
        <span>© 2026 mentisQ · Structured NSW high-school maths</span>
      </div>
    </footer>
  </div>
</template>

<style scoped>
/* Landing-page-only tokens layered on the global design system (web/src/style.css
   already defines --color-bg / surface / accent / primary / text / header). */
.landing {
  --white: #fff;
  --color-text-muted: color-mix(in srgb, var(--color-text) 66%, transparent);
  --shadow-sm: 0 1px 4px rgba(12, 58, 61, 0.12);
  --shadow-md: 0 12px 32px -12px rgba(12, 58, 61, 0.28);
  --shadow-lg: 0 28px 64px -24px rgba(12, 58, 61, 0.35);
  --radius: 14px;
  --content-max: 1120px;
  --gutter: clamp(1rem, 5vw, 2.5rem);

  line-height: 1.6;
  color: var(--color-text);
  background: var(--color-bg);
  -webkit-font-smoothing: antialiased;
}

.landing img { max-width: 100%; display: block; }
.landing h1,
.landing h2,
.landing h3 { line-height: 1.15; margin: 0; }

.wrap {
  max-width: var(--content-max);
  margin: 0 auto;
  padding-inline: var(--gutter);
}

.eyebrow {
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-size: 0.78rem;
  font-weight: 700;
  color: var(--color-primary);
  margin: 0 0 0.75rem;
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.72rem 1.35rem;
  border-radius: 6px; /* match the app's global .btn (web/src/style.css) */
  border: 1px solid transparent;
  font: inherit;
  font-weight: 600;
  text-decoration: none;
  cursor: pointer;
  transition: transform 0.12s ease, box-shadow 0.12s ease, background 0.12s ease;
}
.btn:hover { transform: translateY(-1px); }
.btn-primary { background: var(--color-primary); color: var(--white); box-shadow: var(--shadow-sm); }
.btn-primary:hover { box-shadow: var(--shadow-md); }
.btn-ghost { background: transparent; color: var(--color-primary); border-color: var(--color-accent); }
.btn-ghost:hover { background: var(--color-surface); }
.btn-on-dark { background: var(--white); color: var(--color-primary); }
.btn-on-dark-ghost { background: transparent; color: var(--white); border-color: rgba(255, 255, 255, 0.6); }
.btn-on-dark-ghost:hover { background: rgba(255, 255, 255, 0.12); }

/* ---------- Header ---------- */
.site-header {
  position: sticky;
  top: 0;
  z-index: 20;
  background: var(--color-header);
  box-shadow: 0 1px 4px rgba(12, 58, 61, 0.18);
}
.site-header .wrap {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  padding-block: 0.7rem;
}
.brand-pill {
  display: flex;
  align-items: center;
}
.brand-pill img { height: 32px; width: auto; display: block; }
.site-nav {
  display: flex;
  gap: 1.4rem;
  margin-left: auto;
  align-items: center;
}
.site-nav a {
  color: var(--white);
  text-decoration: none;
  font-weight: 500;
  font-size: 0.95rem;
}
.site-nav a.plain:hover { color: rgba(255, 255, 255, 0.82); }
/* Underline the link being interacted with, the one whose section is in view
   (scroll-spy), or whose route is active — matches the app header's treatment. */
.site-nav a:active,
.site-nav a:focus-visible,
.site-nav a.is-active,
.site-nav a.router-link-active { text-decoration: underline; }
.site-nav .btn { padding: 0.5rem 1.1rem; font-size: 0.92rem; }
/* Beat the `.site-nav a { color: #fff }` rule so the button label shows. */
.site-nav a.btn-on-dark { color: var(--color-primary); }
/* On narrow screens drop the section links but keep both account actions. */
@media (max-width: 860px) {
  .site-nav a.plain { display: none; }
}

/* ---------- Hero ---------- */
.hero {
  background:
    radial-gradient(1100px 460px at 82% -8%, var(--color-accent), transparent 62%),
    linear-gradient(180deg, var(--color-surface), var(--color-bg) 78%);
  padding-block: clamp(3rem, 8vw, 5.5rem) clamp(3rem, 7vw, 5rem);
  border-bottom: 1px solid var(--color-accent);
}
.hero .wrap {
  display: grid;
  grid-template-columns: 1.05fr 0.95fr;
  gap: clamp(2rem, 5vw, 4rem);
  align-items: center;
}
.hero h1 {
  font-size: clamp(2.1rem, 4.6vw, 3.3rem);
  letter-spacing: -0.02em;
  margin-bottom: 1.1rem;
}
.hero h1 .hl {
  color: var(--color-primary);
  background: linear-gradient(180deg, transparent 62%, var(--color-accent) 62%);
  padding-inline: 0.1em;
}
.hero p.lede {
  font-size: 1.15rem;
  color: var(--color-text-muted);
  max-width: 34ch;
  margin: 0 0 1.8rem;
}
.hero-cta { display: flex; gap: 0.8rem; flex-wrap: wrap; }
.hero-meta {
  margin-top: 1.6rem;
  font-size: 0.9rem;
  color: var(--color-text-muted);
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.hero-meta svg { width: 18px; height: 18px; flex: none; }

@media (max-width: 880px) {
  .hero .wrap { grid-template-columns: 1fr; }
  .hero p.lede { max-width: none; }
}

/* ---------- Hero visual: lesson card + tutor chat ---------- */
.stage { position: relative; }
.card {
  background: var(--white);
  border: 1px solid var(--color-accent);
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
}
.lesson-card { padding: 1.15rem 1.25rem 1.35rem; }
.lesson-card .tab {
  display: inline-block;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-primary);
  background: var(--color-surface);
  padding: 0.25rem 0.6rem;
  border-radius: 999px;
}
.lesson-card h3 { font-size: 1.06rem; margin: 0.7rem 0 0.5rem; }
.lesson-card .q { font-size: 0.96rem; margin: 0 0 0.85rem; }
.frac {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  vertical-align: middle;
  margin: 0 0.2em;
  font-size: 0.86em;
  line-height: 1.15;
}
.frac span:first-child {
  border-bottom: 1.5px solid currentColor;
  padding: 0 0.35em 0.05em;
}
.frac span:last-child { padding-top: 0.05em; }
.opts { display: grid; gap: 0.5rem; }
.opt {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  padding: 0.6rem 0.8rem;
  border: 1px solid var(--color-accent);
  border-radius: 10px;
  font-size: 0.92rem;
}
.opt .key {
  width: 1.5rem; height: 1.5rem; flex: none;
  display: grid; place-items: center;
  border-radius: 6px;
  background: var(--color-surface);
  font-weight: 700; font-size: 0.8rem;
}
.opt.correct { border-color: var(--color-primary); background: var(--color-surface); }
.opt.correct .key { background: var(--color-primary); color: var(--white); }
.opt.correct .tick { margin-left: auto; color: var(--color-primary); font-weight: 700; }

.chat-card {
  position: absolute;
  right: clamp(-0.5rem, -2vw, -2.5rem);
  bottom: -2.4rem;
  width: min(78%, 320px);
  padding: 0.95rem 1rem 1.05rem;
}
.chat-card .who {
  display: flex; align-items: center; gap: 0.5rem;
  font-weight: 700; font-size: 0.82rem; color: var(--color-primary);
  margin-bottom: 0.6rem;
}
.chat-card .who .dot {
  width: 1.4rem; height: 1.4rem; border-radius: 50%;
  background: var(--color-primary); color: var(--white);
  display: grid; place-items: center; font-size: 0.72rem; font-weight: 800;
}
.bubble {
  font-size: 0.85rem;
  padding: 0.55rem 0.75rem;
  border-radius: 12px;
  margin-bottom: 0.45rem;
}
.bubble.them { background: var(--color-surface); border-bottom-left-radius: 4px; }
.bubble.you {
  background: var(--color-primary); color: var(--white);
  border-bottom-right-radius: 4px; margin-left: auto; max-width: 82%;
}
.bubble .step-ok { display: block; margin-top: 0.3rem; font-size: 0.78rem; color: var(--color-primary); font-weight: 700; }

@media (max-width: 460px) {
  .chat-card { position: static; width: 100%; margin-top: 1.2rem; }
}

/* ---------- Trust strip ---------- */
.trust {
  padding-block: 1.4rem;
  border-bottom: 1px solid var(--color-accent);
  background: var(--color-bg);
}
.trust .wrap {
  display: flex; flex-wrap: wrap; gap: 0.7rem 2rem;
  align-items: center; justify-content: center;
  font-size: 0.9rem; color: var(--color-text-muted);
}
.trust b { color: var(--color-text); font-weight: 700; }
.trust .sep { width: 5px; height: 5px; border-radius: 50%; background: var(--color-accent); }

/* ---------- Section scaffolding ---------- */
section.block { padding-block: clamp(3.2rem, 8vw, 5.5rem); }
/* Clear the sticky header when a nav link scrolls a section into view. */
section.block[id],
.site-footer[id] { scroll-margin-top: 72px; }
.section-head { max-width: 640px; margin-bottom: 2.6rem; }
.section-head.center { margin-inline: auto; text-align: center; }
.section-head h2 { font-size: clamp(1.7rem, 3.4vw, 2.3rem); letter-spacing: -0.015em; }
.section-head p { color: var(--color-text-muted); font-size: 1.05rem; margin: 0.7rem 0 0; }

/* ---------- Feature grid ---------- */
.features { background: var(--color-surface); }
.feature-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1.1rem;
}
@media (max-width: 900px) { .feature-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 600px) { .feature-grid { grid-template-columns: 1fr; } }
.feature {
  background: var(--white);
  border: 1px solid var(--color-accent);
  border-radius: var(--radius);
  padding: 1.5rem 1.4rem;
  box-shadow: var(--shadow-sm);
}
.feature .ico {
  width: 2.6rem; height: 2.6rem;
  display: grid; place-items: center;
  border-radius: 12px;
  background: var(--color-surface);
  color: var(--color-primary);
  margin-bottom: 1rem;
}
.feature .ico svg { width: 1.4rem; height: 1.4rem; }
.feature h3 { font-size: 1.08rem; margin-bottom: 0.45rem; }
.feature p { margin: 0; font-size: 0.94rem; color: var(--color-text-muted); }

/* ---------- How it works ---------- */
.steps { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.5rem; counter-reset: step; }
@media (max-width: 780px) { .steps { grid-template-columns: 1fr; } }
.step { position: relative; padding-top: 3.2rem; }
.step::before {
  counter-increment: step;
  content: counter(step);
  position: absolute; top: 0; left: 0;
  width: 2.4rem; height: 2.4rem;
  display: grid; place-items: center;
  border-radius: 50%;
  background: var(--color-primary); color: var(--white);
  font-weight: 800;
}
.step h3 { font-size: 1.12rem; margin-bottom: 0.5rem; }
.step p { margin: 0; color: var(--color-text-muted); font-size: 0.96rem; }

/* ---------- Spotlights (tutor + progress) ---------- */
.spotlight { background: var(--color-surface); }
.spotlight .wrap,
.spotlight-wrap {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: clamp(2rem, 5vw, 4rem);
  align-items: center;
}
@media (max-width: 880px) {
  .spotlight .wrap,
  .spotlight-wrap { grid-template-columns: 1fr; }
}
.spotlight-lede { color: var(--color-text-muted); font-size: 1.05rem; margin: 0.8rem 0 0; }
.checklist { list-style: none; padding: 0; margin: 1.6rem 0 0; display: grid; gap: 0.9rem; }
.checklist li { display: flex; gap: 0.7rem; font-size: 0.98rem; }
.checklist li svg { width: 1.35rem; height: 1.35rem; flex: none; color: var(--color-primary); margin-top: 0.1rem; }
.checklist li b { font-weight: 700; }

.transcript { padding: 1.25rem 1.3rem 1.4rem; }
.transcript .who { display: flex; align-items: center; gap: 0.55rem; font-weight: 800; font-size: 0.85rem; color: var(--color-primary); margin-bottom: 0.9rem; }
.transcript .who .dot { width: 1.6rem; height: 1.6rem; border-radius: 50%; background: var(--color-primary); color: var(--white); display: grid; place-items: center; font-size: 0.75rem; font-weight: 800; }
.transcript .bubble { font-size: 0.9rem; max-width: 88%; }
.transcript .bubble.you { max-width: 78%; }
.transcript .muted { font-size: 0.78rem; color: var(--color-text-muted); margin: 0.6rem 0 0.2rem; text-align: center; }

/* ---------- Progress spotlight ---------- */
.progress-vis { padding: 1.4rem 1.5rem 1.6rem; }
.progress-vis h3 { font-size: 1rem; margin-bottom: 1.1rem; }
.mastery-row { margin-bottom: 1rem; }
.mastery-row .lab { display: flex; justify-content: space-between; font-size: 0.86rem; margin-bottom: 0.35rem; }
.mastery-row .lab .val { font-weight: 700; color: var(--color-primary); }
.bar { height: 0.7rem; border-radius: 999px; background: var(--color-accent); overflow: hidden; }
.bar > span { display: block; height: 100%; border-radius: 999px; background: var(--color-primary); }
.trend { display: inline-flex; align-items: center; gap: 0.3rem; font-size: 0.78rem; color: var(--color-text-muted); margin-top: 0.3rem; }
.trend svg { width: 0.9rem; height: 0.9rem; }

/* ---------- CTA band ---------- */
.cta-band { background: var(--color-primary); color: var(--white); text-align: center; }
.cta-band h2 { font-size: clamp(1.7rem, 3.6vw, 2.4rem); margin-bottom: 0.8rem; }
.cta-band p { color: rgba(255, 255, 255, 0.86); font-size: 1.08rem; margin: 0 auto 1.8rem; max-width: 46ch; }
.cta-band .hero-cta { justify-content: center; }

/* ---------- Footer ---------- */
.site-footer { background: var(--color-bg); border-top: 1px solid var(--color-accent); padding-block: 2.4rem; }
.site-footer .wrap { display: flex; flex-wrap: wrap; gap: 1rem 2rem; align-items: center; justify-content: space-between; font-size: 0.88rem; color: var(--color-text-muted); }
.site-footer nav { display: flex; gap: 1.3rem; flex-wrap: wrap; }
.site-footer nav a { color: var(--color-text-muted); text-decoration: none; }
.site-footer nav a:hover { color: var(--color-primary); }
.site-footer img { height: 22px; width: auto; opacity: 0.9; }
</style>
