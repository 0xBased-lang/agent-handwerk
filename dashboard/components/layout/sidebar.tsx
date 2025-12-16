"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  ListTodo,
  Building2,
  Users,
  Route,
  Settings,
  Phone,
  Mail,
  MessageSquare,
  HelpCircle,
  LogOut,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useState } from "react";

interface NavItem {
  href: string;
  label: string;
  labelDe: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: number;
}

const mainNavItems: NavItem[] = [
  {
    href: "/",
    label: "Dashboard",
    labelDe: "Übersicht",
    icon: LayoutDashboard,
  },
  {
    href: "/aufgaben",
    label: "Tasks",
    labelDe: "Aufgaben",
    icon: ListTodo,
  },
  {
    href: "/abteilungen",
    label: "Departments",
    labelDe: "Abteilungen",
    icon: Building2,
  },
  {
    href: "/mitarbeiter",
    label: "Workers",
    labelDe: "Mitarbeiter",
    icon: Users,
  },
  {
    href: "/routing",
    label: "Routing Rules",
    labelDe: "Routing-Regeln",
    icon: Route,
  },
];

const channelNavItems: NavItem[] = [
  {
    href: "/kanaele/telefon",
    label: "Phone",
    labelDe: "Telefon",
    icon: Phone,
  },
  {
    href: "/kanaele/email",
    label: "Email",
    labelDe: "E-Mail",
    icon: Mail,
  },
  {
    href: "/kanaele/chat",
    label: "Chat",
    labelDe: "Chat",
    icon: MessageSquare,
  },
];

const bottomNavItems: NavItem[] = [
  {
    href: "/einstellungen",
    label: "Settings",
    labelDe: "Einstellungen",
    icon: Settings,
  },
  {
    href: "/hilfe",
    label: "Help",
    labelDe: "Hilfe",
    icon: HelpCircle,
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  const NavLink = ({ item }: { item: NavItem }) => {
    const isActive =
      pathname === item.href ||
      (item.href !== "/" && pathname.startsWith(item.href));
    const Icon = item.icon;

    return (
      <Link
        href={item.href}
        className={cn(
          "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all hover:bg-accent hover:text-accent-foreground",
          isActive
            ? "bg-accent text-accent-foreground"
            : "text-muted-foreground",
          collapsed && "justify-center px-2"
        )}
        title={collapsed ? item.labelDe : undefined}
      >
        <Icon className="h-5 w-5 shrink-0" />
        {!collapsed && <span>{item.labelDe}</span>}
        {!collapsed && item.badge !== undefined && item.badge > 0 && (
          <span className="ml-auto flex h-5 min-w-5 items-center justify-center rounded-full bg-red-500 px-1.5 text-[10px] font-bold text-white">
            {item.badge > 99 ? "99+" : item.badge}
          </span>
        )}
      </Link>
    );
  };

  return (
    <aside
      className={cn(
        "fixed left-0 top-0 z-40 flex h-screen flex-col border-r bg-card transition-all duration-300",
        collapsed ? "w-16" : "w-64"
      )}
    >
      {/* Logo / Brand */}
      <div
        className={cn(
          "flex h-16 items-center border-b px-4",
          collapsed ? "justify-center" : "gap-3"
        )}
      >
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-600 text-white font-bold">
          ITF
        </div>
        {!collapsed && (
          <div className="flex flex-col">
            <span className="text-sm font-semibold">IT-Friends</span>
            <span className="text-xs text-muted-foreground">Handwerk</span>
          </div>
        )}
      </div>

      {/* Main Navigation */}
      <nav className="flex-1 space-y-1 overflow-y-auto p-3">
        <div className="space-y-1">
          {mainNavItems.map((item) => (
            <NavLink key={item.href} item={item} />
          ))}
        </div>

        {/* Channels Section */}
        {!collapsed && (
          <div className="mt-6">
            <p className="mb-2 px-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Kanäle
            </p>
          </div>
        )}
        <div className="space-y-1">
          {channelNavItems.map((item) => (
            <NavLink key={item.href} item={item} />
          ))}
        </div>
      </nav>

      {/* Bottom Navigation */}
      <div className="border-t p-3 space-y-1">
        {bottomNavItems.map((item) => (
          <NavLink key={item.href} item={item} />
        ))}

        {/* Logout */}
        <button
          className={cn(
            "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground transition-all hover:bg-destructive/10 hover:text-destructive",
            collapsed && "justify-center px-2"
          )}
          title={collapsed ? "Abmelden" : undefined}
        >
          <LogOut className="h-5 w-5 shrink-0" />
          {!collapsed && <span>Abmelden</span>}
        </button>
      </div>

      {/* Collapse Toggle */}
      <Button
        variant="ghost"
        size="icon"
        className="absolute -right-3 top-20 h-6 w-6 rounded-full border bg-background shadow-sm"
        onClick={() => setCollapsed(!collapsed)}
      >
        {collapsed ? (
          <ChevronRight className="h-3 w-3" />
        ) : (
          <ChevronLeft className="h-3 w-3" />
        )}
      </Button>
    </aside>
  );
}
