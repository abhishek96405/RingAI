import { useState, useEffect, useCallback } from "react";
import { AppLayout } from "@/layouts/AppLayout";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  Plus,
  Search,
  Pencil,
  Trash2,
  UtensilsCrossed,
  DollarSign,
  AlertTriangle,
} from "lucide-react";
import { getMenuItems, createMenuItem, updateMenuItem, deleteMenuItem, toggleMenuItem } from "@/lib/api";
import { toast } from "sonner";
import { motion } from "framer-motion";

const defaultItem = {
  name: "", description: "", category: "Appetizers", price: 0, available: true, allergens: [], modifiers: [],
};

const categories = ["Appetizers", "Pizza", "Pasta", "Entrees", "Desserts", "Beverages", "Sides", "Specials"];
const allergenOptions = ["gluten", "dairy", "nuts", "soy", "eggs", "shellfish"];

export default function MenuManager() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("ALL");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingItem, setEditingItem] = useState(null);
  const [formData, setFormData] = useState(defaultItem);
  const [saving, setSaving] = useState(false);

  const fetchItems = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getMenuItems();
      setItems(res.data);
    } catch (err) {
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

  const openEdit = (item) => {
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
    if (!formData.name.trim()) { toast.error("Item name is required"); return; }
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
    } catch (err) {
      toast.error("Failed to save item");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (itemId) => {
    try {
      await deleteMenuItem(itemId);
      toast.success("Item deleted");
      fetchItems();
    } catch (err) {
      toast.error("Failed to delete item");
    }
  };

  const handleToggle = async (itemId) => {
    try {
      await toggleMenuItem(itemId);
      setItems(prev => prev.map(item => item.id === itemId ? { ...item, available: !item.available } : item));
    } catch (err) {
      toast.error("Failed to toggle availability");
    }
  };

  const toggleAllergen = (allergen) => {
    setFormData(prev => ({
      ...prev,
      allergens: prev.allergens.includes(allergen)
        ? prev.allergens.filter(a => a !== allergen)
        : [...prev.allergens, allergen]
    }));
  };

  const filteredItems = items.filter(item => {
    if (categoryFilter !== "ALL" && item.category !== categoryFilter) return false;
    if (search && !item.name.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const groupedItems = filteredItems.reduce((acc, item) => {
    if (!acc[item.category]) acc[item.category] = [];
    acc[item.category].push(item);
    return acc;
  }, {});

  return (
    <AppLayout>
      <div className="p-4 lg:p-6 space-y-4">
        {/* Header */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-heading font-bold text-foreground">Menu Manager</h1>
            <p className="text-sm text-muted-foreground">{items.length} items · {items.filter(i => i.available).length} available</p>
          </div>
          <Button variant="premium" size="sm" onClick={openAdd}>
            <Plus className="w-4 h-4" />
            Add Item
          </Button>
        </div>

        {/* Filters */}
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input placeholder="Search menu items..." value={search} onChange={(e) => setSearch(e.target.value)} className="pl-9" />
          </div>
          <Select value={categoryFilter} onValueChange={setCategoryFilter}>
            <SelectTrigger className="w-44">
              <SelectValue placeholder="All categories" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL">All Categories</SelectItem>
              {categories.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>

        {/* Menu Items Grouped by Category */}
        {loading ? (
          <div className="grid gap-3">
            {[...Array(4)].map((_, i) => (
              <Card key={i} className="p-4 animate-pulse border-border bg-card">
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 rounded-lg bg-muted" />
                  <div className="flex-1 space-y-2">
                    <div className="h-4 w-40 bg-muted rounded" />
                    <div className="h-3 w-60 bg-muted rounded" />
                  </div>
                </div>
              </Card>
            ))}
          </div>
        ) : Object.keys(groupedItems).length === 0 ? (
          <Card className="p-12 border-border bg-card text-center">
            <UtensilsCrossed className="w-10 h-10 text-muted-foreground/30 mx-auto mb-3" />
            <p className="text-sm text-muted-foreground">No menu items found</p>
            <Button variant="outline" size="sm" className="mt-3" onClick={openAdd}>Add your first item</Button>
          </Card>
        ) : (
          Object.entries(groupedItems).map(([category, catItems]) => (
            <div key={category}>
              <h3 className="text-sm font-heading font-semibold text-muted-foreground uppercase tracking-wider mb-3">
                {category} <span className="text-xs font-normal">({catItems.length})</span>
              </h3>
              <div className="space-y-2">
                {catItems.map((item, i) => (
                  <motion.div
                    key={item.id}
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.02 }}
                  >
                    <Card className={`flex items-center gap-4 p-4 border-border bg-card hover:shadow-sm transition-shadow ${
                      !item.available ? 'opacity-60' : ''
                    }`}>
                      <div className="w-11 h-11 rounded-lg bg-primary/5 flex items-center justify-center flex-shrink-0">
                        <UtensilsCrossed className="w-5 h-5 text-primary" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-medium text-foreground truncate">{item.name}</p>
                          {!item.available && (
                            <Badge variant="secondary" className="text-xs bg-destructive/10 text-destructive border-0">Unavailable</Badge>
                          )}
                        </div>
                        {item.description && (
                          <p className="text-xs text-muted-foreground truncate mt-0.5">{item.description}</p>
                        )}
                        {item.allergens?.length > 0 && (
                          <div className="flex gap-1 mt-1">
                            {item.allergens.map(a => (
                              <Badge key={a} variant="secondary" className="text-xs py-0 h-4 border-0 bg-accent/10 text-accent">{a}</Badge>
                            ))}
                          </div>
                        )}
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="text-sm font-heading font-semibold text-foreground">
                          ${(item.price / 100).toFixed(2)}
                        </span>
                        <Switch checked={item.available} onCheckedChange={() => handleToggle(item.id)} />
                        <Button variant="ghost" size="icon" onClick={() => openEdit(item)} className="h-8 w-8">
                          <Pencil className="w-3.5 h-3.5" />
                        </Button>
                        <Button variant="ghost" size="icon" onClick={() => handleDelete(item.id)} className="h-8 w-8 text-destructive hover:text-destructive">
                          <Trash2 className="w-3.5 h-3.5" />
                        </Button>
                      </div>
                    </Card>
                  </motion.div>
                ))}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Add/Edit Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="font-heading">{editingItem ? "Edit Menu Item" : "Add Menu Item"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <Label className="text-xs">Name</Label>
                <Input value={formData.name} onChange={(e) => setFormData({ ...formData, name: e.target.value })} placeholder="Item name" />
              </div>
              <div>
                <Label className="text-xs">Category</Label>
                <Select value={formData.category} onValueChange={(v) => setFormData({ ...formData, category: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {categories.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">Price (cents)</Label>
                <Input type="number" value={formData.price} onChange={(e) => setFormData({ ...formData, price: parseInt(e.target.value) || 0 })} placeholder="1499" />
              </div>
              <div className="col-span-2">
                <Label className="text-xs">Description</Label>
                <Textarea value={formData.description} onChange={(e) => setFormData({ ...formData, description: e.target.value })} placeholder="Brief description..." rows={2} />
              </div>
              <div className="col-span-2">
                <Label className="text-xs mb-2 block">Allergens</Label>
                <div className="flex flex-wrap gap-2">
                  {allergenOptions.map(a => (
                    <Button
                      key={a}
                      type="button"
                      variant={formData.allergens.includes(a) ? "default" : "outline"}
                      size="sm"
                      onClick={() => toggleAllergen(a)}
                      className="text-xs h-7"
                    >
                      {a}
                    </Button>
                  ))}
                </div>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
            <Button variant="premium" onClick={handleSave} disabled={saving}>
              {saving ? "Saving..." : editingItem ? "Update Item" : "Add Item"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </AppLayout>
  );
}
