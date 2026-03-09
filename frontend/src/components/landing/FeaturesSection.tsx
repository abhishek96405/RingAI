import { Phone, Brain, Globe, CreditCard, BarChart3, Clock, ShieldCheck, Utensils } from "lucide-react";
import { motion } from "framer-motion";

const features = [
  { icon: Phone, title: "AI Phone Agent", description: "Answers every call instantly. Takes orders, handles questions, and routes complex requests to staff." },
  { icon: Brain, title: "Smart Understanding", description: "Understands accents, menu modifications, allergies, and complex orders with human-level accuracy." },
  { icon: Globe, title: "Multilingual Support", description: "Speaks 30+ languages natively. Serve every customer in their preferred language, automatically." },
  { icon: Utensils, title: "Menu Intelligence", description: "Learns your full menu, specials, pricing, and inventory. Suggests upsells that feel natural." },
  { icon: CreditCard, title: "POS Integration", description: "Sends orders directly to your POS system. No manual entry, no errors, no delays." },
  { icon: BarChart3, title: "Real-Time Analytics", description: "Track call volume, order value, peak hours, and customer satisfaction in a live dashboard." },
  { icon: Clock, title: "24/7 Availability", description: "Never miss a late-night craving or early reservation. Your AI receptionist never sleeps." },
  { icon: ShieldCheck, title: "Enterprise Security", description: "SOC 2 compliant. Encrypted calls, secure payment handling, and full audit trails." },
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
            Everything Your Restaurant Phone Needs
          </h2>
          <p className="text-base text-muted-foreground">
            From answering calls to processing payments, RingAI handles it all so your team can focus on food.
          </p>
        </motion.div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
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
      </div>
    </section>
  );
};

export default FeaturesSection;
