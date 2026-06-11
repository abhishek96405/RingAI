import { useCallback, useEffect, useState } from "react";
import { useAppSession } from "@/context/AppSessionContext";
import { getRestaurantId, getStatus, getTestModeStatus, getTelnyxStatus, getSquareConnectUrl, provisionTelnyxNumber, assignTelnyxNumber, getCalendarStatus, connectGoogleCalendar, disconnectGoogleCalendar, savePOSCredentials, testPOSConnection } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CheckCircle2, CreditCard, Key, Phone, ShieldAlert, Sparkles, TestTube, CalendarDays, Store, Loader2 } from "lucide-react";
import { toast } from "sonner";

function POSCredentialsCard({ restaurantId }: { restaurantId: string }) {
  const [posType, setPosType] = useState("clover");
  const [posEnv, setPosEnv] = useState("sandbox");
  const [cloverToken, setCloverToken] = useState("");
  const [cloverMid, setCloverMid] = useState("");
  const [squareToken, setSquareToken] = useState("");
  const [squareLocationId, setSquareLocationId] = useState("");
  const [toastClientId, setToastClientId] = useState("");
  const [toastClientSecret, setToastClientSecret] = useState("");
  const [toastRestaurantGuid, setToastRestaurantGuid] = useState("");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message?: string } | null>(null);

  const handleTest = async () => {
    try {
      setTesting(true);
      setTestResult(null);
      const res = await testPOSConnection(restaurantId);
      setTestResult(res.data);
      if (res.data.success) toast.success("POS connection successful!");
      else toast.error(res.data.error || "Connection failed");
    } catch {
      setTestResult({ success: false, message: "Connection test failed" });
      toast.error("Connection test failed");
    } finally {
      setTesting(false);
    }
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      await savePOSCredentials({
        pos_type: posType,
        pos_env: posEnv,
        clover_api_token: cloverToken || undefined,
        clover_merchant_id: cloverMid || undefined,
        square_access_token: squareToken || undefined,
        square_location_id: squareLocationId || undefined,
        toast_client_id: toastClientId || undefined,
        toast_client_secret: toastClientSecret || undefined,
        toast_restaurant_guid: toastRestaurantGuid || undefined,
      }, restaurantId);
      toast.success("POS credentials saved");
    } catch {
      toast.error("Failed to save POS credentials");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="premium-card p-6 space-y-4">
      <div className="flex items-center gap-2">
        <Store className="w-5 h-5 text-primary" />
        <h3 className="font-display font-bold text-lg">POS Integration</h3>
      </div>
      <p className="text-sm text-muted-foreground">Connect your Point of Sale system to sync your menu automatically.</p>
      <div className="space-y-2">
        <Label>POS System</Label>
        <select value={posType} onChange={e => { setPosType(e.target.value); setTestResult(null); }} className="w-full h-10 rounded-xl border border-border bg-card px-3 text-sm">
          <option value="clover">Clover</option>
          <option value="square">Square</option>
          <option value="toast">Toast</option>
        </select>
      </div>
      <div className="space-y-2">
        <Label>Environment</Label>
        <select value={posEnv} onChange={e => setPosEnv(e.target.value)} className="w-full h-10 rounded-xl border border-border bg-card px-3 text-sm">
          <option value="sandbox">Sandbox (Testing)</option>
          <option value="production">Production (Live)</option>
        </select>
        <p className="text-xs text-muted-foreground">Use Sandbox for testing. Switch to Production only when you have live POS credentials.</p>
      </div>

      {posType === "clover" && (
        <>
          <div className="space-y-2">
            <Label>API Token</Label>
            <Input value={cloverToken} onChange={e => setCloverToken(e.target.value)} placeholder="Enter Clover API token" type="password" className="rounded-xl" />
          </div>
          <div className="space-y-2">
            <Label>Merchant ID</Label>
            <Input value={cloverMid} onChange={e => setCloverMid(e.target.value)} placeholder="e.g. BP79YX4YNBJW1" className="rounded-xl" />
          </div>
          <p className="text-xs text-muted-foreground">Find these in your Clover Developer Dashboard → App Settings → API Credentials.</p>
        </>
      )}

      {posType === "square" && (
        <>
          <div className="space-y-2">
            <Label>Access Token</Label>
            <Input value={squareToken} onChange={e => setSquareToken(e.target.value)} placeholder="Enter Square Access Token" type="password" className="rounded-xl" />
          </div>
          <div className="space-y-2">
            <Label>Location ID</Label>
            <Input value={squareLocationId} onChange={e => setSquareLocationId(e.target.value)} placeholder="Enter Square Location ID" className="rounded-xl" />
          </div>
          <p className="text-xs text-muted-foreground">Find these in your Square Developer Dashboard → Applications → Credentials.</p>
        </>
      )}

      {posType === "toast" && (
        <>
          <div className="space-y-2">
            <Label>Client ID</Label>
            <Input value={toastClientId} onChange={e => setToastClientId(e.target.value)} placeholder="Enter Toast Client ID" className="rounded-xl" />
          </div>
          <div className="space-y-2">
            <Label>Client Secret</Label>
            <Input value={toastClientSecret} onChange={e => setToastClientSecret(e.target.value)} placeholder="Enter Toast Client Secret" type="password" className="rounded-xl" />
          </div>
          <div className="space-y-2">
            <Label>Restaurant GUID</Label>
            <Input value={toastRestaurantGuid} onChange={e => setToastRestaurantGuid(e.target.value)} placeholder="Enter Toast Restaurant GUID" className="rounded-xl" />
          </div>
          <p className="text-xs text-muted-foreground">Find Client ID and Secret in Toast Developer Portal → Credentials. Restaurant GUID is in Toast Web → Admin → General.</p>
        </>
      )}

      {testResult && (
        <div className={`text-sm p-2 rounded-lg ${testResult.success ? "bg-green-500/10 text-green-600" : "bg-red-500/10 text-red-600"}`}>
          {testResult.success ? "✓ Connection successful" : `✗ ${testResult.message || "Connection failed"}`}
        </div>
      )}

      <div className="flex gap-2">
        <Button variant="outline" onClick={handleTest} disabled={testing} className="rounded-xl flex-1">
          {testing ? <><Loader2 className="w-4 h-4 animate-spin mr-1" /> Testing...</> : "Test Connection"}
        </Button>
        <Button onClick={handleSave} disabled={saving} className="bg-gradient-primary text-primary-foreground rounded-xl shadow-glow hover:opacity-90 flex-1">
          {saving ? "Saving..." : "Save Credentials"}
        </Button>
      </div>
    </Card>
  );
}

