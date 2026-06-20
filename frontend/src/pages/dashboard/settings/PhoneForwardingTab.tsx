import { useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from "react";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertTriangle, Copy, PhoneForwarded, Save } from "lucide-react";
import { toast } from "sonner";
import { updateConfig, updateRestaurant } from "@/lib/api";
import type { Restaurant, Config } from "@/types";
import { CARRIERS } from "./forwardingInstructions";

interface Props {
  restaurantId: string | null;
  restaurant: Restaurant | null;
  setRestaurant: Dispatch<SetStateAction<Restaurant | null>>;
  config: Config | null;
  setConfig: Dispatch<SetStateAction<Config | null>>;
  onAfterSave?: () => Promise<void>;
}

interface ConflictHighlight {
  business_phone: boolean;
  escalation_phone_number: boolean;
  phone_number: boolean;
}

const NO_CONFLICT: ConflictHighlight = {
  business_phone: false,
  escalation_phone_number: false,
  phone_number: false,
};

// The backend wraps the conflicting labels into a sentence like
// "phone_number and business_phone must be different phone numbers...".
// Parse that out so we can highlight the right fields inline. Note that
// the literal "phone_number" substring also matches inside
// "escalation_phone_number", so we strip that occurrence before checking.
const detectConflictFields = (message: string): ConflictHighlight => {
  if (!message) return NO_CONFLICT;
  const lower = message.toLowerCase();
  const business = lower.includes("business_phone");
  const escalation = lower.includes("escalation_phone_number");
  const withoutEscalation = lower.replace(/escalation_phone_number/g, "");
  const phone = withoutEscalation.includes("phone_number");
  return {
    phone_number: phone,
    business_phone: business,
    escalation_phone_number: escalation,
  };
};

const substituteAINumber = (template: string, aiNumber: string): string => {
  const display = aiNumber?.trim() ? aiNumber : "your AI number";
  return template.replace(/\{AI number\}/g, display);
};

