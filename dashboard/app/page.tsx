"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Clock,
  CheckCircle2,
  ListTodo,
  TrendingUp,
  Phone,
  Mail,
  MessageSquare,
  ArrowUpRight,
  ArrowDownRight,
  Users,
  Building2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DashboardStats,
  Task,
  URGENCY_LABELS,
  TASK_TYPE_LABELS,
  TaskStatus,
} from "@/types";
import {
  formatTimeAgo,
  getUrgencyColor,
  getSourceColor,
  getSourceTypeLabel,
  formatPercentage,
  cn,
} from "@/lib/utils";

// Mock data for demonstration - in production, fetch from API
const mockStats: DashboardStats = {
  total_tasks_today: 24,
  open_tasks: 12,
  open_emergencies: 2,
  in_progress_tasks: 8,
  completed_today: 14,
  completion_rate: 58.3,
  average_response_time_minutes: 23,
  tasks_by_type: {
    repairs: 8,
    quotes: 6,
    complaints: 2,
    billing: 3,
    appointment: 4,
    general: 1,
    spam: 0,
    parts: 0,
    callback: 0,
  },
  tasks_by_urgency: {
    notfall: 2,
    dringend: 4,
    normal: 10,
    routine: 8,
  },
  tasks_by_status: {
    new: 4,
    assigned: 3,
    in_progress: 8,
    completed: 9,
    cancelled: 0,
  },
  tasks_by_source: {
    phone: 12,
    email: 8,
    chat: 3,
    form: 1,
    whatsapp: 0,
  },
  tasks_trend_7_days: [
    { date: "2024-12-10", count: 18 },
    { date: "2024-12-11", count: 22 },
    { date: "2024-12-12", count: 15 },
    { date: "2024-12-13", count: 28 },
    { date: "2024-12-14", count: 12 },
    { date: "2024-12-15", count: 20 },
    { date: "2024-12-16", count: 24 },
  ],
};

const mockRecentTasks: Task[] = [
  {
    id: "1",
    tenant_id: "t1",
    job_number: "JOB-2024-0089",
    source_type: "phone",
    task_type: "repairs",
    urgency: "notfall",
    trade_category: "shk",
    customer_name: "Familie Weber",
    customer_phone: "+49 7471 12345",
    title: "Heizungsausfall - Keine Wärme",
    description: "Heizung komplett ausgefallen seit heute Morgen",
    status: "new",
    routing_priority: 1,
    created_at: new Date(Date.now() - 15 * 60 * 1000).toISOString(),
    updated_at: new Date(Date.now() - 15 * 60 * 1000).toISOString(),
  },
  {
    id: "2",
    tenant_id: "t1",
    job_number: "JOB-2024-0088",
    source_type: "email",
    task_type: "quotes",
    urgency: "normal",
    trade_category: "elektro",
    customer_name: "Firma Schmidt GmbH",
    customer_email: "info@schmidt.de",
    title: "Angebot für Elektroinstallation",
    description: "Anfrage für Neuinstallation im Bürogebäude",
    status: "assigned",
    routing_priority: 3,
    assigned_worker_name: "Hans Müller",
    created_at: new Date(Date.now() - 45 * 60 * 1000).toISOString(),
    updated_at: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
  },
  {
    id: "3",
    tenant_id: "t1",
    job_number: "JOB-2024-0087",
    source_type: "phone",
    task_type: "repairs",
    urgency: "dringend",
    trade_category: "sanitaer",
    customer_name: "Herr Bauer",
    customer_phone: "+49 7471 54321",
    title: "Wasserrohrbruch im Keller",
    description: "Wasser läuft aus Rohr im Keller",
    status: "in_progress",
    routing_priority: 2,
    assigned_worker_name: "Peter Schmidt",
    created_at: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
    updated_at: new Date(Date.now() - 1 * 60 * 60 * 1000).toISOString(),
  },
  {
    id: "4",
    tenant_id: "t1",
    job_number: "JOB-2024-0086",
    source_type: "chat",
    task_type: "appointment",
    urgency: "routine",
    customer_name: "Frau Meier",
    title: "Terminanfrage für Wartung",
    status: "completed",
    routing_priority: 5,
    completed_at: new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString(),
    created_at: new Date(Date.now() - 5 * 60 * 60 * 1000).toISOString(),
    updated_at: new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString(),
  },
];

