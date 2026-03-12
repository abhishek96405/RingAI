import { Link } from "react-router-dom";
import { SignIn } from "@clerk/clerk-react";
import { Phone } from "lucide-react";
import { motion } from "framer-motion";

const clerkAppearance = {
  elements: {
    rootBox: "w-full !block",
    cardBox: "w-full !block",
    card: "ringai-clerk-card !w-full !shadow-none !border-0 !bg-transparent !p-0",
    main: "w-full !p-0",
    header: "hidden",
    headerTitle: "hidden",
    headerSubtitle: "hidden",
    socialButtonsBlockButton: "ringai-clerk-social-btn !h-11 !rounded-xl !text-sm !font-medium",
    socialButtonsBlockButtonText: "!text-sm !font-medium",
    form: "!gap-4",
    formFieldRow: "!gap-2",
    formFieldLabel: "!text-sm !font-medium !text-foreground !mb-1.5",
    formFieldInput: "ringai-clerk-input !h-11 !rounded-xl !text-sm",
    formButtonPrimary: "ringai-clerk-primary-btn !h-11 !rounded-xl !text-sm !font-medium",
    footerActionLink: "!text-primary hover:!text-primary",
    dividerLine: "!bg-border",
    dividerText: "!text-muted-foreground !text-xs",
    identityPreviewText: "!text-sm",
    formResendCodeLink: "!text-primary hover:!text-primary",
    otpCodeFieldInput: "ringai-clerk-otp-input !h-11 !w-11 !min-w-11 !rounded-xl !text-base !font-semibold !text-center !px-0",
    alertText: "!text-sm",
    formFieldSuccessText: "!text-sm",
    formFieldWarningText: "!text-sm",
    formFieldErrorText: "!text-sm",
    footer: "!pt-4",
    footerAction: "!text-sm",
    footerActionText: "!text-sm",
  },
};

const Login = () => {
  return (
    <div className="min-h-screen flex bg-background">
      <div className="flex-1 flex items-start lg:items-center justify-center px-6 py-8 md:px-8 md:py-10">
        <div className="w-full max-w-sm">
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5 }}
          >
            <Link to="/" className="flex items-center gap-2.5 mb-10">
              <motion.div
                className="w-9 h-9 rounded-xl bg-gradient-primary flex items-center justify-center"
                whileHover={{ scale: 1.1, rotate: 5 }}
                transition={{ type: "spring", stiffness: 300 }}
              >
                <Phone className="w-4 h-4 text-primary-foreground" />
              </motion.div>
              <span className="font-display font-bold text-xl">
                Ring<span className="text-gradient">AI</span>
              </span>
            </Link>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
          >
            <h1 className="font-display font-extrabold text-2xl mb-2">Welcome back</h1>
            <p className="text-sm text-muted-foreground mb-8">
              Sign in to your RingAI dashboard.
            </p>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.2 }}
          >
            <div className="ringai-auth-shell">
              <SignIn
                routing="path"
                path="/login"
                signUpUrl="/signup"
                forceRedirectUrl="/dashboard"
                fallbackRedirectUrl="/dashboard"
                appearance={clerkAppearance}
              />
            </div>
          </motion.div>
        </div>
      </div>

      <div className="hidden lg:flex flex-1 items-center justify-center bg-gradient-dark relative overflow-hidden">
        <motion.div
          className="absolute top-1/3 left-1/4 w-72 h-72 rounded-full bg-primary/15 blur-3xl"
          animate={{ scale: [1, 1.2, 1], opacity: [0.15, 0.25, 0.15] }}
          transition={{ duration: 6, repeat: Infinity, ease: "easeInOut" }}
        />
        <motion.div
          className="absolute bottom-1/3 right-1/4 w-56 h-56 rounded-full bg-primary/10 blur-3xl"
          animate={{ scale: [1, 1.3, 1], opacity: [0.1, 0.2, 0.1] }}
          transition={{ duration: 8, repeat: Infinity, ease: "easeInOut", delay: 2 }}
        />
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.8, delay: 0.3 }}
          className="relative z-10 text-center max-w-md px-8"
        >
          <motion.div
            className="w-20 h-20 rounded-3xl bg-gradient-primary mx-auto mb-8 flex items-center justify-center shadow-glow"
            animate={{ y: [0, -15, 0] }}
            transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
          >
            <Phone className="w-10 h-10 text-primary-foreground" />
          </motion.div>
          <motion.h2
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.5, duration: 0.6 }}
            className="font-display font-bold text-2xl text-primary-foreground mb-3"
          >
            Your AI Receptionist Awaits
          </motion.h2>
          <motion.p
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.65, duration: 0.6 }}
            className="text-primary-foreground/60 text-sm"
          >
            Manage calls, orders, and analytics from one powerful dashboard.
          </motion.p>
        </motion.div>
      </div>
    </div>
  );
};

export default Login;