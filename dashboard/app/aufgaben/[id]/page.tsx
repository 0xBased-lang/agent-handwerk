"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  Phone,
  Mail,
  MapPin,
  Clock,
  User,
  Building2,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Edit,
  Trash2,
  UserPlus,
  MessageSquare,
  FileText,
  History,
  Send,
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
import {
  Task,
  TaskHistoryEntry,
  Worker,
  Department,
  URGENCY_LABELS,
  TASK_TYPE_LABELS,
  TASK_STATUS_LABELS,
  SOURCE_TYPE_LABELS,
  TRADE_CATEGORY_LABELS,
  TaskStatus,
} from "@/types";
import {
  formatDateTime,
  formatTimeAgo,
  getUrgencyColor,
  getStatusColor,
  cn,
} from "@/lib/utils";

// Mock data
const mockTask: Task = {
  id: "1",
  tenant_id: "t1",
  job_number: "JOB-2024-0089",
  source_type: "phone",
  source_id: "call-123",
  task_type: "repairs",
  urgency: "notfall",
  trade_category: "shk",
  customer_name: "Familie Weber",
  customer_phone: "+49 7471 12345",
  customer_email: "weber@example.de",
  customer_address: "Hauptstraße 42, 72379 Hechingen",
  customer_plz: "72379",
  title: "Heizungsausfall - Keine Wärme",
  description:
    "Heizung komplett ausgefallen seit heute Morgen. Die Temperatur in der Wohnung liegt bei etwa 10°C. Der Kunde berichtet, dass die Heizung gestern Abend noch funktioniert hat. Heute Morgen war die Anlage komplett aus, kein Display, keine Anzeige. Der Sicherungskasten wurde überprüft - alle Sicherungen sind in Ordnung.",
  ai_summary:
    "Kompletter Heizungsausfall seit Morgen. Display aus trotz intakter Sicherungen. Wohnung kalt (10°C). Sofortige Untersuchung der Heizungsanlage erforderlich.",
  status: "assigned",
  routing_priority: 1,
  routing_reason: "Notfall-Routing: Heizungsausfall im Winter → Außendienst",
  assigned_department_id: "d1",
  assigned_department_name: "Außendienst",
  assigned_worker_id: "w1",
  assigned_worker_name: "Hans Müller",
  distance_from_hq_km: 12.5,
  created_at: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
  updated_at: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
};

const mockHistory: TaskHistoryEntry[] = [
  {
    id: "h1",
    task_id: "1",
    action: "Aufgabe erstellt",
    details: { source: "phone", urgency: "notfall" },
    created_at: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
  },
  {
    id: "h2",
    task_id: "1",
    action: "KI-Klassifizierung abgeschlossen",
    details: { task_type: "repairs", confidence: 0.95 },
    created_at: new Date(Date.now() - 2 * 60 * 60 * 1000 + 5000).toISOString(),
  },
  {
    id: "h3",
    task_id: "1",
    action: "Automatisch geroutet",
    details: { department: "Außendienst", reason: "Notfall-Routing" },
    created_at: new Date(Date.now() - 2 * 60 * 60 * 1000 + 10000).toISOString(),
  },
  {
    id: "h4",
    task_id: "1",
    action: "Mitarbeiter zugewiesen",
    actor_name: "System",
    details: { worker: "Hans Müller" },
    created_at: new Date(Date.now() - 1.5 * 60 * 60 * 1000).toISOString(),
  },
  {
    id: "h5",
    task_id: "1",
    action: "SMS-Benachrichtigung gesendet",
    details: { recipient: "Hans Müller", phone: "+49..." },
    created_at: new Date(Date.now() - 1.5 * 60 * 60 * 1000 + 5000).toISOString(),
  },
  {
    id: "h6",
    task_id: "1",
    action: "Status geändert",
    actor_name: "Hans Müller",
    details: { from: "new", to: "assigned" },
    created_at: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
  },
];

const mockWorkers: Worker[] = [
  {
    id: "w1",
    tenant_id: "t1",
    first_name: "Hans",
    last_name: "Müller",
    role: "worker",
    phone: "+49 7471 11111",
    trade_categories: ["shk"],
    max_tasks_per_day: 8,
    is_active: true,
    created_at: "",
    full_name: "Hans Müller",
  },
  {
    id: "w2",
    tenant_id: "t1",
    first_name: "Peter",
    last_name: "Schmidt",
    role: "worker",
    phone: "+49 7471 22222",
    trade_categories: ["shk", "sanitaer"],
    max_tasks_per_day: 10,
    is_active: true,
    created_at: "",
    full_name: "Peter Schmidt",
  },
  {
    id: "w3",
    tenant_id: "t1",
    first_name: "Klaus",
    last_name: "Weber",
    role: "worker",
    phone: "+49 7471 33333",
    trade_categories: ["elektro"],
    max_tasks_per_day: 8,
    is_active: true,
    created_at: "",
    full_name: "Klaus Weber",
  },
];