const IntegrationsPage = () => {
  const { activeRestaurant } = useAppSession();
  const [testMode, setTestMode] = useState<any>(null);
  const [status, setStatus] = useState<any>(null);
  const [telnyxStatus, setTelnyxStatusState] = useState<any>(null);
  const [areaCode, setAreaCode] = useState("");
  const [existingNumber, setExistingNumber] = useState("");
  const [loading, setLoading] = useState(true);
  const [calendarConnected, setCalendarConnected] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const restaurantId = activeRestaurant?.id || getRestaurantId();
      const [testModeRes, statusRes, telnyxRes, calendarRes] = await Promise.all([
        getTestModeStatus(),
        getStatus(),
        getTelnyxStatus(restaurantId),
        getCalendarStatus(restaurantId).catch(() => ({ data: { connected: false } })),
      ]);
      setTestMode(testModeRes.data);
      setStatus(statusRes.data);
      setTelnyxStatusState(telnyxRes.data);
      setCalendarConnected(calendarRes.data?.connected || false);
    } catch {
      toast.error("Failed to load integrations");
    } finally {
      setLoading(false);
    }
  }, [activeRestaurant]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const connectSquare = async () => {
    try {
      const restaurantId = activeRestaurant?.id || getRestaurantId();
      const res = await getSquareConnectUrl(restaurantId);
      const url = res?.data?.connect_url;
      if (!url) return toast.error("Square connect URL not available");
      window.location.href = url;
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to start Square connection");
    }
  };

  const provisionNumber = async () => {
    try {
      const restaurantId = activeRestaurant?.id || getRestaurantId();
      await provisionTelnyxNumber(restaurantId, areaCode);
      await fetchData();
      toast.success("Telnyx number provisioned");
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to provision Telnyx number");
    }
  };

  const assignExistingNumber = async () => {
    if (!existingNumber.trim()) {
      toast.error("Please enter a phone number");
      return;
    }
    try {
      const restaurantId = activeRestaurant?.id || getRestaurantId();
      await assignTelnyxNumber(restaurantId, existingNumber.trim());
      await fetchData();
      toast.success("Telnyx number assigned successfully");
      setExistingNumber("");
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to assign Telnyx number");
    }
  };

  const connectCalendar = async () => {
    try {
      const restaurantId = activeRestaurant?.id || getRestaurantId();
      const res = await connectGoogleCalendar(restaurantId);
      const url = res?.data?.authorization_url;
      if (!url) return toast.error("Google Calendar connect URL not available");
      window.location.href = url;
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Google Calendar not configured — check GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in Render");
    }
  };

  const disconnectCalendar = async () => {
    if (!confirm("Disconnect Google Calendar?")) return;
    try {
      const restaurantId = activeRestaurant?.id || getRestaurantId();
      await disconnectGoogleCalendar(restaurantId);
      setCalendarConnected(false);
      toast.success("Google Calendar disconnected");
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to disconnect");
    }
  };

  if (loading) return <Card className="premium-card h-48 animate-pulse" />;

  return (
    <div className="space-y-6 max-w-4xl">
      <Card className="premium-card p-6">
        <h3 className="font-display font-bold text-lg mb-4 flex items-center gap-2"><Key className="w-4 h-4" /> Integration Status</h3>
        <p className="text-xs text-muted-foreground mb-4">Current mode: <Badge variant="secondary" className={`ml-1 ${(testMode?.mode === "sandbox") ? "bg-primary/10 text-primary" : (testMode?.mode === "live") ? "bg-success/10 text-success" : "bg-muted"} border-0`}>{testMode?.mode || "simulation"}</Badge></p>
        <div className="space-y-3">
          {[
            { name: "Gemini AI", icon: Sparkles, configured: !!status?.gemini?.available, message: testMode?.integrations?.gemini?.message || "Not configured" },
            { name: "Telnyx Telephony", icon: Phone, configured: !!status?.telnyx?.available, message: testMode?.integrations?.telnyx?.message || "Not configured" },
            { name: "Stripe Billing", icon: CreditCard, configured: !!testMode?.integrations?.stripe?.configured, message: testMode?.integrations?.stripe?.message || "Not configured" },
            { name: "Clerk Authentication", icon: ShieldAlert, configured: !!testMode?.integrations?.clerk?.configured, message: testMode?.integrations?.clerk?.message || "Not configured" },
          ].map((item) => <div key={item.name} className="flex items-center justify-between p-4 rounded-lg border border-border"><div className="flex items-center gap-3"><div className={`w-10 h-10 rounded-lg flex items-center justify-center ${item.configured ? "bg-success/10" : "bg-muted"}`}><item.icon className={`w-5 h-5 ${item.configured ? "text-success" : "text-muted-foreground"}`} /></div><div><p className="text-sm font-medium">{item.name}</p><p className="text-xs text-muted-foreground">{item.message}</p></div></div>{item.configured ? <Badge variant="secondary" className="bg-success/10 text-success border-0 gap-1"><CheckCircle2 className="w-3 h-3" /> Active</Badge> : <Badge variant="secondary" className="bg-warning/10 text-warning border-0 gap-1"><TestTube className="w-3 h-3" /> Simulated</Badge>}</div>)}
        </div>
      </Card>

      <Card className="premium-card p-6 space-y-4">
        <h3 className="font-display font-bold text-lg">Telnyx Number</h3>
        <div className="space-y-2"><Label>Current Number</Label><Input value={telnyxStatus?.phone_number || status?.telnyx?.phone_number || ""} readOnly placeholder="No number assigned yet" /></div>
        <div className="space-y-2"><Label>Preferred Area Code</Label><Input value={areaCode} onChange={(e) => setAreaCode(e.target.value)} placeholder="815" /></div>
        <div className="space-y-2"><Label>Or Assign Existing Number</Label><Input value={existingNumber} onChange={(e) => setExistingNumber(e.target.value)} placeholder="+19803515351" /></div>
        <div className="flex gap-2 flex-wrap">
          <Button className="bg-gradient-primary text-primary-foreground rounded-xl shadow-glow hover:opacity-90" onClick={provisionNumber}>Provision New Number</Button>
          <Button variant="outline" onClick={assignExistingNumber}>Assign Existing Number</Button>
          <Button variant="outline" onClick={connectSquare}>Connect Square</Button>
        </div>
      </Card>

      <Card className="premium-card p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CalendarDays className="w-5 h-5 text-primary" />
            <h3 className="font-display font-bold text-lg">Google Calendar</h3>
          </div>
          {calendarConnected && (
            <Badge variant="secondary" className="bg-success/10 text-success border-0 gap-1">
              <CheckCircle2 className="w-3 h-3" /> Connected
            </Badge>
          )}
        </div>
        <p className="text-sm text-muted-foreground">
          Sync appointments directly to your Google Calendar. New bookings will appear automatically.
        </p>
        {calendarConnected ? (
          <Button variant="outline" className="text-destructive" onClick={disconnectCalendar}>
            Disconnect Google Calendar
          </Button>
        ) : (
          <Button className="bg-gradient-primary text-primary-foreground rounded-xl shadow-glow hover:opacity-90" onClick={connectCalendar}>
            Connect Google Calendar
          </Button>
        )}
      </Card>

      <POSCredentialsCard restaurantId={activeRestaurant?.id || getRestaurantId() || ""} />

      <Card className="premium-card p-6">
        <h3 className="font-display font-bold text-lg mb-2">Required Environment Variables</h3>
        <div className="space-y-2 text-xs font-mono bg-muted/30 p-4 rounded-lg">
          <p className="text-muted-foreground"># Frontend</p>
          <p>VITE_BACKEND_URL=https://your-backend.onrender.com</p>
          <p>VITE_CLERK_PUBLISHABLE_KEY=pk_test_xxxxx</p>
          <p className="text-muted-foreground mt-3"># Backend</p>
          <p>TELNYX_API_KEY=KEYxxxxxx</p>
          <p>TELNYX_PUBLIC_KEY=xxxxxx</p>
          <p>TELNYX_MESSAGING_PROFILE_ID=xxxxxx</p>
          <p>TELNYX_TEXML_APP_ID=xxxxxx</p>
          <p>STRIPE_SECRET_KEY=sk_test_xxxxx</p>
          <p>STRIPE_DEFAULT_PRICE_ID=price_xxxxx</p>
          <p>CLERK_JWKS_URL=https://your-clerk/.well-known/jwks.json</p>
          <p>MONGO_URL=mongodb+srv://...</p>
        </div>
      </Card>
    </div>
  );
};

export default IntegrationsPage;
