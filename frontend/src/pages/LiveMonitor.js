import { useState, useEffect, useRef, useCallback } from "react";
import { AppLayout } from "@/layouts/AppLayout";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
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
  Play,
  TestTube,
  CheckCircle2,
  XCircle,
  Loader2,
  Sparkles,
} from "lucide-react";
import { getTestScenarios, runTestScenario, getStatus } from "@/lib/api";
import { toast } from "sonner";
import { motion, AnimatePresence } from "framer-motion";

export default function LiveMonitor() {
  const [status, setStatus] = useState(null);
  const [scenarios, setScenarios] = useState([]);
  const [selectedScenario, setSelectedScenario] = useState(null);
  const [isRunning, setIsRunning] = useState(false);
  const [messages, setMessages] = useState([]);
  const [callDuration, setCallDuration] = useState(0);
  const [cartItems, setCartItems] = useState([]);
  const [callResult, setCallResult] = useState(null);
  const [displayIndex, setDisplayIndex] = useState(0);
  const chatEndRef = useRef(null);
  const timerRef = useRef(null);

  const scrollToBottom = () => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => { scrollToBottom(); }, [messages]);

  // Fetch status and scenarios on mount
  useEffect(() => {
    const fetchData = async () => {
      try {
        const [statusRes, scenariosRes] = await Promise.all([
          getStatus(),
          getTestScenarios(),
        ]);
        setStatus(statusRes.data);
        setScenarios(scenariosRes.data.scenarios || []);
        if (scenariosRes.data.scenarios?.length > 0) {
          setSelectedScenario(scenariosRes.data.scenarios[0]);
        }
      } catch (err) {
        toast.error("Failed to load test scenarios");
      }
    };
    fetchData();
  }, []);

  const runScenario = async () => {
    if (!selectedScenario) return;
    
    setIsRunning(true);
    setMessages([]);
    setCallDuration(0);
    setCartItems([]);
    setCallResult(null);
    setDisplayIndex(0);

    // Start duration timer
    timerRef.current = setInterval(() => setCallDuration(prev => prev + 1), 1000);

    try {
      toast.info(`Running "${selectedScenario.name}" scenario...`);
      const res = await runTestScenario(null, selectedScenario.id);
      const call = res.data.call;
      
      // Animate transcript display
      const transcript = call.transcript || [];
      setCallResult(call);
      
      // Display messages one by one with animation
      for (let i = 0; i < transcript.length; i++) {
        await new Promise(resolve => setTimeout(resolve, 800));
        setMessages(prev => [...prev, transcript[i]]);
        setDisplayIndex(i + 1);
        
        // Update cart when we see AI confirming items
        if (call.order_json?.items && i >= transcript.length / 2) {
          setCartItems(call.order_json.items.map(item => ({
            name: item.name,
            price: item.price,
            qty: item.quantity,
          })));
        }
      }

      // Call complete
      clearInterval(timerRef.current);
      toast.success(`Test call completed! Quality score: ${call.quality_score}`);
      
    } catch (err) {
      clearInterval(timerRef.current);
      toast.error("Failed to run test scenario");
    } finally {
      setIsRunning(false);
    }
  };

  const endCall = () => {
    clearInterval(timerRef.current);
    setIsRunning(false);
  };

  const formatTimer = (seconds) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  const cartTotal = cartItems.reduce((sum, item) => sum + item.price * item.qty, 0);
  const geminiAvailable = status?.gemini?.available;

  return (
    <AppLayout>
      <div className="p-4 lg:p-6 space-y-4">
        {/* Header */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-heading font-bold text-foreground flex items-center gap-2">
              <TestTube className="w-5 h-5" /> Test Mode
            </h1>
            <p className="text-sm text-muted-foreground">
              Run AI-powered test calls with predefined scenarios
            </p>
          </div>
          
          {/* Status Badge */}
          <div className="flex items-center gap-2">
            {geminiAvailable ? (
              <Badge variant="secondary" className="bg-success/10 text-success border-0 gap-1">
                <Sparkles className="w-3 h-3" /> Gemini AI Active
              </Badge>
            ) : (
              <Badge variant="secondary" className="bg-accent/10 text-accent border-0 gap-1">
                <AlertTriangle className="w-3 h-3" /> Simulation Mode
              </Badge>
            )}
          </div>
        </div>

        {/* Scenario Selector */}
        <Card className="p-4 border-border bg-card">
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
            <div className="flex-1 w-full">
              <label className="text-xs font-medium text-muted-foreground mb-1.5 block">
                Select Test Scenario
              </label>
              <Select 
                value={selectedScenario?.id?.toString()} 
                onValueChange={(v) => setSelectedScenario(scenarios.find(s => s.id.toString() === v))}
                disabled={isRunning}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Choose a scenario..." />
                </SelectTrigger>
                <SelectContent>
                  {scenarios.map((scenario) => (
                    <SelectItem key={scenario.id} value={scenario.id.toString()}>
                      <div className="flex items-center gap-2">
                        <span>{scenario.name}</span>
                        <Badge variant="secondary" className="text-xs">
                          {scenario.order_type}
                        </Badge>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            
            {!isRunning ? (
              <Button 
                variant="premium" 
                onClick={runScenario} 
                disabled={!selectedScenario}
                className="sm:mt-5"
              >
                <Play className="w-4 h-4" />
                Run Test Call
              </Button>
            ) : (
              <Button 
                variant="destructive" 
                onClick={endCall}
                className="sm:mt-5"
              >
                <PhoneOff className="w-4 h-4" />
                Stop
              </Button>
            )}
          </div>
          
          {selectedScenario && (
            <div className="mt-3 pt-3 border-t border-border">
              <div className="flex flex-wrap gap-2">
                <Badge variant="outline" className="text-xs">
                  {selectedScenario.message_count} messages
                </Badge>
                {selectedScenario.expected_items?.map((item, i) => (
                  <Badge key={i} variant="secondary" className="text-xs bg-primary/10 text-primary border-0">
                    {item}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </Card>

        <div className="grid lg:grid-cols-3 gap-4">
          {/* Live Transcript */}
          <div className="lg:col-span-2">
            <Card className="border-border bg-card overflow-hidden">
              {/* Call Header */}
              <div className={`px-5 py-3 flex items-center justify-between ${
                isRunning ? 'bg-primary' : callResult ? 'bg-success' : 'bg-muted'
              }`}>
                <div className="flex items-center gap-3">
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
                    isRunning ? 'bg-primary-foreground/20' : callResult ? 'bg-success-foreground/20' : 'bg-muted-foreground/20'
                  }`}>
                    <Phone className={`w-4 h-4 ${
                      isRunning ? 'text-primary-foreground' : callResult ? 'text-success-foreground' : 'text-muted-foreground'
                    }`} />
                  </div>
                  <div>
                    <p className={`text-sm font-semibold ${
                      isRunning ? 'text-primary-foreground' : callResult ? 'text-success-foreground' : 'text-foreground'
                    }`}>
                      {isRunning ? 'Test Call in Progress' : callResult ? 'Test Call Complete' : 'Ready for Test'}
                    </p>
                    {(isRunning || callResult) && (
                      <p className={`text-xs ${
                        isRunning ? 'text-primary-foreground/70' : 'text-success-foreground/70'
                      } flex items-center gap-1`}>
                        <Clock className="w-3 h-3" /> {formatTimer(callDuration)}
                        {callResult && ` · ${callResult.caller_name}`}
                      </p>
                    )}
                  </div>
                </div>
                {isRunning && (
                  <div className="flex items-center gap-2">
                    <Loader2 className="w-4 h-4 text-primary-foreground animate-spin" />
                    <span className="text-xs font-medium text-primary-foreground">RUNNING</span>
                  </div>
                )}
                {callResult && !isRunning && (
                  <Badge variant="secondary" className="bg-white/20 text-success-foreground border-0">
                    Score: {callResult.quality_score}
                  </Badge>
                )}
              </div>

              {/* Chat Area */}
              <div className="h-[500px] overflow-y-auto p-5 space-y-3 bg-muted/10">
                {!isRunning && messages.length === 0 && (
                  <div className="h-full flex flex-col items-center justify-center text-center">
                    <TestTube className="w-12 h-12 text-muted-foreground/20 mb-4" />
                    <p className="text-sm font-medium text-muted-foreground">No active test</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Select a scenario and click "Run Test Call" to start
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
                        <p className={`text-xs mt-1 ${
                          msg.role === 'customer' ? 'text-primary-foreground/60' : 'text-muted-foreground'
                        }`}>
                          {msg.timestamp}
                        </p>
                      </div>
                      {msg.role === 'customer' && (
                        <div className="w-7 h-7 rounded-full bg-accent/10 flex items-center justify-center flex-shrink-0 mt-0.5">
                          <User className="w-3.5 h-3.5 text-accent" />
                        </div>
                      )}
                    </motion.div>
                  ))}
                </AnimatePresence>

                {isRunning && displayIndex < (callResult?.transcript?.length || 0) && (
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
                  <Badge variant="secondary" className={`text-xs ${
                    isRunning ? 'bg-primary/10 text-primary' : 
                    callResult ? 'bg-success/10 text-success' : ''
                  } border-0`}>
                    {isRunning ? 'Running' : callResult ? 'Completed' : 'Idle'}
                  </Badge>
                </div>
                <div className="flex justify-between">
                  <span className="text-xs text-muted-foreground">Duration</span>
                  <span className="text-sm font-medium text-foreground">{formatTimer(callDuration)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-xs text-muted-foreground">AI Model</span>
                  <span className="text-xs text-muted-foreground">
                    {status?.gemini?.model || 'Gemini 2.5 Flash'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-xs text-muted-foreground">Mode</span>
                  <span className="text-xs text-muted-foreground">
                    {status?.mode || 'sandbox'}
                  </span>
                </div>
                {callResult && (
                  <>
                    <Separator />
                    <div className="flex justify-between">
                      <span className="text-xs text-muted-foreground">Quality Score</span>
                      <span className="text-sm font-bold text-foreground">{callResult.quality_score}/100</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-xs text-muted-foreground">Result</span>
                      {callResult.status === 'COMPLETED' ? (
                        <Badge variant="secondary" className="bg-success/10 text-success border-0 text-xs gap-1">
                          <CheckCircle2 className="w-3 h-3" /> Success
                        </Badge>
                      ) : (
                        <Badge variant="secondary" className="bg-accent/10 text-accent border-0 text-xs gap-1">
                          <AlertTriangle className="w-3 h-3" /> Escalated
                        </Badge>
                      )}
                    </div>
                  </>
                )}
              </div>
            </Card>

            {/* Live Cart */}
            <Card className="p-5 border-border bg-card">
              <h3 className="text-sm font-heading font-semibold text-foreground mb-3">Order Cart</h3>
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

            {/* Analysis Preview */}
            {callResult?.analysis_json && (
              <Card className="p-5 border-border bg-card">
                <h3 className="text-sm font-heading font-semibold text-foreground mb-3">AI Analysis</h3>
                <p className="text-xs text-muted-foreground mb-3">{callResult.analysis_json.summary}</p>
                {callResult.analysis_json.highlights?.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {callResult.analysis_json.highlights.slice(0, 3).map((h, i) => (
                      <Badge key={i} variant="secondary" className="text-xs bg-success/10 text-success border-0">
                        {h}
                      </Badge>
                    ))}
                  </div>
                )}
              </Card>
            )}
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
