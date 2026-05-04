import { CheckCircle2 } from "lucide-react";
import { useSearchParams, Link } from "react-router-dom";

const PaymentSuccessPage = () => {
  const [params] = useSearchParams();
  const cancelled = params.get("cancelled") === "true";

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="text-center space-y-4 px-6 max-w-sm">
        {cancelled ? (
          <>
            <div className="w-16 h-16 rounded-full bg-muted flex items-center justify-center mx-auto">
              <span className="text-2xl">✕</span>
            </div>
            <h1 className="text-2xl font-bold">Payment Cancelled</h1>
            <p className="text-muted-foreground text-sm">
              Your order is still placed — you can pay at pickup.
            </p>
          </>
        ) : (
          <>
            <div className="w-16 h-16 rounded-full bg-success/10 flex items-center justify-center mx-auto">
              <CheckCircle2 className="w-8 h-8 text-success" />
            </div>
            <h1 className="text-2xl font-bold">Payment Received!</h1>
            <p className="text-muted-foreground text-sm">
              Your order is confirmed and being prepared. You'll receive a text confirmation shortly.
            </p>
          </>
        )}
        <p className="text-xs text-muted-foreground pt-4">Powered by Duuutah AI</p>
      </div>
    </div>
  );
};

export default PaymentSuccessPage;