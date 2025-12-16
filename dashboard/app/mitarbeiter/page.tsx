"use client";

import { useState } from "react";
import {
  Users,
  Plus,
  Edit,
  Trash2,
  Phone,
  Mail,
  Search,
  Filter,
  MoreHorizontal,
  CheckCircle2,
  XCircle,
  Building2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { Worker, TRADE_CATEGORY_LABELS, TradeCategory } from "@/types";
import { cn, getInitials } from "@/lib/utils";

// Mock data
const mockWorkers: Worker[] = [
  {
    id: "w1",
    tenant_id: "t1",
    department_id: "d2",
    first_name: "Hans",
    last_name: "Müller",
    role: "worker",
    phone: "+49 7471 11111",
    email: "hans.mueller@firma.de",
    trade_categories: ["shk"],
    certifications: ["Meister SHK", "Gasinstallateur"],
    max_tasks_per_day: 8,
    is_active: true,
    created_at: "2024-01-01",
    department_name: "Außendienst",
    current_tasks_count: 3,
    full_name: "Hans Müller",
  },
  {
    id: "w2",
    tenant_id: "t1",
    department_id: "d2",
    first_name: "Peter",
    last_name: "Schmidt",
    role: "worker",
    phone: "+49 7471 22222",
    email: "peter.schmidt@firma.de",
    trade_categories: ["shk", "sanitaer"],
    certifications: ["Geselle SHK"],
    max_tasks_per_day: 10,
    is_active: true,
    created_at: "2024-01-15",
    department_name: "Außendienst",
    current_tasks_count: 5,
    full_name: "Peter Schmidt",
  },
  {
    id: "w3",
    tenant_id: "t1",
    department_id: "d2",
    first_name: "Klaus",
    last_name: "Weber",
    role: "worker",
    phone: "+49 7471 33333",
    email: "klaus.weber@firma.de",
    trade_categories: ["elektro"],
    certifications: ["Meister Elektro"],
    max_tasks_per_day: 8,
    is_active: true,
    created_at: "2024-02-01",
    department_name: "Außendienst",
    current_tasks_count: 2,
    full_name: "Klaus Weber",
  },
  {
    id: "w4",
    tenant_id: "t1",
    department_id: "d1",
    first_name: "Maria",
    last_name: "Bauer",
    role: "admin",
    phone: "+49 7471 44444",
    email: "maria.bauer@firma.de",
    trade_categories: ["general"],
    max_tasks_per_day: 20,
    is_active: true,
    created_at: "2024-01-01",
    department_name: "Kundendienst",
    current_tasks_count: 8,
    full_name: "Maria Bauer",
  },
  {
    id: "w5",
    tenant_id: "t1",
    department_id: "d3",
    first_name: "Thomas",
    last_name: "Fischer",
    role: "admin",
    phone: "+49 7471 55555",
    email: "thomas.fischer@firma.de",
    trade_categories: ["general"],
    max_tasks_per_day: 15,
    is_active: true,
    created_at: "2024-01-01",
    department_name: "Büro/Verwaltung",
    current_tasks_count: 6,
    full_name: "Thomas Fischer",
  },
  {
    id: "w6",
    tenant_id: "t1",
    department_id: "d4",
    first_name: "Stefan",
    last_name: "Meier",
    role: "owner",
    phone: "+49 7471 99999",
    email: "stefan.meier@firma.de",
    trade_categories: ["shk", "elektro", "sanitaer", "general"],
    certifications: ["Meister SHK", "Betriebswirt"],
    max_tasks_per_day: 5,
    is_active: true,
    created_at: "2020-01-01",
    department_name: "Geschäftsführung",
    current_tasks_count: 2,
    full_name: "Stefan Meier",
  },
];

// Role Labels
const ROLE_LABELS: Record<string, string> = {
  owner: "Inhaber",
  admin: "Administrator",
  worker: "Mitarbeiter",
};

// Worker Row Component
function WorkerRow({ worker }: { worker: Worker }) {
  const workload = ((worker.current_tasks_count || 0) / worker.max_tasks_per_day) * 100;
  const workloadColor = workload > 80 ? "bg-red-500" : workload > 50 ? "bg-amber-500" : "bg-green-500";

  return (
    <tr className="border-b hover:bg-muted/50">
      <td className="px-4 py-3">
        <div className="flex items-center gap-3">
          <div
            className={cn(
              "flex h-10 w-10 items-center justify-center rounded-full text-sm font-medium",
              worker.is_active
                ? "bg-brand-100 text-brand-700"
                : "bg-gray-100 text-gray-500"
            )}
          >
            {getInitials(worker.full_name || `${worker.first_name} ${worker.last_name}`)}
          </div>
          <div>
            <p className="font-medium">{worker.full_name || `${worker.first_name} ${worker.last_name}`}</p>
            <p className="text-sm text-muted-foreground">{ROLE_LABELS[worker.role]}</p>
          </div>
        </div>
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <Building2 className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm">{worker.department_name || "-"}</span>
        </div>
      </td>
      <td className="px-4 py-3">
        <div className="flex flex-wrap gap-1">
          {worker.trade_categories.map((cat) => (
            <Badge key={cat} variant="secondary" className="text-xs">
              {TRADE_CATEGORY_LABELS[cat as TradeCategory] || cat}
            </Badge>
          ))}
        </div>
      </td>
      <td className="px-4 py-3">
        <div className="space-y-1">
          <div className="flex items-center justify-between text-sm">
            <span>{worker.current_tasks_count || 0} / {worker.max_tasks_per_day}</span>
            <span className="text-muted-foreground">{workload.toFixed(0)}%</span>
          </div>
          <div className="h-2 w-24 rounded-full bg-muted">
            <div
              className={cn("h-full rounded-full", workloadColor)}
              style={{ width: `${Math.min(workload, 100)}%` }}
            />
          </div>
        </div>
      </td>
      <td className="px-4 py-3">
        <div className="space-y-1 text-sm">
          {worker.phone && (
            <a href={`tel:${worker.phone}`} className="flex items-center gap-1 hover:underline">
              <Phone className="h-3 w-3" />
              {worker.phone}
            </a>
          )}
          {worker.email && (
            <a href={`mailto:${worker.email}`} className="flex items-center gap-1 hover:underline text-muted-foreground">
              <Mail className="h-3 w-3" />
              {worker.email}
            </a>
          )}
        </div>
      </td>
      <td className="px-4 py-3">
        {worker.is_active ? (
          <Badge variant="completed" className="gap-1">
            <CheckCircle2 className="h-3 w-3" />
            Aktiv
          </Badge>
        ) : (
          <Badge variant="cancelled" className="gap-1">
            <XCircle className="h-3 w-3" />
            Inaktiv
          </Badge>
        )}
      </td>
      <td className="px-4 py-3">
        <Button variant="ghost" size="icon">
          <MoreHorizontal className="h-4 w-4" />
        </Button>
      </td>
    </tr>
  );
}

export default function WorkersPage() {
  const [workers] = useState<Worker[]>(mockWorkers);
  const [search, setSearch] = useState("");
  const [departmentFilter, setDepartmentFilter] = useState<string>("all");

  const filteredWorkers = workers.filter((worker) => {
    const matchesSearch =
      !search ||
      worker.first_name.toLowerCase().includes(search.toLowerCase()) ||
      worker.last_name.toLowerCase().includes(search.toLowerCase()) ||
      worker.email?.toLowerCase().includes(search.toLowerCase());
    const matchesDepartment =
      departmentFilter === "all" || worker.department_id === departmentFilter;
    return matchesSearch && matchesDepartment;
  });

  const activeWorkers = workers.filter((w) => w.is_active).length;
  const totalCapacity = workers.reduce((sum, w) => sum + w.max_tasks_per_day, 0);
  const currentLoad = workers.reduce((sum, w) => sum + (w.current_tasks_count || 0), 0);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Mitarbeiter</h1>
          <p className="text-muted-foreground">
            {activeWorkers} aktive Mitarbeiter • Auslastung: {currentLoad}/{totalCapacity} Aufgaben ({((currentLoad/totalCapacity)*100).toFixed(0)}%)
          </p>
        </div>
        <Button>
          <Plus className="mr-2 h-4 w-4" />
          Neuer Mitarbeiter
        </Button>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="p-4">
          <div className="flex gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Suchen nach Name oder E-Mail..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-9"
              />
            </div>
            <Select value={departmentFilter} onValueChange={setDepartmentFilter}>
              <SelectTrigger className="w-48">
                <SelectValue placeholder="Abteilung" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Alle Abteilungen</SelectItem>
                <SelectItem value="d1">Kundendienst</SelectItem>
                <SelectItem value="d2">Außendienst</SelectItem>
                <SelectItem value="d3">Büro/Verwaltung</SelectItem>
                <SelectItem value="d4">Geschäftsführung</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Workers Table */}
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="px-4 py-3 text-left text-sm font-medium">Mitarbeiter</th>
                <th className="px-4 py-3 text-left text-sm font-medium">Abteilung</th>
                <th className="px-4 py-3 text-left text-sm font-medium">Gewerke</th>
                <th className="px-4 py-3 text-left text-sm font-medium">Auslastung</th>
                <th className="px-4 py-3 text-left text-sm font-medium">Kontakt</th>
                <th className="px-4 py-3 text-left text-sm font-medium">Status</th>
                <th className="w-12 px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {filteredWorkers.map((worker) => (
                <WorkerRow key={worker.id} worker={worker} />
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
