import React from "react";
import ReactDOM from "react-dom/client";
import { ClerkProvider } from "@clerk/clerk-react";
import "@/index.css";
import App from "@/App";

const clerkKey = process.env.REACT_APP_CLERK_PUBLISHABLE_KEY;
const root = ReactDOM.createRoot(document.getElementById("root"));

if (!clerkKey) {
  root.render(
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", padding: 24, fontFamily: "Inter, system-ui, sans-serif" }}>
      <div style={{ maxWidth: 560 }}>
        <h1 style={{ fontSize: 24, marginBottom: 12 }}>Clerk is not configured</h1>
        <p>Add <code>REACT_APP_CLERK_PUBLISHABLE_KEY</code> to <code>frontend/.env</code> and restart the frontend.</p>
      </div>
    </div>,
  );
} else {
  root.render(
    <React.StrictMode>
      <ClerkProvider publishableKey={clerkKey}>
        <App />
      </ClerkProvider>
    </React.StrictMode>,
  );
}
