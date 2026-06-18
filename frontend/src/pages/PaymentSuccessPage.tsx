import { CheckCircle2 } from "lucide-react";
import { useSearchParams, Link } from "react-router-dom";

const PaymentSuccessPage = () => {
  const [params] = useSearchParams();
  const cancelled = params.get("cancelled") === "true";

  return (
    <div className="dash dash-surface min-h-screen flex items-center justify-center px-6">
      <div className="dash-card text-center space-y-4 px-8 py-10 max-w-sm">
        {cancelled ? (
          <>
            <div className="w-16 h-16 rounded-full bg-line flex items-center justify-center mx-auto">
              <span className="text-2xl">✕</span>
            </div>
            <h1 className="text-2xl font-display font-bold">Payment Cancelled</h1>
            <p className="text-ink-soft text-sm">
              Your order is still placed — you can pay at pickup.
            </p>
          </>
        ) : (
          <>
            <div className="w-16 h-16 rounded-full bg-success/10 flex items-center justify-center mx-auto">
              <CheckCircle2 className="w-8 h-8 text-success" />
            </div>
            <h1 className="text-2xl font-display font-bold">Payment Received!</h1>
            <p className="text-ink-soft text-sm">
              Your order is confirmed and being prepared. You'll receive a text confirmation shortly.
            </p>
          </>
        )}
        <p className="text-xs text-ink-soft pt-4">Powered by Duuutah AI</p>
      </div>
    </div>
  );
};

export default PaymentSuccessPage;