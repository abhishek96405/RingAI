import { useState } from "react";
import { motion } from "framer-motion";
import { Phone, Volume2, Mic, PhoneCall, Check } from "lucide-react";
import { Button } from "@/components/ui/button";

const bulletPoints = [
  "Natural, warm conversational voice",
  "Understands complex requests and special occasions",
  "Confirms details and sends text notifications",
  "Handles multiple calls simultaneously",
];

const transcript = [
  { role: "ai", text: "Hi, thank you for calling Bella Italia! How can I help you today?" },
  { role: "caller", text: "Hi, I'd like to make a reservation for 4 people this Saturday at 7pm." },
  { role: "ai", text: "Of course! Let me check availability for Saturday at 7 PM for 4 guests... Great news, I have a table available! Can I get a name for the reservation?" },
  { role: "caller", text: "It's under Johnson. Also, it's a birthday — any chance for a window seat?" },
  { role: "ai", text: "Happy birthday! I've reserved a window table for 4 under Johnson, Saturday at 7 PM. I'll send a confirmation text shortly. Anything else?" },
];

const LiveDemoSection = () => {
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);

  const handleStartDemo = () => {
    setIsPlaying(true);
    setCurrentStep(0);
    transcript.forEach((_, i) => {
      setTimeout(() => setCurrentStep(i + 1), (i + 1) * 2000);
    });
    setTimeout(() => setIsPlaying(false), transcript.length * 2000 + 1000);
  };

  return (
    <section id="demo" className="section-padding section-divider relative overflow-hidden bg-gradient-surface">
      <div className="absolute top-0 right-0 w-96 h-96 rounded-full bg-primary/5 blur-3xl" />

      <div className="container-wide relative z-10">
        <div className="grid lg:grid-cols-2 gap-10 lg:gap-14 items-center">
          {/* Left content */}
          <motion.div
            initial={{ opacity: 0, x: -30 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
          >
            <span className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-accent text-accent-foreground text-xs font-semibold tracking-wide uppercase mb-4">
              <PhoneCall className="w-3.5 h-3.5" />
              Live Demo
            </span>
            <h2 className="font-display font-extrabold text-3xl md:text-4xl text-foreground mb-4 leading-tight">
              Hear Duuutah <span className="text-gradient">AI</span> in Action
            </h2>
            <p className="text-muted-foreground text-base mb-6 max-w-lg">
              Experience how Duuutah AI handles a real reservation call. Our AI speaks naturally, understands context, and books tables seamlessly.
            </p>

            <ul className="space-y-3">
              {bulletPoints.map((point) => (
                <li key={point} className="flex items-center gap-3">
                  <div className="w-5 h-5 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                    <Check className="w-3 h-3 text-primary" />
                  </div>
                  <span className="text-sm text-foreground/80">{point}</span>
                </li>
              ))}
            </ul>
          </motion.div>

          {/* Right: Phone mockup */}
          <motion.div
            initial={{ opacity: 0, x: 30 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, delay: 0.2 }}
            className="flex justify-center"
          >
            <div className="w-full max-w-sm">
              <div className="rounded-3xl border border-border/60 bg-card shadow-xl overflow-hidden">
                <div className="bg-gradient-primary px-5 py-3.5 flex items-center gap-3">
                  <div className="w-9 h-9 rounded-full bg-white/20 flex items-center justify-center">
                    <Phone className="w-4 h-4 text-primary-foreground" />
                  </div>
                  <div>
                    <p className="font-display font-bold text-sm text-primary-foreground">Duuutah AI Demo</p>
                    <p className="text-xs text-primary-foreground/70">Tap to start demo</p>
                  </div>
                </div>

                <div className="p-4 min-h-[280px] flex flex-col">
                  {!isPlaying && currentStep === 0 ? (
                    <div className="flex-1 flex flex-col items-center justify-center text-center py-6">
                      <div className="w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center mb-3 animate-pulse-glow">
                        <Volume2 className="w-6 h-6 text-primary" />
                      </div>
                      <p className="font-display font-semibold text-foreground text-sm mb-1">Ready to Demo</p>
                      <p className="text-xs text-muted-foreground">Start a simulated call to see Duuutah AI in action</p>
                    </div>
                  ) : (
                    <div className="flex-1 space-y-2.5 overflow-y-auto">
                      {transcript.slice(0, currentStep).map((msg, i) => (
                        <motion.div
                          key={i}
                          initial={{ opacity: 0, y: 10 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ duration: 0.3 }}
                          className={`flex ${msg.role === "caller" ? "justify-end" : "justify-start"}`}
                        >
                          <div
                            className={`max-w-[85%] rounded-2xl px-3.5 py-2 text-xs leading-relaxed ${
                              msg.role === "caller"
                                ? "bg-primary text-primary-foreground rounded-br-md"
                                : "bg-muted text-foreground rounded-bl-md"
                            }`}
                          >
                            {msg.text}
                          </div>
                        </motion.div>
                      ))}
                      {isPlaying && currentStep < transcript.length && (
                        <div className="flex justify-start">
                          <div className="bg-muted rounded-2xl rounded-bl-md px-4 py-2.5 flex gap-1">
                            <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/40 animate-bounce" style={{ animationDelay: "0ms" }} />
                            <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/40 animate-bounce" style={{ animationDelay: "150ms" }} />
                            <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/40 animate-bounce" style={{ animationDelay: "300ms" }} />
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                <div className="border-t border-border/50 px-4 py-3 flex items-center justify-center gap-3">
                  <button className="w-9 h-9 rounded-full bg-muted flex items-center justify-center text-muted-foreground hover:bg-muted/80 transition-colors">
                    <Mic className="w-4 h-4" />
                  </button>
                  <Button
                    onClick={handleStartDemo}
                    disabled={isPlaying}
                    className="bg-gradient-primary text-primary-foreground rounded-full px-5 h-10 text-sm font-semibold shadow-glow hover:opacity-90 transition-opacity gap-2"
                  >
                    <Phone className="w-3.5 h-3.5" />
                    {isPlaying ? "Call in Progress..." : "Start Demo Call"}
                  </Button>
                  <button className="w-9 h-9 rounded-full bg-muted flex items-center justify-center text-muted-foreground hover:bg-muted/80 transition-colors">
                    <Volume2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
};

export default LiveDemoSection;
