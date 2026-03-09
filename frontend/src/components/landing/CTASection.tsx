import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ArrowRight } from "lucide-react";
import { motion } from "framer-motion";
import ctaBg from "@/assets/cta-bg.jpg";

const CTASection = () => {
  return (
    <section className="section-padding relative overflow-hidden">
      <div className="absolute inset-0">
        <img src={ctaBg} alt="" className="w-full h-full object-cover" />
        <div className="absolute inset-0 bg-gradient-dark/80" />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 30 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        transition={{ duration: 0.7 }}
        className="container-tight relative z-10 text-center"
      >
        <motion.h2
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.2, duration: 0.5 }}
          className="font-display font-extrabold text-3xl sm:text-4xl lg:text-5xl text-primary-foreground mb-5"
        >
          Ready to Never Miss<br />a Call Again?
        </motion.h2>
        <motion.p
          initial={{ opacity: 0, y: 15 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.35, duration: 0.5 }}
          className="text-lg text-primary-foreground/70 max-w-lg mx-auto mb-7"
        >
          Join 2,000+ restaurants already using RingAI to boost revenue and delight customers.
        </motion.p>
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.5, duration: 0.5 }}
          className="flex flex-col sm:flex-row gap-3 justify-center"
        >
          <Button asChild size="lg" className="bg-primary-foreground text-foreground rounded-xl px-8 h-13 text-base font-semibold hover:bg-primary-foreground/90">
            <Link to="/signup">
              Start Free Trial
              <ArrowRight className="ml-2 w-4 h-4" />
            </Link>
          </Button>
          <Button variant="outline" size="lg" className="rounded-xl px-8 h-13 text-base font-semibold border-primary-foreground/20 text-primary-foreground hover:bg-primary-foreground/10">
            Book a Demo
          </Button>
        </motion.div>
      </motion.div>
    </section>
  );
};

export default CTASection;