// KPI Card Component
function KPICard({
  title,
  value,
  icon: Icon,
  trend,
  trendValue,
  description,
  variant = "default",
  href,
}: {
  title: string;
  value: number | string;
  icon: React.ComponentType<{ className?: string }>;
  trend?: "up" | "down" | "neutral";
  trendValue?: string;
  description?: string;
  variant?: "default" | "emergency" | "success" | "warning";
  href?: string;
}) {
  const variantStyles = {
    default: "border-l-brand-500",
    emergency: "border-l-red-500 bg-red-50/50",
    success: "border-l-green-500 bg-green-50/50",
    warning: "border-l-orange-500 bg-orange-50/50",
  };

  const iconStyles = {
    default: "text-brand-500 bg-brand-100",
    emergency: "text-red-600 bg-red-100",
    success: "text-green-600 bg-green-100",
    warning: "text-orange-600 bg-orange-100",
  };

  const content = (
    <Card
      className={cn(
        "border-l-4 transition-all hover:shadow-md",
        variantStyles[variant],
        href && "cursor-pointer"
      )}
    >
      <CardContent className="p-6">
        <div className="flex items-start justify-between">
          <div className="space-y-2">
            <p className="text-sm font-medium text-muted-foreground">{title}</p>
            <p className="text-3xl font-bold">{value}</p>
            {(trend || description) && (
              <div className="flex items-center gap-2">
                {trend && trendValue && (
                  <span
                    className={cn(
                      "flex items-center gap-0.5 text-xs font-medium",
                      trend === "up" && "text-green-600",
                      trend === "down" && "text-red-600",
                      trend === "neutral" && "text-muted-foreground"
                    )}
                  >
                    {trend === "up" && <ArrowUpRight className="h-3 w-3" />}
                    {trend === "down" && <ArrowDownRight className="h-3 w-3" />}
                    {trendValue}
                  </span>
                )}
                {description && (
                  <span className="text-xs text-muted-foreground">
                    {description}
                  </span>
                )}
              </div>
            )}
          </div>
          <div
            className={cn(
              "flex h-12 w-12 items-center justify-center rounded-lg",
              iconStyles[variant]
            )}
          >
            <Icon className="h-6 w-6" />
          </div>
        </div>
      </CardContent>
    </Card>
  );

  if (href) {
    return <Link href={href}>{content}</Link>;
  }

  return content;
}

// Source Icon
function SourceIcon({ source }: { source: string }) {
  switch (source) {
    case "phone":
      return <Phone className="h-4 w-4" />;
    case "email":
      return <Mail className="h-4 w-4" />;
    case "chat":
    case "whatsapp":
      return <MessageSquare className="h-4 w-4" />;
    default:
      return <ListTodo className="h-4 w-4" />;
  }
}

