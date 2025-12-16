"use client";

import { useState, useMemo, Suspense } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { useJobs } from "@/hooks/use-jobs";
import { apiClient } from "@/lib/api-client";
import {
  Search,
  Filter,
  SlidersHorizontal,
  Phone,
  Mail,
  MessageSquare,
  AlertTriangle,
  Clock,
  CheckCircle2,
  XCircle,
  ChevronDown,
  ChevronUp,
  MoreHorizontal,
  Eye,
  UserPlus,
  Trash2,
  RefreshCw,
  Download,
  Plus,
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
  TaskFilters,
  UrgencyLevel,
  TaskType,
  TaskStatus,
  SourceType,
  URGENCY_LABELS,
  TASK_TYPE_LABELS,
  TASK_STATUS_LABELS,
  SOURCE_TYPE_LABELS,
} from "@/types";
import {
  formatDateTime,
  formatTimeAgo,
  getUrgencyColor,
  getStatusColor,
  getSourceColor,
  cn,
} from "@/lib/utils";

// Mock data - in production, fetch from API
const mockTasks: Task[] = [
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
    customer_plz: "72379",
    title: "Heizungsausfall - Keine Wärme",
    description: "Heizung komplett ausgefallen seit heute Morgen. Temperatur in der Wohnung bei 10°C.",
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
    customer_plz: "72336",
    title: "Angebot für Elektroinstallation im Bürogebäude",
    description: "Anfrage für komplette Neuinstallation der Elektrik im neuen Bürogebäude.",
    status: "assigned",
    routing_priority: 3,
    assigned_worker_name: "Hans Müller",
    assigned_department_name: "Büro",
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
    customer_plz: "72764",
    title: "Wasserrohrbruch im Keller",
    description: "Wasser läuft aus Rohr im Keller. Haupthahn wurde abgedreht.",
    status: "in_progress",
    routing_priority: 2,
    assigned_worker_name: "Peter Schmidt",
    assigned_department_name: "Außendienst",
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
    customer_email: "meier@web.de",
    title: "Terminanfrage für Wartung",
    description: "Jährliche Heizungswartung, keine Eile.",
    status: "completed",
    routing_priority: 5,
    assigned_worker_name: "Klaus Weber",
    completed_at: new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString(),
    created_at: new Date(Date.now() - 5 * 60 * 60 * 1000).toISOString(),
    updated_at: new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString(),
  },
  {
    id: "5",
    tenant_id: "t1",
    job_number: "JOB-2024-0085",
    source_type: "email",
    task_type: "complaints",
    urgency: "dringend",
    customer_name: "Herr Hoffmann",
    customer_phone: "+49 7471 98765",
    title: "Reklamation: Undichte Leitung nach Reparatur",
    description: "Nach der Reparatur letzte Woche ist die Leitung wieder undicht.",
    status: "assigned",
    routing_priority: 2,
    assigned_worker_name: "Hans Müller",
    assigned_department_name: "Geschäftsführung",
    created_at: new Date(Date.now() - 4 * 60 * 60 * 1000).toISOString(),
    updated_at: new Date(Date.now() - 3.5 * 60 * 60 * 1000).toISOString(),
  },
  {
    id: "6",
    tenant_id: "t1",
    job_number: "JOB-2024-0084",
    source_type: "phone",
    task_type: "billing",
    urgency: "normal",
    customer_name: "Firma ABC GmbH",
    customer_email: "rechnung@abc.de",
    title: "Frage zur Rechnung #2024-456",
    description: "Rückfrage zur Position 3 auf der Rechnung.",
    status: "new",
    routing_priority: 4,
    created_at: new Date(Date.now() - 6 * 60 * 60 * 1000).toISOString(),
    updated_at: new Date(Date.now() - 6 * 60 * 60 * 1000).toISOString(),
  },
];

// Source Icon Component
function SourceIcon({ source }: { source: SourceType }) {
  switch (source) {
    case "phone":
      return <Phone className="h-4 w-4" />;
    case "email":
      return <Mail className="h-4 w-4" />;
    case "chat":
    case "whatsapp":
      return <MessageSquare className="h-4 w-4" />;
    default:
      return <Mail className="h-4 w-4" />;
  }
}

// Status Icon Component
function StatusIcon({ status }: { status: TaskStatus }) {
  switch (status) {
    case "new":
      return <AlertTriangle className="h-4 w-4 text-purple-500" />;
    case "assigned":
      return <UserPlus className="h-4 w-4 text-blue-500" />;
    case "in_progress":
      return <Clock className="h-4 w-4 text-amber-500" />;
    case "completed":
      return <CheckCircle2 className="h-4 w-4 text-green-500" />;
    case "cancelled":
      return <XCircle className="h-4 w-4 text-gray-500" />;
  }
}

