import { type ReactNode } from "react";
import { Link } from "react-router-dom";

const LAST_UPDATED = "June 18, 2026";

const H2 = ({ children }: { children: ReactNode }) => (
  <h2 className="font-display font-bold text-xl text-ink mt-10 mb-3">{children}</h2>
);
const P = ({ children }: { children: ReactNode }) => <p className="mb-5">{children}</p>;
const Bullets = ({ children }: { children: ReactNode }) => (
  <ul className="list-disc pl-5 space-y-2 mb-5 marker:text-coral">{children}</ul>
);

export default function TermsOfService() {
  return (
    <div className="landing min-h-screen antialiased bg-cream text-ink">
      <header className="border-b border-line">
        <div className="max-w-3xl mx-auto px-5 h-16 flex items-center justify-between">
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

      <main className="max-w-3xl mx-auto px-5 py-14 md:py-20">
        <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-3">Terms of Service</h1>
        <p className="text-ink-soft mb-10">Last updated {LAST_UPDATED}</p>

        <div className="text-[15px] leading-relaxed text-ink/85">
          <P>
            These terms are an agreement between Duuutah AI LLC ("Duuutah," "we," or "us") and the business that
            signs up for our service ("you" or "your"). They cover your use of the Duuutah website, dashboard,
            and call-answering service (together, the "Service"). By signing up or using the Service, you agree
            to these terms. You must be at least 18 and authorized to act for your business.
          </P>

          <H2>The service</H2>
          <P>
            Duuutah is an AI phone assistant for restaurants and salons. It answers your inbound calls, takes
            pickup and delivery orders, books tables and appointments, answers common questions, and sends text
            confirmations. It can connect to supported point-of-sale and calendar systems to pass along orders
            and bookings. The assistant speaks English today; more languages are on the way.
          </P>

          <H2>Your account</H2>
          <P>
            You're responsible for your login and for everything that happens under your account. Keep your
            menu, prices, hours, and call-handling rules accurate and up to date — the assistant works from what
            you give it. Tell us promptly if you think someone has used your account without permission.
          </P>

          <H2>Free trial, fees, and billing</H2>
          <P>
            <strong>Free trial.</strong> Duuutah starts with a 7-day free trial. On day 8 we charge your card
            the plan fee, unless you cancel during the trial.
          </P>
          <P>
            <strong>Plans.</strong> Starter is $199/month and includes 500 AI-answered calls, then $0.30 per
            call after that. Pro is $349/month and includes 1,000 calls, then $0.25 per call. Fees are billed to
            the card on file each month. You authorize us to charge that card on a recurring basis for your plan
            fee, any calls over your monthly allowance, and applicable taxes, until you cancel.
          </P>
          <P>
            <strong>No refunds.</strong> Because you get a full 7 days to try Duuutah before paying, monthly
            fees are not refundable once charged — including for partial months and unused calls — except where
            the law requires otherwise. We may choose to issue a credit or refund in a particular case, but
            we're not obligated to.
          </P>
          <P>
            <strong>Cancellation.</strong> You can cancel anytime from your dashboard or by emailing
            office@duuutah.com. Cancellation stops your next charge, and you keep access through the end of the
            period you've already paid for. There's no long-term contract.
          </P>
          <P>
            <strong>Failed payments.</strong> If a charge doesn't go through, we may pause the Service until
            payment clears. Unpaid amounts remain due.
          </P>

          <H2>Calls, transcripts, and AI disclosure</H2>
          <P>
            You authorize Duuutah to answer and create written transcripts of calls to the phone number or
            numbers you forward to us. We keep transcripts, not audio recordings.
          </P>
          <P>
            You are responsible for telling your callers that calls are answered by an automated assistant and
            may be transcribed, and for getting any consent the law requires in the places where your business
            operates. Call-recording and call-monitoring laws vary by state, and meeting them for your callers
            is your responsibility, not ours. You agree not to turn off the assistant's disclosure that callers
            are speaking with an automated system.
          </P>

          <H2>Text messaging</H2>
          <P>
            If you use the text-message features, you confirm you have the consent needed to text your callers,
            and you'll follow the laws that apply to business messaging, including the Telephone Consumer
            Protection Act. Standard message and data rates may apply to the people you text.
          </P>

          <H2>AI accuracy and your responsibility</H2>
          <P>
            The assistant uses AI, and AI can make mistakes — it might mishear an item, a quantity, or a time.
            You're responsible for reviewing orders, reservations, and appointments before you act on them. We
            don't promise the assistant will be error-free, and you shouldn't rely on it as your only check on an
            order or booking.
          </P>

          <H2>Acceptable use</H2>
          <P>Use the Service lawfully. You agree not to:</P>
          <Bullets>
            <li>use it to harass, mislead, or harm anyone, or to break the law;</li>
            <li>interfere with how the Service runs or try to get around its limits;</li>
            <li>resell it, copy it, or attempt to reverse-engineer it; or</li>
            <li>give us information that's false or that you don't have the right to provide.</li>
          </Bullets>

          <H2>Your data</H2>
          <P>
            You own your data — your account information, menu, transcripts, orders, bookings, and caller phone
            numbers. You give us permission to store and process it so we can run the Service for you. We handle
            personal information as described in our{" "}
            <Link to="/privacy" className="text-coral font-medium hover:underline">
              Privacy Policy
            </Link>
            . For information from your callers, we act as your service provider: we process it on your behalf,
            and if a caller contacts us directly about their information, we'll point them to you. We may use
            data with personal details removed — anonymized and aggregated — to improve the Service.
          </P>

          <H2>Other services you connect</H2>
          <P>
            Duuutah works with outside services like point-of-sale systems, calendars, and phone carriers. Those
            services are run by other companies, and your use of them is governed by their own terms. We're not
            responsible for their availability or for what they do with the information you send them at your
            direction.
          </P>

          <H2>Availability</H2>
          <P>
            We aim to keep the Service running reliably, but we don't guarantee it will be available without
            interruption. We may take it down for maintenance or updates, and parts of it depend on third
            parties — like phone carriers and AI providers — that are outside our control.
          </P>

          <H2>Disclaimers</H2>
          <P>
            The Service is provided "as is" and "as available." To the extent the law allows, we disclaim
            warranties of any kind, including that the Service will be uninterrupted, error-free, or fit for a
            particular purpose.
          </P>

          <H2>Limitation of liability</H2>
          <P>
            To the extent the law allows, Duuutah won't be liable for indirect, incidental, or consequential
            damages — including lost profits, lost revenue, lost data, or a missed or incorrect order or
            booking. Our total liability for any claim relating to the Service is limited to the amount you paid
            us in the three months before the claim.
          </P>

          <H2>Indemnification</H2>
          <P>
            You agree to cover Duuutah for claims, damages, and costs (including reasonable legal fees) that come
            from your use of the Service, your breach of these terms or the law — including call-recording
            consent and messaging laws — or a dispute between you and one of your callers.
          </P>

          <H2>Suspension and termination</H2>
          <P>
            You can cancel as described above. We can suspend or end your access if you break these terms, don't
            pay, or use the Service in a way that harms it or other people. When the Service ends, your right to
            use it stops; the parts of these terms that should outlast the agreement — like fees owed,
            disclaimers, liability limits, and indemnification — continue to apply.
          </P>

          <H2>Changes to these terms</H2>
          <P>
            We may update these terms. For significant changes, we'll email business account holders, and we'll
            update the date at the top. If you keep using the Service after a change takes effect, that means you
            accept the updated terms.
          </P>

          <H2>Governing law</H2>
          <P>
            These terms are governed by the laws of the State of Delaware, without regard to its
            conflict-of-laws rules.
          </P>

          <H2>Contact</H2>
          <P>
            Questions about these terms:
            <br />
            Duuutah AI LLC
            <br />
            24201 W Hazelcrest Dr, Ste 200
            <br />
            Plainfield, IL 60544
            <br />
            <a href="mailto:office@duuutah.com" className="text-coral font-medium hover:underline">
              office@duuutah.com
            </a>
          </P>
        </div>

        <div className="mt-12 pt-6 border-t border-line text-sm text-ink-soft">
          See also our{" "}
          <Link to="/privacy" className="text-coral font-medium hover:underline">
            Privacy Policy
          </Link>
          .
        </div>
      </main>

      <footer className="border-t border-line">
        <div className="max-w-3xl mx-auto px-5 py-8 flex flex-col sm:flex-row items-center justify-between gap-3 text-sm text-ink-soft">
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
