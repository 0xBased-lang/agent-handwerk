"use client";

/**
 * IT-Friends Handwerk Dashboard - Technician Assignment
 *
 * Smart technician matching and assignment component.
 */

import { useState } from "react";
import {
  Users,
  Search,
  Filter,
  Loader2,
  AlertTriangle,
  RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { TechnicianCard } from "./technician-card";
import {
  TradeCategory,
  TechnicianMatch,
  TRADE_CATEGORY_LABELS,
} from "@/types";
import {
  useTechnicianSearchFull,
  useAssignTechnician,
} from "@/hooks/use-jobs";
import { toast } from "sonner";

// ============================================================================
// Main Component
// ============================================================================

interface TechnicianAssignmentProps {
  jobId: string;
  tradeCategory: TradeCategory;
  currentTechnicianId?: string;
  onAssigned?: (technicianId: string) => void;
}

export function TechnicianAssignment({
  jobId,
  tradeCategory,
  currentTechnicianId,
  onAssigned,
}: TechnicianAssignmentProps) {
  const [search, setSearch] = useState("");
  const [filterCategory, setFilterCategory] = useState<TradeCategory | "all">(
    tradeCategory
  );

  // Fetch technicians
  const {
    data: technicians,
    isLoading,
    error,
    refetch,
  } = useTechnicianSearchFull(
    {
      trade_category: filterCategory === "all" ? tradeCategory : filterCategory,
    },
    { enabled: true }
  );

  // Assign mutation
  const assignTechnician = useAssignTechnician();

  // Filter technicians by search
  const filteredTechnicians =
    technicians?.filter((tech) => {
      if (!search) return true;
      const searchLower = search.toLowerCase();
      return (
        tech.name.toLowerCase().includes(searchLower) ||
        tech.first_name.toLowerCase().includes(searchLower) ||
        tech.last_name.toLowerCase().includes(searchLower) ||
        tech.certifications.some((cert) =>
          cert.toLowerCase().includes(searchLower)
        )
      );
    }) ?? [];

  // Sort by match score (highest first)
  const sortedTechnicians = [...filteredTechnicians].sort(
    (a, b) => b.match_score - a.match_score
  );

  const handleAssign = async (technicianId: string) => {
    try {
      await assignTechnician.mutateAsync({ jobId, technicianId });
      toast.success("Techniker erfolgreich zugewiesen");
      onAssigned?.(technicianId);
    } catch (error) {
      toast.error("Fehler beim Zuweisen", {
        description:
          error instanceof Error ? error.message : "Unbekannter Fehler",
      });
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Users className="h-5 w-5 text-brand-500" />
          Techniker zuweisen
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Search and Filter */}
        <div className="flex flex-col sm:flex-row gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Techniker suchen..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
            />
          </div>

          <Select
            value={filterCategory}
            onValueChange={(v) => setFilterCategory(v as TradeCategory | "all")}
          >
            <SelectTrigger className="w-[200px]">
              <Filter className="mr-2 h-4 w-4" />
              <SelectValue placeholder="Gewerk" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Alle Gewerke</SelectItem>
              {Object.entries(TRADE_CATEGORY_LABELS).map(([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Button variant="outline" size="icon" onClick={() => refetch()}>
            <RefreshCw className={isLoading ? "animate-spin" : ""} />
          </Button>
        </div>

        {/* Loading State */}
        {isLoading && (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            <span className="ml-2 text-muted-foreground">
              Suche passende Techniker...
            </span>
          </div>
        )}

        {/* Error State */}
        {error && (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <AlertTriangle className="h-12 w-12 text-red-500 mb-4" />
            <h3 className="font-medium">Fehler beim Laden</h3>
            <p className="text-sm text-muted-foreground mt-1">
              {error instanceof Error ? error.message : "Unbekannter Fehler"}
            </p>
            <Button variant="outline" className="mt-4" onClick={() => refetch()}>
              Erneut versuchen
            </Button>
          </div>
        )}

        {/* Empty State */}
        {!isLoading && !error && sortedTechnicians.length === 0 && (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <Users className="h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="font-medium">Keine Techniker gefunden</h3>
            <p className="text-sm text-muted-foreground mt-1">
              {search
                ? "Versuchen Sie eine andere Suche"
                : "Keine passenden Techniker für dieses Gewerk verfügbar"}
            </p>
          </div>
        )}

        {/* Technician List */}
        {!isLoading && !error && sortedTechnicians.length > 0 && (
          <div data-testid="technician-list" className="space-y-3">
            <p className="text-sm text-muted-foreground">
              {sortedTechnicians.length} Techniker gefunden
            </p>
            {sortedTechnicians.map((technician) => (
              <TechnicianCard
                key={technician.id}
                technician={technician}
                onAssign={handleAssign}
                isAssigning={
                  assignTechnician.isPending &&
                  assignTechnician.variables?.technicianId === technician.id
                }
                isAssigned={currentTechnicianId === technician.id}
              />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default TechnicianAssignment;