// Status Button Component
function StatusButton({
  status,
  currentStatus,
  onClick,
}: {
  status: TaskStatus;
  currentStatus: TaskStatus;
  onClick: () => void;
}) {
  const isActive = status === currentStatus;
  const config: Record<TaskStatus, { icon: typeof CheckCircle2; color: string }> = {
    new: { icon: AlertTriangle, color: "purple" },
    assigned: { icon: UserPlus, color: "blue" },
    in_progress: { icon: Clock, color: "amber" },
    completed: { icon: CheckCircle2, color: "green" },
    cancelled: { icon: XCircle, color: "gray" },
  };

  const Icon = config[status].icon;

  return (
    <Button
      variant={isActive ? "default" : "outline"}
      size="sm"
      onClick={onClick}
      className={cn(
        "gap-2",
        isActive &&
          status === "completed" &&
          "bg-green-600 hover:bg-green-700",
        isActive &&
          status === "in_progress" &&
          "bg-amber-500 hover:bg-amber-600",
        isActive && status === "cancelled" && "bg-gray-500 hover:bg-gray-600"
      )}
    >
      <Icon className="h-4 w-4" />
      {TASK_STATUS_LABELS[status]}
    </Button>
  );
}

export default function TaskDetailPage() {
  const params = useParams();
  const router = useRouter();
  const taskId = params.id as string;

  const [task, setTask] = useState<Task>(mockTask);
  const [history, setHistory] = useState<TaskHistoryEntry[]>(mockHistory);
  const [loading, setLoading] = useState(false);
  const [newNote, setNewNote] = useState("");
  const [selectedWorker, setSelectedWorker] = useState<string | undefined>(
    task.assigned_worker_id
  );

  // Update task status
  const updateStatus = async (newStatus: TaskStatus) => {
    setTask({ ...task, status: newStatus, updated_at: new Date().toISOString() });
    // In production: await apiClient.updateTaskStatus(taskId, newStatus);
  };

  // Assign worker
  const assignWorker = async (workerId: string) => {
    const worker = mockWorkers.find((w) => w.id === workerId);
    if (worker) {
      setTask({
        ...task,
        assigned_worker_id: workerId,
        assigned_worker_name: worker.full_name,
        status: task.status === "new" ? "assigned" : task.status,
        updated_at: new Date().toISOString(),
      });
      setSelectedWorker(workerId);
    }
  };

  // Add note
  const addNote = async () => {
    if (!newNote.trim()) return;
    const newEntry: TaskHistoryEntry = {
      id: `h${history.length + 1}`,
      task_id: taskId,
      action: "Notiz hinzugefügt",
      actor_name: "Admin",
      details: { note: newNote },
      created_at: new Date().toISOString(),
    };
    setHistory([newEntry, ...history]);
    setNewNote("");
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={() => router.back()}>
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold">{task.job_number}</h1>
              <Badge
                variant={task.urgency as "notfall" | "dringend" | "normal" | "routine"}
                className="text-sm"
              >
                {URGENCY_LABELS[task.urgency]}
              </Badge>
              <Badge variant={task.status as "new" | "assigned" | "in_progress" | "completed"}>
                {TASK_STATUS_LABELS[task.status]}
              </Badge>
            </div>
            <p className="text-muted-foreground mt-1">{task.title}</p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm">
            <Edit className="mr-2 h-4 w-4" />
            Bearbeiten
          </Button>
          <Button variant="destructive" size="sm">
            <Trash2 className="mr-2 h-4 w-4" />
            Löschen
          </Button>
        </div>
      </div>

      {/* Emergency Banner */}
      {task.urgency === "notfall" && task.status !== "completed" && (
        <div className="flex items-center gap-3 rounded-lg border border-red-200 bg-red-50 p-4">
          <AlertTriangle className="h-5 w-5 text-red-600" />
          <div className="flex-1">
            <p className="font-semibold text-red-800">Notfall-Aufgabe</p>
            <p className="text-sm text-red-700">
              Diese Aufgabe erfordert sofortige Bearbeitung!
            </p>
          </div>
        </div>
      )}

      {/* Main Content Grid */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Left Column - Task Details */}
        <div className="space-y-6 lg:col-span-2">
          {/* Task Info Card */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileText className="h-5 w-5" />
                Aufgabendetails
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Meta Info */}
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">
                    Aufgabentyp
                  </p>
                  <p className="mt-1">{TASK_TYPE_LABELS[task.task_type]}</p>
                </div>
                <div>
                  <p className="text-sm font-medium text-muted-foreground">
                    Gewerk
                  </p>
                  <p className="mt-1">
                    {task.trade_category
                      ? TRADE_CATEGORY_LABELS[task.trade_category]
                      : "-"}
                  </p>
                </div>
                <div>
                  <p className="text-sm font-medium text-muted-foreground">
                    Quelle
                  </p>
                  <p className="mt-1">{SOURCE_TYPE_LABELS[task.source_type]}</p>
                </div>
                <div>
                  <p className="text-sm font-medium text-muted-foreground">
                    Erstellt
                  </p>
                  <p className="mt-1">{formatDateTime(task.created_at)}</p>
                </div>
              </div>

              {/* Description */}
              <div>
                <p className="text-sm font-medium text-muted-foreground">
                  Beschreibung
                </p>
                <p className="mt-2 whitespace-pre-wrap rounded-lg bg-muted p-4 text-sm">
                  {task.description || "Keine Beschreibung vorhanden."}
                </p>
              </div>

              {/* AI Summary */}
              {task.ai_summary && (
                <div>
                  <p className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                    <span className="inline-flex h-5 w-5 items-center justify-center rounded bg-brand-100 text-xs font-bold text-brand-700">
                      KI
                    </span>
                    KI-Zusammenfassung
                  </p>
                  <p className="mt-2 rounded-lg border border-brand-200 bg-brand-50 p-4 text-sm">
                    {task.ai_summary}
                  </p>
                </div>
              )}

              {/* Routing Info */}
              {task.routing_reason && (
                <div>
                  <p className="text-sm font-medium text-muted-foreground">
                    Routing-Grund
                  </p>
                  <p className="mt-1 text-sm">{task.routing_reason}</p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Customer Info Card */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <User className="h-5 w-5" />
                Kundeninformationen
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="flex items-start gap-3">
                  <User className="h-5 w-5 text-muted-foreground mt-0.5" />
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">
                      Name
                    </p>
                    <p className="mt-1">{task.customer_name || "-"}</p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <Phone className="h-5 w-5 text-muted-foreground mt-0.5" />
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">
                      Telefon
                    </p>
                    <p className="mt-1">
                      {task.customer_phone ? (
                        <a
                          href={`tel:${task.customer_phone}`}
                          className="text-brand-600 hover:underline"
                        >
                          {task.customer_phone}
                        </a>
                      ) : (
                        "-"
                      )}
                    </p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <Mail className="h-5 w-5 text-muted-foreground mt-0.5" />
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">
                      E-Mail
                    </p>
                    <p className="mt-1">
                      {task.customer_email ? (
                        <a
                          href={`mailto:${task.customer_email}`}
                          className="text-brand-600 hover:underline"
                        >
                          {task.customer_email}
                        </a>
                      ) : (
                        "-"
                      )}
                    </p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <MapPin className="h-5 w-5 text-muted-foreground mt-0.5" />
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">
                      Adresse
                    </p>
                    <p className="mt-1">{task.customer_address || "-"}</p>
                    {task.distance_from_hq_km && (
                      <p className="text-xs text-muted-foreground">
                        ~{task.distance_from_hq_km.toFixed(1)} km entfernt
                      </p>
                    )}
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* History Card */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <History className="h-5 w-5" />
                Verlauf
              </CardTitle>
            </CardHeader>
            <CardContent>
              {/* Add Note */}
              <div className="mb-4 flex gap-2">
                <Input
                  placeholder="Notiz hinzufügen..."
                  value={newNote}
                  onChange={(e) => setNewNote(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && addNote()}
                />
                <Button onClick={addNote} disabled={!newNote.trim()}>
                  <Send className="h-4 w-4" />
                </Button>
              </div>

              {/* History Timeline */}
              <div className="space-y-4">
                {history.map((entry, index) => (
                  <div key={entry.id} className="flex gap-3">
                    <div className="relative flex flex-col items-center">
                      <div className="flex h-8 w-8 items-center justify-center rounded-full border bg-background">
                        <Clock className="h-4 w-4 text-muted-foreground" />
                      </div>
                      {index < history.length - 1 && (
                        <div className="absolute top-8 h-full w-px bg-border" />
                      )}
                    </div>
                    <div className="flex-1 pb-4">
                      <div className="flex items-center gap-2">
                        <p className="font-medium">{entry.action}</p>
                        {entry.actor_name && (
                          <span className="text-sm text-muted-foreground">
                            von {entry.actor_name}
                          </span>
                        )}
                      </div>
                      {entry.details && (
                        <p className="text-sm text-muted-foreground mt-1">
                          {Object.entries(entry.details)
                            .map(([k, v]) => `${k}: ${v}`)
                            .join(", ")}
                        </p>
                      )}
                      <p className="text-xs text-muted-foreground mt-1">
                        {formatTimeAgo(entry.created_at)}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Right Column - Actions & Assignment */}
        <div className="space-y-6">
          {/* Status Actions */}
          <Card>
            <CardHeader>
              <CardTitle>Status ändern</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="grid grid-cols-2 gap-2">
                <StatusButton
                  status="new"
                  currentStatus={task.status}
                  onClick={() => updateStatus("new")}
                />
                <StatusButton
                  status="assigned"
                  currentStatus={task.status}
                  onClick={() => updateStatus("assigned")}
                />
                <StatusButton
                  status="in_progress"
                  currentStatus={task.status}
                  onClick={() => updateStatus("in_progress")}
                />
                <StatusButton
                  status="completed"
                  currentStatus={task.status}
                  onClick={() => updateStatus("completed")}
                />
              </div>
              <div className="pt-2">
                <StatusButton
                  status="cancelled"
                  currentStatus={task.status}
                  onClick={() => updateStatus("cancelled")}
                />
              </div>
            </CardContent>
          </Card>

          {/* Assignment Card */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <UserPlus className="h-5 w-5" />
                Zuweisung
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Current Assignment */}
              {task.assigned_worker_name && (
                <div className="flex items-center gap-3 rounded-lg border p-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-full bg-brand-100 text-brand-700 font-medium">
                    {task.assigned_worker_name
                      .split(" ")
                      .map((n) => n[0])
                      .join("")}
                  </div>
                  <div>
                    <p className="font-medium">{task.assigned_worker_name}</p>
                    <p className="text-sm text-muted-foreground">
                      {task.assigned_department_name}
                    </p>
                  </div>
                </div>
              )}

              {/* Worker Selection */}
              <div>
                <label className="text-sm font-medium text-muted-foreground">
                  Mitarbeiter zuweisen
                </label>
                <Select value={selectedWorker} onValueChange={assignWorker}>
                  <SelectTrigger className="mt-1">
                    <SelectValue placeholder="Mitarbeiter auswählen" />
                  </SelectTrigger>
                  <SelectContent>
                    {mockWorkers.map((worker) => (
                      <SelectItem key={worker.id} value={worker.id}>
                        <div className="flex items-center gap-2">
                          <span>{worker.full_name}</span>
                          <span className="text-xs text-muted-foreground">
                            ({worker.trade_categories.join(", ")})
                          </span>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>

          {/* Quick Actions */}
          <Card>
            <CardHeader>
              <CardTitle>Schnellaktionen</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {task.customer_phone && (
                <Button variant="outline" className="w-full justify-start" asChild>
                  <a href={`tel:${task.customer_phone}`}>
                    <Phone className="mr-2 h-4 w-4" />
                    Kunden anrufen
                  </a>
                </Button>
              )}
              {task.customer_email && (
                <Button variant="outline" className="w-full justify-start" asChild>
                  <a href={`mailto:${task.customer_email}`}>
                    <Mail className="mr-2 h-4 w-4" />
                    E-Mail senden
                  </a>
                </Button>
              )}
              <Button variant="outline" className="w-full justify-start">
                <MessageSquare className="mr-2 h-4 w-4" />
                SMS an Mitarbeiter
              </Button>
              {task.customer_address && (
                <Button variant="outline" className="w-full justify-start" asChild>
                  <a
                    href={`https://maps.google.com/?q=${encodeURIComponent(
                      task.customer_address
                    )}`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <MapPin className="mr-2 h-4 w-4" />
                    Route planen
                  </a>
                </Button>
              )}
            </CardContent>
          </Card>

          {/* Meta Info */}
          <Card>
            <CardContent className="pt-6">
              <div className="space-y-3 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Erstellt</span>
                  <span>{formatDateTime(task.created_at)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Aktualisiert</span>
                  <span>{formatTimeAgo(task.updated_at)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Priorität</span>
                  <span>#{task.routing_priority}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">ID</span>
                  <span className="font-mono text-xs">{task.id}</span>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
