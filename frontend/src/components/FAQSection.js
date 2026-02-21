import { motion } from "framer-motion";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";

const faqs = [
  {
    question: "What are the benefits of using ringAI?",
    answer:
      "Restaurants using ringAI report 50% more phone reservations, 96% guest satisfaction, up to 200 hours saved monthly and 10x ROI. ringAI ensures that calls are answered promptly, reducing missed opportunities and enhancing the customer experience.",
  },
  {
    question: "How long does setup take?",
    answer:
      "Setting up ringAI typically requires less than 30 minutes. Our onboarding process is streamlined, allowing restaurants to go live on the same day. We handle the technical setup so you can focus on what you do best.",
  },
  {
    question: "Can I customize the AI voice and responses?",
    answer:
      "Yes! ringAI offers a selection of premium voices, including various accents, to match your brand's tone. You can customize greetings, responses, hold music, and even the AI's personality to align with your restaurant's unique style.",
  },
  {
    question: "How many calls can ringAI handle at once?",
    answer:
      "ringAI can handle an unlimited number of simultaneous calls, ensuring that no customer is ever left waiting — even during peak hours on a Friday night. Every call gets the same warm, attentive service.",
  },
  {
    question: "Does ringAI integrate with reservation platforms?",
    answer:
      "Yes. ringAI integrates seamlessly with OpenTable, Resy, SevenRooms, and more, allowing for automated reservation management. Guests can book, modify, or cancel reservations over the phone without staff involvement.",
  },
  {
    question: "What happens if ringAI can't answer a question?",
    answer:
      "If ringAI encounters a query it can't address, it automatically forwards the call to a human staff member or sends a text message with relevant contact information, ensuring the caller always receives assistance.",
  },
  {
    question: "Can I keep my existing phone number?",
    answer:
      "Absolutely. ringAI works with your existing phone number through simple call forwarding. There's no need to change your number — your guests won't notice any difference except better service.",
  },
];

export const FAQSection = () => {
  return (
    <section id="faq" className="py-24 lg:py-32 bg-gradient-subtle">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.6 }}
          className="text-center mb-12"
        >
          <span className="text-sm font-medium text-primary tracking-wide uppercase">
            FAQ
          </span>
          <h2 className="mt-3 text-3xl sm:text-4xl lg:text-5xl font-heading font-bold text-foreground leading-tight">
            Frequently Asked Questions
          </h2>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-60px" }}
          transition={{ duration: 0.6, delay: 0.1 }}
        >
          <Accordion type="single" collapsible className="space-y-3">
            {faqs.map((faq, i) => (
              <AccordionItem
                key={i}
                value={`item-${i}`}
                className="border border-border rounded-lg bg-card px-5 data-[state=open]:shadow-md transition-shadow"
              >
                <AccordionTrigger className="text-left font-heading font-medium text-foreground hover:no-underline py-4 text-base">
                  {faq.question}
                </AccordionTrigger>
                <AccordionContent className="text-sm text-muted-foreground leading-relaxed pb-4">
                  {faq.answer}
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        </motion.div>
      </div>
    </section>
  );
};
