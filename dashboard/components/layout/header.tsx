"use client";

import { useState } from "react";
import { usePathname } from "next/navigation";
import {
  Bell,
  Search,
  User,
  ChevronDown,
  AlertTriangle,
  CheckCircle2,
  Clock,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

// Map routes to German titles
const routeTitles: Record<string, string> = {
  "/": "Übersicht",
  "/aufgaben": "Aufgaben",
  "/abteilungen": "Abteilungen",
  "/mitarbeiter": "Mitarbeiter",
  "/routing": "Routing-Regeln",
  "/einstellungen": "Einstellungen",
  "/hilfe": "Hilfe",
  "/kanaele/telefon": "Telefon",
  "/kanaele/email": "E-Mail",
  "/kanaele/chat": "Chat",
};

interface Notification {
  id: string;
  type: "emergency" | "urgent" | "info";
  title: string;
  message: string;
  time: string;
  read: boolean;
}

// Mock notifications - in production, fetch from API
const mockNotifications: Notification[] = [
  {
    id: "1",
    type: "emergency",
    title: "Notfall: Heizungsausfall",
    message: "Kunde meldet Heizungsausfall - sofortige Bearbeitung erforderlich",
    time: "vor 5 Min.",
    read: false,
  },
  {
    id: "2",
    type: "urgent",
    title: "Neue dringende Aufgabe",
    message: "Wasserrohrbruch bei Firma Schmidt - heute noch bearbeiten",
    time: "vor 15 Min.",
    read: false,
  },
  {
    id: "3",
    type: "info",
    title: "Aufgabe abgeschlossen",
    message: "Hans Müller hat Aufgabe #1234 erfolgreich abgeschlossen",
    time: "vor 1 Std.",
    read: true,
  },
];

export function Header() {
  const pathname = usePathname();
  const [showNotifications, setShowNotifications] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);

  // Get page title from route
  const pageTitle =
    routeTitles[pathname] ||
    Object.entries(routeTitles).find(([route]) =>
      pathname.startsWith(route) && route !== "/"
    )?.[1] ||
    "Dashboard";

  const unreadCount = mockNotifications.filter((n) => !n.read).length;

  const NotificationIcon = ({ type }: { type: Notification["type"] }) => {
    switch (type) {
      case "emergency":
        return <AlertTriangle className="h-4 w-4 text-red-500" />;
      case "urgent":
        return <Clock className="h-4 w-4 text-orange-500" />;
      default:
        return <CheckCircle2 className="h-4 w-4 text-green-500" />;
    }
  };

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-4 border-b bg-background px-6">
      {/* Page Title */}
      <div className="flex-1">
        <h1 className="text-xl font-semibold">{pageTitle}</h1>
      </div>

      {/* Search */}
      <div className="hidden md:flex md:w-80">
        <div className="relative w-full">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="search"
            placeholder="Suchen... (⌘K)"
            className="pl-9"
          />
        </div>
      </div>

      {/* Notifications */}
      <div className="relative">
        <Button
          variant="ghost"
          size="icon"
          className="relative"
          onClick={() => setShowNotifications(!showNotifications)}
        >
          <Bell className="h-5 w-5" />
          {unreadCount > 0 && (
            <span className="absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white">
              {unreadCount}
            </span>
          )}
        </Button>

        {/* Notifications Dropdown */}
        {showNotifications && (
          <>
            <div
              className="fixed inset-0 z-40"
              onClick={() => setShowNotifications(false)}
            />
            <div className="absolute right-0 top-full z-50 mt-2 w-80 rounded-lg border bg-card shadow-lg">
              <div className="flex items-center justify-between border-b px-4 py-3">
                <span className="font-semibold">Benachrichtigungen</span>
                {unreadCount > 0 && (
                  <Badge variant="destructive" className="h-5 px-1.5">
                    {unreadCount} neu
                  </Badge>
                )}
              </div>
              <div className="max-h-96 overflow-y-auto">
                {mockNotifications.map((notification) => (
                  <div
                    key={notification.id}
                    className={cn(
                      "flex gap-3 border-b px-4 py-3 transition-colors hover:bg-accent cursor-pointer",
                      !notification.read && "bg-blue-50/50"
                    )}
                  >
                    <div className="mt-0.5">
                      <NotificationIcon type={notification.type} />
                    </div>
                    <div className="flex-1 space-y-1">
                      <p className="text-sm font-medium leading-none">
                        {notification.title}
                      </p>
                      <p className="text-xs text-muted-foreground line-clamp-2">
                        {notification.message}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {notification.time}
                      </p>
                    </div>
                    {!notification.read && (
                      <div className="h-2 w-2 rounded-full bg-blue-500" />
                    )}
                  </div>
                ))}
              </div>
              <div className="border-t px-4 py-2">
                <Button variant="ghost" size="sm" className="w-full">
                  Alle anzeigen
                </Button>
              </div>
            </div>
          </>
        )}
      </div>

      {/* User Menu */}
      <div className="relative">
        <Button
          variant="ghost"
          className="flex items-center gap-2"
          onClick={() => setShowUserMenu(!showUserMenu)}
        >
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-100 text-brand-700">
            <User className="h-4 w-4" />
          </div>
          <div className="hidden md:block text-left">
            <p className="text-sm font-medium">Admin</p>
            <p className="text-xs text-muted-foreground">Firma Müller SHK</p>
          </div>
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        </Button>

        {/* User Menu Dropdown */}
        {showUserMenu && (
          <>
            <div
              className="fixed inset-0 z-40"
              onClick={() => setShowUserMenu(false)}
            />
            <div className="absolute right-0 top-full z-50 mt-2 w-56 rounded-lg border bg-card shadow-lg">
              <div className="border-b px-4 py-3">
                <p className="font-medium">Admin Benutzer</p>
                <p className="text-sm text-muted-foreground">
                  admin@mueller-shk.de
                </p>
              </div>
              <div className="p-1">
                <button className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-accent">
                  Profil bearbeiten
                </button>
                <button className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-accent">
                  Firmeneinstellungen
                </button>
                <button className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-accent">
                  Abonnement
                </button>
              </div>
              <div className="border-t p-1">
                <button className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-destructive hover:bg-destructive/10">
                  Abmelden
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </header>
  );
}