export default function PhoneForwardingTab({
  restaurantId,
  restaurant,
  setRestaurant,
  config,
  setConfig,
  onAfterSave,
}: Props) {
  const aiNumber = restaurant?.phone_number || "";
  const businessName = restaurant?.name || "your business";
  const businessPhone = restaurant?.business_phone || "";
  const escalationPhone = config?.escalation_phone_number || "";

  // Selected carrier persists for the lifetime of the tab.
  const [carrierId, setCarrierId] = useState<string>(CARRIERS[0].id);

  // Backend 400 detail string + which fields it referenced.
  const [conflictMessage, setConflictMessage] = useState<string | null>(null);
  const conflict = useMemo(
    () => (conflictMessage ? detectConflictFields(conflictMessage) : NO_CONFLICT),
    [conflictMessage],
  );

  // Inline soft warning when the user saves with no business phone set.
  const [showEmptyWarning, setShowEmptyWarning] = useState(false);

  const [saving, setSaving] = useState(false);

  // Snapshot of last-known-persisted values so we only PUT changed fields.
  // Initialised once data first arrives and refreshed after a successful save.
  const lastSavedBusinessPhoneRef = useRef<string>(businessPhone);
  const lastSavedEscalationRef = useRef<string>(escalationPhone);
  const initializedRef = useRef<boolean>(false);
  useEffect(() => {
    if (!initializedRef.current && (restaurant || config)) {
      lastSavedBusinessPhoneRef.current = businessPhone;
      lastSavedEscalationRef.current = escalationPhone;
      initializedRef.current = true;
    }
  }, [restaurant, config, businessPhone, escalationPhone]);

  const handleCopyAINumber = async () => {
    if (!aiNumber) {
      toast.error("No AI number to copy yet");
      return;
    }
    try {
      await navigator.clipboard.writeText(aiNumber);
      toast.success("AI number copied to clipboard");
    } catch {
      toast.error("Could not copy â€” please copy manually");
    }
  };

  const handleSave = async () => {
    setConflictMessage(null);
    setShowEmptyWarning(!businessPhone?.trim());

    if (!restaurantId) {
      toast.error("No active restaurant â€” refresh and try again");
      return;
    }

    const businessChanged = businessPhone !== lastSavedBusinessPhoneRef.current;
    const escalationChanged = escalationPhone !== lastSavedEscalationRef.current;

    if (!businessChanged && !escalationChanged) {
      toast.success("No changes to save");
      return;
    }

    setSaving(true);
    try {
      if (businessChanged) {
        await updateRestaurant(restaurantId, { business_phone: businessPhone });
        lastSavedBusinessPhoneRef.current = businessPhone;
      }
      if (escalationChanged) {
        await updateConfig(restaurantId, {
          escalation_phone_number: escalationPhone,
        });
        lastSavedEscalationRef.current = escalationPhone;
      }
      if (onAfterSave) await onAfterSave();
      toast.success("Phone settings saved");
    } catch (err: unknown) {
      let detail: string | null = null;
      if (axios.isAxiosError(err)) {
        const respDetail = err.response?.data?.detail;
        if (typeof respDetail === "string") detail = respDetail;
      } else if (typeof err === "string") {
        detail = err;
      } else if (typeof err === "object" && err !== null) {
        // Some callers (and tests) hand us a plain object shaped like an
        // axios error rather than a real AxiosError instance.
        if (
          "response" in err &&
          typeof err.response === "object" &&
          err.response !== null &&
          "data" in err.response &&
          typeof err.response.data === "object" &&
          err.response.data !== null &&
          "detail" in err.response.data &&
          typeof err.response.data.detail === "string"
        ) {
          detail = err.response.data.detail;
        } else if ("detail" in err && typeof err.detail === "string") {
          detail = err.detail;
        }
      }
      if (detail) {
        setConflictMessage(detail);
        toast.error(detail);
      } else {
        toast.error("Failed to save phone settings");
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* ----------------------------------------------------------------- */}
      {/* Section 1 â€” Your phone numbers                                    */}
      {/* ----------------------------------------------------------------- */}
      <Card className="dash-card p-6 space-y-5">
        <div>
          <h3 className="font-display font-bold text-lg mb-1">Your phone numbers</h3>
          <p className="text-sm text-ink-soft">
            Three distinct numbers power your AI assistant. The AI number is the line
            we provision for you; your business and escalation numbers are yours.
          </p>
        </div>

        {conflictMessage && (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Phone numbers must be distinct</AlertTitle>
            <AlertDescription>{conflictMessage}</AlertDescription>
          </Alert>
        )}

        {/* AI number â€” read-only with copy */}
        <div className="space-y-2">
          <Label htmlFor="ai-number">Duuutah AI number (read-only)</Label>
          <div className="flex gap-2">
            <Input
              id="ai-number"
              value={aiNumber}
              readOnly
              placeholder="Pending provisioning"
              aria-invalid={conflict.phone_number || undefined}
              className={`h-11 rounded-xl opacity-90 ${
                conflict.phone_number
                  ? "border-destructive focus-visible:ring-destructive"
                  : ""
              }`}
            />
            <Button
              type="button"
              variant="outline"
              onClick={handleCopyAINumber}
              disabled={!aiNumber}
              className="h-11 rounded-xl"
              aria-label="Copy AI number"
            >
              <Copy className="w-4 h-4 mr-2" />
              Copy
            </Button>
          </div>
          <p className="text-xs text-ink-soft">
            The line your AI assistant answers. Type this into your carrier's
            call-forwarding setup so calls to your business phone route here.
          </p>
        </div>

        {/* Business phone â€” editable */}
        <div className="space-y-2">
          <Label htmlFor="business-phone">Business phone</Label>
          <Input
            id="business-phone"
            value={businessPhone}
            onChange={(e) => {
              setRestaurant({ ...restaurant, business_phone: e.target.value });
              if (conflictMessage) setConflictMessage(null);
              if (showEmptyWarning && e.target.value.trim()) setShowEmptyWarning(false);
            }}
            placeholder="+13125551234"
            aria-invalid={conflict.business_phone || undefined}
            className={`h-11 rounded-xl ${
              conflict.business_phone
                ? "border-destructive focus-visible:ring-destructive"
                : ""
            }`}
          />
          <p className="text-xs text-ink-soft">
            The number customers call. You'll forward this line to your AI number
            using the instructions below.
          </p>
        </div>

        {/* Escalation phone â€” editable, optional */}
        <div className="space-y-2">
          <Label htmlFor="escalation-phone">Escalation phone</Label>
          <Input
            id="escalation-phone"
            value={escalationPhone}
            onChange={(e) => {
              setConfig({ ...config, escalation_phone_number: e.target.value });
              if (conflictMessage) setConflictMessage(null);
            }}
            placeholder="+13125559876"
            aria-invalid={conflict.escalation_phone_number || undefined}
            className={`h-11 rounded-xl ${
              conflict.escalation_phone_number
                ? "border-destructive focus-visible:ring-destructive"
                : ""
            }`}
          />
          <p className="text-xs text-ink-soft">
            A separate phone inside your business that rings when the AI hands off
            to a human. Must be different from your AI and business numbers. Optional.
          </p>
        </div>

        {showEmptyWarning && (
          <Alert>
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>
              Your AI won't receive customer calls until you set a business phone
              and configure forwarding.
            </AlertDescription>
          </Alert>
        )}

        <Button
          onClick={handleSave}
          disabled={saving}
          className="bg-coral hover:bg-coral-deep text-white rounded-xl hover:opacity-90"
        >
          <Save className="w-4 h-4 mr-2" />
          {saving ? "Saving..." : "Save Changes"}
        </Button>
      </Card>

      {/* ----------------------------------------------------------------- */}
      {/* Section 2 â€” Set up call forwarding                                */}
      {/* ----------------------------------------------------------------- */}
      <Card className="dash-card p-6 space-y-5">
        <div>
          <h3 className="font-display font-bold text-lg mb-1 flex items-center gap-2">
            <PhoneForwarded className="w-5 h-5" />
            Set up call forwarding
          </h3>
          <p className="text-sm text-ink-soft">
            To use your AI assistant, forward calls from your business phone to your
            Duuutah AI number. Choose your carrier below for step-by-step instructions.
          </p>
        </div>

        <Tabs value={carrierId} onValueChange={setCarrierId} className="space-y-4">
          <TabsList className="bg-cream rounded-xl p-1 h-auto flex-wrap">
            {CARRIERS.map((c) => (
              <TabsTrigger
                key={c.id}
                value={c.id}
                className="rounded-lg px-3 py-1.5 text-xs sm:text-sm data-[state=active]:bg-card data-[state=active]:shadow-sm"
              >
                {c.label}
              </TabsTrigger>
            ))}
          </TabsList>

          {CARRIERS.map((c) => (
            <TabsContent key={c.id} value={c.id} className="space-y-5">
              <div>
                <h4 className="text-sm font-semibold mb-2">Turn forwarding on</h4>
                <ol className="space-y-2 list-decimal list-inside text-sm text-foreground/90">
                  {c.activationSteps.map((step, idx) => (
                    <li key={idx}>{substituteAINumber(step, aiNumber)}</li>
                  ))}
                </ol>
              </div>
              <div>
                <h4 className="text-sm font-semibold mb-2">Turn forwarding off</h4>
                <ol className="space-y-2 list-decimal list-inside text-sm text-foreground/90">
                  {c.deactivationSteps.map((step, idx) => (
                    <li key={idx}>{substituteAINumber(step, aiNumber)}</li>
                  ))}
                </ol>
              </div>
              {c.notes && (
                <Alert>
                  <AlertDescription className="text-xs">
                    {substituteAINumber(c.notes, aiNumber)}
                  </AlertDescription>
                </Alert>
              )}
            </TabsContent>
          ))}
        </Tabs>
      </Card>

      {/* ----------------------------------------------------------------- */}
      {/* Section 3 â€” Verify your forwarding works                          */}
      {/* ----------------------------------------------------------------- */}
      <Card className="dash-card p-6 space-y-4">
        <div>
          <h3 className="font-display font-bold text-lg mb-1">
            Verify your forwarding works
          </h3>
          <p className="text-sm text-ink-soft">
            Run through this checklist after you set up forwarding on your carrier.
          </p>
        </div>

        {!businessPhone || !aiNumber ? (
          <Alert>
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>
              Set your phone numbers in Section 1 first.
            </AlertDescription>
          </Alert>
        ) : (
          <ol className="space-y-2 list-decimal list-inside text-sm text-foreground/90">
            <li>Set up forwarding using the steps above.</li>
            <li>
              From a different phone (not your business line), dial your business
              phone number:{" "}
              <span className="font-mono font-semibold">{businessPhone}</span>.
            </li>
            <li>
              You should hear: <em>"Welcome to {businessName}!"</em> or your AI's
              configured greeting.
            </li>
            <li>If you hear the AI greeting â€” forwarding is working.</li>
            <li>
              If your business phone rings normally â€” forwarding isn't set up
              correctly. Try the carrier steps again or contact your carrier.
            </li>
          </ol>
        )}
      </Card>
    </div>
  );
}
