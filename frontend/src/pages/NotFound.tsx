import { useLocation } from "react-router-dom";
import { useEffect } from "react";

const NotFound = () => {
  const location = useLocation();

  useEffect(() => {
    console.error("404 Error: User attempted to access non-existent route:", location.pathname);
  }, [location.pathname]);

  return (
    <div className="dash dash-surface flex min-h-screen items-center justify-center px-6">
      <div className="dash-card text-center px-10 py-12 max-w-sm">
        <h1 className="mb-2 text-5xl font-display font-extrabold text-coral">404</h1>
        <p className="mb-5 text-lg text-ink-soft">Oops! Page not found</p>
        <a href="/" className="inline-flex items-center justify-center rounded-xl bg-coral px-5 py-2 text-sm font-medium text-white hover:bg-coral-deep">
          Return to Home
        </a>
      </div>
    </div>
  );
};

export default NotFound;
