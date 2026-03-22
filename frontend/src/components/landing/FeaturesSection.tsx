import { Phone, Brain, Globe, CreditCard, BarChart3, Clock, ShieldCheck, Calendar, Stethoscope, Scissors, Wrench, MessageSquare } from "lucide-react";
import { motion } from "framer-motion";

const features = [
  { icon: Phone, title: "AI Phone Agent", description: "Answers every call instantly. Books appointments, takes orders, handles questions, and routes complex requests to staff." },
  { icon: Brain, title: "Smart Understanding", description: "Understands accents, service preferences, special requests, and complex inquiries with human-level accuracy." },
  { icon: Globe, title: "Multilingual Support", description: "Speaks 30+ languages natively. Serve every customer in their preferred language, automatically." },
  { icon: Calendar, title: "Smart Scheduling", description: "Manages appointments, checks availability, sends reminders, and syncs with Google Calendar automatically." },
  { icon: MessageSquare, title: "SMS Notifications", description: "Sends booking confirmations, reminders 24h before appointments, and follow-up messages automatically." },
  { icon: BarChart3, title: "Real-Time Analytics", description: "Track call volume, booking rates, peak hours, and customer satisfaction in a live dashboard." },
  { icon: Clock, title: "24/7 Availability", description: "Never miss a late-night inquiry or early booking. Your AI receptionist never sleeps." },
  { icon: ShieldCheck, title: "Enterprise Security", description: "SOC 2 compliant. Encrypted calls, secure data handling, and full audit trails." },
];

const businessExamples = [
  { icon: Stethoscope, type: "Clinics", example: "Book dental cleaning for next Tuesday at 2pm" },
  { icon: Scissors, type: "Salons", example: "Schedule a haircut with Sarah on Saturday" },
  { icon: Wrench, type: "Home Services", example: "I need an HVAC repair appointment this week" },
];

const FeaturesSection = () => {
  return (
    <section id="features" className="section-padding section-divider relative">
      <div className="container-wide">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-center max-w-2xl mx-auto mb-12"
        >
          <span className="text-sm font-semibold text-primary uppercase tracking-wider">Features</span>
          <h2 className="font-display font-extrabold text-3xl sm:text-4xl mt-3 mb-3">
            Everything Your Business Phone Needs
          </h2>
          <p className="text-base text-muted-foreground">
            From answering calls to booking appointments, RingAI handles it all so your team can focus on what matters.
          </p>
        </motion.div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5 mb-16">
          {features.map((feature, i) => (
            <motion.div
              key={feature.title}
              initial={{ opacity: 0, y: 25 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.06, duration: 0.5 }}
              whileHover={{ y: -6, transition: { duration: 0.25 } }}
              className="premium-card p-5 group"
            >
              <motion.div
                className="w-11 h-11 rounded-xl bg-accent flex items-center justify-center mb-3 group-hover:bg-gradient-primary group-hover:shadow-glow transition-all duration-300"
                whileHover={{ scale: 1.1, rotate: 5 }}
                transition={{ type: "spring", stiffness: 300 }}
              >
                <feature.icon className="w-5 h-5 text-accent-foreground group-hover:text-primary-foreground transition-colors" />
              </motion.div>
              <h3 className="font-display font-bold text-base mb-1.5">{feature.title}</h3>
              <p className="text-sm text-muted-foreground leading-relaxed">{feature.description}</p>
            </motion.div>
          ))}
        </div>

        {/* Business Examples */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="bg-gradient-surface rounded-2xl p-8"
        >
          <h3 className="font-display font-bold text-xl text-center mb-6">Works for Every Business Type</h3>
          <div className="grid md:grid-cols-3 gap-6">
            {businessExamples.map((biz, i) => (
              <motion.div
                key={biz.type}
                initial={{ opacity: 0, x: -20 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1 }}
                className="flex items-start gap-4 p-4 rounded-xl bg-card border border-border/50"
              >
                <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                  <biz.icon className="w-5 h-5 text-primary" />
                </div>
                <div>
                  <p className="font-semibold text-sm mb-1">{biz.type}</p>
                  <p className="text-xs text-muted-foreground italic">"{biz.example}"</p>
                </div>
              </motion.div>
            ))}
          </div>
        </motion.div>
      </div>
    </section>
  );
};

export default FeaturesSection;
