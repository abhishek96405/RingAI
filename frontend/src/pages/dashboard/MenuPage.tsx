import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  createMenuItem, deleteMenuItem, getMenuItems, toggleMenuItem, updateMenuItem,
  getModifierGroups, createModifierGroup, updateModifierGroup, deleteModifierGroup,
  updateItemModifierAssignments, syncMenuFromPOS
} from "@/lib/api";
import { useAppSession } from "@/context/AppSessionContext";
import type { MenuItem, ModifierGroup } from "@/types";
import { CheckCircle2, ChevronDown, ChevronUp, DollarSign, Edit2, GripVertical, Layers, Plus, RefreshCw, Search, Settings2, Trash2, UtensilsCrossed, X } from "lucide-react";
import { motion } from "framer-motion";
import { toast } from "sonner";

const defaultItem: MenuItem = {
  name: "",
  description: "",
  category: "Appetizers",
  price: 0,
  prep_time_minutes: 0,
  available: true,
  allergens: [] as string[],
  modifiers: [],
  modifier_group_assignments: [],
  special_instructions_enabled: true,
};

const categories = ["Appetizers", "Pizza", "Pasta", "Entrees", "Desserts", "Beverages", "Sides", "Specials", "Uncategorized"];
const allergenOptions = ["gluten", "dairy", "nuts", "soy", "eggs", "shellfish"];

// ── Modifier Library Tab ───────────────────────────────────────────────────

