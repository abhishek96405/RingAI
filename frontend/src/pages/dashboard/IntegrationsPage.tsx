import { useCallback, useEffect, useState } from "react";
import { useAppSession } from "@/context/AppSessionContext";
import { getRestaurantId, getSquareConnectUrl, getCloverConnectUrl, setPendingCloverRestaurantId, getCalendarStatus, connectGoogleCalendar, disconnectGoogleCalendar, savePOSCredentials, testPOSConnection, getRestaurant } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CheckCircle2, CalendarDays, Store, Loader2, Lock, ChevronDown } from "lucide-react";
import { toast } from "sonner";

function POSCard({ restaurantId, squareConnected, cloverConnected }: { restaurantId: string; squareConnected: boolean; cloverConnected: boolean }) {
  const [manualOpen, setManualOpen] = useState(false);

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

  const connectSquare = async () => {
    try {
      const res = await getSquareConnectUrl(restaurantId);
      const url = res?.data?.connect_url;
      if (!url) return toast.error("Square connect URL not available");
      window.location.href = url;
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to start Square connection");
    }
  };

  const handleConnectClover = async () => {
    try {
      setPendingCloverRestaurantId(restaurantId);
      const res = await getCloverConnectUrl(restaurantId);
      const url = res?.data?.connect_url;
      if (!url) return toast.error("Clover connect URL not available");
      window.location.href = url;
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to start Clover connection");
    }
  };

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

  const ConnectedBadge = () => (
    <Badge variant="secondary" className="bg-success/10 text-success border-0 gap-1">
      <CheckCircle2 className="w-3 h-3" /> Connected
    </Badge>
  );

  return (
    <Card className="dash-card p-6 space-y-6">
      {/* Section 1 — Connect your POS (primary path) */}
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <Store className="w-5 h-5 text-coral" />
          <h3 className="font-display font-bold text-lg">Connect your POS</h3>
        </div>
        <p className="text-sm text-ink-soft">Duuutah AI syncs your menu automatically once connected.</p>

        <div className="space-y-3">
          {/* Square */}
          <div className="flex items-center justify-between p-4 rounded-xl border border-line hover:bg-cream transition-colors">
            <p className="text-sm font-medium">Square</p>
            {squareConnected ? (
              <ConnectedBadge />
            ) : (
              <Button onClick={connectSquare} className="bg-coral hover:bg-coral-deep text-white rounded-xl hover:opacity-90">
                Connect with Square
              </Button>
            )}
          </div>

          {/* Clover */}
          <div className="flex items-center justify-between p-4 rounded-xl border border-line hover:bg-cream transition-colors">
            <p className="text-sm font-medium">Clover</p>
            {cloverConnected ? (
              <ConnectedBadge />
            ) : (
              <Button onClick={handleConnectClover} className="bg-coral hover:bg-coral-deep text-white rounded-xl hover:opacity-90">
                Connect with Clover
              </Button>
            )}
          </div>

          {/* Toast */}
          <div className="flex items-center justify-between p-4 rounded-xl border border-line hover:bg-cream transition-colors">
            <div>
              <p className="text-sm font-medium">Toast</p>
              <p className="text-xs text-ink-soft">Toast integration is coming soon.</p>
            </div>
            <Button disabled variant="outline" className="rounded-xl gap-1">
              <Lock className="w-4 h-4" /> Coming soon
            </Button>
          </div>
        </div>
      </div>

      {/* Section 2 — Advanced: enter credentials manually (collapsed by default) */}
      <div className="border-t border-line pt-4">
        <button
          type="button"
          onClick={() => setManualOpen((v) => !v)}
          className="flex w-full items-center justify-between text-sm font-medium text-ink-soft hover:text-foreground transition-colors"
          aria-expanded={manualOpen}
        >
          <span>Advanced: enter credentials manually</span>
          <ChevronDown className={`w-4 h-4 transition-transform ${manualOpen ? "rotate-180" : ""}`} />
        </button>

        {manualOpen && (
          <div className="space-y-4 pt-4">
            <div className="space-y-2">
              <Label>POS System</Label>
              <select value={posType} onChange={e => { setPosType(e.target.value); setTestResult(null); }} className="w-full h-10 rounded-xl border border-line bg-card px-3 text-sm">
                <option value="clover">Clover</option>
                <option value="square">Square</option>
                <option value="toast">Toast</option>
              </select>
            </div>
            <div className="space-y-2">
              <Label>Environment</Label>
              <select value={posEnv} onChange={e => setPosEnv(e.target.value)} className="w-full h-10 rounded-xl border border-line bg-card px-3 text-sm">
                <option value="sandbox">Sandbox (Testing)</option>
                <option value="production">Production (Live)</option>
              </select>
              <p className="text-xs text-ink-soft">Use Sandbox for testing. Switch to Production only when you have live POS credentials.</p>
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
                <p className="text-xs text-ink-soft">Find these in your Clover Developer Dashboard → App Settings → API Credentials.</p>
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
                <p className="text-xs text-ink-soft">Find these in your Square Developer Dashboard → Applications → Credentials.</p>
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
                <p className="text-xs text-ink-soft">Find Client ID and Secret in Toast Developer Portal → Credentials. Restaurant GUID is in Toast Web → Admin → General.</p>
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
              <Button onClick={handleSave} disabled={saving} className="bg-coral hover:bg-coral-deep text-white rounded-xl hover:opacity-90 flex-1">
                {saving ? "Saving..." : "Save Credentials"}
              </Button>
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}

const IntegrationsPage = () => {
  const { activeRestaurant } = useAppSession();
  const [loading, setLoading] = useState(true);
  const [calendarConnected, setCalendarConnected] = useState(false);
  const [squareConnected, setSquareConnected] = useState(false);
  const [cloverConnected, setCloverConnected] = useState(false);
  const [businessType, setBusinessType] = useState("restaurant");

  const fetchData = useCallback(async () => {
    try {
      const restaurantId = activeRestaurant?.id || getRestaurantId();
      // Connected-state is read FRESH from the restaurant doc on mount (not from
      // the stale AppSession bootstrap payload) so badges are correct immediately
      // after returning from an OAuth connect.
      const [restaurantRes, calendarRes] = await Promise.all([
        getRestaurant(restaurantId),
        getCalendarStatus(restaurantId).catch(() => ({ data: { connected: false } })),
      ]);
      const r = restaurantRes.data || {};
      setSquareConnected(!!r.square_connected);
      setCloverConnected(!!r.clover_connected);
      setBusinessType(r.business_type || "restaurant");
      setCalendarConnected(calendarRes.data?.connected || false);
    } catch {
      toast.error("Failed to load integrations");
    } finally {
      setLoading(false);
    }
  }, [activeRestaurant]);

  useEffect(() => { fetchData(); }, [fetchData]);

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

  if (loading) return <div className="dash"><Card className="dash-card h-48 animate-pulse" /></div>;

  return (
    <div className="dash space-y-6 max-w-4xl">
      <div>
        <p className="eyebrow mb-2">Connections</p>
        <h1 className="text-2xl font-display font-bold">Integrations</h1>
        <p className="text-sm text-ink-soft mt-1">Connect your POS and calendar so Duuutah AI stays in sync.</p>
      </div>

      {/* Calendar card: shown for every appointment-based vertical (salon, clinic,
          home_services, legal), hidden only for restaurants. */}
      {businessType !== "restaurant" && (
        <Card className="dash-card p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <CalendarDays className="w-5 h-5 text-coral" />
              <h3 className="font-display font-bold text-lg">Google Calendar</h3>
            </div>
            {calendarConnected && (
              <Badge variant="secondary" className="bg-success/10 text-success border-0 gap-1">
                <CheckCircle2 className="w-3 h-3" /> Connected
              </Badge>
            )}
          </div>
          <p className="text-sm text-ink-soft">
            Sync appointments directly to your Google Calendar. New bookings will appear automatically.
          </p>
          {calendarConnected ? (
            <Button variant="outline" className="text-destructive" onClick={disconnectCalendar}>
              Disconnect Google Calendar
            </Button>
          ) : (
            <Button className="bg-coral hover:bg-coral-deep text-white rounded-xl hover:opacity-90" onClick={connectCalendar}>
              Connect Google Calendar
            </Button>
          )}
        </Card>
      )}

      <POSCard
        restaurantId={activeRestaurant?.id || getRestaurantId() || ""}
        squareConnected={squareConnected}
        cloverConnected={cloverConnected}
      />
    </div>
  );
};

export default IntegrationsPage;
