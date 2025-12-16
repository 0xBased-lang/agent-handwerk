"use client";

import { useState } from "react";
import {
  Route,
  Plus,
  Edit,
  Trash2,
  GripVertical,
  CheckCircle2,
  XCircle,
  ArrowRight,
  Bell,
  Clock,
  AlertTriangle,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  RoutingRule,
  TASK_TYPE_LABELS,
  URGENCY_LABELS,
  TaskType,
  UrgencyLevel,
} from "@/types";
import { cn } from "@/lib/utils";

// Mock data
const mockRules: RoutingRule[] = [
  {
    id: "r1",
    tenant_id: "t1",
    name: "Notfall → Außendienst",
    priority: 1,
    conditions: { urgency: "notfall", task_type: "repairs" },
    route_to_department_id: "d2",
    route_to_department_name: "Außendienst",
    escalate_after_minutes: 15,
    send_notification: true,
    is_active: true,
    created_at: "2024-01-01",
  },
  {
    id: "r2",
    tenant_id: "t1",
    name: "Reklamationen → Geschäftsführung",
    priority: 2,
    conditions: { task_type: "complaints" },
    route_to_department_id: "d4",
    route_to_department_name: "Geschäftsführung",
    escalate_after_minutes: 30,
    send_notification: true,
    is_active: true,
    created_at: "2024-01-01",
  },
  {
    id: "r3",
    tenant_id: "t1",
    name: "Angebote → Büro",
    priority: 3,
    conditions: { task_type: "quotes" },
    route_to_department_id: "d3",
    route_to_department_name: "Büro/Verwaltung",
    send_notification: false,
    is_active: true,
    created_at: "2024-01-01",
  },
  {
    id: "r4",
    tenant_id: "t1",
    name: "Rechnungsfragen → Büro",
    priority: 4,
    conditions: { task_type: "billing" },
    route_to_department_id: "d3",
    route_to_department_name: "Büro/Verwaltung",
    send_notification: false,
    is_active: true,
    created_at: "2024-01-01",
  },
  {
    id: "r5",
    tenant_id: "t1",
    name: "Dringende Reparaturen → Außendienst",
    priority: 5,
    conditions: { urgency: "dringend", task_type: "repairs" },
    route_to_department_id: "d2",
    route_to_department_name: "Außendienst",
    escalate_after_minutes: 60,
    send_notification: true,
    is_active: true,
    created_at: "2024-01-01",
  },
  {
    id: "r6",
    tenant_id: "t1",
    name: "Termine → Kundendienst",
    priority: 6,
    conditions: { task_type: "appointment" },
    route_to_department_id: "d1",
    route_to_department_name: "Kundendienst",
    send_notification: false,
    is_active: true,
    created_at: "2024-01-01",
  },
  {
    id: "r7",
    tenant_id: "t1",
    name: "Standard-Reparaturen → Außendienst",
    priority: 7,
    conditions: { task_type: "repairs", urgency: ["normal", "routine"] },
    route_to_department_id: "d2",
    route_to_department_name: "Außendienst",
    send_notification: false,
    is_active: true,
    created_at: "2024-01-01",
  },
  {
    id: "r8",
    tenant_id: "t1",
    name: "Fallback → Kundendienst",
    priority: 99,
    conditions: {},
    route_to_department_id: "d1",
    route_to_department_name: "Kundendienst",
    send_notification: false,
    is_active: true,
    created_at: "2024-01-01",
  },
];

