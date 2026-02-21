import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { ArrowRight, Phone } from "lucide-react";

export const CTASection = () => {
  return (
    <section className="py-24 lg:py-32 bg-background relative overflow-hidden">
      {/* Subtle accent blobs */}
      <div className="absolute top-0 right-[20%] w-64 h-64 rounded-full bg-primary/5 blur-3xl pointer-events-none" />
      <div className="absolute bottom-0 left-[15%] w-80 h-80 rounded-full bg-accent/5 blur-3xl pointer-events-none" />

      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 relative">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.7 }}
          className="text-center"
        >
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-primary/10 text-primary text-sm font-medium mb-6">
            <Phone className="w-4 h-4" />
            Ready to transform your phone experience?
          </div>

          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-heading font-bold text-foreground leading-tight">
            Start Capturing Every{" "}
            <span className="text-gradient-primary">Reservation</span>
          </h2>

          <p className="mt-4 text-base md:text-lg text-muted-foreground max-w-2xl mx-auto">
            Join thousands of restaurants using ringAI to boost revenue, save time, and deliver 5-star phone experiences — all on autopilot.
          </p>

          <div className="mt-8 flex flex-col sm:flex-row gap-3 justify-center">
            <Button variant="hero" size="xl">
              Get Started Free
              <ArrowRight className="w-5 h-5" />
            </Button>
            <Button variant="hero-outline" size="xl">
              Schedule a Demo
            </Button>
          </div>

          <p className="mt-6 text-xs text-muted-foreground">
            14-day free trial · No credit card required · Setup in 30 minutes
          </p>
        </motion.div>
      </div>
    </section>
  );
};
