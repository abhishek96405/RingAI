import { motion } from "framer-motion";
import { HelpCircle } from "lucide-react";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";

const faqs = [
  {
    q: "How does RingAI handle phone orders?",
    a: "RingAI uses advanced natural language processing to understand callers, take orders from your menu, handle modifications and special requests, and confirm everything before ending the call. Orders are sent directly to your POS or dashboard in real time.",
  },
  {
    q: "How long does setup take?",
    a: "Most restaurants are fully set up in under 10 minutes. Just upload your menu, configure your greeting and hours, connect your phone number, and you're live. No technical expertise required.",
  },
  {
    q: "Can RingAI handle multiple calls at once?",
    a: "Absolutely. Unlike a human receptionist, RingAI can handle unlimited concurrent calls — so you'll never miss an order during peak hours again.",
  },
  {
    q: "Does it work with my existing phone number?",
    a: "Yes. RingAI integrates with your existing phone system through call forwarding. You keep your current number — customers won't notice any change except better, faster service.",
  },
  {
    q: "What happens if the AI can't understand a caller?",
    a: "RingAI is designed to gracefully handle edge cases. If it's unsure, it will politely ask for clarification. You can also set a fallback to transfer to a staff member for complex requests.",
  },
  {
    q: "Is there a contract or can I cancel anytime?",
    a: "No long-term contracts. All plans are month-to-month and you can cancel or change your plan at any time from your dashboard. We also offer a 14-day free trial.",
  },
];

const FAQSection = () => {
  return (
    <section id="faq" className="section-padding relative overflow-hidden">
      <div className="absolute top-1/2 right-0 w-80 h-80 rounded-full bg-primary/5 blur-3xl -translate-y-1/2" />

      <div className="container-tight relative z-10">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="text-center mb-10"
        >
          <span className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-accent text-accent-foreground text-xs font-semibold tracking-wide uppercase mb-3">
            <HelpCircle className="w-3.5 h-3.5" />
            FAQ
          </span>
          <h2 className="font-display font-extrabold text-3xl md:text-4xl text-foreground mb-3">
            Got Questions?{" "}
            <span className="text-gradient">We've Got Answers</span>
          </h2>
          <p className="text-muted-foreground text-base max-w-xl mx-auto">
            Everything you need to know about RingAI before getting started.
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5, delay: 0.2 }}
          className="premium-card p-2 md:p-3"
        >
          <Accordion type="single" collapsible className="w-full">
            {faqs.map((faq, i) => (
              <AccordionItem
                key={i}
                value={`item-${i}`}
                className="border-border/40 px-4 md:px-5"
              >
                <AccordionTrigger className="text-left font-display font-semibold text-sm md:text-base hover:no-underline py-4 text-foreground">
                  {faq.q}
                </AccordionTrigger>
                <AccordionContent className="text-muted-foreground text-sm leading-relaxed pb-4">
                  {faq.a}
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        </motion.div>
      </div>
    </section>
  );
};

export default FAQSection;
