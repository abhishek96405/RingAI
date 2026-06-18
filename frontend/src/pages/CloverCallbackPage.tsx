import { useEffect, useRef, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { useAppSession } from "@/context/AppSessionContext";
import {
  consumePendingCloverRestaurantId,
  exchangeCloverCode,
  getCloverConnectUrl,
  getRestaurantId,
} from "@/lib/api";

type Phase =
  | "loading"
  | "needauth"
  | "exchanging"
  | "success"
  | "error"
  | "redirecting"
  | "appmarket_no_restaurant"
  | "invalid";

const Spinner = () => (
  <div className="mx-auto h-12 w-12 animate-spin rounded-full border-2 border-line border-t-coral" />
);

/**
 * Clover v2 OAuth callback landing page.
 *
 * Clover redirects the BROWSER here (CLOVER_REDIRECT_URI) after the merchant
 * authorizes, with query params merchant_id (sometimes merchantId on App-Market
 * launches), employee_id, client_id, and code. This page reads them and POSTs
 * to the authenticated exchange endpoint — that authenticated, tenant-scoped
 * call IS the CSRF defense, since Clover v2 OAuth has no state parameter.
 *
 * The page owns its own auth states (sign-in prompt, etc.) rather than sitting
 * behind a route wrapper: a wrapper would redirect and destroy the short-lived
 * query params before we can use them.
 */
const CloverCallbackPage = () => {
  const [params] = useSearchParams();
  const { authLoaded, isSignedIn, bootstrapping } = useAppSession();

  const code = params.get("code");
  // App-Market launches may send merchantId instead of merchant_id.
  const merchantId = params.get("merchant_id") || params.get("merchantId");

  const [phase, setPhase] = useState<Phase>("loading");
  const [merchant, setMerchant] = useState("");
  const [errorDetail, setErrorDetail] = useState("");

  // CRITICAL: the auth code is single-use. React 18 StrictMode double-mounts
  // effects in dev, and a duplicate exchange would 502 and paint an error over
  // a success. This ref is checked-and-set synchronously before any await, so
  // the network call fires exactly once.
  const firedRef = useRef(false);

  useEffect(() => {
    if (!authLoaded) return;
    // Wait for the session to settle before deciding anything.
    if (isSignedIn && bootstrapping) return;
    if (firedRef.current) return;

    if (!isSignedIn) {
      // Do NOT auto-redirect to /login — that would silently eat the flow and
      // the short-lived code would expire. Let the user sign in and retry from
      // Integrations. We also don't consume the pending id here, so it survives.
      setPhase("needauth");
      return;
    }

    // Signed in: guard the single-use side effect BEFORE awaiting anything.
    firedRef.current = true;

    const restaurantId = consumePendingCloverRestaurantId() ?? getRestaurantId();

    if (code && merchantId && restaurantId) {
      setMerchant(merchantId);
      setPhase("exchanging");
      exchangeCloverCode({ restaurant_id: restaurantId, code, merchant_id: merchantId })
        .then(() => setPhase("success"))
        .catch((err: any) => {
          setErrorDetail(err?.response?.data?.detail || "");
          setPhase("error");
        });
      return;
    }

    // App-Market launch: merchant_id but no code. The app initiates the
    // authorize redirect itself.
    if (merchantId && !code) {
      if (restaurantId) {
        setPhase("redirecting");
        getCloverConnectUrl(restaurantId)
          .then((res) => {
            const url = res?.data?.connect_url;
            if (url) {
              window.location.href = url;
            } else {
              setPhase("error");
            }
          })
          .catch((err: any) => {
            setErrorDetail(err?.response?.data?.detail || "");
            setPhase("error");
          });
      } else {
        setPhase("appmarket_no_restaurant");
      }
      return;
    }

    // Neither code nor merchant_id — a direct/invalid visit.
    setPhase("invalid");
  }, [authLoaded, isSignedIn, bootstrapping, code, merchantId]);

  return (
    <div className="dash dash-surface min-h-screen flex items-center justify-center px-6">
      <div className="dash-card text-center space-y-4 px-8 py-10 max-w-sm">
        {(phase === "loading" || phase === "exchanging" || phase === "redirecting") && (
          <>
            <Spinner />
            <h1 className="text-2xl font-display font-bold">
              {phase === "redirecting"
                ? "Redirecting to Clover…"
                : phase === "exchanging"
                  ? "Connecting your Clover account…"
                  : "Finishing Clover connection…"}
            </h1>
          </>
        )}

        {phase === "needauth" && (
          <>
            <h1 className="text-2xl font-display font-bold">Please sign in to finish connecting Clover</h1>
            <p className="text-ink-soft text-sm">
              Sign in and reconnect Clover from the Integrations page.
            </p>
            <Link
              to="/login"
              className="inline-flex items-center justify-center rounded-md bg-coral px-5 py-2 text-sm font-medium text-white hover:bg-coral-deep"
            >
              Sign in
            </Link>
          </>
        )}

        {phase === "success" && (
          <>
            <div className="w-16 h-16 rounded-full bg-success/10 flex items-center justify-center mx-auto">
              <CheckCircle2 className="w-8 h-8 text-success" />
            </div>
            <h1 className="text-2xl font-display font-bold">Clover connected</h1>
            {merchant && (
              <p className="text-ink-soft text-sm">
                Merchant ID: <span className="font-mono">{merchant}</span>
              </p>
            )}
            <Link
              to="/dashboard/integrations"
              className="inline-flex items-center justify-center rounded-md bg-coral px-5 py-2 text-sm font-medium text-white hover:bg-coral-deep"
            >
              Back to Integrations
            </Link>
          </>
        )}

        {phase === "error" && (
          <>
            <div className="w-16 h-16 rounded-full bg-destructive/10 flex items-center justify-center mx-auto">
              <XCircle className="w-8 h-8 text-destructive" />
            </div>
            <h1 className="text-2xl font-display font-bold">Clover connection failed</h1>
            <p className="text-ink-soft text-sm">
              {errorDetail
                ? errorDetail
                : "The authorization may have expired — please try connecting again from Integrations."}
            </p>
            <Link
              to="/dashboard/integrations"
              className="inline-flex items-center justify-center rounded-md bg-coral px-5 py-2 text-sm font-medium text-white hover:bg-coral-deep"
            >
              Back to Integrations
            </Link>
          </>
        )}

        {phase === "appmarket_no_restaurant" && (
          <>
            <h1 className="text-2xl font-display font-bold">Almost there</h1>
            <p className="text-ink-soft text-sm">
              Open your Duuutah dashboard and connect Clover from the Integrations page.
            </p>
            <Link
              to="/dashboard/integrations"
              className="inline-flex items-center justify-center rounded-md bg-coral px-5 py-2 text-sm font-medium text-white hover:bg-coral-deep"
            >
              Go to Integrations
            </Link>
          </>
        )}

        {phase === "invalid" && (
          <>
            <h1 className="text-2xl font-display font-bold">Nothing to connect</h1>
            <p className="text-ink-soft text-sm">
              This page completes a Clover connection. Start one from the Integrations page.
            </p>
            <Link
              to="/dashboard/integrations"
              className="inline-flex items-center justify-center rounded-md bg-coral px-5 py-2 text-sm font-medium text-white hover:bg-coral-deep"
            >
              Go to Integrations
            </Link>
          </>
        )}

        <p className="text-xs text-ink-soft pt-4">Powered by Duuutah AI</p>
      </div>
    </div>
  );
};

export default CloverCallbackPage;
