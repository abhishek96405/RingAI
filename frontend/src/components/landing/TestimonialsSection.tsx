import { motion } from "framer-motion";
import { Star, Quote, Phone, Mic, Stethoscope, Scissors, Utensils } from "lucide-react";

const testimonials = [
  {
    name: "Maria Chen",
    role: "Owner, Golden Dragon Restaurant",
    quote: "Duuutah AI cut our missed calls by 90%. We're capturing orders we used to lose every single night.",
    stars: 5,
    initials: "MC",
    accentColor: "from-primary to-purple-500",
    icon: Utensils,
  },
  {
    name: "Dr. James Wilson",
    role: "Director, Sunrise Medical Clinic",
    quote: "Our front desk was overwhelmed with appointment calls. Now patients book 24/7 and our staff can focus on care.",
    stars: 5,
    initials: "JW",
    accentColor: "from-pink-500 to-rose-500",
    icon: Stethoscope,
  },
  {
    name: "Sarah Kim",
    role: "Owner, Luxe Hair Studio",
    quote: "Setup took 10 minutes. Within a week, our booking rate jumped 35%. Clients love the instant confirmations.",
    stars: 5,
    initials: "SK",
    accentColor: "from-amber-500 to-orange-500",
    icon: Scissors,
  },
];

const WaveformBar = ({ height, delay }: { height: number; delay: number }) => (
  <motion.div
    className="w-1 rounded-full bg-primary"
    animate={{ height: [height * 0.3, height, height * 0.5, height * 0.8, height * 0.3] }}
    transition={{ duration: 1.2, repeat: Infinity, delay, ease: "easeInOut" }}
    style={{ minHeight: 4 }}
  />
);

const AnimatedWaveformVisual = () => {
  const barCount = 40;
  const bars = Array.from({ length: barCount }, (_, i) => ({
    height: 12 + Math.random() * 36,
    delay: i * 0.05,
  }));

  const transcript = [
    { role: "ai", text: "Hi! Thanks for calling Luxe Hair Studio. How can I help?", time: "0:00" },
    { role: "caller", text: "I'd like to book a haircut for Saturday.", time: "0:04" },
    { role: "ai", text: "Of course! I have 10am, 2pm, or 4pm available. Which works best?", time: "0:07" },
  ];

  return (
    <div className="relative w-full h-[480px] rounded-2xl overflow-hidden bg-gradient-dark flex flex-col">
      {/* Header */}
      <div className="px-6 pt-6 pb-4 border-b border-primary-foreground/10">
        <div className="flex items-center gap-3">
          <motion.div
            className="w-10 h-10 rounded-xl bg-gradient-primary flex items-center justify-center shadow-glow"
            animate={{ scale: [1, 1.05, 1] }}
            transition={{ duration: 2, repeat: Infinity }}
          >
            <Phone className="w-5 h-5 text-primary-foreground" />
          </motion.div>
          <div>
            <p className="font-display font-bold text-sm text-primary-foreground">Duuutah AI Live Call</p>
            <div className="flex items-center gap-1.5">
              <motion.div
                className="w-2 h-2 rounded-full bg-success"
                animate={{ opacity: [1, 0.4, 1] }}
                transition={{ duration: 1.5, repeat: Infinity }}
              />
              <span className="text-[11px] text-primary-foreground/50">Active — 0:12</span>
            </div>
          </div>
        </div>
      </div>

      {/* Waveform */}
      <div className="px-6 py-5">
        <div className="flex items-center justify-center gap-[3px] h-14">
          {bars.map((bar, i) => (
            <WaveformBar key={i} height={bar.height} delay={bar.delay} />
          ))}
        </div>
        <div className="flex items-center justify-between mt-2">
          <span className="text-[10px] text-primary-foreground/30">0:00</span>
          <div className="flex items-center gap-1.5">
            <Mic className="w-3 h-3 text-primary-foreground/40" />
            <span className="text-[10px] text-primary-foreground/40">AI Processing</span>
          </div>
          <span className="text-[10px] text-primary-foreground/30">0:12</span>
        </div>
      </div>

      {/* Live transcript */}
      <div className="flex-1 px-6 pb-6 space-y-3 overflow-hidden">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-primary-foreground/30 mb-2">Live Transcript</p>
        {transcript.map((msg, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 1 + i * 1.5, duration: 0.5 }}
            className={`flex ${msg.role === "caller" ? "justify-end" : "justify-start"}`}
          >
            <div className={`max-w-[80%] rounded-2xl px-3.5 py-2 text-xs leading-relaxed ${
              msg.role === "caller"
                ? "bg-primary/30 text-primary-foreground rounded-br-md"
                : "bg-primary-foreground/10 text-primary-foreground/80 rounded-bl-md"
            }`}>
              <span className="text-[9px] text-primary-foreground/40 block mb-0.5">{msg.role === "ai" ? "Duuutah AI" : "Caller"} · {msg.time}</span>
              {msg.text}
            </div>
          </motion.div>
        ))}
        {/* Typing indicator */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 5.5 }}
          className="flex justify-start"
        >
          <div className="bg-primary-foreground/10 rounded-2xl rounded-bl-md px-4 py-2.5 flex gap-1">
            <motion.span className="w-1.5 h-1.5 rounded-full bg-primary-foreground/30" animate={{ y: [0, -4, 0] }} transition={{ duration: 0.6, repeat: Infinity, delay: 0 }} />
            <motion.span className="w-1.5 h-1.5 rounded-full bg-primary-foreground/30" animate={{ y: [0, -4, 0] }} transition={{ duration: 0.6, repeat: Infinity, delay: 0.15 }} />
            <motion.span className="w-1.5 h-1.5 rounded-full bg-primary-foreground/30" animate={{ y: [0, -4, 0] }} transition={{ duration: 0.6, repeat: Infinity, delay: 0.3 }} />
          </div>
        </motion.div>
      </div>

      {/* Bottom quality bar */}
      <div className="px-6 py-3 border-t border-primary-foreground/10 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="text-center">
            <p className="font-display font-bold text-sm text-primary-foreground">98%</p>
            <p className="text-[9px] text-primary-foreground/40">Accuracy</p>
          </div>
          <div className="w-px h-6 bg-primary-foreground/10" />
          <div className="text-center">
            <p className="font-display font-bold text-sm text-success">4.9</p>
            <p className="text-[9px] text-primary-foreground/40">Quality</p>
          </div>
        </div>
        <motion.div
          className="px-3 py-1 rounded-full bg-success/20 text-success text-[10px] font-semibold"
          animate={{ opacity: [1, 0.6, 1] }}
          transition={{ duration: 2, repeat: Infinity }}
        >
          ● AI Handling
        </motion.div>
      </div>
    </div>
  );
};

