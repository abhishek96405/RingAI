import { useState, useEffect, useRef } from "react";
import { AppLayout } from "@/layouts/AppLayout";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Radio,
  Phone,
  PhoneOff,
  Mic,
  Volume2,
  User,
  Bot,
  Clock,
  Zap,
  AlertTriangle,
} from "lucide-react";
import { simulateCall, getRestaurantId } from "@/lib/api";
import { toast } from "sonner";
import { motion, AnimatePresence } from "framer-motion";

const mockLiveConversation = [
  { role: "ai", text: "Hi! I'm Bella, the AI assistant for Bella Cucina. How can I help you today?", delay: 0 },
  { role: "customer", text: "Hi, I'd like to place an order for delivery.", delay: 2500 },
  { role: "ai", text: "Of course! What would you like to order?", delay: 4500 },
  { role: "customer", text: "Can I get a Margherita Pizza and a Caesar Salad?", delay: 7000 },
  { role: "ai", text: "Great choices! One Margherita Pizza and one Caesar Salad. Would you like to add any drinks?", delay: 9000 },
  { role: "customer", text: "Yeah, two Italian Sodas please.", delay: 11500 },
  { role: "ai", text: "Perfect! Two Italian Sodas added. Your subtotal is $27.97. What's the delivery address?", delay: 13500 },
  { role: "customer", text: "456 Oak Avenue, Apartment 3B.", delay: 16000 },
  { role: "ai", text: "Got it! Let me read back your order: 1 Margherita Pizza, 1 Caesar Salad, and 2 Italian Sodas for delivery to 456 Oak Avenue, Apt 3B. Total is $27.97 plus delivery fee. Sound good?", delay: 18500 },
  { role: "customer", text: "Yes, that's perfect!", delay: 22000 },
  { role: "ai", text: "Your order has been placed! Estimated delivery time is 35-45 minutes. Thank you for calling Bella Cucina!", delay: 24000 },
];

