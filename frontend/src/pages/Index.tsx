import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { Link } from "react-router-dom";

/* ──────────────────────────────────────────────────────────────
   PLACEHOLDERS — swap when the real values are ready:
   • DEMO_TEL / DEMO_TEL_DISPLAY  → real Telnyx demo number
   • Founder name + photo (Founder note section)
   • Footer: socials, company city
   ────────────────────────────────────────────────────────────── */
const DEMO_TEL = "+15550100100";
const DEMO_TEL_DISPLAY = "(555) 010-0100";
const CONTACT_EMAIL = "office@duuutah.com";

const Check = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#E8502E" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M20 6 9 17l-5-5" />
  </svg>
);

const PhoneIcon = ({ size = 17 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z" />
  </svg>
);

const marqueeItems = [
  "Takes pickup orders", "Books tables", "Handles delivery", "Knows your hours",
  "Never puts a caller on hold", "Confirms by text", "Works 24/7",
];

const features = [
  {
    title: "24/7 call answering", badge: null,
    desc: "Answers every call instantly, day or night, so no one ever hits voicemail.",
    icon: (<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z" /></svg>),
  },
  {
    title: "Pickup orders", badge: null,
    desc: "Takes complete pickup orders, including menu items and every modifier.",
    icon: (<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z" /><path d="M3 6h18" /><path d="M16 10a4 4 0 0 1-8 0" /></svg>),
  },
  {
    title: "Delivery handling", badge: "Pro",
    desc: "Captures delivery orders along with the customer's address and details.",
    icon: (<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="1" y="3" width="15" height="13" rx="1" /><path d="M16 8h4l3 3v5h-7z" /><circle cx="5.5" cy="18.5" r="2.5" /><circle cx="18.5" cy="18.5" r="2.5" /></svg>),
  },
  {
    title: "Reservations & bookings", badge: "Pro",
    desc: "Books tables and salon appointments straight into your calendar.",
    icon: (<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" /><path d="M16 2v4M8 2v4M3 10h18" /></svg>),
  },
  {
    title: "POS sync", badge: null,
    desc: "Pushes every order straight into Clover and Square automatically.",
    icon: (<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12a9 9 0 1 1-9-9" /><path d="M21 3v6h-6" /></svg>),
  },
  {
    title: "SMS confirmations", badge: null,
    desc: "Texts each caller a tidy confirmation the moment the call ends.",
    icon: (<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>),
  },
  {
    title: "Analytics & transcripts", badge: null,
    desc: "Every call logged with a full transcript and insights in your dashboard.",
    icon: (<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 3v18h18" /><path d="M7 14l3-3 3 3 5-6" /></svg>),
  },
  {
    title: "AI upselling", badge: "Pro",
    desc: "Suggests sides, drinks, and add-ons naturally, right in the conversation.",
    icon: (<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2l2.2 6.6L21 11l-6.8 2.4L12 20l-2.2-6.6L3 11l6.8-2.4z" /></svg>),
  },
  {
    title: "Multi-language", badge: "Coming soon",
    desc: "Greet and serve callers in more languages, beyond English.",
    icon: (<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10" /><path d="M2 12h20" /><path d="M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20z" /></svg>),
  },
];

const starterFeatures = [
  "AI pickup order taking", "1 AI voice · English", "Full menu & modifier management",
  "POS integration (Clover, Square)", "SMS order confirmations", "Full analytics dashboard",
  "Call history & transcripts", "Email support",
];
const proFeatures = [
  "Everything in Starter, plus:", "AI delivery & table reservations", "AI upselling during calls",
  "Customer recognition & CRM profiles", "Auto AI learning", "8 premium voice options",
  "Multi-language support (coming soon)", "Priority support",
];

const faqs = [
  { q: "Do I need new hardware or a new phone number?", a: "No. You keep your existing number and your existing phone. You simply forward your calls to Duuutah — setup takes a few minutes." },
  { q: "Which POS systems do you support?", a: "Clover and Square today, connected securely through their official integrations. Orders flow straight into your POS automatically." },
  { q: "What happens if Duuutah can't handle a call?", a: "You set the rules. Duuutah can take a message or hand the call off, and anything important is always logged with a full transcript so nothing gets lost." },
  { q: "What languages does it support?", a: "English today. Multi-language support is on the way and will be available on the Pro plan." },
  { q: "How does pricing work past my included calls?", a: "Each plan includes a monthly call allowance — 500 on Starter, 1,000 on Pro. Beyond that it's a simple per-call rate: $0.30 on Starter, $0.25 on Pro." },
  { q: "Can I cancel anytime?", a: "Yes. There's a 7-day free trial, and you can cancel whenever you like — no long-term contract." },
  { q: "Is my data secure?", a: "Your data is encrypted in transit and at rest, and POS connections use each provider's official, permission-based integration." },
];

const founders = [
  { name: "Abhishek Dharmapuri", role: "Co-founder & AI Product Engineer", initials: "AD", bio: "Builds the voice AI that answers every call — and the systems behind it." },
  { name: "Amogha Abbi", role: "Co-founder", initials: "AA", bio: "Bio coming soon." },
  { name: "Nagashreya Dachepalli", role: "Co-founder", initials: "ND", bio: "Bio coming soon." },
];

function Waveform({ color = "#fff", bars = 48 }: { color?: string; bars?: number }) {
  return (
    <div className="wf" style={{ ["--wc" as string]: color } as CSSProperties}>
      {Array.from({ length: bars }).map((_, i) => {
        const env = 0.3 + 0.7 * Math.sin((i / (bars - 1)) * Math.PI);
        return (
          <span
            key={i}
            style={{
              height: `${env * 100}%`,
              animationDelay: `${-(i * 0.05)}s`,
              animationDuration: `${1.0 + (i % 6) * 0.13}s`,
            }}
          />
        );
      })}
    </div>
  );
}

function PricingCalculator() {
  const [calls, setCalls] = useState(700);
  const sOver = Math.max(0, calls - 500) * 0.3;
  const pOver = Math.max(0, calls - 1000) * 0.25;
  const s = 199 + sOver;
  const p = 349 + pOver;
  const money = (n: number) => "$" + Math.round(n).toLocaleString();
  const starterHi = s <= p;
  const proHi = p < s;

  let rec: ReactNode;
  if (Math.abs(s - p) < 0.5) {
    rec = "Right at the crossover — both plans cost the same around 1,000 calls/month.";
  } else if (s < p) {
    rec = (<><span className="text-coral font-bold">Starter</span> is cheaper by {money(p - s)}/month at this volume.</>);
  } else {
    rec = (<><span className="text-coral font-bold">Pro</span> is cheaper by {money(s - p)}/month at this volume.</>);
  }

  return (
    <div className="reveal card border border-line p-8 shadow-soft">
      <div className="flex justify-between items-baseline mb-4">
        <label htmlFor="calSlider" className="text-sm font-semibold text-ink-soft">Expected calls / month</label>
        <span className="font-display font-extrabold text-3xl">{calls.toLocaleString()}</span>
      </div>
      <input id="calSlider" type="range" className="cal" min={0} max={3000} step={50} value={calls} onChange={(e) => setCalls(+e.target.value)} />
      <div className="flex justify-between text-xs text-ink-soft mt-2"><span>0</span><span>3,000</span></div>
      <div className="grid grid-cols-2 gap-4 mt-8">
        <div className="rounded-2xl border-2 p-5 text-center transition" style={{ borderColor: starterHi ? "#E8502E" : "#EBE2D8", background: starterHi ? "rgba(251,231,220,.5)" : "transparent" }}>
          <p className="text-sm font-semibold text-ink-soft mb-1">Starter</p>
          <p className="font-display font-extrabold text-3xl">{money(s)}</p>
          <p className="text-xs text-ink-soft mt-1">{sOver > 0 ? `$199 + ${money(sOver)} overage` : "base plan"}</p>
        </div>
        <div className="rounded-2xl border-2 p-5 text-center transition" style={{ borderColor: proHi ? "#E8502E" : "#EBE2D8", background: proHi ? "rgba(251,231,220,.5)" : "transparent" }}>
          <p className="text-sm font-semibold text-ink-soft mb-1">Pro</p>
          <p className="font-display font-extrabold text-3xl">{money(p)}</p>
          <p className="text-xs text-ink-soft mt-1">{pOver > 0 ? `$349 + ${money(pOver)} overage` : "base plan"}</p>
        </div>
      </div>
      <p className="text-center mt-6 text-sm font-medium text-ink">{rec}</p>
    </div>
  );
}

const Index = () => {
  const playIconRef = useRef<HTMLSpanElement>(null);

  // Reveal-on-scroll
  useEffect(() => {
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add("in");
            io.unobserve(e.target);
          }
        });
      },
      { threshold: 0.12 }
    );
    document.querySelectorAll(".landing .reveal").forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);

  // Hero "Hear Duuutah on a live call" — speaks a sample line
  const handlePlay = () => {
    if (!("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance("Thanks for calling Bella Napoli! Would you like pickup, delivery, or a table?");
    u.rate = 1;
    u.pitch = 1;
    playIconRef.current?.classList.add("animate-pulse");
    u.onend = () => playIconRef.current?.classList.remove("animate-pulse");
    window.speechSynthesis.speak(u);
  };

  return (
    <div className="landing min-h-screen antialiased text-ink">
      {/* NAV */}
      <header className="relative z-50 border-b border-line">
        <nav className="relative max-w-6xl mx-auto px-5 h-16 flex items-center justify-between gap-6">
          <Link to="/" className="flex items-center gap-2.5 shrink-0">
            <img src="/logo.png" alt="Duuutah AI" className="h-8 w-auto rounded-lg" />
            <span className="font-display font-extrabold text-xl tracking-tight">Duuutah <span className="text-coral">AI</span></span>
          </Link>
          <div className="hidden md:flex items-center gap-8 text-sm font-medium text-ink-soft absolute left-1/2 -translate-x-1/2">
            <a href="#how" className="hover:text-ink transition">How it works</a>
            <a href="#features" className="hover:text-ink transition">Features</a>
            <a href="#about" className="hover:text-ink transition">About</a>
            <a href="#pricing" className="hover:text-ink transition">Pricing</a>
            <a href="#faq" className="hover:text-ink transition">FAQ</a>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <Link to="/login" className="hidden sm:inline text-sm font-semibold border border-line hover:border-ink/30 px-4 py-2 rounded-full transition">Log in</Link>
            <Link to="/signup" className="inline-flex items-center gap-2 bg-coral hover:bg-coral-deep text-white text-sm font-semibold px-4 py-2.5 rounded-full transition btn-lift">Start free trial</Link>
          </div>
        </nav>
      </header>

      {/* HERO */}
      <section className="hero-bg relative min-h-[86vh] flex items-center">
        <div className="max-w-6xl mx-auto px-5 w-full py-20">
          <div className="max-w-2xl text-white">
            <button onClick={handlePlay} className="group inline-flex items-center gap-3 bg-black/30 hover:bg-black/45 backdrop-blur border border-white/15 rounded-full pl-1.5 pr-5 py-1.5 mb-8 transition">
              <span ref={playIconRef} className="flex h-9 w-9 items-center justify-center rounded-full bg-coral text-white">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>
              </span>
              <span className="text-sm font-semibold">Hear Duuutah on a live call</span>
            </button>
            <h1 className="font-display font-extrabold leading-[0.98] tracking-tight" style={{ fontSize: "clamp(3rem,7vw,5.75rem)" }}>
              Never miss{" "}
              <span className="relative inline-block" style={{ whiteSpace: "nowrap" }}>
                a&nbsp;call
                <svg style={{ position: "absolute", left: "-7%", top: "-24%", width: "114%", height: "152%", overflow: "visible" }} viewBox="0 0 340 150" fill="none" preserveAspectRatio="none">
                  <path d="M40,82 C54,34 152,20 236,26 C318,32 332,60 312,90 C295,118 198,130 118,123 C54,117 20,99 38,68" stroke="#E8502E" strokeWidth="4.5" strokeLinecap="round" fill="none" vectorEffect="non-scaling-stroke" />
                </svg>
              </span>.
            </h1>
            <p className="mt-7 text-lg md:text-xl text-white/85 leading-relaxed max-w-xl">
              While your team takes care of the table, Duuutah takes care of the phone — answering every call 24/7 to handle orders, bookings, and questions for your restaurant or salon.
            </p>
            <div className="mt-9 flex flex-col sm:flex-row gap-3">
              <a href={`tel:${DEMO_TEL}`} className="inline-flex items-center justify-center gap-2 bg-coral hover:bg-coral-deep text-white font-semibold px-7 py-4 rounded-full btn-lift text-base">
                <PhoneIcon />Call our AI now
              </a>
              <Link to="/signup" className="inline-flex items-center justify-center gap-2 bg-white/10 hover:bg-white/20 border border-white/25 text-white font-semibold px-7 py-4 rounded-full backdrop-blur transition text-base">Start free trial</Link>
            </div>
            <p className="mt-4 text-sm text-white/60">Or dial {DEMO_TEL_DISPLAY} · works with Clover &amp; Square · 7-day free trial</p>
          </div>
        </div>
      </section>

      {/* HOW IT WORKS */}
      <section id="how" className="py-12 md:py-16">
        <div className="max-w-6xl mx-auto px-5">
          <div className="reveal text-center max-w-3xl mx-auto mb-14">
            <div className="flex justify-center mb-4"><span className="eyebrow">How it works</span></div>
            <h2 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-4">Up and running in an afternoon.</h2>
            <p className="text-lg text-ink-soft">No new hardware, no new number. Forward your calls and Duuutah takes it from there.</p>
          </div>
          <div className="relative grid md:grid-cols-3 gap-6">
            {[33.333, 66.666].map((left) => (
              <span key={left} className="hidden md:flex absolute z-20 h-9 w-9 items-center justify-center rounded-full bg-white border border-line text-coral shadow-soft" style={{ left: `${left}%`, top: "60px", transform: "translate(-50%,-50%)" }}>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
              </span>
            ))}
            <div className="reveal card border border-line p-8 relative"><div className="font-display font-extrabold text-5xl text-coral/90 mb-5">01</div><h3 className="font-display font-bold text-xl mb-2">Forward your calls</h3><p className="text-ink-soft leading-relaxed">Keep your existing number. Point it to Duuutah in a few minutes — no new phone, no new hardware.</p></div>
            <div className="reveal card border border-line p-8 relative"><div className="font-display font-extrabold text-5xl text-coral/90 mb-5">02</div><h3 className="font-display font-bold text-xl mb-2">Duuutah answers, 24/7</h3><p className="text-ink-soft leading-relaxed">It greets every caller in a natural voice — taking orders, booking tables and appointments, and answering questions.</p></div>
            <div className="reveal card border border-line p-8 relative"><div className="font-display font-extrabold text-5xl text-coral/90 mb-5">03</div><h3 className="font-display font-bold text-xl mb-2">Everything lands in place</h3><p className="text-ink-soft leading-relaxed">Orders flow to your POS, bookings to your calendar, and every call is logged with a full transcript in your dashboard.</p></div>
          </div>
        </div>
      </section>

      {/* MARQUEE */}
      <div className="marquee-wrap border-y border-line">
        <div className="marquee py-3.5 text-base md:text-lg font-medium text-ink">
          {[false, true].map((dup) => (
            <div key={String(dup)} className="flex items-center shrink-0" aria-hidden={dup || undefined}>
              {marqueeItems.map((t, i) => (
                <span key={i} className="contents">
                  <span className="px-6">{t}</span>
                  <span className="text-coral">•</span>
                </span>
              ))}
            </div>
          ))}
        </div>
      </div>

      {/* FEATURES */}
      <section id="features" className="py-12 md:py-16">
        <div className="max-w-6xl mx-auto px-5">
          <div className="reveal text-center max-w-3xl mx-auto mb-14">
            <div className="flex justify-center mb-4"><span className="eyebrow">Features</span></div>
            <h2 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-4">Your best front-desk hire.</h2>
            <p className="text-lg text-ink-soft">Everything Duuutah does on every call, day or night.</p>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {features.map((f) => (
              <div key={f.title} className="reveal card border border-line p-6">
                <div className="flex items-start gap-4">
                  <span className="shrink-0 flex h-12 w-12 items-center justify-center rounded-2xl text-white bg-gradient-to-br from-[#F2763E] to-[#E8502E] shadow-[0_8px_18px_-6px_rgba(232,80,46,0.45)]">{f.icon}</span>
                  <div className="min-w-0">
                    {f.badge ? (
                      <div className="flex flex-wrap items-center gap-2 mb-1.5">
                        <h3 className="font-display font-bold text-lg leading-tight">{f.title}</h3>
                        <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${f.badge === "Pro" ? "bg-coral text-white" : "bg-ink/10 text-ink-soft"}`}>{f.badge}</span>
                      </div>
                    ) : (
                      <h3 className="font-display font-bold text-lg leading-tight mb-1.5">{f.title}</h3>
                    )}
                    <p className="text-sm text-ink-soft leading-relaxed">{f.desc}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* VIDEO */}
      <section className="py-12 md:py-16">
        <div className="max-w-4xl mx-auto px-5 text-center">
          <div className="flex justify-center mb-4"><span className="eyebrow">See it in action</span></div>
          <h2 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-4">Watch Duuutah take a call.</h2>
          <p className="text-lg text-ink-soft mb-10 max-w-xl mx-auto">A real call from hello to confirmed order — start to finish.</p>
          <div className="reveal relative rounded-3xl overflow-hidden border border-line shadow-warm" style={{ aspectRatio: "16/9", background: "linear-gradient(115deg,#46291a,#23150c 60%,#120b06)" }}>
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="flex h-20 w-20 items-center justify-center rounded-full bg-coral text-white btn-lift cursor-pointer shadow-warm">
                <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>
              </span>
            </div>
            <span className="absolute bottom-4 left-5 text-white/80 text-sm font-medium">Duuutah · a 2-minute call</span>
          </div>
          <p className="text-xs text-ink-soft mt-3">Demo video coming soon.</p>
        </div>
      </section>

      {/* PRICING */}
      <section id="pricing" className="py-12 md:py-16">
        <div className="max-w-5xl mx-auto px-5">
          <div className="reveal text-center max-w-3xl mx-auto mb-14">
            <div className="flex justify-center mb-4"><span className="eyebrow">Pricing</span></div>
            <h2 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-4">Simple pricing.</h2>
            <p className="text-lg text-ink-soft">Free for 7 days — your card is charged on day 8. Cancel anytime.</p>
          </div>
          <div className="grid md:grid-cols-2 gap-6 items-start">
            {/* Starter */}
            <div className="reveal card border border-line p-8">
              <h3 className="font-display font-bold text-xl mb-1">Starter</h3>
              <p className="text-ink-soft text-sm mb-5">For pickup-focused restaurants.</p>
              <div className="flex items-end gap-1 mb-1"><span className="font-display font-extrabold text-5xl">$199</span><span className="text-ink-soft mb-1.5">/month</span></div>
              <p className="text-sm text-ink-soft mb-6">500 AI calls included · $0.30/call after</p>
              <Link to="/signup" className="block text-center bg-ink text-cream font-semibold py-3.5 rounded-full hover:bg-black transition mb-7">Start free trial</Link>
              <ul className="space-y-3 text-sm">
                {starterFeatures.map((t) => (
                  <li key={t} className="flex gap-2.5"><Check /><span>{t}</span></li>
                ))}
              </ul>
            </div>
            {/* Pro */}
            <div className="reveal card border-2 border-coral p-8 relative shadow-warm">
              <span className="absolute -top-3 left-8 bg-coral text-white text-xs font-bold uppercase tracking-wider px-3 py-1 rounded-full">Most popular</span>
              <h3 className="font-display font-bold text-xl mb-1">Pro</h3>
              <p className="text-ink-soft text-sm mb-5">For full-service restaurants &amp; salons.</p>
              <div className="flex items-end gap-1 mb-1"><span className="font-display font-extrabold text-5xl">$349</span><span className="text-ink-soft mb-1.5">/month</span></div>
              <p className="text-sm text-ink-soft mb-6">1,000 AI calls included · $0.25/call after</p>
              <Link to="/signup" className="block text-center bg-coral text-white font-semibold py-3.5 rounded-full hover:bg-coral-deep transition mb-7">Start free trial</Link>
              <ul className="space-y-3 text-sm">
                {proFeatures.map((t, i) => (
                  <li key={t} className="flex gap-2.5"><Check /><span className={i === 0 ? "font-semibold" : undefined}>{t}</span></li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* CALCULATOR */}
      <section className="py-12 md:py-16">
        <div className="max-w-3xl mx-auto px-5">
          <div className="reveal text-center mb-10">
            <div className="flex justify-center mb-4"><span className="eyebrow">Which plan fits</span></div>
            <h2 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-4">Estimate your cost.</h2>
            <p className="text-lg text-ink-soft">Drag to your expected call volume — we'll point you to the cheaper plan.</p>
          </div>
          <PricingCalculator />
        </div>
      </section>

      {/* INTEGRATIONS */}
      <section className="py-16">
        <div className="max-w-5xl mx-auto px-5 text-center">
          <p className="text-xs uppercase tracking-[0.16em] text-ink-soft font-bold mb-7">Works with the tools you already use</p>
          <div className="flex flex-wrap items-center justify-center gap-3">
            <span className="inline-flex items-center gap-2.5 paper border border-line rounded-xl px-5 py-3 font-semibold"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#E8502E" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="3" /><circle cx="12" cy="12" r="3" /></svg>Clover</span>
            <span className="inline-flex items-center gap-2.5 paper border border-line rounded-xl px-5 py-3 font-semibold"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#E8502E" strokeWidth="2"><rect x="4" y="4" width="16" height="16" rx="3" /><rect x="9" y="9" width="6" height="6" rx="1" /></svg>Square</span>
            <span className="inline-flex items-center gap-2.5 paper border border-line rounded-xl px-5 py-3 font-semibold"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#E8502E" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" /><path d="M16 2v4M8 2v4M3 10h18" /></svg>Google Calendar</span>
          </div>
        </div>
      </section>

      {/* ABOUT */}
      <section id="about" className="py-12 md:py-16">
        <div className="max-w-6xl mx-auto px-5">
          {/* header */}
          <div className="reveal text-center max-w-3xl mx-auto mb-14">
            <div className="flex justify-center mb-4"><span className="eyebrow">About us</span></div>
            <h2 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-4">Built by people who kept getting voicemail.</h2>
            <p className="text-lg text-ink-soft">Three former Amazon teammates, building the always-on front desk that independent restaurants and salons deserve.</p>
          </div>

          {/* story + pull quote */}
          <div className="grid lg:grid-cols-[1.5fr_1fr] gap-8 lg:gap-12 items-start max-w-5xl mx-auto mb-16">
            <div className="reveal space-y-5 text-[1.05rem] leading-relaxed text-ink-soft">
              <p>We met at Amazon, working on systems built to serve millions of people without dropping a single one. Then we split up for our master's degrees and landed on three different continents — Abhishek in the US, Amogha in Australia, Shreya in India.</p>
              <p>But the same small frustration followed all three of us. You'd call a neighborhood spot to place an order and get a busy signal — or voicemail, or a phone that just rang while the staff, you knew, were heads-down taking care of a full house.</p>
              <p>That gap stuck with us. The technology that keeps a global company from ever missing a beat had somehow never reached the businesses we love most — the family kitchen, the two-chair salon, the place where the owner knows your name. For them, a missed call isn't a number on a dashboard. It's an empty table, an order lost to the chain down the street, a regular who quietly stops showing up.</p>
              <p>So we came back together to build the thing we kept wishing existed. Duuutah — from the Sanskrit for <span className="text-coral font-semibold">messenger</span>, the one who carries word faithfully between two people — answers every call in your business's own voice, gets the details right, and makes sure nothing, and no one, slips through. No new hardware. No new number. No call center. Just a front desk that's always there, so you can focus on the person standing right in front of you.</p>
            </div>
            <aside className="reveal card border border-line p-8 shadow-soft">
              <span className="font-display font-extrabold text-5xl leading-none text-coral block mb-3">&ldquo;</span>
              <blockquote className="font-display font-semibold text-xl leading-snug tracking-tight text-ink">Every missed call is a real person who needed something — a table, an order, an appointment — and a business that just lost them.</blockquote>
            </aside>
          </div>

          {/* mission & vision */}
          <div className="grid md:grid-cols-2 gap-5 max-w-5xl mx-auto mb-16">
            <div className="reveal card border border-line p-8">
              <span className="flex h-12 w-12 items-center justify-center rounded-2xl text-white bg-gradient-to-br from-[#F2763E] to-[#E8502E] shadow-[0_8px_18px_-6px_rgba(232,80,46,0.45)] mb-5">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>
              </span>
              <p className="eyebrow mb-3">Our mission</p>
              <h3 className="font-display font-bold text-2xl tracking-tight mb-3">Give every small business a front desk that never sleeps.</h3>
              <p className="text-ink-soft leading-relaxed">We build voice AI that answers every call, takes every order, and books every appointment — so independent restaurants and salons never have to choose between the customer on the phone and the one at the counter.</p>
            </div>
            <div className="reveal card border border-line p-8">
              <span className="flex h-12 w-12 items-center justify-center rounded-2xl text-white bg-gradient-to-br from-[#F2763E] to-[#E8502E] shadow-[0_8px_18px_-6px_rgba(232,80,46,0.45)] mb-5">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/></svg>
              </span>
              <p className="eyebrow mb-3">Our vision</p>
              <h3 className="font-display font-bold text-2xl tracking-tight mb-3">A world where no one loses a customer to a ringing phone.</h3>
              <p className="text-ink-soft leading-relaxed">We're working toward a future where the corner café and the neighborhood salon have the same always-on, intelligent service as the biggest chains — and win on what they already do best: taking care of people.</p>
            </div>
          </div>

          {/* founders */}
          <div className="reveal rounded-3xl bg-ink text-cream p-8 md:p-12 shadow-warm">
            <div className="text-center max-w-2xl mx-auto mb-10">
              <div className="flex justify-center mb-4"><span className="eyebrow light">The team</span></div>
              <h3 className="font-display font-extrabold text-3xl md:text-4xl tracking-tight">Meet the founders</h3>
              <p className="text-cream/60 mt-3">Three ex-Amazon builders who'd rather sweat the details than miss a call.</p>
            </div>
            <div className="grid sm:grid-cols-3 gap-5">
              {founders.map((f) => (
                <div key={f.name} className="rounded-2xl bg-white/[0.04] border border-white/10 p-6 text-center">
                  <span className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-coral/20 border border-white/15 font-display font-bold text-coral text-lg">{f.initials}</span>
                  <p className="font-semibold text-cream">{f.name}</p>
                  <p className="text-sm text-coral/90 mt-0.5">{f.role}</p>
                  <span className="inline-block mt-3 text-[11px] font-bold uppercase tracking-wider text-cream/55 bg-white/[0.06] border border-white/10 px-2.5 py-1 rounded-full">Ex-Amazon</span>
                  <p className="text-sm text-cream/55 leading-relaxed mt-4">{f.bio}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section id="faq" className="py-12 md:py-16">
        <div className="max-w-3xl mx-auto px-5">
          <div className="reveal text-center mb-12">
            <div className="flex justify-center mb-4"><span className="eyebrow">FAQ</span></div>
            <h2 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight">Questions, answered.</h2>
          </div>
          <div className="reveal">
            {faqs.map((f) => (
              <details key={f.q} className="faq">
                <summary>
                  {f.q}
                  <svg className="chev" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>
                </summary>
                <div className="ans">{f.a}</div>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* FINAL CTA */}
      <section className="relative overflow-hidden bg-coral text-white">
        <div className="max-w-4xl mx-auto px-5 py-20 md:py-24 text-center">
          <h2 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-5">Ready to never miss a call?</h2>
          <p className="text-white/85 text-lg mb-9 max-w-xl mx-auto">Call our AI and hear it for yourself, or start your 7-day free trial today.</p>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <a href={`tel:${DEMO_TEL}`} className="inline-flex items-center justify-center gap-2 bg-white text-coral font-semibold px-7 py-4 rounded-full btn-lift"><PhoneIcon />Call our AI now</a>
            <Link to="/signup" className="inline-flex items-center justify-center gap-2 bg-coral-deep/40 border border-white/40 text-white font-semibold px-7 py-4 rounded-full hover:bg-coral-deep/60 transition">Start free trial</Link>
          </div>
          <div className="max-w-md mx-auto mt-12"><Waveform color="#fff" /></div>
        </div>
      </section>

      {/* FOOTER */}
      <footer className="relative overflow-hidden bg-ink text-cream/70">
        <span className="pointer-events-none select-none absolute left-1/2 -translate-x-1/2 -bottom-6 font-display font-extrabold text-white/[0.04] whitespace-nowrap leading-none" style={{ fontSize: "clamp(5rem,20vw,15rem)" }}>Duuutah</span>
        <div className="relative z-10 max-w-6xl mx-auto px-5 py-16">
          <div className="grid md:grid-cols-[1.4fr_1fr_1fr_1fr] gap-10">
            <div>
              <div className="flex items-center gap-2.5 mb-4">
                <img src="/logo.png" alt="Duuutah AI" className="h-7 w-auto rounded-lg" />
                <span className="font-display font-extrabold text-xl text-cream">Duuutah AI</span>
              </div>
              <p className="text-sm text-cream/50 max-w-xs">The AI receptionist for restaurants &amp; salons. Never miss another call.</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.14em] text-cream/40 mb-4">Product</p>
              <div className="flex flex-col gap-2.5 text-sm">
                <a href="#how" className="hover:text-cream transition">How it works</a>
                <a href="#features" className="hover:text-cream transition">Features</a>
                <a href="#pricing" className="hover:text-cream transition">Pricing</a>
                <a href={`tel:${DEMO_TEL}`} className="hover:text-cream transition">Call the AI</a>
              </div>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.14em] text-cream/40 mb-4">Company</p>
              <div className="flex flex-col gap-2.5 text-sm">
                <a href="#about" className="hover:text-cream transition">About</a>
                <a href={`mailto:${CONTACT_EMAIL}`} className="hover:text-cream transition">{CONTACT_EMAIL}</a>
                <a href="#" className="hover:text-cream transition">Contact</a>
              </div>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.14em] text-cream/40 mb-4">Legal</p>
              <div className="flex flex-col gap-2.5 text-sm">
                <Link to="/privacy" className="hover:text-cream transition">Privacy Policy</Link>
                <Link to="/terms" className="hover:text-cream transition">Terms of Service</Link>
              </div>
            </div>
          </div>
          <div className="mt-12 pt-6 border-t border-white/10 text-xs text-cream/40">© {new Date().getFullYear()} Duuutah AI</div>
        </div>
      </footer>
    </div>
  );
};

export default Index;
