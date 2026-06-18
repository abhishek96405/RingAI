import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { ChevronDown, Save, Volume2 } from "lucide-react";
import { toast } from "sonner";
import { getVoicePreview } from "@/lib/api";
import { voiceOptions, SUPPORTED_LANGUAGES } from "./constants";
import { isProPlan } from "@/lib/plan";

interface Props {
  restaurant: any;
  config: any;
  setConfig: (c: any) => void;
  saving: boolean;
  onSave: () => Promise<void>;
}

export default function VoiceAndAITab({ restaurant, config, setConfig, saving, onSave }: Props) {
  const [greetingOpen, setGreetingOpen] = useState(false);

  const playVoicePreview = async (voiceId: string) => {
    try {
      const res = await getVoicePreview(voiceId);
      const base64 = res.data.audio_base64;
      const binaryStr = atob(base64);
      const pcmBytes = new Uint8Array(binaryStr.length);
      for (let i = 0; i < binaryStr.length; i++) pcmBytes[i] = binaryStr.charCodeAt(i);
      const sampleRate = 24000, numChannels = 1, bitsPerSample = 16, dataSize = pcmBytes.byteLength;
      const wavBuffer = new ArrayBuffer(44 + dataSize);
      const v = new DataView(wavBuffer);
      [0x52, 0x49, 0x46, 0x46].forEach((b, i) => v.setUint8(i, b));
      v.setUint32(4, 36 + dataSize, true);
      [0x57, 0x41, 0x56, 0x45].forEach((b, i) => v.setUint8(8 + i, b));
      [0x66, 0x6d, 0x74, 0x20].forEach((b, i) => v.setUint8(12 + i, b));
      v.setUint32(16, 16, true);
      v.setUint16(20, 1, true);
      v.setUint16(22, numChannels, true);
      v.setUint32(24, sampleRate, true);
      v.setUint32(28, sampleRate * numChannels * bitsPerSample / 8, true);
      v.setUint16(32, numChannels * bitsPerSample / 8, true);
      v.setUint16(34, bitsPerSample, true);
      [0x64, 0x61, 0x74, 0x61].forEach((b, i) => v.setUint8(36 + i, b));
      v.setUint32(40, dataSize, true);
      new Uint8Array(wavBuffer, 44).set(pcmBytes);
      const blob = new Blob([wavBuffer], { type: "audio/wav" });
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.onended = () => URL.revokeObjectURL(url);
      await audio.play();
    } catch {
      toast.error("Could not load voice preview");
    }
  };

  return (
    <Card className="dash-card p-6 space-y-6">
      <div>
        <h3 className="font-display font-bold text-lg mb-1">Voice & AI</h3>
        <p className="text-sm text-ink-soft">How the AI sounds and behaves during calls.</p>
      </div>

      {/* Persona */}
      <div className="space-y-2">
        <Label>AI Persona</Label>
        <Select value={config?.persona || "friendly"} onValueChange={(v) => setConfig({ ...config, persona: v })}>
          <SelectTrigger className="h-11 rounded-xl"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="friendly">Friendly & Warm</SelectItem>
            <SelectItem value="professional">Professional & Formal</SelectItem>
            <SelectItem value="casual">Casual & Relaxed</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Voice */}
      <div className="space-y-2">
        <Label>Voice</Label>
        <div className="grid gap-2 mt-1">
          {voiceOptions.map((voice) => {
            const isVoiceLocked = !isProPlan(restaurant?.plan) && voice.id !== "Leda";
            return (
              <div key={voice.id} onClick={() => !isVoiceLocked && setConfig({ ...config, voice_id: voice.id })}
                className={`flex items-center gap-3 p-3 rounded-lg border transition-colors ${isVoiceLocked ? "opacity-50 cursor-not-allowed" : "cursor-pointer"} ${config?.voice_id === voice.id ? "border-coral bg-coral/5" : "border-line hover:border-coral/30"}`}>
                <Volume2 className="w-4 h-4 text-ink-soft" />
                <div className="flex-1">
                  <p className="text-sm font-medium">{voice.name}</p>
                  <p className="text-xs text-ink-soft">{voice.accent}</p>
                </div>
                <div className="flex items-center gap-2">
                  {config?.voice_id === voice.id && <span className="text-xs bg-coral/10 text-coral rounded-full px-2 py-0.5">Selected</span>}
                  <button onClick={(e) => { e.stopPropagation(); playVoicePreview(voice.id); }} className="text-ink-soft hover:text-coral transition-colors" title="Preview voice">
                    <Volume2 className="w-3.5 h-3.5" />
                  </button>
                </div>
                {isVoiceLocked && <span className="text-xs text-ink-soft">Pro</span>}
              </div>
            );
          })}
        </div>
      </div>

      {/* Custom Greeting â€” Collapsible */}
      <Collapsible open={greetingOpen} onOpenChange={setGreetingOpen}>
        <CollapsibleTrigger className="flex items-center gap-2 text-sm font-medium text-ink-soft hover:text-foreground transition-colors">
          <ChevronDown className={`w-4 h-4 transition-transform ${greetingOpen ? "rotate-180" : ""}`} />
          Customize greeting
        </CollapsibleTrigger>
        <CollapsibleContent className="space-y-2 pt-3">
          <p className="text-xs text-ink-soft">
            The opening line the AI says at the start of every call. Leave blank to use the default friendly greeting.
          </p>
          <Textarea
            value={config?.disclosure_text || ""}
            onChange={(e) => setConfig({ ...config, disclosure_text: e.target.value })}
            placeholder="Hi! I'm the AI assistant for [your business]. How can I help you today?"
            className="rounded-xl min-h-[80px]"
          />
        </CollapsibleContent>
      </Collapsible>

      {/* Language Support */}
      <div className="space-y-4 p-4 rounded-lg border border-coral/20 bg-coral/5">
        <div>
          <h4 className="text-sm font-semibold mb-1">Language Support</h4>
          <p className="text-xs text-ink-soft">
            {isProPlan(restaurant?.plan)
              ? "Configure the AI's spoken language. With multilingual on, callers press a digit at the start to pick a language. Returning callers skip the menu â€” their last choice is remembered."
              : "Upgrade to Pro to let callers choose their language via IVR. Starter plans use the primary language only."}
          </p>
        </div>

        <div className="space-y-2">
          <Label>Primary Language</Label>
          <Select value={config?.primary_language || "en"} onValueChange={(v) => setConfig({ ...config, primary_language: v })}>
            <SelectTrigger className="h-11 rounded-xl"><SelectValue /></SelectTrigger>
            <SelectContent>
              {SUPPORTED_LANGUAGES.map((lang) => (
                <SelectItem key={lang.code} value={lang.code}>{lang.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-ink-soft">The default for all calls. On Pro, also used as the fallback if a caller doesn't pick a digit at the IVR.</p>
        </div>

        <div className="flex items-center justify-between p-3 rounded-lg bg-card border border-line">
          <div>
            <p className="text-sm font-medium">
              Multilingual IVR
              {!isProPlan(restaurant?.plan) && <span className="ml-2 text-xs text-ink-soft font-normal">(Pro)</span>}
            </p>
            <p className="text-xs text-ink-soft">Callers hear a menu and press a digit to choose their language</p>
          </div>
          <Switch
            checked={config?.multilingual_enabled || false}
            disabled={!isProPlan(restaurant?.plan)}
            onCheckedChange={(v) => setConfig({ ...config, multilingual_enabled: v })}
          />
        </div>

        {config?.multilingual_enabled && isProPlan(restaurant?.plan) && (
          <div className="space-y-2">
            <Label>Additional Languages</Label>
            <p className="text-xs text-ink-soft">
              Each selected language becomes an IVR option. "1" is always the primary; additional ones get "2", "3", etc. in the order shown.
            </p>
            <div className="grid sm:grid-cols-2 gap-2">
              {SUPPORTED_LANGUAGES.filter((l) => l.code !== (config?.primary_language || "en")).map((lang) => {
                const selected = (config?.additional_languages || []).includes(lang.code);
                return (
                  <label
                    key={lang.code}
                    className={`flex items-center gap-2 p-2.5 rounded-lg border cursor-pointer transition-colors ${
                      selected ? "border-coral bg-coral/10" : "border-line hover:border-coral/30 bg-card"
                    }`}
                  >
                    <input
                      type="checkbox" className="accent-coral" checked={selected}
                      onChange={(e) => {
                        const current: string[] = config?.additional_languages || [];
                        const updated = e.target.checked ? [...current, lang.code] : current.filter((c) => c !== lang.code);
                        setConfig({ ...config, additional_languages: updated });
                      }}
                    />
                    <span className="text-sm">{lang.label}</span>
                  </label>
                );
              })}
            </div>
            {(config?.additional_languages?.length ?? 0) === 0 && (
              <p className="text-xs text-[#a26d0d]">âš  Select at least one additional language, or turn multilingual off.</p>
            )}
          </div>
        )}
      </div>

      {/* Upsell */}
      <div className="flex items-center justify-between p-3 rounded-lg bg-cream">
        <div className="flex items-center gap-2">
          <div>
            <p className="text-sm font-medium">Upselling</p>
            <p className="text-xs text-ink-soft">Suggest add-ons after the main order</p>
          </div>
          {!isProPlan(restaurant?.plan) && <span className="text-xs text-ink-soft">(Pro)</span>}
        </div>
        <Switch checked={config?.upsell_enabled || false} disabled={!isProPlan(restaurant?.plan)} onCheckedChange={(v) => setConfig({ ...config, upsell_enabled: v })} />
      </div>

      <Button onClick={onSave} disabled={saving} className="bg-coral hover:bg-coral-deep text-white rounded-xl hover:opacity-90">
        <Save className="w-4 h-4 mr-2" />{saving ? "Saving..." : "Save Voice & AI"}
      </Button>
    </Card>
  );
}