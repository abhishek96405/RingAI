import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ArrowRight, Play, Star, Zap, PhoneCall, TrendingUp, DollarSign, Calendar, Stethoscope, Scissors, Wrench, Scale, Utensils } from "lucide-react";
import { motion } from "framer-motion";

const businessTypes = [
  { icon: Utensils, label: "Restaurants", value: "restaurant" },
  { icon: Stethoscope, label: "Clinics", value: "clinic" },
  { icon: Scissors, label: "Salons", value: "salon" },
  { icon: Wrench, label: "Home Services", value: "home_services" },
  { icon: Scale, label: "Legal", value: "legal" },
];

const AnimatedDashboard = () => {
  const bars = [65, 45, 80, 55, 90, 70, 85];
  const days = ["M", "T", "W", "T", "F", "S", "S"];

  return (
    <div className="relative w-full">
      <div className="rounded-2xl overflow-hidden border border-border/30 bg-card shadow-xl">
        {/* Title bar */}
        <div className="flex items-center gap-2 px-4 py-3 border-b border-border/30 bg-muted/30">
          <div className="flex gap-1.5">
            <div className="w-3 h-3 rounded-full bg-destructive/60" />
            <div className="w-3 h-3 rounded-full bg-warning/60" />
            <div className="w-3 h-3 rounded-full bg-success/60" />
          </div>
          <span className="text-xs text-muted-foreground font-medium ml-2">RingAI Dashboard</span>
        </div>

        <div className="p-5 space-y-4">
          {/* KPI row */}
          <div className="grid grid-cols-3 gap-3">
            {[
              { icon: PhoneCall, label: "Calls Today", value: "127", color: "text-primary" },
              { icon: Calendar, label: "Bookings", value: "34", color: "text-success" },
              { icon: DollarSign, label: "Revenue", value: "$4.2k", color: "text-warning" },
            ].map((kpi, i) => (
              <motion.div
                key={kpi.label}
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.8 + i * 0.15, duration: 0.4, type: "spring" }}
                className="rounded-xl bg-muted/40 p-3 text-center"
              >
                <kpi.icon className={`w-4 h-4 mx-auto mb-1 ${kpi.color}`} />
                <motion.p
                  className="font-display font-bold text-lg"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 1.2 + i * 0.15 }}
                >
                  {kpi.value}
                </motion.p>
                <p className="text-[10px] text-muted-foreground">{kpi.label}</p>
              </motion.div>
            ))}
          </div>

          {/* Animated bar chart */}
          <div className="rounded-xl bg-muted/20 p-4">
            <p className="text-xs font-semibold text-muted-foreground mb-3">Weekly Call Volume</p>
            <div className="flex items-end gap-2 h-24">
              {bars.map((h, i) => (
                <div key={i} className="flex-1 flex flex-col items-center gap-1">
                  <motion.div
                    className="w-full rounded-t-md bg-gradient-primary"
                    initial={{ height: 0 }}
                    animate={{ height: `${h}%` }}
                    transition={{ delay: 1.5 + i * 0.1, duration: 0.6, ease: "easeOut" }}
                  />
                  <span className="text-[9px] text-muted-foreground">{days[i]}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Animated activity feed */}
          <div className="space-y-2">
            {[
              { text: "Appointment booked — Haircut 2pm", time: "Just now", dot: "bg-success" },
              { text: "New patient inquiry handled", time: "2m ago", dot: "bg-primary" },
              { text: "Service call scheduled — HVAC", time: "5m ago", dot: "bg-info" },
            ].map((item, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 2.2 + i * 0.2, duration: 0.4 }}
                className="flex items-center gap-2.5 text-xs px-3 py-2 rounded-lg bg-muted/30"
              >
                <motion.div
                  className={`w-2 h-2 rounded-full ${item.dot}`}
                  animate={{ scale: [1, 1.3, 1] }}
                  transition={{ duration: 2, repeat: Infinity, delay: i * 0.5 }}
                />
                <span className="flex-1 text-foreground/80">{item.text}</span>
                <span className="text-muted-foreground">{item.time}</span>
              </motion.div>
            ))}
          </div>
        </div>
      </div>

      {/* Floating glow */}
      <motion.div
        className="absolute -inset-4 bg-primary/10 rounded-3xl blur-2xl -z-10"
        animate={{ opacity: [0.1, 0.2, 0.1] }}
        transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
      />
    </div>
  );
};

