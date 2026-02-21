import { motion } from "framer-motion";
import { Card } from "@/components/ui/card";
import { ExternalLink } from "lucide-react";

const integrations = [
  {
    name: "OpenTable",
    description: "Automated reservation management",
    letter: "OT",
    color: "bg-[hsl(0_65%_48%)]" ,
  },
  {
    name: "Resy",
    description: "Seamless table booking sync",
    letter: "R",
    color: "bg-[hsl(220_60%_50%)]" ,
  },
  {
    name: "Toast POS",
    description: "Order & menu integration",
    letter: "T",
    color: "bg-accent",
  },
  {
    name: "Yelp",
    description: "Review & listing management",
    letter: "Y",
    color: "bg-[hsl(0_72%_51%)]" ,
  },
  {
    name: "SevenRooms",
    description: "Guest experience platform",
    letter: "7R",
    color: "bg-primary" ,
  },
  {
    name: "Square",
    description: "Payment & POS integration",
    letter: "S",
    color: "bg-foreground" ,
  },
];

export const IntegrationsSection = () => {
  return (
    <section className="py-24 lg:py-32 bg-background">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.6 }}
          className="text-center max-w-2xl mx-auto mb-16"
        >
          <span className="text-sm font-medium text-primary tracking-wide uppercase">
            Integrations
          </span>
          <h2 className="mt-3 text-3xl sm:text-4xl lg:text-5xl font-heading font-bold text-foreground leading-tight">
            Works With Your Stack
          </h2>
          <p className="mt-4 text-base md:text-lg text-muted-foreground">
            Seamlessly connects with the tools your restaurant already uses.
          </p>
        </motion.div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {integrations.map((integration, i) => (
            <motion.div
              key={integration.name}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ delay: i * 0.08, duration: 0.5 }}
            >
              <Card className="group relative h-full p-5 flex items-center gap-4 border-border bg-card hover:shadow-md transition-all duration-300 hover:-translate-y-0.5 cursor-pointer">
                <div className={`w-12 h-12 rounded-xl ${integration.color} flex items-center justify-center flex-shrink-0`}>
                  <span className="text-sm font-heading font-bold text-primary-foreground">
                    {integration.letter}
                  </span>
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="font-heading font-semibold text-foreground flex items-center gap-2">
                    {integration.name}
                    <ExternalLink className="w-3.5 h-3.5 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                  </h3>
                  <p className="text-sm text-muted-foreground">
                    {integration.description}
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