// Rule Card Component
function RuleCard({
  rule,
  onToggle,
}: {
  rule: RoutingRule;
  onToggle: (id: string) => void;
}) {
  const conditions = rule.conditions;
  const hasConditions = Object.keys(conditions).length > 0;

  return (
    <Card className={cn("task-card", !rule.is_active && "opacity-60")}>
      <CardContent className="p-4">
        <div className="flex items-start gap-4">
          {/* Drag Handle */}
          <div className="flex flex-col items-center gap-1 cursor-grab">
            <GripVertical className="h-5 w-5 text-muted-foreground" />
            <span className="text-xs font-medium text-muted-foreground">
              #{rule.priority}
            </span>
          </div>

          {/* Rule Content */}
          <div className="flex-1 space-y-3">
            {/* Header */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <h3 className="font-medium">{rule.name}</h3>
                {!rule.is_active && (
                  <Badge variant="cancelled">Deaktiviert</Badge>
                )}
              </div>
              <div className="flex items-center gap-2">
                {rule.send_notification && (
                  <Badge variant="secondary" className="gap-1">
                    <Bell className="h-3 w-3" />
                    SMS
                  </Badge>
                )}
                {rule.escalate_after_minutes && (
                  <Badge variant="secondary" className="gap-1">
                    <Clock className="h-3 w-3" />
                    {rule.escalate_after_minutes} Min.
                  </Badge>
                )}
              </div>
            </div>

            {/* Conditions → Target */}
            <div className="flex items-center gap-3 text-sm">
              {/* Conditions */}
              <div className="flex flex-wrap gap-1">
                {hasConditions ? (
                  <>
                    {conditions.task_type && (
                      <Badge variant="outline">
                        {Array.isArray(conditions.task_type)
                          ? conditions.task_type
                              .map((t) => TASK_TYPE_LABELS[t as TaskType])
                              .join(", ")
                          : TASK_TYPE_LABELS[conditions.task_type as TaskType]}
                      </Badge>
                    )}
                    {conditions.urgency && (
                      <Badge
                        variant={
                          Array.isArray(conditions.urgency)
                            ? "outline"
                            : (conditions.urgency as "notfall" | "dringend" | "normal" | "routine")
                        }
                      >
                        {Array.isArray(conditions.urgency)
                          ? conditions.urgency
                              .map((u) => URGENCY_LABELS[u as UrgencyLevel])
                              .join(", ")
                          : URGENCY_LABELS[conditions.urgency as UrgencyLevel]}
                      </Badge>
                    )}
                  </>
                ) : (
                  <Badge variant="outline">Alle Aufgaben</Badge>
                )}
              </div>

              <ArrowRight className="h-4 w-4 text-muted-foreground shrink-0" />

              {/* Target */}
              <div className="flex items-center gap-2">
                <Badge variant="default">
                  {rule.route_to_department_name || rule.route_to_worker_name}
                </Badge>
              </div>
            </div>

            {/* Actions */}
            <div className="flex gap-2 pt-2 border-t">
              <Button variant="outline" size="sm">
                <Edit className="mr-2 h-3 w-3" />
                Bearbeiten
              </Button>
              <Button
                variant={rule.is_active ? "outline" : "default"}
                size="sm"
                onClick={() => onToggle(rule.id)}
              >
                {rule.is_active ? (
                  <>
                    <XCircle className="mr-2 h-3 w-3" />
                    Deaktivieren
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="mr-2 h-3 w-3" />
                    Aktivieren
                  </>
                )}
              </Button>
              <Button variant="ghost" size="sm" className="text-destructive">
                <Trash2 className="h-3 w-3" />
              </Button>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function RoutingRulesPage() {
  const [rules, setRules] = useState<RoutingRule[]>(mockRules);

  const toggleRule = (id: string) => {
    setRules(
      rules.map((rule) =>
        rule.id === id ? { ...rule, is_active: !rule.is_active } : rule
      )
    );
  };

  const activeRules = rules.filter((r) => r.is_active).length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Routing-Regeln</h1>
          <p className="text-muted-foreground">
            {activeRules} von {rules.length} Regeln aktiv • Regeln werden von oben nach unten ausgewertet
          </p>
        </div>
        <Button>
          <Plus className="mr-2 h-4 w-4" />
          Neue Regel
        </Button>
      </div>

      {/* Info Banner */}
      <Card className="bg-blue-50 border-blue-200">
        <CardContent className="p-4">
          <div className="flex gap-3">
            <AlertTriangle className="h-5 w-5 text-blue-600 shrink-0" />
            <div>
              <p className="font-medium text-blue-900">Wie funktioniert das Routing?</p>
              <p className="text-sm text-blue-700 mt-1">
                Eingehende Aufgaben werden von oben nach unten gegen die Regeln geprüft.
                Die erste passende Regel bestimmt die Zuweisung. Ziehen Sie Regeln per
                Drag & Drop, um die Priorität zu ändern. Die letzte Regel sollte als
                Fallback für alle nicht zugeordneten Aufgaben dienen.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Rules List */}
      <div className="space-y-3">
        {rules
          .sort((a, b) => a.priority - b.priority)
          .map((rule) => (
            <RuleCard key={rule.id} rule={rule} onToggle={toggleRule} />
          ))}
      </div>
    </div>
  );
}