const HeroSection = () => {
  const navigate = useNavigate();
  const [selectedBusinessType, setSelectedBusinessType] = useState<string | null>(null);

  const handleBusinessTypeSelect = (businessValue: string) => {
    setSelectedBusinessType(businessValue);
    // Navigate to signup with business_type as query parameter
    navigate(`/signup?business_type=${businessValue}`);
  };

  return (
    <section className="relative min-h-[90vh] flex items-center overflow-hidden pt-20">
      {/* Background */}
      <div className="absolute inset-0 bg-gradient-surface" />
      <motion.div
        className="absolute top-1/4 -right-32 w-96 h-96 rounded-full bg-primary/5 blur-3xl"
        animate={{ scale: [1, 1.2, 1], x: [0, 20, 0] }}
        transition={{ duration: 8, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="absolute bottom-1/4 -left-32 w-96 h-96 rounded-full bg-primary/10 blur-3xl"
        animate={{ scale: [1, 1.3, 1], y: [0, -30, 0] }}
        transition={{ duration: 10, repeat: Infinity, ease: "easeInOut", delay: 2 }}
      />

      <div className="container-wide relative z-10">
        <div className="grid lg:grid-cols-2 gap-12 items-center">
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7 }}
            className="max-w-xl"
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 0.2, duration: 0.4 }}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-accent border border-primary/10 mb-5"
            >
              <Zap className="w-4 h-4 text-accent-foreground" />
              <span className="text-sm font-medium text-accent-foreground">AI-Powered Phone Reception</span>
            </motion.div>

            <h1 className="font-display font-extrabold text-4xl sm:text-5xl lg:text-6xl leading-[1.1] tracking-tight mb-5">
              Your Business's
              <br />
              <span className="text-gradient">AI Receptionist</span>
            </h1>

            <p className="text-lg text-muted-foreground leading-relaxed mb-6 max-w-md">
              Never miss a call again. RingAI answers phones, books appointments, takes orders, and handles inquiries — 24/7, in any language.
            </p>

            {/* Business Type Selection */}
            <div className="mb-7">
              <p className="text-sm font-semibold text-foreground mb-3">Choose Your Business Type to Get Started:</p>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
                {businessTypes.map((type, i) => (
                  <motion.button
                    key={type.value}
                    initial={{ opacity: 0, scale: 0.8 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 0.4 + i * 0.1 }}
                    onClick={() => handleBusinessTypeSelect(type.value)}
                    className="flex flex-col items-center gap-2 px-3 py-3 rounded-xl bg-card hover:bg-accent border border-border hover:border-primary/30 transition-all group"
                  >
                    <type.icon className="w-6 h-6 text-primary group-hover:scale-110 transition-transform" />
                    <span className="text-xs font-medium text-center">{type.label}</span>
                  </motion.button>
                ))}
              </div>
            </div>

            <div className="flex flex-col sm:flex-row gap-3 mb-8">
              <Button asChild size="lg" className="bg-gradient-primary text-primary-foreground rounded-xl px-8 h-13 text-base font-semibold shadow-glow hover:opacity-90 transition-opacity">
                <Link to="/signup" data-testid="hero-get-started-btn">
                  Start Free Trial
                  <ArrowRight className="ml-2 w-4 h-4" />
                </Link>
              </Button>
              <Button variant="outline" size="lg" className="rounded-xl px-8 h-13 text-base font-semibold border-border/60">
                <Play className="mr-2 w-4 h-4" />
                Watch Demo
              </Button>
            </div>

            <div className="flex items-center gap-6 text-sm text-muted-foreground">
              <div className="flex items-center gap-1.5">
                <div className="flex -space-x-2">
                  {[1, 2, 3, 4].map(i => (
                    <motion.div
                      key={i}
                      initial={{ opacity: 0, scale: 0 }}
                      animate={{ opacity: 1, scale: 1 }}
                      transition={{ delay: 0.8 + i * 0.1, type: "spring" }}
                      className="w-7 h-7 rounded-full bg-gradient-primary border-2 border-background"
                    />
                  ))}
                </div>
                <span className="ml-2 font-medium">5,000+ businesses</span>
              </div>
              <div className="flex items-center gap-1">
                {[1, 2, 3, 4, 5].map(i => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, rotateY: 90 }}
                    animate={{ opacity: 1, rotateY: 0 }}
                    transition={{ delay: 1.2 + i * 0.08 }}
                  >
                    <Star className="w-4 h-4 fill-warning text-warning" />
                  </motion.div>
                ))}
                <span className="ml-1 font-medium">4.9/5</span>
              </div>
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.3 }}
            className="hidden lg:block relative"
          >
            <AnimatedDashboard />
          </motion.div>
        </div>
      </div>
    </section>
  );
};

export default HeroSection;
