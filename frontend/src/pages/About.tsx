import { Link } from "react-router-dom";

const founders = [
  { name: "Abhishek Dharmapuri", role: "Co-founder & AI Product Engineer", initials: "AD", photo: "/Abhishek.jpeg", bio: "Builds the voice AI that answers every call — and the systems behind it." },
  { name: "Amogha Abbi", role: "Co-founder", initials: "AA", photo: "", bio: "Bio coming soon." },
  { name: "Nagashreya Dachepalli", role: "Co-founder", initials: "ND", photo: "/Shreya.jpeg", bio: "Bio coming soon." },
];

export default function About() {
  return (
    <div className="landing min-h-screen antialiased bg-cream text-ink">
      {/* HEADER — matches PrivacyPolicy / TermsOfService */}
      <header className="border-b border-line">
        <div className="max-w-4xl mx-auto px-5 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2.5">
            <img src="/logo.png" alt="Duuutah AI" className="h-8 w-auto rounded-lg" />
            <span className="font-display font-extrabold text-xl tracking-tight">
              Duuutah <span className="text-coral">AI</span>
            </span>
          </Link>
          <Link to="/" className="text-sm font-semibold text-ink-soft hover:text-ink transition">
            ← Back to home
          </Link>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-5 py-14 md:py-20">
        {/* title */}
        <span className="eyebrow">About us</span>
        <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mt-4 mb-4">
          Built by people who kept getting voicemail.
        </h1>
        <p className="text-lg text-ink-soft max-w-2xl">
          Three former Amazon teammates, building the always-on front desk that independent restaurants and salons deserve.
        </p>

        {/* story */}
        <div className="mt-12 max-w-2xl space-y-5 text-[1.05rem] leading-relaxed text-ink/85">
          <p>We met at Amazon, working on systems built to serve millions of people without dropping a single one. Then we split up for our master's degrees and landed on three different continents — Abhishek in the US, Amogha in Australia, Shreya in India.</p>
          <p>But the same small frustration followed all three of us. You'd call a neighborhood spot to place an order and get a busy signal — or voicemail, or a phone that just rang while the staff, you knew, were heads-down taking care of a full house.</p>
          <p>That gap stuck with us. The technology that keeps a global company from ever missing a beat had somehow never reached the businesses we love most — the family kitchen, the two-chair salon, the place where the owner knows your name. For them, a missed call isn't a number on a dashboard. It's an empty table, an order lost to the chain down the street, a regular who quietly stops showing up.</p>
          <p>So we came back together to build the thing we kept wishing existed. Duuutah — from the Sanskrit for <span className="text-coral font-semibold">messenger</span>, the one who carries word faithfully between two people — answers every call in your business's own voice, gets the details right, and makes sure nothing, and no one, slips through. No new hardware. No new number. No call center. Just a front desk that's always there, so you can focus on the person standing right in front of you.</p>
        </div>

        {/* pull quote */}
        <blockquote className="my-14 max-w-2xl border-l-2 border-coral pl-6">
          <span className="font-display font-extrabold text-4xl leading-none text-coral block mb-2">&ldquo;</span>
          <p className="font-display font-semibold text-2xl leading-snug tracking-tight text-ink">
            Every missed call is a real person who needed something — a table, an order, an appointment — and a business that just lost them.
          </p>
        </blockquote>

        {/* mission & vision */}
        <div className="grid md:grid-cols-2 gap-5 mt-12">
          <div className="card border border-line p-8">
            <span className="flex h-12 w-12 items-center justify-center rounded-2xl text-white bg-gradient-to-br from-[#F2763E] to-[#E8502E] shadow-[0_8px_18px_-6px_rgba(232,80,46,0.45)] mb-5">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>
            </span>
            <p className="eyebrow mb-3">Our mission</p>
            <h2 className="font-display font-bold text-2xl tracking-tight mb-3">Give every small business a front desk that never sleeps.</h2>
            <p className="text-ink-soft leading-relaxed">We build voice AI that answers every call, takes every order, and books every appointment — so independent restaurants and salons never have to choose between the customer on the phone and the one at the counter.</p>
          </div>
          <div className="card border border-line p-8">
            <span className="flex h-12 w-12 items-center justify-center rounded-2xl text-white bg-gradient-to-br from-[#F2763E] to-[#E8502E] shadow-[0_8px_18px_-6px_rgba(232,80,46,0.45)] mb-5">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/></svg>
            </span>
            <p className="eyebrow mb-3">Our vision</p>
            <h2 className="font-display font-bold text-2xl tracking-tight mb-3">A world where no one loses a customer to a ringing phone.</h2>
            <p className="text-ink-soft leading-relaxed">We're working toward a future where the corner café and the neighborhood salon have the same always-on, intelligent service as the biggest chains — and win on what they already do best: taking care of people.</p>
          </div>
        </div>

        {/* founders */}
        <div className="rounded-3xl bg-ink text-cream p-8 md:p-12 shadow-warm mt-12">
          <div className="text-center max-w-2xl mx-auto mb-10">
            <div className="flex justify-center mb-4"><span className="eyebrow light">The team</span></div>
            <h2 className="font-display font-extrabold text-3xl md:text-4xl tracking-tight">Meet the founders</h2>
            <p className="text-cream/60 mt-3">Three ex-Amazon builders who'd rather sweat the details than miss a call.</p>
          </div>
          <div className="grid sm:grid-cols-3 gap-5">
            {founders.map((f) => (
              <div key={f.name} className="rounded-2xl bg-white/[0.04] border border-white/10 p-6 text-center">
                {f.photo ? (
                  <img src={f.photo} alt={f.name} className="mx-auto mb-4 h-28 w-28 rounded-full border border-white/15 object-cover" />
                ) : (
                  <span className="mx-auto mb-4 flex h-28 w-28 items-center justify-center rounded-full bg-coral/20 border border-white/15 font-display font-bold text-coral text-2xl">{f.initials}</span>
                )}
                <p className="font-semibold text-cream">{f.name}</p>
                <p className="text-sm text-coral/90 mt-0.5">{f.role}</p>
                <span className="inline-block mt-3 text-[11px] font-bold uppercase tracking-wider text-cream/55 bg-white/[0.06] border border-white/10 px-2.5 py-1 rounded-full">Ex-Amazon</span>
                <p className="text-sm text-cream/55 leading-relaxed mt-4">{f.bio}</p>
              </div>
            ))}
          </div>
        </div>

        {/* closing CTA */}
        <div className="text-center mt-16">
          <h2 className="font-display font-extrabold text-3xl tracking-tight mb-3">Ready to never miss a call?</h2>
          <p className="text-ink-soft mb-7">Hear Duuutah answer a call, or start your 7-day free trial.</p>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Link to="/signup" className="inline-flex items-center justify-center bg-coral hover:bg-coral-deep text-white font-semibold px-7 py-4 rounded-full btn-lift">Start free trial</Link>
            <Link to="/" className="inline-flex items-center justify-center bg-white border border-line hover:border-ink/30 text-ink font-semibold px-7 py-4 rounded-full transition">Back to home</Link>
          </div>
        </div>
      </main>

      {/* FOOTER — matches PrivacyPolicy / TermsOfService */}
      <footer className="border-t border-line">
        <div className="max-w-4xl mx-auto px-5 py-8 flex flex-col sm:flex-row items-center justify-between gap-3 text-sm text-ink-soft">
          <span>© {new Date().getFullYear()} Duuutah AI LLC</span>
          <div className="flex gap-5">
            <Link to="/privacy" className="hover:text-ink transition">Privacy</Link>
            <Link to="/terms" className="hover:text-ink transition">Terms</Link>
            <a href="mailto:office@duuutah.com" className="hover:text-ink transition">office@duuutah.com</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