// Filter Chip Component
function FilterChip({
  label,
  onRemove,
}: {
  label: string;
  onRemove: () => void;
}) {
  return (
    <div className="flex items-center gap-1 rounded-full bg-brand-100 px-2.5 py-1 text-xs font-medium text-brand-700">
      {label}
      <button
        onClick={onRemove}
        className="ml-1 rounded-full p-0.5 hover:bg-brand-200"
      >
        <XCircle className="h-3 w-3" />
      </button>
    </div>
  );
}

function TasksPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  // Filter state
  const [search, setSearch] = useState(searchParams.get("search") || "");
  const [statusFilter, setStatusFilter] = useState<TaskStatus | "all">(
    (searchParams.get("status") as TaskStatus) || "all"
  );
  const [urgencyFilter, setUrgencyFilter] = useState<UrgencyLevel | "all">(
    (searchParams.get("urgency") as UrgencyLevel) || "all"
  );
  const [typeFilter, setTypeFilter] = useState<TaskType | "all">(
    (searchParams.get("task_type") as TaskType) || "all"
  );
  const [sourceFilter, setSourceFilter] = useState<SourceType | "all">(
    (searchParams.get("source") as SourceType) || "all"
  );

  // Sort state
  const [sortField, setSortField] = useState<keyof Task>("created_at");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");

  // Tasks state - use API or fallback to mock data
  const [showFilters, setShowFilters] = useState(false);

  // Build filters from state
  const apiFilters = useMemo(() => {
    const filters: TaskFilters = {};
    if (statusFilter !== "all") filters.status = [statusFilter];
    if (urgencyFilter !== "all") filters.urgency = [urgencyFilter];
    if (typeFilter !== "all") filters.task_type = [typeFilter];
    if (sourceFilter !== "all") filters.source_type = [sourceFilter];
    if (search) filters.search = search;
    return filters;
  }, [statusFilter, urgencyFilter, typeFilter, sourceFilter, search]);

  // Fetch tasks from API
  const { data: apiData, isLoading: loading, refetch } = useJobs(apiFilters);

  // Use API data or fallback to mock data
  const tasks = apiData?.items ?? mockTasks;

  // Filter and sort tasks
  const filteredTasks = useMemo(() => {
    let result = [...tasks];

    // Apply search filter
    if (search) {
      const searchLower = search.toLowerCase();
      result = result.filter(
        (task) =>
          task.title.toLowerCase().includes(searchLower) ||
          task.customer_name?.toLowerCase().includes(searchLower) ||
          task.job_number?.toLowerCase().includes(searchLower) ||
          task.description?.toLowerCase().includes(searchLower)
      );
    }

    // Apply status filter
    if (statusFilter !== "all") {
      result = result.filter((task) => task.status === statusFilter);
    }

    // Apply urgency filter
    if (urgencyFilter !== "all") {
      result = result.filter((task) => task.urgency === urgencyFilter);
    }

    // Apply type filter
    if (typeFilter !== "all") {
      result = result.filter((task) => task.task_type === typeFilter);
    }

    // Apply source filter
    if (sourceFilter !== "all") {
      result = result.filter((task) => task.source_type === sourceFilter);
    }

    // Apply sorting
    result.sort((a, b) => {
      let aVal = a[sortField];
      let bVal = b[sortField];

      // Handle null/undefined
      if (aVal === null || aVal === undefined) return 1;
      if (bVal === null || bVal === undefined) return -1;

      // Compare
      if (typeof aVal === "string" && typeof bVal === "string") {
        return sortDirection === "asc"
          ? aVal.localeCompare(bVal)
          : bVal.localeCompare(aVal);
      }

      return sortDirection === "asc"
        ? (aVal as number) - (bVal as number)
        : (bVal as number) - (aVal as number);
    });

    return result;
  }, [tasks, search, statusFilter, urgencyFilter, typeFilter, sourceFilter, sortField, sortDirection]);

  // Active filter count
  const activeFilterCount = [
    statusFilter !== "all",
    urgencyFilter !== "all",
    typeFilter !== "all",
    sourceFilter !== "all",
  ].filter(Boolean).length;

  // Clear all filters
  const clearFilters = () => {
    setSearch("");
    setStatusFilter("all");
    setUrgencyFilter("all");
    setTypeFilter("all");
    setSourceFilter("all");
  };

  // Toggle sort
  const toggleSort = (field: keyof Task) => {
    if (sortField === field) {
      setSortDirection(sortDirection === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortDirection("desc");
    }
  };

  // Sort indicator
  const SortIndicator = ({ field }: { field: keyof Task }) => {
    if (sortField !== field) return null;
    return sortDirection === "asc" ? (
      <ChevronUp className="h-4 w-4" />
    ) : (
      <ChevronDown className="h-4 w-4" />
    );
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold">Aufgaben</h1>
          <p className="text-muted-foreground">
            {filteredTasks.length} von {tasks.length} Aufgaben
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm">
            <Download className="mr-2 h-4 w-4" />
            Exportieren
          </Button>
          <Link href="/aufgaben/neu">
            <Button size="sm">
              <Plus className="mr-2 h-4 w-4" />
              Neue Aufgabe
            </Button>
          </Link>
        </div>
      </div>

      {/* Search and Filters */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col gap-4">
            {/* Search Bar */}
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="Suchen nach Titel, Kunde, Auftragsnummer..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="pl-9"
                />
              </div>
              <Button
                variant={showFilters ? "secondary" : "outline"}
                onClick={() => setShowFilters(!showFilters)}
              >
                <SlidersHorizontal className="mr-2 h-4 w-4" />
                Filter
                {activeFilterCount > 0 && (
                  <Badge variant="default" className="ml-2">
                    {activeFilterCount}
                  </Badge>
                )}
              </Button>
              <Button
                variant="outline"
                size="icon"
                onClick={() => refetch()}
              >
                <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
              </Button>
            </div>

            {/* Filter Panel */}
            {showFilters && (
              <div className="flex flex-wrap gap-4 border-t pt-4">
                {/* Status Filter */}
                <div className="w-40">
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">
                    Status
                  </label>
                  <Select
                    value={statusFilter}
                    onValueChange={(v) => setStatusFilter(v as TaskStatus | "all")}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Alle" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">Alle</SelectItem>
                      {Object.entries(TASK_STATUS_LABELS).map(([value, label]) => (
                        <SelectItem key={value} value={value}>
                          {label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {/* Urgency Filter */}
                <div className="w-40">
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">
                    Dringlichkeit
                  </label>
                  <Select
                    value={urgencyFilter}
                    onValueChange={(v) => setUrgencyFilter(v as UrgencyLevel | "all")}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Alle" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">Alle</SelectItem>
                      {Object.entries(URGENCY_LABELS).map(([value, label]) => (
                        <SelectItem key={value} value={value}>
                          {label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {/* Type Filter */}
                <div className="w-40">
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">
                    Typ
                  </label>
                  <Select
                    value={typeFilter}
                    onValueChange={(v) => setTypeFilter(v as TaskType | "all")}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Alle" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">Alle</SelectItem>
                      {Object.entries(TASK_TYPE_LABELS).map(([value, label]) => (
                        <SelectItem key={value} value={value}>
                          {label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {/* Source Filter */}
                <div className="w-40">
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">
                    Quelle
                  </label>
                  <Select
                    value={sourceFilter}
                    onValueChange={(v) => setSourceFilter(v as SourceType | "all")}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Alle" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">Alle</SelectItem>
                      {Object.entries(SOURCE_TYPE_LABELS).map(([value, label]) => (
                        <SelectItem key={value} value={value}>
                          {label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {activeFilterCount > 0 && (
                  <div className="flex items-end">
                    <Button variant="ghost" size="sm" onClick={clearFilters}>
                      Filter zurücksetzen
                    </Button>
                  </div>
                )}
              </div>
            )}

            {/* Active Filter Chips */}
            {activeFilterCount > 0 && (
              <div className="flex flex-wrap gap-2">
                {statusFilter !== "all" && (
                  <FilterChip
                    label={`Status: ${TASK_STATUS_LABELS[statusFilter]}`}
                    onRemove={() => setStatusFilter("all")}
                  />
                )}
                {urgencyFilter !== "all" && (
                  <FilterChip
                    label={`Dringlichkeit: ${URGENCY_LABELS[urgencyFilter]}`}
                    onRemove={() => setUrgencyFilter("all")}
                  />
                )}
                {typeFilter !== "all" && (
                  <FilterChip
                    label={`Typ: ${TASK_TYPE_LABELS[typeFilter]}`}
                    onRemove={() => setTypeFilter("all")}
                  />
                )}
                {sourceFilter !== "all" && (
                  <FilterChip
                    label={`Quelle: ${SOURCE_TYPE_LABELS[sourceFilter]}`}
                    onRemove={() => setSourceFilter("all")}
                  />
                )}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Tasks Table */}
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="w-12 px-4 py-3">
                  <input type="checkbox" className="rounded" />
                </th>
                <th
                  className="px-4 py-3 text-left text-sm font-medium cursor-pointer hover:bg-muted/70"
                  onClick={() => toggleSort("routing_priority")}
                >
                  <div className="flex items-center gap-1">
                    Priorität
                    <SortIndicator field="routing_priority" />
                  </div>
                </th>
                <th
                  className="px-4 py-3 text-left text-sm font-medium cursor-pointer hover:bg-muted/70"
                  onClick={() => toggleSort("title")}
                >
                  <div className="flex items-center gap-1">
                    Aufgabe
                    <SortIndicator field="title" />
                  </div>
                </th>
                <th className="px-4 py-3 text-left text-sm font-medium">
                  Kunde
                </th>
                <th className="px-4 py-3 text-left text-sm font-medium">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-sm font-medium">
                  Zugewiesen
                </th>
                <th
                  className="px-4 py-3 text-left text-sm font-medium cursor-pointer hover:bg-muted/70"
                  onClick={() => toggleSort("created_at")}
                >
                  <div className="flex items-center gap-1">
                    Erstellt
                    <SortIndicator field="created_at" />
                  </div>
                </th>
                <th className="w-12 px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {filteredTasks.map((task) => (
                <tr
                  key={task.id}
                  className="border-b transition-colors hover:bg-muted/50 cursor-pointer"
                  onClick={() => router.push(`/aufgaben/${task.id}`)}
                >
                  <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                    <input type="checkbox" className="rounded" />
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <Badge
                        variant={task.urgency as "notfall" | "dringend" | "normal" | "routine"}
                      >
                        {URGENCY_LABELS[task.urgency]}
                      </Badge>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div
                        className={cn(
                          "flex h-8 w-8 items-center justify-center rounded-lg shrink-0",
                          getSourceColor(task.source_type)
                        )}
                      >
                        <SourceIcon source={task.source_type} />
                      </div>
                      <div className="min-w-0">
                        <p className="font-medium truncate max-w-[300px]">
                          {task.title}
                        </p>
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                          <span>{task.job_number}</span>
                          <span>•</span>
                          <span>{TASK_TYPE_LABELS[task.task_type]}</span>
                        </div>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div>
                      <p className="text-sm font-medium">
                        {task.customer_name || "-"}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {task.customer_plz && `PLZ ${task.customer_plz}`}
                      </p>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <StatusIcon status={task.status} />
                      <span className="text-sm">
                        {TASK_STATUS_LABELS[task.status]}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    {task.assigned_worker_name ? (
                      <div>
                        <p className="text-sm">{task.assigned_worker_name}</p>
                        <p className="text-xs text-muted-foreground">
                          {task.assigned_department_name}
                        </p>
                      </div>
                    ) : (
                      <span className="text-sm text-muted-foreground">
                        Nicht zugewiesen
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div>
                      <p className="text-sm">{formatTimeAgo(task.created_at)}</p>
                      <p className="text-xs text-muted-foreground">
                        {formatDateTime(task.created_at)}
                      </p>
                    </div>
                  </td>
                  <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                    <Button variant="ghost" size="icon">
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Empty State */}
        {filteredTasks.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <AlertTriangle className="h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-medium">Keine Aufgaben gefunden</h3>
            <p className="text-muted-foreground mt-1">
              Versuchen Sie, Ihre Filter anzupassen oder eine neue Aufgabe zu erstellen.
            </p>
            <Button className="mt-4" onClick={clearFilters}>
              Filter zurücksetzen
            </Button>
          </div>
        )}

        {/* Pagination */}
        {filteredTasks.length > 0 && (
          <div className="flex items-center justify-between border-t px-4 py-3">
            <p className="text-sm text-muted-foreground">
              Zeige 1-{filteredTasks.length} von {filteredTasks.length} Aufgaben
            </p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled>
                Zurück
              </Button>
              <Button variant="outline" size="sm" disabled>
                Weiter
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}

// Loading fallback component
function TasksPageLoading() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <div className="h-8 w-48 bg-muted animate-pulse rounded" />
          <div className="h-4 w-96 bg-muted animate-pulse rounded mt-2" />
        </div>
      </div>
      <Card>
        <CardContent className="py-12">
          <div className="flex flex-col items-center justify-center">
            <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
            <p className="mt-4 text-muted-foreground">Lade Aufgaben...</p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default function TasksPage() {
  return (
    <Suspense fallback={<TasksPageLoading />}>
      <TasksPageContent />
    </Suspense>
  );
}