export default function LiveMonitor() {
  const [isLive, setIsLive] = useState(false);
  const [messages, setMessages] = useState([]);
  const [currentStep, setCurrentStep] = useState(0);
  const [callDuration, setCallDuration] = useState(0);
  const [cartItems, setCartItems] = useState([]);
  const chatEndRef = useRef(null);
  const timerRef = useRef(null);
  const messageTimersRef = useRef([]);

  const scrollToBottom = () => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => { scrollToBottom(); }, [messages]);

  const startLiveCall = () => {
    setIsLive(true);
    setMessages([]);
    setCurrentStep(0);
    setCallDuration(0);
    setCartItems([]);

    // Start duration timer
    timerRef.current = setInterval(() => setCallDuration(prev => prev + 1), 1000);

    // Schedule messages
    const timers = mockLiveConversation.map((msg, i) => {
      return setTimeout(() => {
        setMessages(prev => [...prev, { ...msg, timestamp: new Date().toISOString() }]);
        setCurrentStep(i + 1);

        // Update cart at specific steps
        if (i === 3) setCartItems([{ name: "Margherita Pizza", price: 1699, qty: 1 }, { name: "Caesar Salad", price: 1199, qty: 1 }]);
        if (i === 5) setCartItems(prev => [...prev, { name: "Italian Soda", price: 499, qty: 2 }]);

        // End call
        if (i === mockLiveConversation.length - 1) {
          setTimeout(() => {
            endCall(true);
          }, 2000);
        }
      }, msg.delay);
    });
    messageTimersRef.current = timers;
  };

  const endCall = async (autoEnd = false) => {
    messageTimersRef.current.forEach(t => clearTimeout(t));
    clearInterval(timerRef.current);
    setIsLive(false);

    if (autoEnd) {
      try {
        await simulateCall();
        toast.success("Call completed and saved to history!");
      } catch (err) {
        // Silent fail for demo
      }
    }
  };

  const formatTimer = (seconds) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  const cartTotal = cartItems.reduce((sum, item) => sum + item.price * item.qty, 0);

  return (
    <AppLayout>
      <div className="p-4 lg:p-6 space-y-4">
        {/* Header */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-heading font-bold text-foreground flex items-center gap-2">
              <Radio className="w-5 h-5" /> Live Monitor
            </h1>
            <p className="text-sm text-muted-foreground">Watch AI calls in real-time</p>
          </div>
          <div className="flex gap-2">
            {!isLive ? (
              <Button variant="premium" size="sm" onClick={startLiveCall}>
                <Zap className="w-4 h-4" />
                Simulate Live Call
              </Button>
            ) : (
              <Button variant="destructive" size="sm" onClick={() => endCall(false)}>
                <PhoneOff className="w-4 h-4" />
                End Call
              </Button>
            )}
          </div>
        </div>

        <div className="grid lg:grid-cols-3 gap-4">
          {/* Live Transcript */}
          <div className="lg:col-span-2">
            <Card className="border-border bg-card overflow-hidden">
              {/* Call Header */}
              <div className={`px-5 py-3 flex items-center justify-between ${
                isLive ? 'bg-primary' : 'bg-muted'
              }`}>
                <div className="flex items-center gap-3">
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
                    isLive ? 'bg-primary-foreground/20' : 'bg-muted-foreground/20'
                  }`}>
                    <Phone className={`w-4 h-4 ${isLive ? 'text-primary-foreground' : 'text-muted-foreground'}`} />
                  </div>
                  <div>
                    <p className={`text-sm font-semibold ${isLive ? 'text-primary-foreground' : 'text-foreground'}`}>
                      {isLive ? 'Live Call in Progress' : 'No Active Call'}
                    </p>
                    {isLive && (
                      <p className="text-xs text-primary-foreground/70 flex items-center gap-1">
                        <Clock className="w-3 h-3" /> {formatTimer(callDuration)} · +1 (555) 867-5309
                      </p>
                    )}
                  </div>
                </div>
                {isLive && (
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-destructive animate-pulse" />
                    <span className="text-xs font-medium text-primary-foreground">LIVE</span>
                    <div className="flex items-center gap-0.5 ml-2">
                      {[0.4, 0.7, 1, 0.6, 0.9].map((h, i) => (
                        <div key={i} className="w-0.5 bg-primary-foreground/60 rounded-full animate-wave-pulse" style={{ height: `${h * 14}px`, animationDelay: `${i * 0.12}s` }} />
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Chat Area */}
              <div className="h-[500px] overflow-y-auto p-5 space-y-3 bg-muted/10">
                {!isLive && messages.length === 0 && (
                  <div className="h-full flex flex-col items-center justify-center text-center">
                    <Radio className="w-12 h-12 text-muted-foreground/20 mb-4" />
                    <p className="text-sm font-medium text-muted-foreground">No active call</p>
                    <p className="text-xs text-muted-foreground mt-1">Start a simulated call to see the live monitor in action</p>
                  </div>
                )}

                <AnimatePresence>
                  {messages.map((msg, i) => (
                    <motion.div
                      key={i}
                      initial={{ opacity: 0, y: 10, scale: 0.95 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      transition={{ duration: 0.3 }}
                      className={`flex gap-2.5 ${msg.role === 'customer' ? 'justify-end' : 'justify-start'}`}
                    >
                      {msg.role === 'ai' && (
                        <div className="w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0 mt-0.5">
                          <Bot className="w-3.5 h-3.5 text-primary" />
                        </div>
                      )}
                      <div className={`max-w-[75%] rounded-xl px-4 py-2.5 text-sm ${
                        msg.role === 'customer'
                          ? 'bg-primary text-primary-foreground rounded-br-sm'
                          : 'bg-card border border-border text-foreground rounded-bl-sm'
                      }`}>
                        {msg.text}
                      </div>
                      {msg.role === 'customer' && (
                        <div className="w-7 h-7 rounded-full bg-accent/10 flex items-center justify-center flex-shrink-0 mt-0.5">
                          <User className="w-3.5 h-3.5 text-accent" />
                        </div>
                      )}
                    </motion.div>
                  ))}
                </AnimatePresence>

                {isLive && currentStep < mockLiveConversation.length && (
                  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex gap-2.5">
                    <div className="w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
                      <Bot className="w-3.5 h-3.5 text-primary" />
                    </div>
                    <div className="bg-card border border-border rounded-xl px-4 py-2.5 rounded-bl-sm">
                      <div className="flex gap-1">
                        <div className="w-2 h-2 rounded-full bg-muted-foreground/40 animate-bounce" style={{ animationDelay: '0ms' }} />
                        <div className="w-2 h-2 rounded-full bg-muted-foreground/40 animate-bounce" style={{ animationDelay: '150ms' }} />
                        <div className="w-2 h-2 rounded-full bg-muted-foreground/40 animate-bounce" style={{ animationDelay: '300ms' }} />
                      </div>
                    </div>
                  </motion.div>
                )}
                <div ref={chatEndRef} />
              </div>
            </Card>
          </div>

          {/* Side Panel */}
          <div className="space-y-4">
            {/* Call Info */}
            <Card className="p-5 border-border bg-card">
              <h3 className="text-sm font-heading font-semibold text-foreground mb-3">Call Info</h3>
              <div className="space-y-3">
                <div className="flex justify-between">
                  <span className="text-xs text-muted-foreground">Status</span>
                  <Badge variant="secondary" className={isLive ? 'bg-success/10 text-success border-0' : 'text-xs'}>
                    {isLive ? 'Active' : 'Idle'}
                  </Badge>
                </div>
                <div className="flex justify-between">
                  <span className="text-xs text-muted-foreground">Duration</span>
                  <span className="text-sm font-medium text-foreground">{formatTimer(callDuration)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-xs text-muted-foreground">AI Model</span>
                  <span className="text-xs text-muted-foreground">Claude Opus 4</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-xs text-muted-foreground">Voice</span>
                  <span className="text-xs text-muted-foreground">Rachel</span>
                </div>
              </div>
            </Card>

            {/* Live Cart */}
            <Card className="p-5 border-border bg-card">
              <h3 className="text-sm font-heading font-semibold text-foreground mb-3">Live Cart</h3>
              {cartItems.length === 0 ? (
                <p className="text-xs text-muted-foreground text-center py-4">No items yet</p>
              ) : (
                <div className="space-y-2">
                  <AnimatePresence>
                    {cartItems.map((item, i) => (
                      <motion.div
                        key={item.name}
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        className="flex justify-between text-sm"
                      >
                        <span className="text-foreground">{item.qty}x {item.name}</span>
                        <span className="text-muted-foreground">${(item.price * item.qty / 100).toFixed(2)}</span>
                      </motion.div>
                    ))}
                  </AnimatePresence>
                  <Separator />
                  <div className="flex justify-between text-sm font-semibold">
                    <span className="text-foreground">Total</span>
                    <span className="text-foreground">${(cartTotal / 100).toFixed(2)}</span>
                  </div>
                </div>
              )}
            </Card>

            {/* Actions */}
            <Card className="p-5 border-border bg-card">
              <h3 className="text-sm font-heading font-semibold text-foreground mb-3">Actions</h3>
              <div className="space-y-2">
                <Button variant="outline" size="sm" className="w-full justify-start" disabled={!isLive}>
                  <AlertTriangle className="w-4 h-4" /> Take Over Call
                </Button>
                <Button variant="outline" size="sm" className="w-full justify-start" disabled={!isLive}>
                  <Mic className="w-4 h-4" /> Whisper to AI
                </Button>
                <Button variant="outline" size="sm" className="w-full justify-start" disabled={!isLive}>
                  <Volume2 className="w-4 h-4" /> Mute Customer
                </Button>
              </div>
            </Card>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
