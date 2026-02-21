import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { SignedIn, SignedOut, SignInButton } from "@clerk/clerk-react";
import { motion } from "framer-motion";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Check, Sparkles } from "lucide-react";
import { toast } from "sonner";

const plans = [
  {
    name: "Starter",
    description: "Perfect for single-location restaurants getting started",
    priceMonthly: 199,
    priceYearly: 169,
    features: [
      "Up to 500 calls/month",
      "Reservation booking",
      "FAQ handling",
      "Basic analytics",
      "Email support",
      "1 location",
    ],
    cta: "Start Free Trial",
    popular: false,
  },
  {
    name: "Professional",
    description: "For busy restaurants that need the full AI experience",
    priceMonthly: 399,
    priceYearly: 339,
    features: [
      "Unlimited calls",
      "All Starter features",
      "OpenTable & Resy integration",
      "VIP call routing",
      "Smart alerts",
      "Advanced analytics",
      "Priority support",
      "Up to 3 locations",
    ],
    cta: "Start Free Trial",
    popular: true,
  },
  {
    name: "Enterprise",
    description: "For restaurant groups and large hospitality brands",
    priceMonthly: null,
    priceYearly: null,
    features: [
      "Everything in Professional",
      "Unlimited locations",
      "Cross-sell between venues",
      "Custom AI voice & persona",
      "Dedicated account manager",
      "Custom integrations",
      "SLA guarantee",
      "White-label options",
    ],
    cta: "Contact Sales",
    popular: false,
  },
];

export const PricingSection = () => {
  const [annual, setAnnual] = useState(false);
  const navigate = useNavigate();

  const handleCTA = (cta) => {
    if (cta === "Contact Sales") {
      toast.info("Contact us at sales@ringai.com");
      window.open("mailto:sales@ringai.com?subject=Enterprise%20Inquiry", "_blank");
    }
  };

  return (
    <section id="pricing" className="py-24 lg:py-32 bg-background">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.6 }}
          className="text-center max-w-2xl mx-auto mb-12"
        >
          <span className="text-sm font-medium text-primary tracking-wide uppercase">
            Pricing
          </span>
          <h2 className="mt-3 text-3xl sm:text-4xl lg:text-5xl font-heading font-bold text-foreground leading-tight">
            Simple, Transparent Pricing
          </h2>
          <p className="mt-4 text-base md:text-lg text-muted-foreground">
            Start your 14-day free trial. No credit card required.
          </p>

          {/* Toggle */}
          <div className="mt-8 flex items-center justify-center gap-3">
            <Label htmlFor="billing" className="text-sm text-muted-foreground">
              Monthly
            </Label>
            <Switch
              id="billing"
              checked={annual}
              onCheckedChange={setAnnual}
            />
            <Label htmlFor="billing" className="text-sm text-muted-foreground">
              Annual
            </Label>
            {annual && (
              <Badge variant="secondary" className="border-primary/20 text-primary text-xs">
                Save 15%
              </Badge>
            )}
          </div>
        </motion.div>

        <div className="grid md:grid-cols-3 gap-6 max-w-5xl mx-auto">
          {plans.map((plan, i) => (
            <motion.div
              key={plan.name}
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ delay: i * 0.1, duration: 0.5 }}
              className="flex"
            >
              <Card
                className={`relative flex flex-col w-full p-6 lg:p-8 border transition-all duration-300 hover:shadow-lg ${
                  plan.popular
                    ? "border-primary shadow-glow-primary bg-card scale-[1.02]"
                    : "border-border bg-card"
                }`}
              >
                {plan.popular && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                    <Badge className="bg-primary text-primary-foreground shadow-sm">
                      <Sparkles className="w-3 h-3 mr-1" />
                      Most Popular
                    </Badge>
                  </div>
                )}

                <div className="mb-6">
                  <h3 className="text-lg font-heading font-semibold text-foreground">
                    {plan.name}
                  </h3>
                  <p className="text-sm text-muted-foreground mt-1">
                    {plan.description}
                  </p>
                </div>

                <div className="mb-6">
                  {plan.priceMonthly ? (
                    <div className="flex items-end gap-1">
                      <span className="text-4xl font-heading font-bold text-foreground">
                        ${annual ? plan.priceYearly : plan.priceMonthly}
                      </span>
                      <span className="text-sm text-muted-foreground mb-1">
                        /month
                      </span>
                    </div>
                  ) : (
                    <span className="text-4xl font-heading font-bold text-foreground">
                      Custom
                    </span>
                  )}
                </div>

                <ul className="space-y-3 mb-8 flex-1">
                  {plan.features.map((feature) => (
                    <li key={feature} className="flex items-start gap-2.5">
                      <Check className="w-4 h-4 text-primary flex-shrink-0 mt-0.5" />
                      <span className="text-sm text-foreground">{feature}</span>
                    </li>
                  ))}
                </ul>

                {plan.cta === "Contact Sales" ? (
                  <Button
                    variant="outline"
                    size="lg"
                    className="w-full mt-auto"
                    onClick={() => handleCTA(plan.cta)}
                  >
                    {plan.cta}
                  </Button>
                ) : (
                  <>
                    <SignedOut>
                      <SignInButton mode="modal" forceRedirectUrl="/onboarding">
                        <Button
                          variant={plan.popular ? "premium" : "outline"}
                          size="lg"
                          className="w-full mt-auto"
                        >
                          {plan.cta}
                        </Button>
                      </SignInButton>
                    </SignedOut>
                    <SignedIn>
                      <Button
                        variant={plan.popular ? "premium" : "outline"}
                        size="lg"
                        className="w-full mt-auto"
                        onClick={() => navigate("/onboarding")}
                      >
                        {plan.cta}
                      </Button>
                    </SignedIn>
                  </>
                )}
              </Card>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
};
