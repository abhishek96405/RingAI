import { useCallback, useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { createMenuItem, deleteMenuItem, getMenuItems, toggleMenuItem, updateMenuItem } from "@/lib/api";
import { DollarSign, Edit2, Plus, Search, Trash2, UtensilsCrossed } from "lucide-react";
import { motion } from "framer-motion";
import { toast } from "sonner";

const defaultItem = { name: "", description: "", category: "Appetizers", price: 0, available: true, allergens: [] as string[], modifiers: [] as any[] };
const categories = ["Appetizers", "Pizza", "Pasta", "Entrees", "Desserts", "Beverages", "Sides", "Specials", "Uncategorized"];
const allergenOptions = ["gluten", "dairy", "nuts", "soy", "eggs", "shellfish"];

const MenuPage = () => {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [activeCategory, setActiveCategory] = useState("all");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<any>(null);
  const [formData, setFormData] = useState<any>(defaultItem);
  const [saving, setSaving] = useState(false);

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

  useEffect(() => { fetchItems(); }, [fetchItems]);

  const openAdd = () => {
    setEditingItem(null);
    setFormData(defaultItem);
    setDialogOpen(true);
  };

  const openEdit = (item: any) => {
    setEditingItem(item);
    setFormData({
      name: item.name,
      description: item.description || "",
      category: item.category,
      price: item.price,
      available: item.available,
      allergens: item.allergens || [],
      modifiers: item.modifiers || [],
    });
    setDialogOpen(true);
  };

  const handleSave = async () => {
    if (!formData.name.trim()) {
      toast.error("Item name is required");
      return;
    }
    setSaving(true);
    try {
      if (editingItem) {
        await updateMenuItem(editingItem.id, formData);
        toast.success("Menu item updated!");
      } else {
        await createMenuItem(null, formData);
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
    setFormData((prev: any) => ({
      ...prev,
      allergens: prev.allergens.includes(allergen)
        ? prev.allergens.filter((a: string) => a !== allergen)
        : [...prev.allergens, allergen],
    }));
  };

  const filteredItems = useMemo(() => items.filter((item) => {
    if (activeCategory !== "all" && item.category !== activeCategory) return false;
    if (search && !item.name.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  }), [items, activeCategory, search]);

  const groupedItems = useMemo(() => filteredItems.reduce((acc: Record<string, any[]>, item: any) => {
    if (!acc[item.category]) acc[item.category] = [];
    acc[item.category].push(item);
    return acc;
  }, {}), [filteredItems]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row gap-4 justify-between">
        <div className="relative max-w-md flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input placeholder="Search menu items..." value={search} onChange={(e) => setSearch(e.target.value)} className="pl-9 h-10 rounded-xl" />
        </div>
        <Button onClick={openAdd} className="bg-gradient-primary text-primary-foreground rounded-xl shadow-glow hover:opacity-90"><Plus className="w-4 h-4 mr-2" /> Add Item</Button>
      </div>

      <div className="flex gap-2 overflow-x-auto pb-1">
        {["all", ...categories].map((cat) => (
          <button key={cat} onClick={() => setActiveCategory(cat)} className={`px-4 py-2 rounded-xl text-sm font-medium whitespace-nowrap transition-all ${activeCategory === cat ? "bg-primary text-primary-foreground shadow-glow" : "bg-muted text-muted-foreground hover:text-foreground"}`}>
            {cat === "all" ? "All Items" : cat}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">{[...Array(6)].map((_, i) => <div key={i} className="premium-card h-44 animate-pulse" />)}</div>
      ) : Object.keys(groupedItems).length === 0 ? (
        <div className="text-center py-20">
          <UtensilsCrossed className="w-12 h-12 text-muted-foreground/30 mx-auto mb-4" />
          <h3 className="font-display font-semibold text-lg mb-1">No menu items found</h3>
          <p className="text-sm text-muted-foreground">Try a different search or add new items.</p>
        </div>
      ) : Object.entries(groupedItems).map(([category, catItems]) => (
        <div key={category}>
          <h3 className="font-display font-bold text-lg mb-4">{category}</h3>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {(catItems as any[]).map((item, i) => (
              <motion.div key={item.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }} className="premium-card p-5">
                <div className="flex justify-between items-start mb-3 gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h4 className="font-display font-semibold truncate">{item.name}</h4>
                      {!item.available && <span className="px-2 py-0.5 rounded-full bg-destructive/10 text-destructive text-xs font-medium">Unavailable</span>}
                    </div>
                    <p className="text-sm text-muted-foreground mt-1">{item.description}</p>
                    {item.allergens?.length > 0 && <div className="flex flex-wrap gap-1.5 mt-2">{item.allergens.map((a: string) => <Badge key={a} variant="secondary" className="text-xs border-0 bg-warning/10 text-warning">{a}</Badge>)}</div>}
                  </div>
                  <Switch checked={item.available} onCheckedChange={() => handleToggle(item.id)} />
                </div>
                <div className="flex items-center justify-between">
                  <span className="flex items-center text-lg font-display font-bold"><DollarSign className="w-4 h-4 mr-0.5" />{(item.price / 100).toFixed(2)}</span>
                  <div className="flex gap-1">
                    <Button variant="ghost" size="sm" className="rounded-lg h-8 w-8 p-0" onClick={() => openEdit(item)}><Edit2 className="w-3.5 h-3.5" /></Button>
                    <Button variant="ghost" size="sm" className="rounded-lg h-8 w-8 p-0 text-destructive" onClick={() => handleDelete(item.id)}><Trash2 className="w-3.5 h-3.5" /></Button>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      ))}

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle className="font-display">{editingItem ? "Edit Menu Item" : "Add Menu Item"}</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2"><Label>Name</Label><Input value={formData.name} onChange={(e) => setFormData({ ...formData, name: e.target.value })} placeholder="Item name" /></div>
              <div><Label>Category</Label><Select value={formData.category} onValueChange={(v) => setFormData({ ...formData, category: v })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{categories.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent></Select></div>
              <div><Label>Price (cents)</Label><Input type="number" value={formData.price} onChange={(e) => setFormData({ ...formData, price: parseInt(e.target.value) || 0 })} placeholder="1499" /></div>
              <div className="col-span-2"><Label>Description</Label><Textarea value={formData.description} onChange={(e) => setFormData({ ...formData, description: e.target.value })} rows={2} /></div>
              <div className="col-span-2"><Label className="mb-2 block">Allergens</Label><div className="flex flex-wrap gap-2">{allergenOptions.map((a) => <Button key={a} type="button" variant={formData.allergens.includes(a) ? "default" : "outline"} size="sm" onClick={() => toggleAllergen(a)} className="text-xs h-7">{a}</Button>)}</div></div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleSave} disabled={saving} className="bg-gradient-primary text-primary-foreground rounded-xl shadow-glow hover:opacity-90">{saving ? "Saving..." : editingItem ? "Update Item" : "Add Item"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default MenuPage;
