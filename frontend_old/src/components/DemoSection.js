import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Phone, PhoneOff, Mic, MicOff, Volume2 } from "lucide-react";

const demoConversation = [
  { role: "caller", text: "Hi, I'd like to make a reservation for tonight." },
  { role: "ai", text: "Of course! How many guests will be joining tonight?" },
  { role: "caller", text: "It'll be 4 of us, around 7pm if possible." },
  { role: "ai", text: "Great news! I have a lovely table for 4 available at 7:15pm. May I have a name for the reservation?" },
  { role: "caller", text: "Sarah Mitchell, please." },
  { role: "ai", text: "Perfect, Sarah! You're all set — table for 4 at 7:15pm tonight. We'll send a confirmation text. Looking forward to seeing you!" },
];

export const DemoSection = () => {
  const [isActive, setIsActive] = useState(false);
  const [messages, setMessages] = useState([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isMuted, setIsMuted] = useState(false);

  const startDemo = () => {
    setIsActive(true);
    setMessages([]);
    setCurrentIndex(0);
    playMessages(0);
  };

  const playMessages = (startIdx) => {
    let idx = startIdx;
    const interval = setInterval(() => {
      if (idx < demoConversation.length) {
        setMessages((prev) => [...prev, demoConversation[idx]]);
        setCurrentIndex(idx + 1);
        idx++;
      } else {
        clearInterval(interval);
      }
    }, 2000);
  };

  const endDemo = () => {
    setIsActive(false);
    setMessages([]);
    setCurrentIndex(0);
  };

  return (
    <section className="py-24 lg:py-32 bg-gradient-subtle">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid lg:grid-cols-2 gap-12 lg:gap-16 items-center">
          {/* Left: Description */}
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true, margin: "-80px" }}
            transition={{ duration: 0.6 }}
          >
            <span className="text-sm font-medium text-primary tracking-wide uppercase">
              Live Demo
            </span>
            <h2 className="mt-3 text-3xl sm:text-4xl lg:text-5xl font-heading font-bold text-foreground leading-tight">
              Hear ringAI in Action
            </h2>
            <p className="mt-4 text-base md:text-lg text-muted-foreground leading-relaxed">
              Experience how ringAI handles a real reservation call. Our AI speaks naturally, understands context, and books tables seamlessly.
            </p>

            <div className="mt-8 space-y-4">
              {[
                "Natural, warm conversational voice",
                "Understands complex requests and special occasions",
                "Confirms details and sends text notifications",
                "Handles multiple calls simultaneously",
              ].map((item, i) => (
                <div key={i} className="flex items-start gap-3">
                  <div className="w-5 h-5 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <div className="w-1.5 h-1.5 rounded-full bg-primary" />
                  </div>
                  <span className="text-sm text-foreground">{item}</span>
                </div>
              ))}
            </div>

            <div className="mt-8">
              <img
                src="https://images.pexels.com/photos/4254255/pexels-photo-4254255.jpeg"
                alt="Restaurant hostess"
                className="w-full max-w-sm rounded-xl shadow-md object-cover aspect-[16/10]"
              />
            </div>
          </motion.div>

          {/* Right: Phone Demo Interface */}
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true, margin: "-80px" }}
            transition={{ duration: 0.6, delay: 0.15 }}
            className="flex justify-center"
          >
            <Card className="w-full max-w-sm border-border bg-card shadow-elevated overflow-hidden">
              {/* Phone header */}
              <div className="bg-primary px-5 py-4 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-full bg-primary-foreground/20 flex items-center justify-center">
                    <Phone className="w-4 h-4 text-primary-foreground" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-primary-foreground">ringAI Demo</p>
                    <p className="text-xs text-primary-foreground/70">
                      {isActive ? "Call in progress..." : "Tap to start demo"}
                    </p>
                  </div>
                </div>
                {isActive && (
                  <div className="flex items-center gap-1">
                    {[0.4, 0.7, 1, 0.6, 0.9].map((h, i) => (
                      <div
                        key={i}
                        className="w-0.5 bg-primary-foreground/60 rounded-full animate-wave-pulse"
                        style={{ height: `${h * 16}px`, animationDelay: `${i * 0.15}s` }}
                      />
                    ))}
                  </div>
                )}
              </div>

              {/* Chat area */}
              <div className="h-80 overflow-y-auto p-4 space-y-3 bg-muted/30">
                {!isActive && messages.length === 0 && (
                  <div className="h-full flex flex-col items-center justify-center text-center px-4">
                    <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center mb-4">
                      <Volume2 className="w-7 h-7 text-primary" />
                    </div>
                    <p className="text-sm font-medium text-foreground">Ready to Demo</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Start a simulated call to see ringAI handle a reservation
                    </p>
                  </div>
                )}

                <AnimatePresence>
                  {messages.map((msg, i) => (
                    <motion.div
                      key={i}
                      initial={{ opacity: 0, y: 10, scale: 0.95 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      transition={{ duration: 0.3 }}
                      className={`flex ${
                        msg.role === "caller" ? "justify-end" : "justify-start"
                      }`}
                    >
                      <div
                        className={`max-w-[80%] rounded-xl px-4 py-2.5 text-sm ${
                          msg.role === "caller"
                            ? "bg-primary text-primary-foreground rounded-br-sm"
                            : "bg-card border border-border text-foreground rounded-bl-sm"
                        }`}
                      >
                        {msg.text}
                      </div>
                    </motion.div>
                  ))}
                </AnimatePresence>

                {isActive && currentIndex < demoConversation.length && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="flex justify-start"
                  >
                    <div className="bg-card border border-border rounded-xl px-4 py-2.5 rounded-bl-sm">
                      <div className="flex gap-1">
                        <div className="w-2 h-2 rounded-full bg-muted-foreground/40 animate-bounce" style={{ animationDelay: "0ms" }} />
                        <div className="w-2 h-2 rounded-full bg-muted-foreground/40 animate-bounce" style={{ animationDelay: "150ms" }} />
                        <div className="w-2 h-2 rounded-full bg-muted-foreground/40 animate-bounce" style={{ animationDelay: "300ms" }} />
                      </div>
                    </div>
                  </motion.div>
                )}
              </div>

              {/* Controls */}
              <div className="p-4 border-t border-border flex items-center justify-center gap-4">
                <button
                  onClick={() => setIsMuted(!isMuted)}
                  className="w-10 h-10 rounded-full bg-muted flex items-center justify-center text-muted-foreground hover:bg-muted/80 transition-colors"
                >
                  {isMuted ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
                </button>

                {!isActive ? (
                  <Button
                    variant="premium"
                    size="lg"
                    onClick={startDemo}
                    className="rounded-full px-8"
                  >
                    <Phone className="w-4 h-4" />
                    Start Demo Call
                  </Button>
                ) : (
                  <Button
                    variant="destructive"
                    size="lg"
                    onClick={endDemo}
                    className="rounded-full px-8"
                  >
                    <PhoneOff className="w-4 h-4" />
                    End Call
                  </Button>
                )}

                <button
                  className="w-10 h-10 rounded-full bg-muted flex items-center justify-center text-muted-foreground hover:bg-muted/80 transition-colors"
                >
                  <Volume2 className="w-4 h-4" />
                </button>
              </div>
            </Card>
          </motion.div>
        </div>
      </div>
    </section>
  );
};
