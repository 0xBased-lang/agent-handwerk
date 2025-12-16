"use client";

import { useState } from "react";
import {
  Settings,
  Building2,
  Mail,
  Phone,
  MapPin,
  Globe,
  Bell,
  Shield,
  CreditCard,
  Save,
  CheckCircle2,
  AlertTriangle,
  ExternalLink,
  TestTube,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Company, TRADE_CATEGORY_LABELS } from "@/types";
import { cn } from "@/lib/utils";

// Mock company data
const mockCompany: Company = {
  id: "c1",
  name: "Müller SHK GmbH",
  legal_name: "Müller Sanitär-Heizung-Klima GmbH",
  industry: "handwerk",
  trade_category: "shk",
  phone: "+49 7471 12345-0",
  email: "info@mueller-shk.de",
  website: "https://mueller-shk.de",
  address_street: "Industriestraße 42",
  address_zip: "72379",
  address_city: "Hechingen",
  latitude: 48.35,
  longitude: 8.9667,
  service_radius_km: 50,
  plan: "professional",
  max_users: 20,
  max_calls_per_month: 2000,
  settings_json: {
    email_intake: {
      enabled: true,
      imap_host: "imap.gmail.com",
      imap_port: 993,
      imap_user: "info@mueller-shk.de",
      poll_interval_minutes: 2,
    },
    notifications: {
      sms_enabled: true,
      email_enabled: true,
    },
  },
  status: "active",
  created_at: "2024-01-01",
  updated_at: "2024-12-16",
};

