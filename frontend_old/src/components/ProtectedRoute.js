import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@clerk/clerk-react";
import { useAppSession } from "@/context/AppSessionContext";

export default function ProtectedRoute({ children }) {
  const location = useLocation();
  const { isLoaded, isSignedIn } = useAuth();
  const { bootstrapping } = useAppSession();

  if (!isLoaded || bootstrapping) {
    return <div className="min-h-screen bg-background flex items-center justify-center text-sm text-muted-foreground">Loading your workspace...</div>;
  }

  if (!isSignedIn) {
    return <Navigate to="/sign-in" replace state={{ from: location }} />;
  }

  return children;
}
