import { useNavigate } from "react-router-dom";
import { SignedIn, SignedOut, SignInButton } from "@clerk/clerk-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ArrowRight, Phone, Sparkles } from "lucide-react";
import { motion } from "framer-motion";
import { toast } from "sonner";

export const HeroSection = () => {
  const navigate = useNavigate();

  const handleDemoCall = () => {
    // Call the demo number
    toast.info("Call +1 980-351-5351 to hear ringAI in action!");
    window.open("tel:+19803515351", "_self");
  };

  return (
    <section className="relative min-h-screen flex items-center overflow-hidden bg-gradient-hero">
      {/* Decorative elements */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-20 right-[15%] w-72 h-72 rounded-full bg-primary/5 blur-3xl" />
        <div className="absolute bottom-20 left-[10%] w-96 h-96 rounded-full bg-accent/5 blur-3xl" />
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-28 pb-20 w-full">
        <div className="grid lg:grid-cols-2 gap-12 lg:gap-16 items-center">
          {/* Left: Text Content */}
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, ease: [0.4, 0, 0.2, 1] }}
            className="max-w-xl"
          >
            <Badge
              variant="secondary"
              className="mb-6 px-4 py-1.5 text-sm font-medium border border-primary/20 bg-primary-muted text-secondary-foreground"
            >
              <Sparkles className="w-3.5 h-3.5 mr-1.5" />
              #1 AI Voice Agent for Restaurants
            </Badge>

            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-heading font-bold leading-tight text-foreground">
              Never Miss a{" "}
              <span className="text-gradient-primary">Reservation</span>{" "}
              Again
            </h1>

            <p className="mt-6 text-base md:text-lg text-muted-foreground leading-relaxed max-w-lg">
              ringAI answers every call, books reservations, handles takeout orders, and answers guest questions — 24/7, with a warm, human-like voice.
            </p>

            <div className="mt-8 flex flex-col sm:flex-row gap-3">
              <SignedOut>
                <SignInButton mode="modal" forceRedirectUrl="/onboarding">
                  <Button variant="hero" size="xl">
                    Try ringAI Free
                    <ArrowRight className="w-5 h-5" />
                  </Button>
                </SignInButton>
              </SignedOut>
              <SignedIn>
                <Button variant="hero" size="xl" onClick={() => navigate("/onboarding")}>
                  Try ringAI Free
                  <ArrowRight className="w-5 h-5" />
                </Button>
              </SignedIn>
              <Button variant="hero-outline" size="xl" onClick={handleDemoCall}>
                <Phone className="w-5 h-5" />
                Hear a Demo Call
              </Button>
            </div>

            <div className="mt-10 flex items-center gap-8">
              <div className="flex flex-col">
                <span className="text-2xl font-heading font-bold text-foreground">50%</span>
                <span className="text-xs text-muted-foreground">More Phone Covers</span>
              </div>
              <div className="w-px h-10 bg-border" />
              <div className="flex flex-col">
                <span className="text-2xl font-heading font-bold text-foreground">200+</span>
                <span className="text-xs text-muted-foreground">Hours Saved/Month</span>
              </div>
              <div className="w-px h-10 bg-border" />
              <div className="flex flex-col">
                <span className="text-2xl font-heading font-bold text-foreground">96%</span>
                <span className="text-xs text-muted-foreground">Guest Satisfaction</span>
              </div>
            </div>
          </motion.div>

          {/* Right: Hero Visual - Phone Call Interface */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.8, delay: 0.2, ease: [0.4, 0, 0.2, 1] }}
            className="relative flex justify-center lg:justify-end"
          >
            <div className="relative">
              {/* Background restaurant image */}
              <div className="w-full max-w-md aspect-[4/5] rounded-2xl overflow-hidden shadow-elevated">
                <img
                  src="https://images.unsplash.com/photo-1685040235380-a42a129ade4e"
                  alt="Modern restaurant interior"
                  className="w-full h-full object-cover"
                />
                {/* Gradient overlay */}
                <div className="absolute inset-0 bg-gradient-to-t from-foreground/70 via-foreground/20 to-transparent" />
              </div>

              {/* Floating call card */}
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.6, duration: 0.5 }}
                className="absolute -bottom-6 -left-6 sm:-left-10 glass-strong rounded-xl p-4 shadow-lg max-w-[260px]"
              >
                <div className="flex items-center gap-3 mb-3">
                  <div className="relative">
                    <div className="w-10 h-10 rounded-full bg-gradient-primary flex items-center justify-center">
                      <Phone className="w-4 h-4 text-primary-foreground" />
                    </div>
                    <div className="absolute inset-0 rounded-full bg-primary/30 animate-pulse-ring" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-foreground">Incoming Call</p>
                    <p className="text-xs text-muted-foreground">ringAI answering...</p>
                  </div>
                </div>
                <div className="bg-secondary rounded-lg p-3">
                  <p className="text-xs text-foreground italic">
                    "Of course! I have a table for 4 available at 7:30pm this Saturday. Shall I book it?"
                  </p>
                </div>
                {/* Sound wave bars */}
                <div className="flex items-center gap-0.5 mt-3 justify-center">
                  {[0.4, 0.7, 1, 0.6, 0.9, 0.5, 0.8, 0.3, 0.7, 0.5, 0.9, 0.6].map((h, i) => (
                    <div
                      key={i}
                      className="w-1 bg-primary rounded-full animate-wave-pulse"
                      style={{
                        height: `${h * 20}px`,
                        animationDelay: `${i * 0.1}s`,
                      }}
                    />
                  ))}
                </div>
              </motion.div>

              {/* Floating badge - top right */}
              <motion.div
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.8, duration: 0.5 }}
                className="absolute -top-3 -right-3 sm:-right-6 glass-strong rounded-lg px-4 py-2.5 shadow-md"
              >
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-success animate-pulse" />
                  <span className="text-xs font-medium text-foreground">Live 24/7</span>
                </div>
              </motion.div>
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
};
