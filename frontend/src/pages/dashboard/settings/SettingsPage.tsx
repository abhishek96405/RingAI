import { useCallback, useEffect, useState } from "react";
import { useAppSession } from "@/context/AppSessionContext";
import { getConfig, getRestaurant, getRestaurantId, updateConfig, updateRestaurant } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Building2, Clock, PhoneForwarded, ShoppingBag, Mic, ShieldAlert } from "lucide-react";
import { toast } from "sonner";
import { APPOINTMENT_TYPES, defaultHours, getBusinessLabel, type FieldErrors } from "./constants";
import BusinessTab from "./BusinessTab";
import PhoneForwardingTab from "./PhoneForwardingTab";
import HoursTab from "./HoursTab";
import FulfillmentTab from "./FulfillmentTab";
import VoiceAndAITab from "./VoiceAndAITab";
import RulesTab from "./RulesTab";

const SettingsPage = () => {
  const { activeRestaurant, refreshSession } = useAppSession();
  const [restaurant, setRestaurant] = useState<any>(null);
  const [config, setConfig] = useState<any>(null);
  const [businessType, setBusinessType] = useState<string>("restaurant");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});

  const isAppointmentBusiness = APPOINTMENT_TYPES.includes(businessType);

  const fetchData = useCallback(async () => {
    try {
      const restaurantId = activeRestaurant?.id || getRestaurantId();
      const [restRes, configRes] = await Promise.all([getRestaurant(restaurantId), getConfig(restaurantId)]);
      const restaurantData = restRes.data;
      const configData = configRes.data;
      if (restaurantData.delivery_enabled === undefined && configData?.delivery_enabled !== undefined) {
        restaurantData.delivery_enabled = configData.delivery_enabled;
      }
      if (restaurantData.pickup_enabled === undefined && configData?.pickup_enabled !== undefined) {
        restaurantData.pickup_enabled = configData.pickup_enabled;
      }
      const addr = restaurantData.address || "";
      const parts = addr.split(",").map((s: string) => s.trim());
      const lastPart = parts[2] || "";
      const stateZip = lastPart.split(" ");
      restaurantData._street = parts[0] || "";
      restaurantData._city = parts[1] || "";
      restaurantData._state = stateZip[0] || "";
      restaurantData._zip = stateZip[1] || parts[3]?.trim() || "";
      setRestaurant(restaurantData);
      setConfig({ ...configData, operating_hours: { ...defaultHours, ...(configData?.operating_hours || {}) } });
      setBusinessType(configRes.data?.business_type || "restaurant");
    } catch {
      toast.error("Failed to load settings");
    } finally {
      setLoading(false);
    }
  }, [activeRestaurant]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const clearError = (field: string) => {
    if (errors[field]) setErrors((prev) => { const next = { ...prev }; delete next[field]; return next; });
  };

  const validateBusinessTab = (): { ok: boolean; errors: FieldErrors } => {
    const e: FieldErrors = {};
    if (!restaurant?.name?.trim()) e.name = "Business name is required.";
    if (!restaurant?._street?.trim()) e._street = "Street address is required.";
    if (!restaurant?._city?.trim()) e._city = "City is required.";
    if (!restaurant?._state?.trim()) e._state = "State is required.";
    if (!restaurant?._zip?.trim()) e._zip = "Zip code is required.";
    return { ok: Object.keys(e).length === 0, errors: e };
  };

  const saveRestaurant = async () => {
    const { ok, errors: validationErrors } = validateBusinessTab();
    if (!ok) {
      setErrors(validationErrors);
      toast.error(Object.values(validationErrors)[0] || "Please fix the highlighted fields.");
      return;
    }
    setErrors({});
    setSaving(true);
    try {
      const restaurantId = activeRestaurant?.id || getRestaurantId();
      const payload: any = {
        name: restaurant?.name,
        address: `${restaurant?._street}, ${restaurant?._city}, ${restaurant?._state} ${restaurant?._zip}`.trim(),
        timezone: restaurant?.timezone,
        owner_name: restaurant?.owner_name,
        owner_email: restaurant?.owner_email,
        owner_phone: restaurant?.owner_phone,
        billing_email: restaurant?.billing_email,
        business_phone: restaurant?.business_phone,
        website: restaurant?.website,
      };
      if (!isAppointmentBusiness) {
        payload.cuisine_type = restaurant?.cuisine_type;
        payload.pickup_enabled = restaurant?.pickup_enabled;
        payload.delivery_enabled = restaurant?.delivery_enabled;
        payload.delivery_fee = Number(restaurant?.delivery_fee || 0);
        payload.delivery_radius_miles = Number(restaurant?.delivery_radius_miles || 5);
        payload.delivery_zip_codes = restaurant?.delivery_zip_codes || [];
        payload.delivery_eta_offset_minutes = Number(restaurant?.delivery_eta_offset_minutes || 15);
        payload.dine_in_enabled = restaurant?.dine_in_enabled;
        payload.reservations_enabled = restaurant?.reservations_enabled;
        payload.offers_delivery = restaurant?.offers_delivery;
        payload.offers_reservations = restaurant?.offers_reservations;
        payload.catering_enabled = restaurant?.catering_enabled;
        payload.avg_prep_time_minutes = Number(restaurant?.avg_prep_time_minutes || 0);
        payload.reservation_party_limit = Number(restaurant?.reservation_party_limit || 0);
      }
      if (restaurant?.reservations_enabled) {
        payload.reservation_slot_duration = Number(restaurant?.reservation_slot_duration || 30);
        payload.reservation_max_per_slot = Number(restaurant?.reservation_max_per_slot || 5);
        payload.reservation_advance_booking_days = Number(restaurant?.reservation_advance_booking_days || 7);
      }
      await updateRestaurant(restaurantId, payload);
      // Escalation phone is owned by the Phone & Forwarding tab — it
      // persists to RestaurantConfig directly and is not part of this save.
      await refreshSession(restaurantId);
      toast.success(`${getBusinessLabel(businessType)} info saved!`);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const saveConfig = async () => {
    setSaving(true);
    try {
      const restaurantId = activeRestaurant?.id || getRestaurantId();
      const payload: any = {
        persona: config?.persona,
        voice_id: config?.voice_id,
        primary_language: config?.primary_language,
        multilingual_enabled: config?.multilingual_enabled ?? false,
        additional_languages: config?.additional_languages || [],
        business_rules: config?.business_rules,
        escalation_rules: config?.escalation_rules,
        disclosure_text: config?.disclosure_text,
        after_hours_mode: config?.after_hours_mode,
        operating_hours: config?.operating_hours,
        sms_payment_enabled: config?.sms_payment_enabled,
      };
      if (!isAppointmentBusiness) {
        payload.upsell_enabled = config?.upsell_enabled;
        payload.delivery_enabled = config?.delivery_enabled;
        payload.delivery_minimum = Number(config?.delivery_minimum || 0);
      }
      // Slot scheduling intentionally NOT sent — managed in the Appointments section.
      await updateConfig(restaurantId, payload);
      await refreshSession(restaurantId);
      toast.success("Settings saved!");
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="space-y-4">{[...Array(3)].map((_, i) => <Card key={i} className="premium-card h-40 animate-pulse" />)}</div>;

  return (
    <div className="max-w-5xl">
      <Tabs defaultValue="business" className="space-y-6">
        <TabsList className="bg-muted/50 rounded-xl p-1 h-auto flex-wrap">
          <TabsTrigger value="business" className="rounded-lg px-4 py-2 text-sm data-[state=active]:bg-card data-[state=active]:shadow-sm">
            <Building2 className="w-4 h-4 mr-2" />Business
          </TabsTrigger>
          <TabsTrigger value="phone" className="rounded-lg px-4 py-2 text-sm data-[state=active]:bg-card data-[state=active]:shadow-sm">
            <PhoneForwarded className="w-4 h-4 mr-2" />Phone & Forwarding
          </TabsTrigger>
          <TabsTrigger value="hours" className="rounded-lg px-4 py-2 text-sm data-[state=active]:bg-card data-[state=active]:shadow-sm">
            <Clock className="w-4 h-4 mr-2" />Hours
          </TabsTrigger>
          {!isAppointmentBusiness && (
            <TabsTrigger value="fulfillment" className="rounded-lg px-4 py-2 text-sm data-[state=active]:bg-card data-[state=active]:shadow-sm">
              <ShoppingBag className="w-4 h-4 mr-2" />Fulfillment
            </TabsTrigger>
          )}
          <TabsTrigger value="ai" className="rounded-lg px-4 py-2 text-sm data-[state=active]:bg-card data-[state=active]:shadow-sm">
            <Mic className="w-4 h-4 mr-2" />Voice & AI
          </TabsTrigger>
          <TabsTrigger value="rules" className="rounded-lg px-4 py-2 text-sm data-[state=active]:bg-card data-[state=active]:shadow-sm">
            <ShieldAlert className="w-4 h-4 mr-2" />Rules
          </TabsTrigger>
        </TabsList>

        <TabsContent value="business">
          <BusinessTab
            restaurant={restaurant}
            setRestaurant={setRestaurant}
            config={config}
            setConfig={setConfig}
            businessType={businessType}
            isAppointmentBusiness={isAppointmentBusiness}
            saving={saving}
            errors={errors}
            clearError={clearError}
            onSave={saveRestaurant}
          />
        </TabsContent>

        <TabsContent value="phone">
          <PhoneForwardingTab
            restaurantId={activeRestaurant?.id || getRestaurantId()}
            restaurant={restaurant}
            setRestaurant={setRestaurant}
            config={config}
            setConfig={setConfig}
            onAfterSave={async () => {
              await refreshSession(activeRestaurant?.id || getRestaurantId());
            }}
          />
        </TabsContent>

        <TabsContent value="hours">
          <HoursTab config={config} setConfig={setConfig} saving={saving} onSave={saveConfig} />
        </TabsContent>

        {!isAppointmentBusiness && (
          <TabsContent value="fulfillment">
            <FulfillmentTab
              restaurant={restaurant}
              setRestaurant={setRestaurant}
              config={config}
              setConfig={setConfig}
              saving={saving}
              onSaveRestaurant={saveRestaurant}
              onSaveConfig={saveConfig}
            />
          </TabsContent>
        )}

        <TabsContent value="ai">
          <VoiceAndAITab
            restaurant={restaurant}
            config={config}
            setConfig={setConfig}
            saving={saving}
            onSave={saveConfig}
          />
        </TabsContent>

        <TabsContent value="rules">
          <RulesTab config={config} setConfig={setConfig} saving={saving} onSave={saveConfig} />
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default SettingsPage;