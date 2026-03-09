import { motion } from "framer-motion";
import { UserPlus, Settings, PhoneCall, BarChart3 } from "lucide-react";

const steps = [
  { icon: UserPlus, step: "01", title: "Sign Up & Onboard", description: "Create your account and tell us about your restaurant in minutes." },
  { icon: Settings, step: "02", title: "Configure Your AI", description: "Upload your menu, set hours, and customize your AI's personality and voice." },
  { icon: PhoneCall, step: "03", title: "Connect Your Phone", description: "Forward your calls or get a new number. We handle the rest." },
  { icon: BarChart3, step: "04", title: "Monitor & Grow", description: "Watch calls, orders, and revenue flow in real-time from your dashboard." },
];

const HowItWorksSection = () => {
  return (
    <section id="how-it-works" className="section-padding section-divider bg-gradient-surface relative">
      <div className="container-wide">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-center max-w-2xl mx-auto mb-12"
        >
          <span className="text-sm font-semibold text-primary uppercase tracking-wider">How It Works</span>
          <h2 className="font-display font-extrabold text-3xl sm:text-4xl mt-3 mb-3">
            Live in Under 10 Minutes
          </h2>
          <p className="text-base text-muted-foreground">
            No complicated setup. No IT team needed. Just sign up and start taking calls.
          </p>
        </motion.div>

        <div className="grid md:grid-cols-4 gap-6">
          {steps.map((step, i) => (
            <motion.div
              key={step.step}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.15, duration: 0.5 }}
              className="relative text-center group"
            >
              {i < steps.length - 1 && (
                <motion.div
                  className="hidden md:block absolute top-8 left-[60%] w-[80%] h-px bg-gradient-to-r from-primary/20 to-transparent"
                  initial={{ scaleX: 0 }}
                  whileInView={{ scaleX: 1 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.15 + 0.3, duration: 0.6 }}
                  style={{ transformOrigin: "left" }}
                />
              )}
              <motion.div
                className="w-14 h-14 rounded-2xl bg-gradient-primary mx-auto mb-4 flex items-center justify-center shadow-glow"
                whileHover={{ scale: 1.1, rotate: 5 }}
                transition={{ type: "spring", stiffness: 300 }}
              >
                <step.icon className="w-6 h-6 text-primary-foreground" />
              </motion.div>
              <span className="text-xs font-bold text-primary uppercase tracking-widest">Step {step.step}</span>
              <h3 className="font-display font-bold text-base mt-2 mb-1.5">{step.title}</h3>
              <p className="text-sm text-muted-foreground">{step.description}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default HowItWorksSection;
