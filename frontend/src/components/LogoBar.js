import { motion } from "framer-motion";

const restaurants = [
  "Bella Vista",
  "The Capital Grille",
  "Nobu",
  "Carmine's",
  "Hakkasan",
  "Per Se",
  "Masa",
  "Blue Hill",
  "Le Bernardin",
  "Eleven Madison",
];

export const LogoBar = () => {
  return (
    <section className="py-14 border-t border-b border-border bg-background">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <p className="text-center text-sm font-medium text-muted-foreground mb-8 tracking-wide uppercase">
          Trusted by 2,000+ restaurants nationwide
        </p>
        <div className="relative overflow-hidden">
          {/* Fade edges */}
          <div className="absolute left-0 top-0 bottom-0 w-24 bg-gradient-to-r from-background to-transparent z-10" />
          <div className="absolute right-0 top-0 bottom-0 w-24 bg-gradient-to-l from-background to-transparent z-10" />
          
          <motion.div
            className="flex gap-12 items-center"
            animate={{ x: ["-0%", "-50%"] }}
            transition={{ duration: 25, repeat: Infinity, ease: "linear" }}
          >
            {[...restaurants, ...restaurants].map((name, i) => (
              <div
                key={i}
                className="flex-shrink-0 px-6 py-2.5 rounded-md border border-border bg-card"
              >
                <span className="text-sm font-heading font-semibold text-muted-foreground whitespace-nowrap">
                  {name}
                </span>
              </div>
            ))}
          </motion.div>
        </div>
      </div>
    </section>
  );
};