// Status Badge Component
function StatusBadge({ status }: { status: TaskStatus }) {
  const statusConfig = {
    new: { label: "Neu", variant: "new" as const },
    assigned: { label: "Zugewiesen", variant: "assigned" as const },
    in_progress: { label: "In Bearbeitung", variant: "in_progress" as const },
    completed: { label: "Erledigt", variant: "completed" as const },
    cancelled: { label: "Storniert", variant: "cancelled" as const },
  };
  const config = statusConfig[status];
  return <Badge variant={config.variant}>{config.label}</Badge>;
}

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats>(mockStats);
  const [recentTasks, setRecentTasks] = useState<Task[]>(mockRecentTasks);
  const [loading, setLoading] = useState(false);

  // In production, fetch real data from API
  useEffect(() => {
    // Simulate API call
    const fetchData = async () => {
      setLoading(true);
      try {
        // const response = await apiClient.getDashboardStats();
        // setStats(response);
        // const tasksResponse = await apiClient.getTasks({ limit: 5 });
        // setRecentTasks(tasksResponse.items);
      } catch (error) {
        console.error("Failed to fetch dashboard data:", error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  return (
    <div className="space-y-6">
      {/* Emergency Alert Banner */}
      {stats.open_emergencies > 0 && (
        <div className="flex items-center gap-3 rounded-lg border border-red-200 bg-red-50 p-4 emergency-pulse">
          <AlertTriangle className="h-5 w-5 text-red-600" />
          <div className="flex-1">
            <p className="font-semibold text-red-800">
              {stats.open_emergencies} offene{" "}
              {stats.open_emergencies === 1 ? "Notfall" : "Notfälle"}!
            </p>
            <p className="text-sm text-red-700">
              Sofortige Bearbeitung erforderlich
            </p>
          </div>
          <Link href="/aufgaben?urgency=notfall">
            <Button variant="notfall" size="sm">
              Jetzt bearbeiten
            </Button>
          </Link>
        </div>
      )}

      {/* KPI Cards Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <KPICard
          title="Aufgaben heute"
          value={stats.total_tasks_today}
          icon={ListTodo}
          trend="up"
          trendValue="+12%"
          description="vs. gestern"
          href="/aufgaben"
        />
        <KPICard
          title="Offene Notfälle"
          value={stats.open_emergencies}
          icon={AlertTriangle}
          variant={stats.open_emergencies > 0 ? "emergency" : "default"}
          description="Sofort bearbeiten"
          href="/aufgaben?urgency=notfall"
        />
        <KPICard
          title="In Bearbeitung"
          value={stats.in_progress_tasks}
          icon={Clock}
          variant="warning"
          description="Mitarbeiter aktiv"
          href="/aufgaben?status=in_progress"
        />
        <KPICard
          title="Erledigungsrate"
          value={formatPercentage(stats.completion_rate)}
          icon={CheckCircle2}
          trend={stats.completion_rate > 50 ? "up" : "down"}
          trendValue={stats.completion_rate > 50 ? "+5%" : "-3%"}
          variant={stats.completion_rate > 50 ? "success" : "default"}
        />
      </div>

      {/* Secondary Stats */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Durchschn. Reaktionszeit
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">
              {stats.average_response_time_minutes} Min.
            </p>
            <p className="text-xs text-muted-foreground">Ziel: 30 Min.</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Heute erledigt
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{stats.completed_today}</p>
            <p className="text-xs text-muted-foreground">
              von {stats.total_tasks_today} Aufgaben
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Offene Aufgaben
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{stats.open_tasks}</p>
            <p className="text-xs text-muted-foreground">Warten auf Bearbeitung</p>
          </CardContent>
        </Card>
      </div>

      {/* Main Content Grid */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Recent Tasks */}
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Aktuelle Aufgaben</CardTitle>
            <Link href="/aufgaben">
              <Button variant="ghost" size="sm">
                Alle anzeigen
                <ArrowUpRight className="ml-1 h-4 w-4" />
              </Button>
            </Link>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {recentTasks.map((task) => (
                <Link
                  key={task.id}
                  href={`/aufgaben/${task.id}`}
                  className="block"
                >
                  <div className="task-card flex items-center gap-4 rounded-lg border p-4">
                    {/* Urgency Indicator */}
                    <div
                      className={cn(
                        "h-10 w-1 rounded-full",
                        task.urgency === "notfall" && "bg-red-500",
                        task.urgency === "dringend" && "bg-orange-500",
                        task.urgency === "normal" && "bg-blue-500",
                        task.urgency === "routine" && "bg-gray-400"
                      )}
                    />

                    {/* Source Icon */}
                    <div
                      className={cn(
                        "flex h-10 w-10 items-center justify-center rounded-lg",
                        getSourceColor(task.source_type)
                      )}
                    >
                      <SourceIcon source={task.source_type} />
                    </div>

                    {/* Task Info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="font-medium truncate">{task.title}</p>
                        <Badge
                          variant={task.urgency as "notfall" | "dringend" | "normal" | "routine"}
                          className="shrink-0"
                        >
                          {URGENCY_LABELS[task.urgency]}
                        </Badge>
                      </div>
                      <div className="flex items-center gap-2 mt-1">
                        <span className="text-sm text-muted-foreground">
                          {task.customer_name || "Unbekannt"}
                        </span>
                        <span className="text-muted-foreground">•</span>
                        <span className="text-sm text-muted-foreground">
                          {TASK_TYPE_LABELS[task.task_type]}
                        </span>
                        <span className="text-muted-foreground">•</span>
                        <span className="text-sm text-muted-foreground">
                          {formatTimeAgo(task.created_at)}
                        </span>
                      </div>
                    </div>

                    {/* Status & Assignee */}
                    <div className="text-right shrink-0">
                      <StatusBadge status={task.status} />
                      {task.assigned_worker_name && (
                        <p className="text-xs text-muted-foreground mt-1">
                          {task.assigned_worker_name}
                        </p>
                      )}
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Tasks by Source */}
        <Card>
          <CardHeader>
            <CardTitle>Aufgaben nach Quelle</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {Object.entries(stats.tasks_by_source)
                .filter(([, count]) => count > 0)
                .sort(([, a], [, b]) => b - a)
                .map(([source, count]) => (
                  <div key={source} className="flex items-center gap-3">
                    <div
                      className={cn(
                        "flex h-9 w-9 items-center justify-center rounded-lg",
                        getSourceColor(source as Task["source_type"])
                      )}
                    >
                      <SourceIcon source={source} />
                    </div>
                    <div className="flex-1">
                      <p className="text-sm font-medium">
                        {getSourceTypeLabel(source as Task["source_type"])}
                      </p>
                      <div className="mt-1 h-2 w-full rounded-full bg-muted">
                        <div
                          className="h-full rounded-full bg-brand-500"
                          style={{
                            width: `${(count / stats.total_tasks_today) * 100}%`,
                          }}
                        />
                      </div>
                    </div>
                    <p className="text-sm font-bold">{count}</p>
                  </div>
                ))}
            </div>

            {/* Quick Links */}
            <div className="mt-6 grid grid-cols-2 gap-2">
              <Link href="/abteilungen">
                <Button variant="outline" size="sm" className="w-full">
                  <Building2 className="mr-1 h-4 w-4" />
                  Abteilungen
                </Button>
              </Link>
              <Link href="/mitarbeiter">
                <Button variant="outline" size="sm" className="w-full">
                  <Users className="mr-1 h-4 w-4" />
                  Mitarbeiter
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Tasks by Type */}
      <Card>
        <CardHeader>
          <CardTitle>Aufgaben nach Typ (Heute)</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-5">
            {Object.entries(stats.tasks_by_type)
              .filter(([, count]) => count > 0)
              .sort(([, a], [, b]) => b - a)
              .map(([type, count]) => (
                <Link
                  key={type}
                  href={`/aufgaben?task_type=${type}`}
                  className="block"
                >
                  <div className="rounded-lg border p-4 text-center transition-colors hover:bg-accent">
                    <p className="text-2xl font-bold">{count}</p>
                    <p className="text-sm text-muted-foreground">
                      {TASK_TYPE_LABELS[type as Task["task_type"]]}
                    </p>
                  </div>
                </Link>
              ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
