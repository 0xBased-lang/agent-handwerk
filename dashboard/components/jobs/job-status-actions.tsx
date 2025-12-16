"use client";

/**
 * IT-Friends Handwerk Dashboard - Job Status Actions
 *
 * Quick action buttons for updating job status with optimistic updates.
 */

import { useState } from "react";
import {
  Play,
  CheckCircle2,
  XCircle,
  Clock,
  AlertTriangle,
  Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { TaskStatus, TASK_STATUS_LABELS } from "@/types";
import { useUpdateJobStatus } from "@/hooks/use-jobs";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

// ============================================================================
// Status Configuration
// ============================================================================

interface StatusConfig {
  label: string;
  icon: React.ReactNode;
  color: string;
  bgColor: string;
  nextStatuses: TaskStatus[];
}

const STATUS_CONFIG: Record<TaskStatus, StatusConfig> = {
  new: {
    label: "Neu",
    icon: <AlertTriangle className="h-4 w-4" />,
    color: "text-purple-600",
    bgColor: "bg-purple-100",
    nextStatuses: ["assigned", "in_progress", "cancelled"],
  },
  assigned: {
    label: "Zugewiesen",
    icon: <Clock className="h-4 w-4" />,
    color: "text-blue-600",
    bgColor: "bg-blue-100",
    nextStatuses: ["in_progress", "cancelled"],
  },
  in_progress: {
    label: "In Bearbeitung",
    icon: <Play className="h-4 w-4" />,
    color: "text-amber-600",
    bgColor: "bg-amber-100",
    nextStatuses: ["completed", "cancelled"],
  },
  completed: {
    label: "Erledigt",
    icon: <CheckCircle2 className="h-4 w-4" />,
    color: "text-green-600",
    bgColor: "bg-green-100",
    nextStatuses: [],
  },
  cancelled: {
    label: "Storniert",
    icon: <XCircle className="h-4 w-4" />,
    color: "text-gray-600",
    bgColor: "bg-gray-100",
    nextStatuses: [],
  },
};

// ============================================================================
// Action Button Configuration
// ============================================================================

interface ActionButton {
  targetStatus: TaskStatus;
  label: string;
  icon: React.ReactNode;
  variant: "default" | "outline" | "destructive" | "secondary";
  requiresConfirmation?: boolean;
  confirmationTitle?: string;
  confirmationMessage?: string;
}

const getActionButtons = (currentStatus: TaskStatus): ActionButton[] => {
  const buttons: ActionButton[] = [];

  if (currentStatus === "new" || currentStatus === "assigned") {
    buttons.push({
      targetStatus: "in_progress",
      label: "Starten",
      icon: <Play className="h-4 w-4" />,
      variant: "default",
    });
  }

  if (currentStatus === "in_progress") {
    buttons.push({
      targetStatus: "completed",
      label: "Erledigt",
      icon: <CheckCircle2 className="h-4 w-4" />,
      variant: "default",
    });
  }

  if (currentStatus !== "completed" && currentStatus !== "cancelled") {
    buttons.push({
      targetStatus: "cancelled",
      label: "Stornieren",
      icon: <XCircle className="h-4 w-4" />,
      variant: "destructive",
      requiresConfirmation: true,
      confirmationTitle: "Aufgabe stornieren",
      confirmationMessage:
        "Möchten Sie diese Aufgabe wirklich stornieren? Diese Aktion kann nicht rückgängig gemacht werden.",
    });
  }

  return buttons;
};

// ============================================================================
// Main Component
// ============================================================================

interface JobStatusActionsProps {
  jobId: string;
  currentStatus: TaskStatus;
  className?: string;
  showCurrentStatus?: boolean;
  size?: "sm" | "default" | "lg";
}

export function JobStatusActions({
  jobId,
  currentStatus,
  className,
  showCurrentStatus = true,
  size = "default",
}: JobStatusActionsProps) {
  const [confirmDialog, setConfirmDialog] = useState<ActionButton | null>(null);
  const updateStatus = useUpdateJobStatus();

  const handleStatusChange = async (targetStatus: TaskStatus) => {
    try {
      await updateStatus.mutateAsync({ jobId, status: targetStatus });
      toast.success("Status aktualisiert", {
        description: `Status geändert zu: ${TASK_STATUS_LABELS[targetStatus]}`,
      });
    } catch (error) {
      toast.error("Fehler beim Aktualisieren", {
        description: error instanceof Error ? error.message : "Unbekannter Fehler",
      });
    }
  };

  const handleActionClick = (action: ActionButton) => {
    if (action.requiresConfirmation) {
      setConfirmDialog(action);
    } else {
      handleStatusChange(action.targetStatus);
    }
  };

  const handleConfirm = async () => {
    if (confirmDialog) {
      await handleStatusChange(confirmDialog.targetStatus);
      setConfirmDialog(null);
    }
  };

  const config = STATUS_CONFIG[currentStatus];
  const actionButtons = getActionButtons(currentStatus);

  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      {/* Current Status Display */}
      {showCurrentStatus && (
        <div
          data-testid="current-status"
          className={cn(
            "flex items-center gap-2 px-3 py-1.5 rounded-lg",
            config.bgColor,
            config.color
          )}
        >
          {config.icon}
          <span className="text-sm font-medium">{config.label}</span>
        </div>
      )}

      {/* Action Buttons */}
      {actionButtons.map((action) => (
        <Button
          key={action.targetStatus}
          variant={action.variant}
          size={size}
          onClick={() => handleActionClick(action)}
          disabled={updateStatus.isPending}
        >
          {updateStatus.isPending &&
          updateStatus.variables?.status === action.targetStatus ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <span className="mr-2">{action.icon}</span>
          )}
          {action.label}
        </Button>
      ))}

      {/* Terminal Status Message */}
      {actionButtons.length === 0 && (
        <p className="text-sm text-muted-foreground">
          Diese Aufgabe ist abgeschlossen und kann nicht mehr geändert werden.
        </p>
      )}

      {/* Confirmation Dialog */}
      <Dialog open={!!confirmDialog} onOpenChange={() => setConfirmDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{confirmDialog?.confirmationTitle}</DialogTitle>
            <DialogDescription>
              {confirmDialog?.confirmationMessage}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDialog(null)}>
              Abbrechen
            </Button>
            <Button
              variant="destructive"
              onClick={handleConfirm}
              disabled={updateStatus.isPending}
            >
              {updateStatus.isPending && (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              )}
              Ja, stornieren
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default JobStatusActions;
