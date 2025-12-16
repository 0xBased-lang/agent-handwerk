"use client";

/**
 * IT-Friends Handwerk Dashboard - New Job Page
 *
 * Page for creating new Handwerk jobs from the dashboard.
 */

import { useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { JobForm } from "@/components/jobs/job-form";
import { Task } from "@/types";
import { toast } from "sonner";

export default function NeueAufgabePage() {
  const router = useRouter();

  const handleSuccess = (job: Task) => {
    toast.success("Aufgabe erfolgreich erstellt", {
      description: `${job.title} (${job.job_number})`,
    });
    router.push(`/aufgaben/${job.id}`);
  };

  const handleCancel = () => {
    router.push("/aufgaben");
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center gap-4">
        <Link href="/aufgaben">
          <Button variant="ghost" size="icon">
            <ArrowLeft className="h-5 w-5" />
          </Button>
        </Link>
        <div>
          <h1 className="text-2xl font-bold">Neue Aufgabe erstellen</h1>
          <p className="text-muted-foreground">
            Erfassen Sie die Details für einen neuen Kundenauftrag
          </p>
        </div>
      </div>

      {/* Job Creation Form */}
      <JobForm onSuccess={handleSuccess} onCancel={handleCancel} />
    </div>
  );
}
