"use client";

import { useState } from "react";
import {
  Building2,
  Plus,
  Edit,
  Trash2,
  Users,
  Phone,
  Mail,
  Clock,
  ListTodo,
  MoreHorizontal,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Department,
  TASK_TYPE_LABELS,
  URGENCY_LABELS,
  TaskType,
  UrgencyLevel,
} from "@/types";
import { cn } from "@/lib/utils";

// Mock data
const mockDepartments: Department[] = [
  {
    id: "d1",
    tenant_id: "t1",
    name: "Kundendienst",
    description: "Allgemeine Kundenanfragen und Terminvereinbarungen",
    handles_task_types: ["general", "appointment", "callback"],
    handles_urgency_levels: ["normal", "routine"],
    phone: "+49 7471 12345-0",
    email: "kundendienst@firma.de",
    working_hours: { monday: "08:00-17:00", tuesday: "08:00-17:00", wednesday: "08:00-17:00", thursday: "08:00-17:00", friday: "08:00-16:00" },
    is_active: true,
    created_at: "2024-01-01",
    worker_count: 3,
    open_tasks_count: 5,
  },
  {
    id: "d2",
    tenant_id: "t1",
    name: "Außendienst",
    description: "Techniker für Vor-Ort-Einsätze und Reparaturen",
    handles_task_types: ["repairs"],
    handles_urgency_levels: ["notfall", "dringend", "normal"],
    phone: "+49 7471 12345-10",
    email: "technik@firma.de",
    working_hours: { monday: "07:00-18:00", tuesday: "07:00-18:00", wednesday: "07:00-18:00", thursday: "07:00-18:00", friday: "07:00-16:00", saturday: "08:00-12:00" },
    is_active: true,
    created_at: "2024-01-01",
    worker_count: 5,
    open_tasks_count: 12,
  },
  {
    id: "d3",
    tenant_id: "t1",
    name: "Büro/Verwaltung",
    description: "Angebote, Rechnungen und Verwaltungsaufgaben",
    handles_task_types: ["quotes", "billing"],
    handles_urgency_levels: ["normal", "routine"],
    phone: "+49 7471 12345-20",
    email: "buero@firma.de",
    working_hours: { monday: "08:00-17:00", tuesday: "08:00-17:00", wednesday: "08:00-17:00", thursday: "08:00-17:00", friday: "08:00-14:00" },
    is_active: true,
    created_at: "2024-01-01",
    worker_count: 2,
    open_tasks_count: 8,
  },
  {
    id: "d4",
    tenant_id: "t1",
    name: "Geschäftsführung",
    description: "Reklamationen und wichtige Kundenanliegen",
    handles_task_types: ["complaints"],
    handles_urgency_levels: ["notfall", "dringend"],
    phone: "+49 7471 12345-99",
    email: "geschaeftsfuehrung@firma.de",
    is_active: true,
    created_at: "2024-01-01",
    worker_count: 1,
    open_tasks_count: 2,
  },
];

// Department Card Component
function DepartmentCard({ department }: { department: Department }) {
  return (
    <Card className="task-card">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-100">
              <Building2 className="h-5 w-5 text-brand-600" />
            </div>
            <div>
              <CardTitle className="text-lg">{department.name}</CardTitle>
              <p className="text-sm text-muted-foreground">
                {department.description}
              </p>
            </div>
          </div>
          <Button variant="ghost" size="icon">
            <MoreHorizontal className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Stats */}
        <div className="grid grid-cols-2 gap-4">
          <div className="flex items-center gap-2">
            <Users className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm">
              <span className="font-medium">{department.worker_count}</span>{" "}
              Mitarbeiter
            </span>
          </div>
          <div className="flex items-center gap-2">
            <ListTodo className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm">
              <span className="font-medium">{department.open_tasks_count}</span>{" "}
              offene Aufgaben
            </span>
          </div>
        </div>

        {/* Contact */}
        {(department.phone || department.email) && (
          <div className="space-y-1">
            {department.phone && (
              <div className="flex items-center gap-2 text-sm">
                <Phone className="h-3 w-3 text-muted-foreground" />
                <a href={`tel:${department.phone}`} className="hover:underline">
                  {department.phone}
                </a>
              </div>
            )}
            {department.email && (
              <div className="flex items-center gap-2 text-sm">
                <Mail className="h-3 w-3 text-muted-foreground" />
                <a href={`mailto:${department.email}`} className="hover:underline">
                  {department.email}
                </a>
              </div>
            )}
          </div>
        )}

        {/* Task Types */}
        <div>
          <p className="text-xs font-medium text-muted-foreground mb-2">
            Bearbeitet
          </p>
          <div className="flex flex-wrap gap-1">
            {department.handles_task_types.map((type) => (
              <Badge key={type} variant="secondary" className="text-xs">
                {TASK_TYPE_LABELS[type as TaskType]}
              </Badge>
            ))}
          </div>
        </div>

        {/* Urgency Levels */}
        <div>
          <p className="text-xs font-medium text-muted-foreground mb-2">
            Dringlichkeitsstufen
          </p>
          <div className="flex flex-wrap gap-1">
            {department.handles_urgency_levels.map((level) => (
              <Badge
                key={level}
                variant={level as "notfall" | "dringend" | "normal" | "routine"}
                className="text-xs"
              >
                {URGENCY_LABELS[level as UrgencyLevel]}
              </Badge>
            ))}
          </div>
        </div>

        {/* Actions */}
        <div className="flex gap-2 pt-2 border-t">
          <Button variant="outline" size="sm" className="flex-1">
            <Edit className="mr-2 h-3 w-3" />
            Bearbeiten
          </Button>
          <Button variant="outline" size="sm">
            <Users className="h-3 w-3" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default function DepartmentsPage() {
  const [departments] = useState<Department[]>(mockDepartments);

  const totalWorkers = departments.reduce((sum, d) => sum + (d.worker_count || 0), 0);
  const totalOpenTasks = departments.reduce((sum, d) => sum + (d.open_tasks_count || 0), 0);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Abteilungen</h1>
          <p className="text-muted-foreground">
            {departments.length} Abteilungen • {totalWorkers} Mitarbeiter • {totalOpenTasks} offene Aufgaben
          </p>
        </div>
        <Button>
          <Plus className="mr-2 h-4 w-4" />
          Neue Abteilung
        </Button>
      </div>

      {/* Department Cards */}
      <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
        {departments.map((department) => (
          <DepartmentCard key={department.id} department={department} />
        ))}
      </div>
    </div>
  );
}
