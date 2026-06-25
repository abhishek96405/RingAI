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

export default function PrivacyPolicy() {
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
        <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-3">Privacy Policy</h1>
        <p className="text-ink-soft mb-10">Last updated {LAST_UPDATED}</p>

        <div className="text-[15px] leading-relaxed text-ink/85">
          <P>
            Duuutah AI LLC ("Duuutah," "we," or "us") runs an AI phone assistant that answers calls for
            restaurants and salons. This policy explains what we collect, how we use it, and the choices you
            have. It covers our website, the customer dashboard, and the call-answering service.
          </P>
          <P>
            Two groups of people are covered here: businesses that sign up for Duuutah, and the people who call
            those businesses. When someone calls a restaurant or salon that uses Duuutah, we handle that call on
            the business's behalf. The business decides to use us and is responsible for the information from
            those calls; we process it for them.
          </P>

          <H2>Information we collect</H2>
          <P>
            <strong>From businesses that sign up.</strong> Your name, your business name, email address, and
            phone number; the login you create (handled through our authentication provider); and the menu,
            hours, pricing, and call-handling preferences you give us. When you subscribe, our payment processor
            collects your card details to bill you — we don't see or store full card numbers.
          </P>
          <P>
            <strong>From callers.</strong> The phone number a call comes from, and a written transcript of the
            call. A transcript can include anything the caller says — their name, what they want to order or
            book, a delivery address, and any other detail they choose to share. We keep the text transcript; we
            do not store an audio recording of the call.
          </P>
          <P>
            <strong>Automatically.</strong> Basic technical information when you use our website or dashboard —
            your device and browser, the pages you view, and when you visit. We use cookies to keep you logged in
            and to make the site work.
          </P>

          <H2>How we use information</H2>
          <P>We use this information to run the service:</P>
          <Bullets>
            <li>answer and transcribe calls, and place the orders, reservations, and appointments callers ask for;</li>
            <li>send order and booking confirmations or reminders by text;</li>
            <li>show each business its call history, transcripts, and analytics in the dashboard;</li>
            <li>provide support and answer your questions;</li>
            <li>bill subscriptions and keep records;</li>
            <li>keep the service secure and look into problems or misuse; and</li>
            <li>meet our legal and tax obligations.</li>
          </Bullets>
          <P>
            In plain terms, we use caller information to do the job the business hired us to do. We may also use
            information with personal details removed — anonymized and combined across accounts — to improve how
            the assistant works. That kind of data doesn't identify any business or any individual caller.
          </P>

          <H2>How we share information</H2>
          <P>We don't sell personal information. We share it only in these situations:</P>
          <Bullets>
            <li>
              <strong>Service providers.</strong> Companies that run parts of the service for us — cloud
              hosting, phone and voice handling, AI transcription, payment processing, text messaging, and
              support tools. They may only use the information to do that work for us, and they're required to
              keep it confidential.
            </li>
            <li>
              <strong>Systems you connect.</strong> If you connect a point-of-sale or calendar system — for
              example Square, Clover, or Google Calendar — we send orders and bookings to it at your direction so
              they reach your kitchen or your calendar.
            </li>
            <li>
              <strong>Legal reasons.</strong> If the law requires it, or to protect the rights, safety, or
              property of Duuutah, our customers, or the public.
            </li>
            <li>
              <strong>A business transfer.</strong> If Duuutah is part of a merger, acquisition, or sale of
              assets, information may transfer along with the business; we'll note any change here.
            </li>
          </Bullets>

          <H2>Text messages</H2>
          <P>
            If a caller leaves a phone number, the business — through Duuutah — may text them about their order
            or booking, such as a confirmation or a reminder. Message and data rates may apply. A recipient can
            reply STOP to any message to stop receiving them.
          </P>

          <H2>How long we keep information</H2>
          <P>We keep information only as long as we have a reason to, then delete or anonymize it.</P>
          <Bullets>
            <li>
              <strong>Call transcripts</strong> and the related order, reservation, and appointment records: up
              to 12 months, then deleted or anonymized.
            </li>
            <li>
              <strong>Business account information:</strong> kept while your account is active, and deleted
              within 60 days after you cancel.
            </li>
            <li>
              <strong>Billing and payment records:</strong> up to 7 years, to meet tax and accounting
              obligations.
            </li>
          </Bullets>

          <H2>Your choices and rights</H2>
          <P>
            If you're a business customer, you can view and update most of your information in the dashboard, or
            email us. You can ask us to delete your account information when you cancel, apart from the billing
            records we keep for tax reasons above.
          </P>
          <P>
            If you're a caller and you want your information accessed or deleted, contact the business you
            called. They control how that information is used, and we'll help them carry out your request.
          </P>
          <P>
            Depending on the state you live in, you may have the right to access or delete personal information
            we hold about you. To make a request, email office@duuutah.com and we'll respond as the law requires.
          </P>

          <H2>Security</H2>
          <P>
            We protect information with encryption in transit and at rest, restricted internal access, and other
            safeguards. Connections to point-of-sale and calendar systems use each provider's official,
            permission-based integration. No system is completely secure, but we work to keep your information
            protected and to deal with problems quickly if they come up.
          </P>

          <H2>Children</H2>
          <P>
            Duuutah isn't meant for anyone under 13, and we don't knowingly collect information from children. If
            you believe a child has given us personal information, email us and we'll delete it.
          </P>

          <H2>Changes to this policy</H2>
          <P>
            We may update this policy. When we do, we'll change the date at the top, and for significant changes
            we'll email business account holders. If you keep using Duuutah after a change takes effect, that
            means you accept the updated policy.
          </P>

          <H2>Contact</H2>
          <P>
            Questions about this policy or your information:
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
          <Link to="/terms" className="text-coral font-medium hover:underline">
            Terms of Service
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
            <Link to="/eula" className="hover:text-ink transition">EULA</Link>
            <a href="mailto:office@duuutah.com" className="hover:text-ink transition">office@duuutah.com</a>
          </div>
        </div>
      </footer>
    </div>
  );
}