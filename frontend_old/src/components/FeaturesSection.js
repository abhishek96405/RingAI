import { motion } from "framer-motion";
import { Card } from "@/components/ui/card";
import {
  PhoneCall,
  CalendarCheck,
  Clock,
  BarChart3,
  UserCheck,
  Globe,
  Bell,
  MessageSquare,
} from "lucide-react";

const features = [
  {
    icon: PhoneCall,
    title: "Answer Every Call",
    description:
      "Never send a guest to voicemail again. ringAI picks up instantly, 24/7, even during the busiest rush hours.",
    accent: true,
  },
  {
    icon: CalendarCheck,
    title: "Automated Reservations",
    description:
      "Seamlessly book, modify, and cancel reservations by integrating with OpenTable, Resy, and more.",
  },
  {
    icon: MessageSquare,
    title: "Handle FAQs",
    description:
      "Hours, directions, menu questions, allergens, dress code — ringAI provides instant, accurate answers.",
  },
  {
    icon: Clock,
    title: "200+ Hours Saved",
    description:
      "Free your staff from the phone so they can focus on what matters: delivering exceptional in-person hospitality.",
  },
  {
    icon: BarChart3,
    title: "Real-Time Analytics",
    description:
      "Track call volume, peak times, reservation conversions, and guest satisfaction with a beautiful dashboard.",
    accent: true,
  },
  {
    icon: UserCheck,
    title: "VIP Call Routing",
    description:
      "Automatically recognize VIP guests and route them to staff or concierge lines for white-glove service.",
  },
  {
    icon: Bell,
    title: "Smart Alerts",
    description:
      "Get real-time notifications for high-priority topics like private dining requests, complaints, or large parties.",
  },
  {
    icon: Globe,
    title: "Multi-Language Support",
    description:
      "Serve guests in their preferred language with natural-sounding AI voice in English, Spanish, French, and more.",
  },
];

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  visible: (i) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.08, duration: 0.5, ease: [0.4, 0, 0.2, 1] },
  }),
};

export const FeaturesSection = () => {
  return (
    <section id="features" className="py-24 lg:py-32 bg-gradient-subtle">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.6 }}
          className="text-center max-w-2xl mx-auto mb-16"
        >
          <span className="text-sm font-medium text-primary tracking-wide uppercase">
            Features
          </span>
          <h2 className="mt-3 text-3xl sm:text-4xl lg:text-5xl font-heading font-bold text-foreground leading-tight">
            Everything Your Front Desk Needs
          </h2>
          <p className="mt-4 text-base md:text-lg text-muted-foreground">
            Purpose-built AI that handles every call with the warmth and precision your restaurant demands.
          </p>
        </motion.div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {features.map((feature, i) => (
            <motion.div
              key={feature.title}
              custom={i}
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true, margin: "-60px" }}
              variants={fadeUp}
            >
              <Card
                className={`group relative h-full p-6 flex flex-col border transition-all duration-300 hover:shadow-lg hover:-translate-y-1 ${
                  feature.accent
                    ? "border-primary/20 bg-primary/[0.03]"
                    : "border-border bg-card"
                }`}
              >
                <div
                  className={`w-11 h-11 rounded-lg flex items-center justify-center mb-4 transition-colors duration-300 ${
                    feature.accent
                      ? "bg-primary/10 text-primary group-hover:bg-primary group-hover:text-primary-foreground"
                      : "bg-muted text-muted-foreground group-hover:bg-primary/10 group-hover:text-primary"
                  }`}
                >
                  <feature.icon className="w-5 h-5" />
                </div>
                <h3 className="font-heading font-semibold text-foreground mb-2">
                  {feature.title}
                </h3>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  {feature.description}
                </p>
              </Card>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
};
