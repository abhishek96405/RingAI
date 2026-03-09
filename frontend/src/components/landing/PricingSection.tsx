import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Check, ArrowRight } from "lucide-react";
import { motion } from "framer-motion";

const plans = [
  {
    name: "Starter",
    price: "$99",
    period: "/month",
    description: "Perfect for small restaurants getting started with AI.",
    features: ["Up to 200 calls/month", "1 phone number", "Basic menu support", "Email support", "Standard analytics"],
    cta: "Start Free Trial",
    popular: false,
  },
  {
    name: "Professional",
    price: "$249",
    period: "/month",
    description: "For growing restaurants that need the full power of AI.",
    features: ["Up to 1,000 calls/month", "3 phone numbers", "Full menu + upselling", "POS integration", "Priority support", "Advanced analytics", "Multilingual support"],
    cta: "Start Free Trial",
    popular: true,
  },
  {
    name: "Enterprise",
    price: "Custom",
    period: "",
    description: "For restaurant chains and high-volume operations.",
    features: ["Unlimited calls", "Unlimited numbers", "Custom AI training", "Multi-location support", "Dedicated account manager", "Custom integrations", "SLA guarantee", "White-label option"],
    cta: "Contact Sales",
    popular: false,
  },
];

const PricingSection = () => {
  return (
    <section id="pricing" className="section-padding section-divider relative">
      <div className="container-wide">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-center max-w-2xl mx-auto mb-12"
        >
          <span className="text-sm font-semibold text-primary uppercase tracking-wider">Pricing</span>
          <h2 className="font-display font-extrabold text-3xl sm:text-4xl mt-3 mb-3">
            Simple, Transparent Pricing
          </h2>
          <p className="text-base text-muted-foreground">
            Start free. Scale as you grow. No hidden fees, no long-term contracts.
          </p>
        </motion.div>

        <div className="grid md:grid-cols-3 gap-6 max-w-5xl mx-auto">
          {plans.map((plan, i) => (
            <motion.div
              key={plan.name}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.12, duration: 0.5 }}
              whileHover={{ y: -6 }}
              className={`premium-card p-7 relative ${
                plan.popular
                  ? "border-primary/30 shadow-glow ring-1 ring-primary/10 scale-[1.03]"
                  : ""
              }`}
            >
              {plan.popular && (
                <motion.div
                  initial={{ opacity: 0, scale: 0.8 }}
                  whileInView={{ opacity: 1, scale: 1 }}
                  viewport={{ once: true }}
                  transition={{ delay: 0.4, type: "spring", stiffness: 200 }}
                  className="absolute -top-3.5 left-1/2 -translate-x-1/2 px-4 py-1 rounded-full bg-gradient-primary text-primary-foreground text-xs font-bold uppercase tracking-wider"
                >
                  Most Popular
                </motion.div>
              )}
              <div className="mb-5">
                <h3 className="font-display font-bold text-xl mb-1.5">{plan.name}</h3>
                <p className="text-sm text-muted-foreground">{plan.description}</p>
              </div>
              <div className="mb-5">
                <span className="font-display font-extrabold text-4xl">{plan.price}</span>
                <span className="text-muted-foreground">{plan.period}</span>
              </div>
              <ul className="space-y-2.5 mb-7">
                {plan.features.map((feature, fi) => (
                  <motion.li
                    key={feature}
                    initial={{ opacity: 0, x: -10 }}
                    whileInView={{ opacity: 1, x: 0 }}
                    viewport={{ once: true }}
                    transition={{ delay: i * 0.12 + fi * 0.04 }}
                    className="flex items-start gap-2.5 text-sm"
                  >
                    <Check className="w-4 h-4 text-success mt-0.5 shrink-0" />
                    <span>{feature}</span>
                  </motion.li>
                ))}
              </ul>
              <Button
                asChild
                className={`w-full rounded-xl h-11 font-semibold ${
                  plan.popular
                    ? "bg-gradient-primary text-primary-foreground shadow-glow hover:opacity-90"
                    : ""
                }`}
                variant={plan.popular ? "default" : "outline"}
              >
                <Link to="/signup">
                  {plan.cta}
                  <ArrowRight className="ml-2 w-4 h-4" />
                </Link>
              </Button>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default PricingSection;
