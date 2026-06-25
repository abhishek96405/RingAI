import { type ReactNode } from "react";
import { Link } from "react-router-dom";

const LAST_UPDATED = "June 24, 2026";

const H2 = ({ children }: { children: ReactNode }) => (
  <h2 className="font-display font-bold text-xl text-ink mt-10 mb-3">{children}</h2>
);
const P = ({ children }: { children: ReactNode }) => <p className="mb-5">{children}</p>;
const Bullets = ({ children }: { children: ReactNode }) => (
  <ul className="list-disc pl-5 space-y-2 mb-5 marker:text-coral">{children}</ul>
);

export default function EULA() {
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
        <h1 className="font-display font-extrabold text-4xl md:text-5xl tracking-tight mb-3">End User License Agreement</h1>
        <p className="text-ink-soft mb-10">Last updated {LAST_UPDATED}</p>

        <div className="text-[15px] leading-relaxed text-ink/85">
          <P>
            This End User License Agreement ("EULA") is an agreement between Duuutah AI LLC ("Duuutah," "we," or
            "us") and the business or person who installs, connects, or uses the Duuutah application ("you" or
            "your"). It governs your license to use the Duuutah app — our dashboard, the AI call-answering
            service, and any related software we provide, including when you reach or connect it through a
            point-of-sale app marketplace or app store (together, the "App"). By installing,
            connecting, or using the App, you agree to this EULA. If you're acting for a business, you confirm
            you're authorized to accept it for that business, and that you're at least 18.
          </P>
          <P>
            This EULA works alongside our{" "}
            <Link to="/terms" className="text-coral font-medium hover:underline">Terms of Service</Link> and{" "}
            <Link to="/privacy" className="text-coral font-medium hover:underline">Privacy Policy</Link>. Our
            Terms of Service cover your subscription, fees, and overall use of the service; this EULA covers your
            license to use the software itself; and our Privacy Policy explains how we handle personal
            information. If this EULA and the Terms of Service ever conflict on a commercial term — like fees or
            billing — the Terms of Service control.
          </P>

          <H2>License we grant</H2>
          <P>
            As long as you follow this EULA and keep your subscription in good standing, Duuutah grants you a
            limited, non-exclusive, non-transferable, non-sublicensable, and revocable license to access and use
            the App to run your own business — answering your calls, taking orders, and booking reservations and
            appointments. That's the scope of the license: your own internal business use.
          </P>

          <H2>What you may not do</H2>
          <P>This license has limits. You agree not to:</P>
          <Bullets>
            <li>copy, modify, translate, or create derivative works of the App;</li>
            <li>reverse-engineer, decompile, or disassemble the App, or try to extract its source code or underlying models, except to the narrow extent the law expressly allows;</li>
            <li>rent, lease, sell, sublicense, or otherwise make the App available to others, or use it to build or train a competing product or service;</li>
            <li>remove or hide any notice or branding, or turn off the assistant's disclosure that callers are speaking with an automated system;</li>
            <li>interfere with the App, probe or test its security, or get around its usage limits or access controls; or</li>
            <li>use the App unlawfully, or in any way our Terms of Service prohibit.</li>
          </Bullets>

          <H2>Ownership</H2>
          <P>
            The App is licensed, not sold. Duuutah and its licensors keep all rights in the App — the software,
            AI models, designs, text, and the Duuutah name and logo — and all related intellectual property.
            This EULA gives you the right to use the App; it doesn't transfer any ownership to you. If you send
            us feedback or suggestions, we're free to use them, with no obligation to you. The data you put into
            the App — your menu, transcripts, orders, bookings, and caller numbers — stays yours, as described in
            our Terms of Service and Privacy Policy.
          </P>

          <H2>Point-of-sale and other connected services</H2>
          <P>
            You can reach or connect the App through services run by other companies — such as point-of-sale
            systems, calendars, and phone carriers. Your use of those services is governed by their own agreements,
            and connecting them is at your direction. When you connect one, you authorize the App to exchange
            information with it — sending orders to your kitchen, or bookings to your calendar — so it can do its
            job. We're not responsible for those services' availability or for what they do with information you
            direct us to send. Where a platform's rules require specific terms for using the App through it,
            those terms apply as well.
          </P>

          <H2>Updates</H2>
          <P>
            We improve the App over time, and we may add, change, or remove features — sometimes automatically,
            and sometimes because an update is needed to keep the App working or secure. This EULA covers those
            updates, unless an update comes with its own separate terms.
          </P>

          <H2>How long this license lasts</H2>
          <P>
            Your license is tied to an active Duuutah subscription. The free trial, fees, and billing are
            described in our Terms of Service. While your subscription is active and you're following this EULA,
            your license continues. If you cancel, stop paying, or break this EULA, the license ends.
          </P>

          <H2>Ending the license</H2>
          <P>
            You can stop using the App at any time, and you can cancel your subscription as described in our
            Terms of Service. We can suspend or end this license if you break it or break our Terms of Service.
            When the license ends, you need to stop using the App and disconnect it from any services you linked
            it to. The parts of this EULA meant to last beyond it — ownership, the use restrictions, disclaimers,
            and the liability limit — keep applying.
          </P>

          <H2>Disclaimers</H2>
          <P>
            The App is provided "as is" and "as available." The assistant uses AI, and AI can make mistakes — it
            might mishear an item, a quantity, or a time — so you're responsible for reviewing orders,
            reservations, and appointments before you act on them. To the extent the law allows, we disclaim
            warranties of any kind, including that the App will be uninterrupted, error-free, or fit for a
            particular purpose.
          </P>

          <H2>Limitation of liability</H2>
          <P>
            To the extent the law allows, Duuutah won't be liable for indirect, incidental, or consequential
            damages arising from the App — including lost profits, lost data, or a missed or incorrect order or
            booking — and our total liability is limited as described in our Terms of Service.
          </P>

          <H2>Compliance with laws</H2>
          <P>
            You agree to use the App in line with the laws that apply to you, including U.S. export and sanctions
            laws, and not to use it where those laws prohibit. You're also responsible for the disclosure and
            consent obligations described in our Terms of Service, including telling your callers that calls are
            answered by an automated assistant and may be transcribed.
          </P>

          <H2>Changes to this EULA</H2>
          <P>
            We may update this EULA. For significant changes, we'll update the date at the top and, where it
            makes sense, let business account holders know. If you keep using the App after a change takes
            effect, that means you accept the updated EULA.
          </P>

          <H2>Governing law</H2>
          <P>
            This EULA is governed by the laws of the State of Delaware, without regard to its conflict-of-laws
            rules.
          </P>

          <H2>Contact</H2>
          <P>
            Questions about this EULA:
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
          <Link to="/terms" className="text-coral font-medium hover:underline">Terms of Service</Link> and{" "}
          <Link to="/privacy" className="text-coral font-medium hover:underline">Privacy Policy</Link>.
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
