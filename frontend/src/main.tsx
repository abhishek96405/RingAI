import { createRoot } from "react-dom/client";
import { ClerkProvider } from "@clerk/clerk-react";
import * as Sentry from "@sentry/react";
import App from "./App.tsx";
import "./index.css";

const clerkPubKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

const sentryDsn = import.meta.env.VITE_SENTRY_DSN;
if (sentryDsn) {
  Sentry.init({
    dsn: sentryDsn,
    environment: import.meta.env.VITE_SENTRY_ENVIRONMENT ?? import.meta.env.MODE,
    integrations: [Sentry.browserTracingIntegration()],
    tracesSampleRate: Number(import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE ?? 0),
  });
}

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

const rootElement = document.getElementById("root")!;

if (!clerkPubKey) {
  // Fail loud, not silent: a missing Clerk key previously mounted ClerkProvider
  // with an empty string, which rendered a blank white app with no explanation
  // (C1-1). Render a visible configuration error instead so the misconfiguration
  // is obvious to whoever deployed it.
  console.error("Missing VITE_CLERK_PUBLISHABLE_KEY — the app cannot start.");
  createRoot(rootElement).render(
    <div
      role="alert"
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 12,
        padding: 24,
        fontFamily: "system-ui, -apple-system, sans-serif",
        textAlign: "center",
      }}
    >
      <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>Configuration error</h1>
      <p style={{ maxWidth: 440, color: "#555", lineHeight: 1.5, margin: 0 }}>
        This app is not configured correctly: the authentication key
        (<code>VITE_CLERK_PUBLISHABLE_KEY</code>) is missing. If you are the site
        owner, set it in your deployment environment and redeploy.
      </p>
    </div>
  );
} else {
  createRoot(rootElement).render(
    <Sentry.ErrorBoundary fallback={<p style={{ padding: 24 }}>Something went wrong. Please refresh.</p>}>
      <ClerkProvider publishableKey={clerkPubKey}>
        <App />
      </ClerkProvider>
    </Sentry.ErrorBoundary>
  );
}