// Settings Section Component
function SettingsSection({
  title,
  description,
  icon: Icon,
  children,
}: {
  title: string;
  description: string;
  icon: typeof Settings;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-100">
            <Icon className="h-5 w-5 text-brand-600" />
          </div>
          <div>
            <CardTitle>{title}</CardTitle>
            <CardDescription>{description}</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

// Form Field Component
function FormField({
  label,
  children,
  hint,
}: {
  label: string;
  children: React.ReactNode;
  hint?: string;
}) {
  return (
    <div className="space-y-2">
      <label className="text-sm font-medium">{label}</label>
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

export default function SettingsPage() {
  const [company, setCompany] = useState<Company>(mockCompany);
  const [saving, setSaving] = useState(false);
  const [testingEmail, setTestingEmail] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    // Simulate API call
    await new Promise((r) => setTimeout(r, 1000));
    setSaving(false);
  };

  const testEmailConnection = async () => {
    setTestingEmail(true);
    // Simulate API call
    await new Promise((r) => setTimeout(r, 2000));
    setTestingEmail(false);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Einstellungen</h1>
          <p className="text-muted-foreground">
            Verwalten Sie Ihre Firmeneinstellungen und Integrationen
          </p>
        </div>
        <Button onClick={handleSave} disabled={saving}>
          {saving ? (
            <>Speichern...</>
          ) : (
            <>
              <Save className="mr-2 h-4 w-4" />
              Änderungen speichern
            </>
          )}
        </Button>
      </div>

      {/* Plan Status */}
      <Card className="bg-brand-50 border-brand-200">
        <CardContent className="p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <CreditCard className="h-8 w-8 text-brand-600" />
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="font-semibold">
                    {company.plan === "starter"
                      ? "Starter"
                      : company.plan === "professional"
                      ? "Professional"
                      : "Enterprise"}{" "}
                    Plan
                  </h3>
                  <Badge variant="default">Aktiv</Badge>
                </div>
                <p className="text-sm text-muted-foreground">
                  {company.max_users} Benutzer • {company.max_calls_per_month.toLocaleString("de-DE")} Anrufe/Monat
                </p>
              </div>
            </div>
            <Button variant="outline">
              <ExternalLink className="mr-2 h-4 w-4" />
              Plan ändern
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Company Information */}
      <SettingsSection
        title="Firmeninformationen"
        description="Grundlegende Informationen über Ihr Unternehmen"
        icon={Building2}
      >
        <div className="grid gap-4 md:grid-cols-2">
          <FormField label="Firmenname">
            <Input
              value={company.name}
              onChange={(e) => setCompany({ ...company, name: e.target.value })}
            />
          </FormField>
          <FormField label="Rechtlicher Name">
            <Input
              value={company.legal_name || ""}
              onChange={(e) => setCompany({ ...company, legal_name: e.target.value })}
            />
          </FormField>
          <FormField label="Gewerk">
            <Select
              value={company.trade_category}
              onValueChange={(v) => setCompany({ ...company, trade_category: v as Company["trade_category"] })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(TRADE_CATEGORY_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FormField>
          <FormField label="Website">
            <Input
              value={company.website || ""}
              onChange={(e) => setCompany({ ...company, website: e.target.value })}
              placeholder="https://"
            />
          </FormField>
        </div>
      </SettingsSection>

      {/* Contact Information */}
      <SettingsSection
        title="Kontaktdaten"
        description="Wie Kunden und das System Sie erreichen können"
        icon={Phone}
      >
        <div className="grid gap-4 md:grid-cols-2">
          <FormField label="Telefon">
            <Input
              value={company.phone || ""}
              onChange={(e) => setCompany({ ...company, phone: e.target.value })}
              placeholder="+49 ..."
            />
          </FormField>
          <FormField label="E-Mail">
            <Input
              type="email"
              value={company.email || ""}
              onChange={(e) => setCompany({ ...company, email: e.target.value })}
            />
          </FormField>
        </div>
      </SettingsSection>

      {/* Address & Service Area */}
      <SettingsSection
        title="Adresse & Servicegebiet"
        description="Standort und Einzugsbereich für geografisches Routing"
        icon={MapPin}
      >
        <div className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <FormField label="Straße">
              <Input
                value={company.address_street || ""}
                onChange={(e) => setCompany({ ...company, address_street: e.target.value })}
              />
            </FormField>
            <div className="grid grid-cols-2 gap-4">
              <FormField label="PLZ">
                <Input
                  value={company.address_zip || ""}
                  onChange={(e) => setCompany({ ...company, address_zip: e.target.value })}
                  maxLength={5}
                />
              </FormField>
              <FormField label="Stadt">
                <Input
                  value={company.address_city || ""}
                  onChange={(e) => setCompany({ ...company, address_city: e.target.value })}
                />
              </FormField>
            </div>
          </div>
          <FormField label="Service-Radius (km)" hint="Kunden außerhalb dieses Radius werden als 'außerhalb Servicegebiet' markiert">
            <div className="flex items-center gap-4">
              <Input
                type="number"
                value={company.service_radius_km}
                onChange={(e) => setCompany({ ...company, service_radius_km: parseInt(e.target.value) })}
                className="w-32"
                min={1}
                max={500}
              />
              <span className="text-sm text-muted-foreground">
                Aktuell: {company.service_radius_km} km um {company.address_zip} {company.address_city}
              </span>
            </div>
          </FormField>
        </div>
      </SettingsSection>

      {/* Email Integration */}
      <SettingsSection
        title="E-Mail Integration"
        description="IMAP-Konfiguration für automatische E-Mail-Verarbeitung"
        icon={Mail}
      >
        <div className="space-y-4">
          <div className="flex items-center justify-between p-3 rounded-lg border">
            <div className="flex items-center gap-3">
              {company.settings_json?.email_intake?.enabled ? (
                <CheckCircle2 className="h-5 w-5 text-green-600" />
              ) : (
                <AlertTriangle className="h-5 w-5 text-amber-600" />
              )}
              <div>
                <p className="font-medium">
                  E-Mail-Eingang {company.settings_json?.email_intake?.enabled ? "aktiv" : "deaktiviert"}
                </p>
                <p className="text-sm text-muted-foreground">
                  {company.settings_json?.email_intake?.imap_user || "Nicht konfiguriert"}
                </p>
              </div>
            </div>
            <Button variant="outline" onClick={testEmailConnection} disabled={testingEmail}>
              <TestTube className="mr-2 h-4 w-4" />
              {testingEmail ? "Testen..." : "Verbindung testen"}
            </Button>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <FormField label="IMAP Server">
              <Input
                value={company.settings_json?.email_intake?.imap_host || ""}
                placeholder="imap.gmail.com"
              />
            </FormField>
            <FormField label="IMAP Port">
              <Input
                type="number"
                value={company.settings_json?.email_intake?.imap_port || 993}
                className="w-32"
              />
            </FormField>
            <FormField label="E-Mail Adresse">
              <Input
                type="email"
                value={company.settings_json?.email_intake?.imap_user || ""}
                placeholder="info@firma.de"
              />
            </FormField>
            <FormField label="Passwort">
              <Input type="password" placeholder="••••••••" />
            </FormField>
            <FormField label="Abfrageintervall" hint="Wie oft neue E-Mails abgerufen werden">
              <Select defaultValue={company.settings_json?.email_intake?.poll_interval_minutes?.toString() || "2"}>
                <SelectTrigger className="w-48">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1">Jede Minute</SelectItem>
                  <SelectItem value="2">Alle 2 Minuten</SelectItem>
                  <SelectItem value="5">Alle 5 Minuten</SelectItem>
                  <SelectItem value="10">Alle 10 Minuten</SelectItem>
                </SelectContent>
              </Select>
            </FormField>
          </div>
        </div>
      </SettingsSection>

      {/* Notifications */}
      <SettingsSection
        title="Benachrichtigungen"
        description="Wie Mitarbeiter über neue Aufgaben informiert werden"
        icon={Bell}
      >
        <div className="space-y-4">
          <div className="flex items-center justify-between p-3 rounded-lg border">
            <div>
              <p className="font-medium">SMS-Benachrichtigungen</p>
              <p className="text-sm text-muted-foreground">
                Mitarbeiter per SMS über dringende Aufgaben informieren
              </p>
            </div>
            <Badge variant={company.settings_json?.notifications?.sms_enabled ? "completed" : "cancelled"}>
              {company.settings_json?.notifications?.sms_enabled ? "Aktiv" : "Deaktiviert"}
            </Badge>
          </div>
          <div className="flex items-center justify-between p-3 rounded-lg border">
            <div>
              <p className="font-medium">E-Mail-Benachrichtigungen</p>
              <p className="text-sm text-muted-foreground">
                Tägliche Zusammenfassung und Aufgaben-Updates per E-Mail
              </p>
            </div>
            <Badge variant={company.settings_json?.notifications?.email_enabled ? "completed" : "cancelled"}>
              {company.settings_json?.notifications?.email_enabled ? "Aktiv" : "Deaktiviert"}
            </Badge>
          </div>
        </div>
      </SettingsSection>

      {/* Security */}
      <SettingsSection
        title="Sicherheit & Datenschutz"
        description="DSGVO-konforme Einstellungen und Zugriffsverwaltung"
        icon={Shield}
      >
        <div className="space-y-4">
          <div className="flex items-center justify-between p-3 rounded-lg border">
            <div>
              <p className="font-medium">Zwei-Faktor-Authentifizierung</p>
              <p className="text-sm text-muted-foreground">
                Zusätzliche Sicherheit für alle Benutzerkonten
              </p>
            </div>
            <Button variant="outline">Aktivieren</Button>
          </div>
          <div className="flex items-center justify-between p-3 rounded-lg border">
            <div>
              <p className="font-medium">Daten exportieren</p>
              <p className="text-sm text-muted-foreground">
                Alle Firmendaten als CSV/JSON exportieren (DSGVO Art. 20)
              </p>
            </div>
            <Button variant="outline">Export starten</Button>
          </div>
          <div className="flex items-center justify-between p-3 rounded-lg border bg-red-50">
            <div>
              <p className="font-medium text-red-800">Konto löschen</p>
              <p className="text-sm text-red-600">
                Alle Daten unwiderruflich löschen (DSGVO Art. 17)
              </p>
            </div>
            <Button variant="destructive">Konto löschen</Button>
          </div>
        </div>
      </SettingsSection>
    </div>
  );
}
