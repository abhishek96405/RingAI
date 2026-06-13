import { useSearchParams, Link } from "react-router-dom";
import { CheckCircle2, XCircle } from "lucide-react";

/**
 * Square OAuth landing page — DISPLAY ONLY.
 *
 * Unlike Clover (which has no state param and so does the token exchange in the
 * browser), Square carries a state param and the BACKEND square_callback does
 * the exchange + token storage. It then redirects the browser here with the
 * outcome in query params. This page only reflects status/merchant_id/reason —
 * no exchange call, no auth handling, no StrictMode fire-once guard.
 */
const REASON_MESSAGES: Record<string, string> = {
  missing_code: "No authorization code was returned by Square.",
  invalid_state:
    "This connection link has expired or is invalid. Please start the connection again from Integrations.",
  exchange_failed:
    "We couldn't finish connecting your Square account. Please try again.",
};

const SquareCallbackPage = () => {
  const [params] = useSearchParams();

  const status = params.get("status");
  const merchantId = params.get("merchant_id");
  const reason = params.get("reason");

  const connected = status === "connected";
  const errorMessage =
    (reason && REASON_MESSAGES[reason]) ||
    "Something went wrong connecting Square. Please try again from Integrations.";

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="text-center space-y-4 px-6 max-w-sm">
        {connected ? (
          <>
            <div className="w-16 h-16 rounded-full bg-success/10 flex items-center justify-center mx-auto">
              <CheckCircle2 className="w-8 h-8 text-success" />
            </div>
            <h1 className="text-2xl font-bold">Square connected</h1>
            {merchantId && (
              <p className="text-muted-foreground text-sm">
                Merchant ID: <span className="font-mono">{merchantId}</span>
              </p>
            )}
            <Link
              to="/dashboard/integrations"
              className="inline-flex items-center justify-center rounded-md bg-foreground px-4 py-2 text-sm font-medium text-background transition-opacity hover:opacity-90"
            >
              Back to Integrations
            </Link>
          </>
        ) : (
          <>
            <div className="w-16 h-16 rounded-full bg-destructive/10 flex items-center justify-center mx-auto">
              <XCircle className="w-8 h-8 text-destructive" />
            </div>
            <h1 className="text-2xl font-bold">Square connection failed</h1>
            <p className="text-muted-foreground text-sm">{errorMessage}</p>
            <Link
              to="/dashboard/integrations"
              className="inline-flex items-center justify-center rounded-md bg-foreground px-4 py-2 text-sm font-medium text-background transition-opacity hover:opacity-90"
            >
              Back to Integrations
            </Link>
          </>
        )}

        <p className="text-xs text-muted-foreground pt-4">Powered by Duuutah AI</p>
      </div>
    </div>
  );
};

export default SquareCallbackPage;
