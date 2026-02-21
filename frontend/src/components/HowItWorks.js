import { motion } from "framer-motion";
import { Card } from "@/components/ui/card";
import { Phone, Bot, ClipboardCheck } from "lucide-react";

const steps = [
  {
    number: "01",
    icon: Phone,
    title: "Guest Calls In",
    subtitle: "Incoming Call",
    message: "\"Hi, can I make a reservation for 6 this Friday evening?\"",
    color: "primary",
  },
  {
    number: "02",
    icon: Bot,
    title: "ringAI Answers",
    subtitle: "AI Processing",
    message: "\"Absolutely! We have availability at 7:00pm and 8:30pm. Which works best?\"",
    color: "accent",
  },
  {
    number: "03",
    icon: ClipboardCheck,
    title: "Staff Gets Updated",
    subtitle: "Confirmation Sent",
    message: "\"Party of 6 confirmed for Friday at 7:00pm. Name: Johnson.\"",
    color: "success",
  },
];

export const HowItWorks = () => {
  return (
    <section id="how-it-works" className="py-24 lg:py-32 bg-background">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.6 }}
          className="text-center max-w-2xl mx-auto mb-16"
        >
          <span className="text-sm font-medium text-primary tracking-wide uppercase">
            How It Works
          </span>
          <h2 className="mt-3 text-3xl sm:text-4xl lg:text-5xl font-heading font-bold text-foreground leading-tight">
            Three Simple Steps
          </h2>
          <p className="mt-4 text-base md:text-lg text-muted-foreground">
            From incoming call to confirmed reservation — all without your staff lifting a finger.
          </p>
        </motion.div>

        <div className="grid md:grid-cols-3 gap-8">
          {steps.map((step, i) => (
            <motion.div
              key={step.number}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ delay: i * 0.15, duration: 0.6 }}
              className="relative"
            >
              {/* Connector line */}
              {i < steps.length - 1 && (
                <div className="hidden md:block absolute top-14 left-[calc(50%+40px)] right-[calc(-50%+40px)] border-t-2 border-dashed border-border" />
              )}

              <Card className="relative h-full p-6 flex flex-col items-center text-center border-border bg-card hover:shadow-lg transition-all duration-300 hover:-translate-y-1">
                {/* Step Number */}
                <span className="text-xs font-heading font-bold text-muted-foreground tracking-widest mb-4">
                  STEP {step.number}
                </span>

                {/* Icon */}
                <div className={`w-14 h-14 rounded-2xl flex items-center justify-center mb-5 ${
                  step.color === "primary" ? "bg-primary/10 text-primary" :
                  step.color === "accent" ? "bg-accent/10 text-accent" :
                  "bg-success/10 text-success"
                }`}>
                  <step.icon className="w-6 h-6" />
                </div>

                <h3 className="font-heading font-semibold text-lg text-foreground mb-1">
                  {step.title}
                </h3>
                <p className="text-sm text-muted-foreground mb-4">
                  {step.subtitle}
                </p>

                {/* Chat bubble */}
                <div className="w-full bg-secondary rounded-lg p-4 mt-auto">
                  <p className="text-sm text-foreground italic leading-relaxed">
                    {step.message}
                  </p>
                </div>
              </Card>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
};