const TestimonialsSection = () => {
  return (
    <section id="testimonials" className="section-padding relative overflow-hidden">
      <motion.div
        className="absolute top-0 left-1/4 w-96 h-96 rounded-full bg-primary/5 blur-3xl"
        animate={{ x: [0, 30, 0], opacity: [0.05, 0.1, 0.05] }}
        transition={{ duration: 10, repeat: Infinity, ease: "easeInOut" }}
      />

      <div className="container-wide relative z-10">
        <div className="grid lg:grid-cols-5 gap-10 items-center">
          {/* Animated visual column */}
          <motion.div
            initial={{ opacity: 0, x: -30 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
            className="lg:col-span-2 hidden lg:block"
          >
            <AnimatedWaveformVisual />
          </motion.div>

          {/* Testimonials column */}
          <div className="lg:col-span-3">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              className="mb-8"
            >
              <span className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-accent text-accent-foreground text-xs font-semibold tracking-wide uppercase mb-3">
                <Star className="w-3.5 h-3.5" />
                Loved by Businesses
              </span>
              <h2 className="font-display font-extrabold text-3xl md:text-4xl text-foreground mb-3">
                Real Results from{" "}
                <span className="text-gradient">Real Businesses</span>
              </h2>
              <p className="text-muted-foreground text-base max-w-lg">
                Join business owners who trust Duuutah AI to handle calls and boost revenue.
              </p>
            </motion.div>

            <div className="space-y-5">
              {testimonials.map((t, i) => (
                <motion.div
                  key={t.name}
                  initial={{ opacity: 0, x: 30 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.5, delay: i * 0.12 }}
                  whileHover={{ x: 6, transition: { duration: 0.2 } }}
                  className="premium-card p-6 flex gap-5 relative group cursor-pointer"
                >
                  <motion.div
                    className="absolute top-4 right-4 opacity-10 group-hover:opacity-20 transition-opacity"
                    whileHover={{ rotate: 15 }}
                  >
                    <Quote className="w-8 h-8 text-primary" />
                  </motion.div>

                  <motion.div
                    className={`w-12 h-12 rounded-xl bg-gradient-to-br ${t.accentColor} flex items-center justify-center text-white text-sm font-bold shrink-0`}
                    whileHover={{ scale: 1.1, rotate: 5 }}
                    transition={{ type: "spring", stiffness: 300 }}
                  >
                    {t.initials}
                  </motion.div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-2">
                      <div className="flex gap-1">
                        {Array.from({ length: t.stars }).map((_, si) => (
                          <motion.div
                            key={si}
                            initial={{ opacity: 0, scale: 0 }}
                            whileInView={{ opacity: 1, scale: 1 }}
                            viewport={{ once: true }}
                            transition={{ delay: i * 0.12 + si * 0.05, type: "spring" }}
                          >
                            <Star className="w-3.5 h-3.5 fill-warning text-warning" />
                          </motion.div>
                        ))}
                      </div>
                      <t.icon className="w-4 h-4 text-muted-foreground" />
                    </div>
                    <p className="text-foreground/90 text-sm leading-relaxed mb-3">"{t.quote}"</p>
                    <div>
                      <p className="font-display font-semibold text-sm text-foreground">{t.name}</p>
                      <p className="text-xs text-muted-foreground">{t.role}</p>
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>

            {/* Stats strip */}
            <motion.div
              initial={{ opacity: 0, y: 15 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: 0.3 }}
              className="mt-8 grid grid-cols-4 gap-4"
            >
              {[
                { value: "5000+", label: "Businesses" },
                { value: "2.5M+", label: "Calls Handled" },
                { value: "99.8%", label: "Uptime" },
                { value: "4.9/5", label: "Rating" },
              ].map((stat, i) => (
                <motion.div
                  key={stat.label}
                  className="text-center"
                  initial={{ opacity: 0, y: 10 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: 0.4 + i * 0.1 }}
                >
                  <p className="font-display font-extrabold text-lg md:text-xl text-gradient">{stat.value}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">{stat.label}</p>
                </motion.div>
              ))}
            </motion.div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default TestimonialsSection;
