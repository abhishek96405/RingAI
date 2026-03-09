import { motion } from "framer-motion";
import { ExternalLink } from "lucide-react";

const integrations = [
  { name: "OpenTable", desc: "Automated reservation management", initials: "OT", color: "bg-red-500" },
  { name: "Resy", desc: "Seamless table booking sync", initials: "R", color: "bg-emerald-500" },
  { name: "Toast POS", desc: "Order & menu integration", initials: "T", color: "bg-orange-500" },
  { name: "Yelp", desc: "Review & listing management", initials: "Y", color: "bg-red-600" },
  { name: "SevenRooms", desc: "Guest experience platform", initials: "7R", color: "bg-teal-500" },
  { name: "Square", desc: "Payment & POS integration", initials: "S", color: "bg-gray-800" },
];

const IntegrationsStripSection = () => {
  return (
    <section id="integrations-strip" className="section-padding section-divider relative overflow-hidden">
      <motion.div
        className="absolute top-1/2 left-0 w-80 h-80 rounded-full bg-primary/5 blur-3xl -translate-y-1/2"
        animate={{ x: [0, 20, 0], opacity: [0.05, 0.1, 0.05] }}
        transition={{ duration: 8, repeat: Infinity, ease: "easeInOut" }}
      />

      <div className="container-wide relative z-10">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="text-center mb-10"
        >
          <span className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-accent text-accent-foreground text-xs font-semibold tracking-wide uppercase mb-3">
            Integrations
          </span>
          <h2 className="font-display font-extrabold text-3xl md:text-4xl text-foreground mb-3">
            Works With Your{" "}
            <span className="text-gradient">Stack</span>
          </h2>
          <p className="text-muted-foreground text-base max-w-xl mx-auto">
            Seamlessly connects with the tools your restaurant already uses.
          </p>
        </motion.div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4 max-w-4xl mx-auto">
          {integrations.map((item, i) => (
            <motion.div
              key={item.name}
              initial={{ opacity: 0, scale: 0.95 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true }}
              transition={{ duration: 0.4, delay: i * 0.08 }}
              whileHover={{ y: -4, scale: 1.02 }}
              className="premium-card px-4 py-4 flex items-center gap-3.5 group cursor-pointer"
            >
              <motion.div
                className={`w-10 h-10 rounded-xl ${item.color} flex items-center justify-center text-white text-xs font-bold shrink-0`}
                whileHover={{ rotate: 10 }}
                transition={{ type: "spring", stiffness: 300 }}
              >
                {item.initials}
              </motion.div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <p className="font-display font-semibold text-sm text-foreground">{item.name}</p>
                  <ExternalLink className="w-3 h-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                </div>
                <p className="text-xs text-muted-foreground">{item.desc}</p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default IntegrationsStripSection;
