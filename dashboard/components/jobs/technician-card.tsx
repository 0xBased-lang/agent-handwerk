"use client";

/**
 * IT-Friends Handwerk Dashboard - Technician Card
 *
 * Display card for a single technician with match score and availability.
 */

import {
  User,
  Phone,
  Mail,
  Award,
  Briefcase,
  Clock,
  CheckCircle2,
  XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TechnicianMatch, TRADE_CATEGORY_LABELS } from "@/types";
import { cn } from "@/lib/utils";

// ============================================================================
// Match Score Badge
// ============================================================================

interface MatchScoreBadgeProps {
  score: number;
}

function MatchScoreBadge({ score }: MatchScoreBadgeProps) {
  const percentage = Math.round(score * 100);
  const color =
    percentage >= 80
      ? "bg-green-100 text-green-700"
      : percentage >= 60
      ? "bg-amber-100 text-amber-700"
      : "bg-red-100 text-red-700";

  return (
    <div
      data-testid="match-score"
      className={cn("px-2 py-1 rounded-full text-xs font-medium", color)}
    >
      {percentage}% Übereinstimmung
    </div>
  );
}

// ============================================================================
// Workload Indicator
// ============================================================================

interface WorkloadIndicatorProps {
  current: number;
  max: number;
}

function WorkloadIndicator({ current, max }: WorkloadIndicatorProps) {
  const percentage = max > 0 ? (current / max) * 100 : 0;
  const color =
    percentage >= 80
      ? "bg-red-500"
      : percentage >= 50
      ? "bg-amber-500"
      : "bg-green-500";

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>Auslastung</span>
        <span>
          {current}/{max} Aufgaben
        </span>
      </div>
      <div className="h-2 bg-muted rounded-full overflow-hidden">
        <div
          className={cn("h-full transition-all", color)}
          style={{ width: `${Math.min(percentage, 100)}%` }}
        />
      </div>
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================

interface TechnicianCardProps {
  technician: TechnicianMatch;
  onAssign?: (technicianId: string) => void;
  isAssigning?: boolean;
  isAssigned?: boolean;
}

export function TechnicianCard({
  technician,
  onAssign,
  isAssigning,
  isAssigned,
}: TechnicianCardProps) {
  return (
    <Card
      data-testid="technician-card"
      className={cn(
        "transition-shadow hover:shadow-md",
        isAssigned && "border-green-500 bg-green-50"
      )}
    >
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-4">
          {/* Technician Info */}
          <div className="flex items-start gap-3 flex-1">
            {/* Avatar */}
            <div className="w-12 h-12 rounded-full bg-brand-100 flex items-center justify-center shrink-0">
              <User className="h-6 w-6 text-brand-600" />
            </div>

            {/* Details */}
            <div className="space-y-2 flex-1">
              <div>
                <div className="flex items-center gap-2">
                  <h4 className="font-medium">{technician.name}</h4>
                  {isAssigned && (
                    <Badge variant="outline" className="bg-green-100 text-green-700">
                      Zugewiesen
                    </Badge>
                  )}
                </div>
                <p className="text-sm text-muted-foreground">
                  {technician.qualification}
                </p>
              </div>

              {/* Trade Categories */}
              <div className="flex flex-wrap gap-1">
                {technician.trade_categories.map((category) => (
                  <Badge key={category} variant="outline" className="text-xs">
                    {TRADE_CATEGORY_LABELS[category] || category}
                  </Badge>
                ))}
              </div>

              {/* Certifications */}
              {technician.certifications.length > 0 && (
                <div className="flex items-center gap-1 text-xs text-muted-foreground">
                  <Award className="h-3 w-3" />
                  <span>{technician.certifications.slice(0, 3).join(", ")}</span>
                  {technician.certifications.length > 3 && (
                    <span>+{technician.certifications.length - 3}</span>
                  )}
                </div>
              )}

              {/* Contact Info */}
              <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
                {technician.phone && (
                  <div className="flex items-center gap-1">
                    <Phone className="h-3 w-3" />
                    <span>{technician.phone}</span>
                  </div>
                )}
                {technician.email && (
                  <div className="flex items-center gap-1">
                    <Mail className="h-3 w-3" />
                    <span>{technician.email}</span>
                  </div>
                )}
              </div>

              {/* Workload */}
              <WorkloadIndicator
                current={technician.current_workload}
                max={technician.max_workload}
              />
            </div>
          </div>

          {/* Right Column: Score & Actions */}
          <div className="flex flex-col items-end gap-3">
            <MatchScoreBadge score={technician.match_score} />

            {/* Availability */}
            <div className="flex items-center gap-1 text-xs">
              {technician.availability_today ? (
                <>
                  <CheckCircle2 className="h-4 w-4 text-green-500" />
                  <span className="text-green-600">Heute verfügbar</span>
                </>
              ) : (
                <>
                  <XCircle className="h-4 w-4 text-red-500" />
                  <span className="text-red-600">Nicht verfügbar</span>
                </>
              )}
            </div>

            {/* Next Available Slot */}
            {technician.next_available_slot && !technician.availability_today && (
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <Clock className="h-3 w-3" />
                <span>
                  Nächster Termin:{" "}
                  {new Date(technician.next_available_slot).toLocaleDateString("de-DE")}
                </span>
              </div>
            )}

            {/* Distance */}
            {technician.distance_km !== undefined && (
              <div className="text-xs text-muted-foreground">
                {technician.distance_km.toFixed(1)} km entfernt
              </div>
            )}

            {/* Assign Button */}
            {onAssign && !isAssigned && (
              <Button
                size="sm"
                onClick={() => onAssign(technician.id)}
                disabled={isAssigning || !technician.availability_today}
              >
                {isAssigning ? "Wird zugewiesen..." : "Zuweisen"}
              </Button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default TechnicianCard;