function ModifierLibrary({ restaurantId }: { restaurantId: string }) {
  const [groups, setGroups] = useState<ModifierGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingGroup, setEditingGroup] = useState<ModifierGroup | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState<ModifierGroup>({
    name: "",
    selection_type: "single",
    required: false,
    min_selections: 0,
    max_selections: 1,
    active: true,
    options: [],
  });
  const [newOptionName, setNewOptionName] = useState("");
  const [newOptionPrice, setNewOptionPrice] = useState("");
  const [newOptionAliases, setNewOptionAliases] = useState("");

  const fetchGroups = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getModifierGroups(restaurantId);
      setGroups(res.data || []);
    } catch {
      toast.error("Failed to load modifier groups");
    } finally {
      setLoading(false);
    }
  }, [restaurantId]);

  useEffect(() => { fetchGroups(); }, [fetchGroups]);

  const openAdd = () => {
    setEditingGroup(null);
    setForm({ name: "", selection_type: "single", required: false, min_selections: 0, max_selections: 1, active: true, options: [] });
    setNewOptionName("");
    setNewOptionPrice("");
    setNewOptionAliases("");
    setDialogOpen(true);
  };

  const openEdit = (group: ModifierGroup) => {
    setEditingGroup(group);
    setForm({ ...group });
    setNewOptionName("");
    setNewOptionPrice("");
    setNewOptionAliases("");
    setDialogOpen(true);
  };

  const addOption = () => {
    if (!newOptionName.trim()) return;
    const priceDelta = Math.round(parseFloat(newOptionPrice || "0") * 100) || 0;
    const aliases = newOptionAliases.split(",").map(a => a.trim()).filter(Boolean);
    const newOpt = {
      id: crypto.randomUUID(),
      name: newOptionName.trim(),
      price_delta: priceDelta,
      default_selected: false,
      in_stock: true,
      display_order: form.options.length,
      ai_aliases: aliases,
    };
    setForm((prev) => ({ ...prev, options: [...prev.options, newOpt] }));
    setNewOptionName("");
    setNewOptionPrice("");
    setNewOptionAliases("");
  };

  const removeOption = (optId: string) => {
    setForm((prev) => ({ ...prev, options: prev.options.filter((o) => o.id !== optId) }));
  };

  const toggleOptionStock = (optId: string) => {
    setForm((prev) => ({
      ...prev,
      options: prev.options.map((o) => o.id === optId ? { ...o, in_stock: !o.in_stock } : o)
    }));
  };

  const handleSave = async () => {
    if (!form.name.trim()) { toast.error("Group name is required"); return; }
    if (form.options.length === 0) { toast.error("Add at least one option"); return; }
    setSaving(true);
    try {
      if (editingGroup) {
        await updateModifierGroup(editingGroup.id, form);
        toast.success("Modifier group updated!");
      } else {
        await createModifierGroup(restaurantId, form);
        toast.success("Modifier group created!");
      }
      setDialogOpen(false);
      fetchGroups();
    } catch {
      toast.error("Failed to save modifier group");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (groupId: string) => {
    try {
      await deleteModifierGroup(groupId);
      toast.success("Modifier group deleted");
      fetchGroups();
    } catch {
      toast.error("Failed to delete modifier group");
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-display font-bold text-lg">Modifier Library</h2>
          <p className="text-sm text-ink-soft mt-0.5">Create reusable modifier groups — Size, Spice Level, Toppings — then assign them to menu items.</p>
        </div>
        <Button onClick={openAdd} className="bg-coral hover:bg-coral-deep text-white rounded-xl">
          <Plus className="w-4 h-4 mr-2" /> New Group
        </Button>
      </div>

      {loading ? (
        <div className="grid sm:grid-cols-2 gap-4">{[...Array(4)].map((_, i) => <div key={i} className="dash-card h-32 animate-pulse" />)}</div>
      ) : groups.length === 0 ? (
        <div className="dash-card p-12 text-center">
          <span className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-coral/10 text-coral">
            <Settings2 className="w-7 h-7" />
          </span>
          <h3 className="font-display font-semibold mb-1">No modifier groups yet</h3>
          <p className="text-sm text-ink-soft mb-4 max-w-sm mx-auto">Create groups like "Size", "Spice Level", or "Toppings" and assign them to menu items.</p>
          <Button onClick={openAdd} className="bg-coral hover:bg-coral-deep text-white rounded-xl">Create First Group</Button>
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 gap-4">
          {groups.map((group) => (
            <div key={group.id} className={`dash-card p-4 ${!group.active ? "opacity-50" : ""}`}>
              <div className="flex items-start justify-between mb-2">
                <div>
                  <div className="flex items-center gap-2">
                    <h4 className="font-display font-semibold">{group.name}</h4>
                    {group.required && <span className="chip b-honey">Required</span>}
                    {!group.active && <span className="chip b-muted">Inactive</span>}
                  </div>
                  <p className="text-xs text-ink-soft mt-0.5">
                    {group.selection_type === "single" ? "Single select" : "Multi select"}
                    {group.required ? ` · min ${group.min_selections}` : " · optional"}
                    {group.max_selections > 1 ? ` · max ${group.max_selections}` : ""}
                  </p>
                </div>
                <div className="flex gap-1">
                  <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => openEdit(group)}>
                    <Edit2 className="w-3.5 h-3.5" />
                  </Button>
                  <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive hover:text-destructive" onClick={() => handleDelete(group.id)}>
                    <Trash2 className="w-3.5 h-3.5" />
                  </Button>
                </div>
              </div>
              <div className="flex flex-wrap gap-1.5 mt-2">
                {group.options.map((opt) => (
                  <span key={opt.id} className={`text-xs px-2 py-0.5 rounded-full border ${!opt.in_stock ? "opacity-40 line-through" : ""} bg-cream`}>
                    {opt.name}{opt.price_delta > 0 ? ` +$${(opt.price_delta / 100).toFixed(2)}` : ""}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create/Edit Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{editingGroup ? "Edit Modifier Group" : "New Modifier Group"}</DialogTitle>
          </DialogHeader>
          <ScrollArea className="max-h-[60vh] pr-2">
            <div className="space-y-4 py-1">
              {/* Name */}
              <div className="space-y-1.5">
                <Label>Group Name</Label>
                <Input value={form.name} onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))} placeholder="e.g. Size, Spice Level, Toppings" />
              </div>

              {/* Selection type */}
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label>Selection Type</Label>
                  <Select value={form.selection_type} onValueChange={(v) => setForm((p) => ({ ...p, selection_type: v }))}>
                    <SelectTrigger className="h-9 rounded-lg"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="single">Single select</SelectItem>
                      <SelectItem value="multiple">Multi select</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label>Required?</Label>
                  <div className="flex items-center gap-2 h-9">
                    <Switch checked={form.required} onCheckedChange={(v) => setForm((p) => ({ ...p, required: v, min_selections: v ? 1 : 0 }))} />
                    <span className="text-sm text-ink-soft">{form.required ? "Required" : "Optional"}</span>
                  </div>
                </div>
              </div>

              {form.selection_type === "multiple" && (
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label>Min Selections</Label>
                    <Input type="number" min={0} value={form.min_selections} onChange={(e) => setForm((p) => ({ ...p, min_selections: parseInt(e.target.value) || 0 }))} className="h-9" />
                  </div>
                  <div className="space-y-1.5">
                    <Label>Max Selections</Label>
                    <Input type="number" min={1} value={form.max_selections} onChange={(e) => setForm((p) => ({ ...p, max_selections: parseInt(e.target.value) || 1 }))} className="h-9" />
                  </div>
                </div>
              )}

              {/* Active toggle */}
              <div className="flex items-center gap-2">
                <Switch checked={form.active} onCheckedChange={(v) => setForm((p) => ({ ...p, active: v }))} />
                <Label>Active</Label>
              </div>

              {/* Options */}
              <div className="space-y-2">
                <Label>Options</Label>
                {form.options.length > 0 && (
                  <div className="space-y-1.5 mb-2">
                    {form.options.map((opt) => (
                      <div key={opt.id} className="flex items-center gap-2 p-2 rounded-lg bg-cream border border-line">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className={`text-sm font-medium ${!opt.in_stock ? "line-through text-ink-soft" : ""}`}>{opt.name}</span>
                            {opt.price_delta > 0 && <span className="text-xs text-emerald-600">+${(opt.price_delta / 100).toFixed(2)}</span>}
                          </div>
                          {opt.ai_aliases?.length > 0 && (
                            <p className="text-xs text-ink-soft">aliases: {opt.ai_aliases.join(", ")}</p>
                          )}
                        </div>
                        <Button variant="ghost" size="icon" className="h-6 w-6 shrink-0" onClick={() => toggleOptionStock(opt.id)} title="Toggle stock">
                          <span className="text-xs">{opt.in_stock ? "✓" : "✗"}</span>
                        </Button>
                        <Button variant="ghost" size="icon" className="h-6 w-6 shrink-0 text-destructive hover:text-destructive" onClick={() => removeOption(opt.id)}>
                          <X className="w-3 h-3" />
                        </Button>
                      </div>
                    ))}
                  </div>
                )}

                {/* Add option form */}
                <div className="border border-dashed border-line rounded-lg p-3 space-y-2">
                  <div className="grid grid-cols-2 gap-2">
                    <Input
                      value={newOptionName}
                      onChange={(e) => setNewOptionName(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && addOption()}
                      placeholder="Option name"
                      className="h-8 text-sm"
                    />
                    <Input
                      value={newOptionPrice}
                      onChange={(e) => setNewOptionPrice(e.target.value)}
                      placeholder="Price delta (e.g. 1.50)"
                      className="h-8 text-sm"
                      type="number"
                      min={0}
                      step={0.01}
                    />
                  </div>
                  <Input
                    value={newOptionAliases}
                    onChange={(e) => setNewOptionAliases(e.target.value)}
                    placeholder="AI aliases (comma separated, e.g. medium, regular)"
                    className="h-8 text-sm"
                  />
                  <Button variant="outline" size="sm" className="w-full h-8 text-xs" onClick={addOption}>
                    <Plus className="w-3 h-3 mr-1" /> Add Option
                  </Button>
                </div>
              </div>
            </div>
          </ScrollArea>
          <DialogFooter className="pt-4 border-t">
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleSave} disabled={saving} className="bg-coral hover:bg-coral-deep text-white">
              {saving ? "Saving..." : editingGroup ? "Update Group" : "Create Group"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ── Menu Items Tab ─────────────────────────────────────────────────────────

const MenuPage = () => {
  const { activeRestaurant } = useAppSession();
  const restaurantId = activeRestaurant?.id ?? "";
  const [items, setItems] = useState<MenuItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [syncing, setSyncing] = useState(false);
  const [lastSync, setLastSync] = useState<string | null>(null);
  const [activeCategory, setActiveCategory] = useState("all");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<MenuItem | null>(null);
  const [formData, setFormData] = useState<MenuItem>(defaultItem);
  const [saving, setSaving] = useState(false);
  const [modifierGroups, setModifierGroups] = useState<ModifierGroup[]>([]);

  // Legacy modifier state (kept for backward compat)
  const [newGroupName, setNewGroupName] = useState("");
  const [newOption, setNewOption] = useState<Record<number, string>>({});

  const fetchItems = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getMenuItems();
      setItems(res.data || []);
    } catch {
      toast.error("Failed to load menu");
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchModifierGroups = useCallback(async () => {
    if (!restaurantId) return;
    try {
      const res = await getModifierGroups(restaurantId);
      setModifierGroups(res.data || []);
    } catch {
      // non-fatal
    }
  }, [restaurantId]);

  const handlePOSSync = async () => {
    try {
      setSyncing(true);
      const res = await syncMenuFromPOS(restaurantId);
      if (res.data?.success) {
        toast.success(`Synced ${res.data.synced} items from ${res.data.source}`);
        setLastSync(new Date().toLocaleTimeString());
        await fetchItems();
      } else {
        toast.error(res.data?.error || "Sync failed");
      }
    } catch {
      toast.error("POS sync failed");
    } finally {
      setSyncing(false);
    }
  };

  useEffect(() => { fetchItems(); }, [fetchItems]);
  useEffect(() => { fetchModifierGroups(); }, [fetchModifierGroups]);

  const openAdd = () => {
    setEditingItem(null);
    setFormData(defaultItem);
    setNewGroupName("");
    setNewOption({});
    setDialogOpen(true);
  };

  const openEdit = (item: MenuItem) => {
    setEditingItem(item);
    setFormData({
      name: item.name,
      description: item.description || "",
      category: item.category,
      price: item.price,
      available: item.available,
      allergens: item.allergens || [],
      modifiers: item.modifiers || [],
      modifier_group_assignments: item.modifier_group_assignments || [],
      special_instructions_enabled: item.special_instructions_enabled !== false,
    });
    setNewGroupName("");
    setNewOption({});
    setDialogOpen(true);
  };

  const handleSave = async () => {
    if (!formData.name.trim()) { toast.error("Item name is required"); return; }
    setSaving(true);
    try {
      const payload = { ...formData };
      if (editingItem) {
        await updateMenuItem(editingItem.id, payload);
        // Save modifier assignments separately
        await updateItemModifierAssignments(editingItem.id, formData.modifier_group_assignments || []);
        toast.success("Menu item updated!");
      } else {
        const res = await createMenuItem(null, payload);
        // Save modifier assignments for new item
        if (res.data?.id && formData.modifier_group_assignments?.length > 0) {
          await updateItemModifierAssignments(res.data.id, formData.modifier_group_assignments);
        }
        toast.success("Menu item added!");
      }
      setDialogOpen(false);
      fetchItems();
    } catch {
      toast.error("Failed to save item");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (itemId: string) => {
    try {
      await deleteMenuItem(itemId);
      toast.success("Item deleted");
      fetchItems();
    } catch {
      toast.error("Failed to delete item");
    }
  };

  const handleToggle = async (itemId: string) => {
    try {
      await toggleMenuItem(itemId);
      setItems((prev) => prev.map((item) => item.id === itemId ? { ...item, available: !item.available } : item));
    } catch {
      toast.error("Failed to toggle availability");
    }
  };

  const toggleAllergen = (allergen: string) => {
    setFormData((prev) => ({
      ...prev,
      allergens: prev.allergens.includes(allergen)
        ? prev.allergens.filter((a: string) => a !== allergen)
        : [...prev.allergens, allergen],
    }));
  };

  const toggleModifierGroupAssignment = (groupId: string) => {
    setFormData((prev) => {
      const assignments = prev.modifier_group_assignments || [];
      const exists = assignments.find((a) => a.modifier_group_id === groupId);
      if (exists) {
        return { ...prev, modifier_group_assignments: assignments.filter((a) => a.modifier_group_id !== groupId) };
      } else {
        return {
          ...prev,
          modifier_group_assignments: [...assignments, {
            modifier_group_id: groupId,
            override_required: null,
            override_min: null,
            override_max: null,
            override_name: null,
            display_order: assignments.length,
          }]
        };
      }
    });
  };

  const isGroupAssigned = (groupId: string) =>
    (formData.modifier_group_assignments || []).some((a) => a.modifier_group_id === groupId);

  // Legacy modifier helpers
  const addModifierGroup = () => {
    if (!newGroupName.trim()) return;
    const exists = formData.modifiers.some((m) => m.name.toLowerCase() === newGroupName.trim().toLowerCase());
    if (exists) { toast.error("Group already exists"); return; }
    setFormData((prev) => ({ ...prev, modifiers: [...prev.modifiers, { name: newGroupName.trim(), options: [] }] }));
    setNewGroupName("");
  };

  const removeModifierGroup = (index: number) => {
    setFormData((prev) => ({ ...prev, modifiers: prev.modifiers.filter((_, i: number) => i !== index) }));
  };

  const addOptionToGroup = (groupIndex: number) => {
    const val = (newOption[groupIndex] || "").trim();
    if (!val) return;
    setFormData((prev) => {
      const mods = [...prev.modifiers];
      if (mods[groupIndex].options.includes(val)) { toast.error("Option already exists"); return prev; }
      mods[groupIndex] = { ...mods[groupIndex], options: [...mods[groupIndex].options, val] };
      return { ...prev, modifiers: mods };
    });
    setNewOption((prev) => ({ ...prev, [groupIndex]: "" }));
  };

  const removeOptionFromGroup = (groupIndex: number, option: string) => {
    setFormData((prev) => {
      const mods = [...prev.modifiers];
      mods[groupIndex] = { ...mods[groupIndex], options: mods[groupIndex].options.filter((o: string) => o !== option) };
      return { ...prev, modifiers: mods };
    });
  };

  const filteredItems = useMemo(() => items.filter((item) => {
    if (activeCategory !== "all" && item.category !== activeCategory) return false;
    if (search && !item.name.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  }), [items, activeCategory, search]);

  const groupedItems = useMemo(() => filteredItems.reduce((acc: Record<string, MenuItem[]>, item) => {
    if (!acc[item.category]) acc[item.category] = [];
    acc[item.category].push(item);
    return acc;
  }, {}), [filteredItems]);

  const menuStats = useMemo(() => {
    const total = items.length;
    const available = items.filter((i) => i.available).length;
    const withModifiers = items.filter((i) => (i.modifier_group_assignments?.length || 0) > 0).length;
    const categoryCount = new Set(items.map((i) => i.category)).size;
    return { total, available, withModifiers, categoryCount };
  }, [items]);

  return (
    <div className="dash space-y-6">
      <div>
        <p className="eyebrow mb-2">Menu</p>
        <h1 className="text-2xl font-display font-bold">Your menu</h1>
        <p className="text-sm text-ink-soft mt-1">Manage the items, modifiers, and allergens your AI uses on every call.</p>
      </div>

      <Tabs defaultValue="items">
        <div className="flex flex-col sm:flex-row gap-4 justify-between items-start">
          <TabsList className="bg-cream rounded-xl p-1 h-auto">
            <TabsTrigger value="items" className="rounded-lg px-4 py-2 text-sm data-[state=active]:bg-card data-[state=active]:shadow-sm">
              <UtensilsCrossed className="w-4 h-4 mr-2" />Menu Items
            </TabsTrigger>
            <TabsTrigger value="modifiers" className="rounded-lg px-4 py-2 text-sm data-[state=active]:bg-card data-[state=active]:shadow-sm">
              <Settings2 className="w-4 h-4 mr-2" />Modifier Library
            </TabsTrigger>
          </TabsList>
          <TabsContent value="items" className="mt-0">
            <div className="flex items-center gap-2">
              <Button onClick={handlePOSSync} disabled={syncing} variant="outline" className="rounded-xl">
                <RefreshCw className={`w-4 h-4 mr-2 ${syncing ? "animate-spin" : ""}`} />
                {syncing ? "Syncing..." : "Sync from POS"}
              </Button>
              {lastSync && <span className="text-xs text-ink-soft">Last synced: {lastSync}</span>}
              <Button onClick={openAdd} className="bg-coral hover:bg-coral-deep text-white rounded-xl">
                <Plus className="w-4 h-4 mr-2" /> Add Item
              </Button>
            </div>
          </TabsContent>
        </div>

        <TabsContent value="items" className="mt-4 space-y-4">
          {/* Menu at a glance */}
          {!loading && menuStats.total > 0 && (
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="dash-card card-hover p-5">
                <span className="h-10 w-10 rounded-2xl flex items-center justify-center text-coral-deep bg-coral/15 icon-tile">
                  <UtensilsCrossed className="w-[18px] h-[18px]" />
                </span>
                <p className="font-display font-extrabold text-3xl mt-4">{menuStats.total}</p>
                <p className="text-sm text-ink-soft">Menu items</p>
              </div>
              <div className="dash-card card-hover p-5">
                <span className="h-10 w-10 rounded-2xl flex items-center justify-center text-white bg-gradient-to-br from-[#4FB089] to-[#3E9E78]" style={{ boxShadow: "0 10px 20px -8px rgba(62,158,120,.5)" }}>
                  <CheckCircle2 className="w-[18px] h-[18px]" />
                </span>
                <p className="font-display font-extrabold text-3xl mt-4">{menuStats.available}<span className="text-lg text-ink-soft font-bold"> / {menuStats.total}</span></p>
                <p className="text-sm text-ink-soft">Available</p>
              </div>
              <div className="dash-card card-hover p-5">
                <span className="h-10 w-10 rounded-2xl flex items-center justify-center text-white bg-gradient-to-br from-[#F6BE5C] to-[#F2A93B]" style={{ boxShadow: "0 10px 20px -8px rgba(242,169,59,.5)" }}>
                  <Settings2 className="w-[18px] h-[18px]" />
                </span>
                <p className="font-display font-extrabold text-3xl mt-4">{menuStats.withModifiers}</p>
                <p className="text-sm text-ink-soft">With modifiers</p>
              </div>
              <div className="dash-card card-hover p-5">
                <span className="h-10 w-10 rounded-2xl flex items-center justify-center text-white bg-gradient-to-br from-[#3A2C22] to-[#1E1813]" style={{ boxShadow: "0 10px 20px -8px rgba(30,24,19,.45)" }}>
                  <Layers className="w-[18px] h-[18px]" />
                </span>
                <p className="font-display font-extrabold text-3xl mt-4">{menuStats.categoryCount}</p>
                <p className="text-sm text-ink-soft">Categories</p>
              </div>
            </div>
          )}

          {/* Category filter */}
          <div className="flex gap-2 overflow-x-auto pb-1">
            {["all", ...categories].map((cat) => (
              <button key={cat} onClick={() => setActiveCategory(cat)} className={`px-4 py-2 rounded-xl text-sm font-medium whitespace-nowrap transition-all ${activeCategory === cat ? "bg-coral text-white" : "bg-cream hover:bg-line/60"}`}>
                {cat === "all" ? "All Items" : cat}
              </button>
            ))}
          </div>

          {/* Search */}
          <div className="relative max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-soft" />
            <Input placeholder="Search menu items..." value={search} onChange={(e) => setSearch(e.target.value)} className="pl-9 h-10 rounded-xl" />
          </div>

          {loading ? (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">{[...Array(6)].map((_, i) => <div key={i} className="dash-card h-44 animate-pulse" />)}</div>
          ) : Object.keys(groupedItems).length === 0 ? (
            <div className="dash-card p-12 text-center">
              <span className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-coral/10 text-coral">
                <UtensilsCrossed className="w-7 h-7" />
              </span>
              <h3 className="font-display font-semibold text-lg mb-1">{search || activeCategory !== "all" ? "No items match your filters" : "Your menu is empty"}</h3>
              <p className="text-sm text-ink-soft mb-5 max-w-sm mx-auto">{search || activeCategory !== "all" ? "Try a different search or category." : "Add your first item, or sync your menu straight from your POS."}</p>
              <div className="flex items-center justify-center gap-2">
                <button onClick={openAdd} className="inline-flex items-center gap-2 bg-coral hover:bg-coral-deep text-white px-4 py-2 rounded-xl text-sm font-semibold transition"><Plus className="w-4 h-4" />Add item</button>
                <button onClick={handlePOSSync} disabled={syncing} className="inline-flex items-center gap-2 border border-line bg-[#FFFDF9] hover:border-ink/25 px-4 py-2 rounded-xl text-sm font-semibold transition disabled:opacity-50"><RefreshCw className={`w-4 h-4 ${syncing ? "animate-spin" : ""}`} />Sync from POS</button>
              </div>
            </div>
          ) : Object.entries(groupedItems).map(([category, catItems]) => (
            <div key={category}>
              <h3 className="font-display font-bold text-lg mb-4">{category}</h3>
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {catItems.map((item, i) => (
                  <motion.div key={item.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }} className="dash-card card-hover p-5">
                    <div className="flex justify-between items-start mb-3 gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h4 className="font-display font-semibold truncate">{item.name}</h4>
                          {!item.available && <span className="px-2 py-0.5 rounded-full bg-destructive/10 text-destructive text-xs font-medium">Unavailable</span>}
                        </div>
                        <p className="text-sm text-ink-soft mt-1">{item.description}</p>
                        {item.allergens?.length > 0 && (
                          <div className="flex flex-wrap gap-1.5 mt-2">
                            {item.allergens.map((a: string) => <span key={a} className="chip bg-honey/15 text-[#a26d0d]">{a}</span>)}
                          </div>
                        )}
                        {item.modifier_group_assignments?.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-2">
                            <span className="chip b-coral inline-flex items-center gap-1">
                              <Settings2 className="w-2.5 h-2.5" />{item.modifier_group_assignments.length} modifier{item.modifier_group_assignments.length > 1 ? "s" : ""}
                            </span>
                          </div>
                        )}
                      </div>
                      <Switch checked={item.available} onCheckedChange={() => handleToggle(item.id)} />
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="flex items-center text-xl font-display font-extrabold"><DollarSign className="w-4 h-4 mr-0.5" />{(item.price / 100).toFixed(2)}</span>
                      <div className="flex gap-1">
                        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => openEdit(item)}><Edit2 className="w-3.5 h-3.5" /></Button>
                        <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive hover:text-destructive" onClick={() => handleDelete(item.id)}><Trash2 className="w-3.5 h-3.5" /></Button>
                      </div>
                    </div>
                  </motion.div>
                ))}
              </div>
            </div>
          ))}
        </TabsContent>

        <TabsContent value="modifiers" className="mt-4">
          <ModifierLibrary restaurantId={restaurantId} />
        </TabsContent>
      </Tabs>

      {/* Add/Edit Item Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{editingItem ? "Edit Menu Item" : "Add Menu Item"}</DialogTitle>
          </DialogHeader>
          <ScrollArea className="max-h-[65vh] pr-2">
            <div className="space-y-4 py-1">
              <div className="space-y-1.5">
                <Label>Item Name *</Label>
                <Input value={formData.name} onChange={(e) => setFormData((p) => ({ ...p, name: e.target.value }))} placeholder="e.g. Margherita Pizza" />
              </div>

              <div className="space-y-1.5">
                <Label>Description</Label>
                <Textarea value={formData.description} onChange={(e) => setFormData((p) => ({ ...p, description: e.target.value }))} placeholder="Brief description..." rows={2} className="resize-none" />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label>Category</Label>
                  <Select value={formData.category} onValueChange={(v) => setFormData((p) => ({ ...p, category: v }))}>
                    <SelectTrigger className="h-9 rounded-lg"><SelectValue /></SelectTrigger>
                    <SelectContent>{categories.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label>Price ($)</Label>
                  <Input
                    type="number" min={0} step={0.01}
                    value={formData.price / 100}
                    onChange={(e) => setFormData((p) => ({ ...p, price: Math.round(parseFloat(e.target.value || "0") * 100) }))}
                    className="h-9"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label>Prep Time (min)</Label>
                  <Input
                    type="number" min={0} step={1}
                    value={formData.prep_time_minutes || 0}
                    onChange={(e) => setFormData((p) => ({ ...p, prep_time_minutes: parseInt(e.target.value || "0") || 0 }))}
                    placeholder="0 = default"
                    className="h-9"
                  />
                  <p className="text-xs text-ink-soft">Leave at 0 to use restaurant default. Set for slow items like Biryani (25 min).</p>
                </div>
              </div>

              {/* Allergens */}
              <div className="space-y-1.5">
                <Label>Allergens</Label>
                <div className="flex flex-wrap gap-2">
                  {allergenOptions.map((a) => (
                    <button key={a} onClick={() => toggleAllergen(a)} className={`px-3 py-1 rounded-full text-xs font-medium border transition-all ${formData.allergens.includes(a) ? "bg-honey/20 border-honey text-[#a26d0d]" : "bg-cream border-line text-ink-soft hover:border-border"}`}>
                      {a}
                    </button>
                  ))}
                </div>
              </div>

              {/* Modifier Group Assignments */}
              <div className="space-y-2">
                <Label>Modifier Groups</Label>
                {modifierGroups.length === 0 ? (
                  <p className="text-xs text-ink-soft">No modifier groups yet. Create them in the Modifier Library tab first.</p>
                ) : (
                  <div className="space-y-1.5">
                    {modifierGroups.filter(g => g.active).map((group) => (
                      <div
                        key={group.id}
                        onClick={() => toggleModifierGroupAssignment(group.id)}
                        className={`flex items-center justify-between p-2.5 rounded-lg border cursor-pointer transition-all ${isGroupAssigned(group.id) ? "border-coral/50 bg-coral/5" : "border-line hover:border-border"}`}
                      >
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium">{group.name}</span>
                            {group.required && <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-honey/20 text-[#a26d0d]">Required</span>}
                          </div>
                          <p className="text-xs text-ink-soft">{group.options.map((o) => o.name).join(", ")}</p>
                        </div>
                        <Switch checked={isGroupAssigned(group.id)} onCheckedChange={() => toggleModifierGroupAssignment(group.id)} onClick={(e) => e.stopPropagation()} />
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Special Instructions toggle */}
              <div className="flex items-center justify-between p-3 rounded-lg bg-cream border border-line">
                <div>
                  <p className="text-sm font-medium">Special Instructions</p>
                  <p className="text-xs text-ink-soft">Allow customers to add free-text notes</p>
                </div>
                <Switch
                  checked={formData.special_instructions_enabled !== false}
                  onCheckedChange={(v) => setFormData((p) => ({ ...p, special_instructions_enabled: v }))}
                />
              </div>

              {/* Available toggle */}
              <div className="flex items-center justify-between">
                <Label>Available</Label>
                <Switch checked={formData.available} onCheckedChange={(v) => setFormData((p) => ({ ...p, available: v }))} />
              </div>
            </div>
          </ScrollArea>
          <DialogFooter className="pt-4 border-t">
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleSave} disabled={saving} className="bg-coral hover:bg-coral-deep text-white">
              {saving ? "Saving..." : editingItem ? "Update Item" : "Add Item"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default MenuPage;