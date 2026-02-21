import { useState, useEffect } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { UserButton } from "@clerk/clerk-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  LayoutDashboard,
  Phone,
  UtensilsCrossed,
  Settings,
  Radio,
  ChevronLeft,
  ChevronRight,
  LogOut,
  Menu,
  PhoneCall,
} from "lucide-react";
import { getRestaurant, getRestaurantId } from "@/lib/api";

const navItems = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "Call History", href: "/calls", icon: Phone },
  { label: "Menu Manager", href: "/menu", icon: UtensilsCrossed },
  { label: "Live Monitor", href: "/live", icon: Radio },
  { label: "Settings", href: "/settings", icon: Settings },
];

export const AppLayout = ({ children }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [restaurant, setRestaurant] = useState(null);

  useEffect(() => {
    const restaurantId = getRestaurantId();
    if (!restaurantId) {
      navigate("/onboarding");
      return;
    }
    getRestaurant(restaurantId)
      .then((res) => setRestaurant(res.data))
      .catch(() => navigate("/onboarding"));
  }, [navigate]);

  const SidebarContent = () => (
    <div className="flex flex-col h-full">
      {/* Logo */}
      <div className="p-4 flex items-center gap-2.5">
        <div className="w-9 h-9 rounded-lg bg-gradient-primary flex items-center justify-center shadow-glow-primary flex-shrink-0">
          <PhoneCall className="w-4.5 h-4.5 text-primary-foreground" />
        </div>
        {!collapsed && (
          <span className="text-lg font-heading font-bold text-foreground">
            ring<span className="text-gradient-primary">AI</span>
          </span>
        )}
      </div>

      <Separator />

      {/* Nav Links */}
      <ScrollArea className="flex-1 p-3">
        <nav className="space-y-1">
          {navItems.map((item) => {
            const isActive = location.pathname === item.href;
            return (
              <Link
                key={item.href}
                to={item.href}
                onClick={() => setMobileOpen(false)}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors duration-200 ${
                  isActive
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted"
                } ${collapsed ? "justify-center" : ""}`}
              >
                <item.icon className="w-4.5 h-4.5 flex-shrink-0" />
                {!collapsed && <span>{item.label}</span>}
                {!collapsed && item.label === "Live Monitor" && (
                  <Badge variant="secondary" className="ml-auto text-xs bg-success/10 text-success border-0 px-1.5 py-0">
                    Live
                  </Badge>
                )}
              </Link>
            );
          })}
        </nav>
      </ScrollArea>

      <Separator />

      {/* Bottom */}
      <div className="p-3">
        <Link
          to="/"
          className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors ${collapsed ? "justify-center" : ""}`}
        >
          <LogOut className="w-4.5 h-4.5 flex-shrink-0" />
          {!collapsed && <span>Back to Site</span>}
        </Link>
      </div>
    </div>
  );

  return (
    <div className="flex h-screen bg-background overflow-hidden">
      {/* Desktop Sidebar */}
      <aside
        className={`hidden lg:flex flex-col border-r border-border bg-card transition-all duration-300 ${
          collapsed ? "w-16" : "w-60"
        }`}
      >
        <SidebarContent />
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="absolute top-5 -right-3 z-10 w-6 h-6 rounded-full border border-border bg-card flex items-center justify-center text-muted-foreground hover:text-foreground shadow-sm"
          style={{ left: collapsed ? "52px" : "228px" }}
        >
          {collapsed ? <ChevronRight className="w-3 h-3" /> : <ChevronLeft className="w-3 h-3" />}
        </button>
      </aside>

      {/* Mobile Sidebar Overlay */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-foreground/20" onClick={() => setMobileOpen(false)} />
          <aside className="relative w-60 h-full bg-card border-r border-border shadow-lg">
            <SidebarContent />
          </aside>
        </div>
      )}

      {/* Main Content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Top Bar */}
        <header className="flex items-center justify-between px-4 lg:px-6 py-3 border-b border-border bg-card">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setMobileOpen(true)}
              className="lg:hidden p-2 text-foreground rounded-md hover:bg-muted transition-colors"
            >
              <Menu className="w-5 h-5" />
            </button>
            <div>
              <h1 className="text-sm font-heading font-semibold text-foreground">
                {restaurant?.name || "Loading..."}
              </h1>
              <p className="text-xs text-muted-foreground">
                {restaurant?.cuisine_type || ""}{restaurant?.address ? ` · ${restaurant.address.split(",")[1]?.trim() || ""}` : ""}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Badge variant="secondary" className="bg-success/10 text-success border-0 text-xs">
              <div className="w-1.5 h-1.5 rounded-full bg-success mr-1.5" />
              AI Active
            </Badge>
            <UserButton afterSignOutUrl="/" />
          </div>
        </header>

        {/* Page Content */}
        <div className="flex-1 overflow-y-auto">
          {children}
        </div>
      </main>
    </div>
  );
};
