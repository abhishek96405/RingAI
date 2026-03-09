import { useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { Bell, ChevronLeft, ChevronRight, CreditCard, LayoutDashboard, LogOut, Menu, Phone, PhoneCall, Plug, Settings, UtensilsCrossed } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { SignOutButton, UserButton } from "@clerk/clerk-react";
import { useAppSession } from "@/context/AppSessionContext";

const navItems = [
  { icon: LayoutDashboard, label: "Dashboard", path: "/dashboard" },
  { icon: PhoneCall, label: "Calls", path: "/dashboard/calls" },
  { icon: UtensilsCrossed, label: "Menu", path: "/dashboard/menu" },
  { icon: Plug, label: "Integrations", path: "/dashboard/integrations" },
  { icon: CreditCard, label: "Billing", path: "/dashboard/billing" },
  { icon: Settings, label: "Settings", path: "/dashboard/settings" },
];

const DashboardLayout = () => {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  const { activeRestaurant } = useAppSession();

  const isActive = (path: string) => location.pathname === path || (path !== "/dashboard" && location.pathname.startsWith(path));

  const sidebar = (
    <div className="flex flex-col h-full">
      <div className="h-16 flex items-center px-4 border-b border-border/50">
        <Link to="/dashboard" className="flex items-center gap-2.5 overflow-hidden">
          <div className="w-9 h-9 rounded-xl bg-gradient-primary flex items-center justify-center shrink-0">
            <Phone className="w-4 h-4 text-primary-foreground" />
          </div>
          {!collapsed && <span className="font-display font-bold text-lg whitespace-nowrap">Ring<span className="text-gradient">AI</span></span>}
        </Link>
      </div>

      <ScrollArea className="flex-1 py-4 px-3">
        <nav className="space-y-1">
          {navItems.map((item) => (
            <Link
              key={item.path}
              to={item.path}
              onClick={() => setMobileOpen(false)}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${isActive(item.path) ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:text-foreground hover:bg-muted/50"}`}
            >
              <item.icon className="w-5 h-5 shrink-0" />
              {!collapsed && <span>{item.label}</span>}
            </Link>
          ))}
        </nav>
      </ScrollArea>

      <Separator />
      <div className="p-3 space-y-2">
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="hidden lg:flex w-full items-center justify-center gap-2 px-3 py-2 rounded-xl text-sm text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
        >
          {collapsed ? <ChevronRight className="w-4 h-4" /> : <><ChevronLeft className="w-4 h-4" /><span>Collapse</span></>}
        </button>
        <SignOutButton redirectUrl="/">
          <button className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-xl text-sm text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors">
            <LogOut className="w-4 h-4" />
            {!collapsed && <span>Sign Out</span>}
          </button>
        </SignOutButton>
      </div>
    </div>
  );

  const currentLabel = navItems.find((n) => isActive(n.path))?.label || "Dashboard";

  return (
    <div className="min-h-screen bg-background flex">
      <aside className={`${collapsed ? "w-[72px]" : "w-60"} hidden lg:flex border-r border-border/50 bg-card flex-col transition-all duration-300 shrink-0`}>
        {sidebar}
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/30" onClick={() => setMobileOpen(false)} />
          <aside className="relative w-64 h-full bg-card border-r border-border/50">{sidebar}</aside>
        </div>
      )}

      <div className="flex-1 flex flex-col min-w-0">
        <header className="h-16 border-b border-border/50 bg-card/80 backdrop-blur-xl flex items-center justify-between px-4 lg:px-6">
          <div className="flex items-center gap-3 min-w-0">
            <Button variant="ghost" size="icon" className="rounded-xl lg:hidden" onClick={() => setMobileOpen(true)}>
              <Menu className="w-5 h-5" />
            </Button>
            <div className="min-w-0">
              <h2 className="font-display font-semibold text-lg truncate">{currentLabel}</h2>
              <p className="text-xs text-muted-foreground truncate">
                {activeRestaurant?.name || "RingAI Workspace"}
                {activeRestaurant?.cuisine_type ? ` · ${activeRestaurant.cuisine_type}` : ""}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <Badge variant="secondary" className="hidden sm:inline-flex bg-success/10 text-success border-0">
              <div className="w-1.5 h-1.5 rounded-full bg-success mr-1.5" /> AI Active
            </Badge>
            <Button variant="ghost" size="icon" className="rounded-xl relative">
              <Bell className="w-5 h-5" />
              <span className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-destructive border-2 border-card" />
            </Button>
            <UserButton afterSignOutUrl="/" />
          </div>
        </header>

        <main className="flex-1 overflow-y-auto p-4 lg:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
};

export default DashboardLayout;
