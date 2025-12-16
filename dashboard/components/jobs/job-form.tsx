"use client";

/**
 * IT-Friends Handwerk Dashboard - Job Creation Form
 *
 * Multi-step form for creating new jobs with German localization.
 * Steps: Kundeninformation -> Auftragsdetails -> Überprüfung
 */

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  User,
  Phone,
  Mail,
  MapPin,
  FileText,
  Wrench,
  AlertTriangle,
  Calendar,
  ChevronLeft,
  ChevronRight,
  Check,
  Loader2,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Task,
  TradeCategory,
  UrgencyLevel,
  TRADE_CATEGORY_LABELS,
  URGENCY_LABELS,
  PROPERTY_TYPE_LABELS,
  TIME_WINDOW_LABELS,
} from "@/types";
import { useCreateJob, useAssessTriage } from "@/hooks/use-jobs";
import { cn } from "@/lib/utils";

// ============================================================================
// Form Schema with German Validation Messages
// ============================================================================

const jobFormSchema = z.object({
  // Step 1: Kundeninformation
  customer_name: z.string().min(2, "Kundenname muss mindestens 2 Zeichen haben"),
  customer_phone: z
    .string()
    .min(6, "Telefonnummer muss mindestens 6 Zeichen haben")
    .optional()
    .or(z.literal("")),
  customer_email: z
    .string()
    .email("Ungültige E-Mail-Adresse")
    .optional()
    .or(z.literal("")),
  address_street: z.string().optional(),
  address_number: z.string().optional(),
  address_zip: z
    .string()
    .regex(/^\d{5}$/, "PLZ muss 5 Ziffern haben")
    .optional()
    .or(z.literal("")),
  address_city: z.string().optional(),
  property_type: z.enum(["residential", "commercial", "industrial"]).optional(),

  // Step 2: Auftragsdetails
  title: z.string().min(5, "Titel muss mindestens 5 Zeichen haben"),
  description: z.string().optional(),
  trade_category: z.enum(["shk", "elektro", "sanitaer", "general"]),
  urgency: z.enum(["notfall", "dringend", "normal", "routine"]),
  preferred_date: z.string().optional(),
  preferred_time_window: z.enum(["morning", "afternoon", "evening", "any"]).optional(),
  access_notes: z.string().optional(),
  customer_notes: z.string().optional(),
});

type JobFormData = z.infer<typeof jobFormSchema>;

// ============================================================================
// Step Indicator Component
// ============================================================================

interface StepIndicatorProps {
  currentStep: number;
  steps: { title: string; description: string }[];
}

function StepIndicator({ currentStep, steps }: StepIndicatorProps) {
  return (
    <div className="flex items-center justify-center mb-8">
      {steps.map((step, index) => (
        <div key={index} className="flex items-center">
          <div className="flex flex-col items-center">
            <div
              className={cn(
                "w-10 h-10 rounded-full flex items-center justify-center text-sm font-medium transition-colors",
                index < currentStep
                  ? "bg-green-500 text-white"
                  : index === currentStep
                  ? "bg-brand-500 text-white"
                  : "bg-muted text-muted-foreground"
              )}
            >
              {index < currentStep ? <Check className="h-5 w-5" /> : index + 1}
            </div>
            <div className="mt-2 text-center">
              <p
                className={cn(
                  "text-sm font-medium",
                  index <= currentStep ? "text-foreground" : "text-muted-foreground"
                )}
              >
                {step.title}
              </p>
              <p className="text-xs text-muted-foreground hidden sm:block">
                {step.description}
              </p>
            </div>
          </div>
          {index < steps.length - 1 && (
            <div
              className={cn(
                "w-16 h-0.5 mx-2",
                index < currentStep ? "bg-green-500" : "bg-muted"
              )}
            />
          )}
        </div>
      ))}
    </div>
  );
}

// ============================================================================
// Form Field Components
// ============================================================================

interface FormFieldProps {
  label: string;
  error?: string;
  required?: boolean;
  children: React.ReactNode;
  icon?: React.ReactNode;
}

function FormField({ label, error, required, children, icon }: FormFieldProps) {
  return (
    <div className="space-y-2">
      <label className="flex items-center gap-2 text-sm font-medium">
        {icon}
        {label}
        {required && <span className="text-red-500">*</span>}
      </label>
      {children}
      {error && <p className="text-sm text-red-500">{error}</p>}
    </div>
  );
}

// ============================================================================
// Main Job Form Component
// ============================================================================

interface JobFormProps {
  onSuccess?: (job: Task) => void;
  onCancel?: () => void;
}

export function JobForm({ onSuccess, onCancel }: JobFormProps) {
  const [currentStep, setCurrentStep] = useState(0);
  const createJob = useCreateJob();
  const assessTriage = useAssessTriage();

  const steps = [
    { title: "Kunde", description: "Kontaktdaten" },
    { title: "Auftrag", description: "Details" },
    { title: "Prüfen", description: "Bestätigen" },
  ];

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors, isSubmitting },
    trigger,
  } = useForm<JobFormData>({
    resolver: zodResolver(jobFormSchema),
    defaultValues: {
      trade_category: "shk",
      urgency: "normal",
      preferred_time_window: "any",
      property_type: "residential",
    },
  });

  const formData = watch();

  // Handle AI triage suggestion
  const handleTriageSuggestion = async () => {
    if (!formData.title && !formData.description) return;

    try {
      const result = await assessTriage.mutateAsync({
        free_text: `${formData.title}. ${formData.description || ""}`,
      });

      // Apply suggestions
      if (result.trade_category) {
        setValue("trade_category", result.trade_category);
      }
      if (result.urgency) {
        setValue("urgency", result.urgency);
      }
    } catch (error) {
      console.error("Triage assessment failed:", error);
    }
  };

  // Navigate to next step with validation
  const handleNext = async () => {
    let isValid = false;

    if (currentStep === 0) {
      isValid = await trigger([
        "customer_name",
        "customer_phone",
        "customer_email",
        "address_zip",
      ]);
    } else if (currentStep === 1) {
      isValid = await trigger(["title", "trade_category", "urgency"]);
    } else {
      isValid = true;
    }

    if (isValid) {
      setCurrentStep((prev) => Math.min(prev + 1, steps.length - 1));
    }
  };

  const handleBack = () => {
    setCurrentStep((prev) => Math.max(prev - 1, 0));
  };

  const onSubmit = async (data: JobFormData) => {
    try {
      const job = await createJob.mutateAsync({
        title: data.title,
        description: data.description,
        trade_category: data.trade_category as TradeCategory,
        urgency: data.urgency as UrgencyLevel,
        customer_name: data.customer_name,
        customer_phone: data.customer_phone || undefined,
        customer_email: data.customer_email || undefined,
        address_street: data.address_street,
        address_number: data.address_number,
        address_zip: data.address_zip || undefined,
        address_city: data.address_city,
        property_type: data.property_type,
        preferred_date: data.preferred_date,
        preferred_time_window: data.preferred_time_window,
        access_notes: data.access_notes,
        customer_notes: data.customer_notes,
      });

      onSuccess?.(job);
    } catch (error) {
      console.error("Job creation failed:", error);
    }
  };

  return (
    <Card className="max-w-2xl mx-auto">
      <CardHeader>
        <CardTitle>Neue Aufgabe erstellen</CardTitle>
      </CardHeader>
      <CardContent>
        <StepIndicator currentStep={currentStep} steps={steps} />

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
          {/* Step 1: Kundeninformation */}
          {currentStep === 0 && (
            <div className="space-y-4">
              <h3 className="text-lg font-medium flex items-center gap-2">
                <User className="h-5 w-5 text-brand-500" />
                Kundeninformation
              </h3>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <FormField
                  label="Kundenname"
                  error={errors.customer_name?.message}
                  required
                  icon={<User className="h-4 w-4 text-muted-foreground" />}
                >
                  <Input
                    {...register("customer_name")}
                    placeholder="z.B. Familie Müller"
                  />
                </FormField>

                <FormField
                  label="Telefon"
                  error={errors.customer_phone?.message}
                  icon={<Phone className="h-4 w-4 text-muted-foreground" />}
                >
                  <Input
                    {...register("customer_phone")}
                    placeholder="+49 7471 12345"
                    type="tel"
                  />
                </FormField>

                <FormField
                  label="E-Mail"
                  error={errors.customer_email?.message}
                  icon={<Mail className="h-4 w-4 text-muted-foreground" />}
                >
                  <Input
                    {...register("customer_email")}
                    placeholder="kunde@beispiel.de"
                    type="email"
                  />
                </FormField>

                <FormField
                  label="Objekttyp"
                  icon={<MapPin className="h-4 w-4 text-muted-foreground" />}
                >
                  <Select
                    value={formData.property_type}
                    onValueChange={(v) =>
                      setValue("property_type", v as JobFormData["property_type"])
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Auswählen..." />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(PROPERTY_TYPE_LABELS).map(([value, label]) => (
                        <SelectItem key={value} value={value}>
                          {label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </FormField>
              </div>

              <h4 className="text-sm font-medium mt-6 flex items-center gap-2">
                <MapPin className="h-4 w-4 text-muted-foreground" />
                Adresse
              </h4>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="md:col-span-2">
                  <FormField label="Straße">
                    <Input
                      {...register("address_street")}
                      placeholder="Musterstraße"
                    />
                  </FormField>
                </div>

                <FormField label="Hausnummer">
                  <Input {...register("address_number")} placeholder="123" />
                </FormField>

                <FormField label="PLZ" error={errors.address_zip?.message}>
                  <Input {...register("address_zip")} placeholder="72379" maxLength={5} />
                </FormField>

                <div className="md:col-span-2">
                  <FormField label="Stadt">
                    <Input {...register("address_city")} placeholder="Hechingen" />
                  </FormField>
                </div>
              </div>
            </div>
          )}

          {/* Step 2: Auftragsdetails */}
          {currentStep === 1 && (
            <div className="space-y-4">
              <h3 className="text-lg font-medium flex items-center gap-2">
                <FileText className="h-5 w-5 text-brand-500" />
                Auftragsdetails
              </h3>

              <FormField
                label="Titel / Problem"
                error={errors.title?.message}
                required
                icon={<FileText className="h-4 w-4 text-muted-foreground" />}
              >
                <Input
                  {...register("title")}
                  placeholder="z.B. Heizung defekt, kein Warmwasser"
                />
              </FormField>

              <FormField
                label="Beschreibung"
                icon={<FileText className="h-4 w-4 text-muted-foreground" />}
              >
                <textarea
                  {...register("description")}
                  className="flex min-h-24 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                  placeholder="Beschreiben Sie das Problem genauer..."
                />
              </FormField>

              {/* AI Triage Button */}
              {(formData.title || formData.description) && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={handleTriageSuggestion}
                  disabled={assessTriage.isPending}
                  className="w-full"
                >
                  {assessTriage.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Sparkles className="mr-2 h-4 w-4 text-amber-500" />
                  )}
                  KI-Vorschlag für Gewerk & Dringlichkeit
                </Button>
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <FormField
                  label="Gewerk"
                  error={errors.trade_category?.message}
                  required
                  icon={<Wrench className="h-4 w-4 text-muted-foreground" />}
                >
                  <Select
                    value={formData.trade_category}
                    onValueChange={(v) =>
                      setValue("trade_category", v as TradeCategory)
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(TRADE_CATEGORY_LABELS).map(([value, label]) => (
                        <SelectItem key={value} value={value}>
                          {label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </FormField>

                <FormField
                  label="Dringlichkeit"
                  error={errors.urgency?.message}
                  required
                  icon={<AlertTriangle className="h-4 w-4 text-muted-foreground" />}
                >
                  <Select
                    value={formData.urgency}
                    onValueChange={(v) => setValue("urgency", v as UrgencyLevel)}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(URGENCY_LABELS).map(([value, label]) => (
                        <SelectItem key={value} value={value}>
                          {label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </FormField>

                <FormField
                  label="Wunschtermin"
                  icon={<Calendar className="h-4 w-4 text-muted-foreground" />}
                >
                  <Input {...register("preferred_date")} type="date" />
                </FormField>

                <FormField
                  label="Bevorzugte Uhrzeit"
                  icon={<Calendar className="h-4 w-4 text-muted-foreground" />}
                >
                  <Select
                    value={formData.preferred_time_window}
                    onValueChange={(v) =>
                      setValue(
                        "preferred_time_window",
                        v as JobFormData["preferred_time_window"]
                      )
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(TIME_WINDOW_LABELS).map(([value, label]) => (
                        <SelectItem key={value} value={value}>
                          {label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </FormField>
              </div>

              <FormField label="Zugangshinweise">
                <Input
                  {...register("access_notes")}
                  placeholder="z.B. Schlüssel bei Nachbar, Hintereingang benutzen"
                />
              </FormField>

              <FormField label="Kundennotizen">
                <textarea
                  {...register("customer_notes")}
                  className="flex min-h-16 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                  placeholder="Zusätzliche Informationen vom Kunden..."
                />
              </FormField>
            </div>
          )}

          {/* Step 3: Überprüfung */}
          {currentStep === 2 && (
            <div className="space-y-6">
              <h3 className="text-lg font-medium flex items-center gap-2">
                <Check className="h-5 w-5 text-brand-500" />
                Zusammenfassung
              </h3>

              {/* Customer Summary */}
              <Card className="bg-muted/50">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <User className="h-4 w-4" />
                    Kunde
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-1 text-sm">
                  <p>
                    <strong>{formData.customer_name}</strong>
                  </p>
                  {formData.customer_phone && <p>Tel: {formData.customer_phone}</p>}
                  {formData.customer_email && <p>E-Mail: {formData.customer_email}</p>}
                  {(formData.address_street || formData.address_zip) && (
                    <p>
                      {formData.address_street} {formData.address_number},{" "}
                      {formData.address_zip} {formData.address_city}
                    </p>
                  )}
                  {formData.property_type && (
                    <p>Objekttyp: {PROPERTY_TYPE_LABELS[formData.property_type]}</p>
                  )}
                </CardContent>
              </Card>

              {/* Job Summary */}
              <Card className="bg-muted/50">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <FileText className="h-4 w-4" />
                    Auftrag
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  <p>
                    <strong>{formData.title}</strong>
                  </p>
                  {formData.description && (
                    <p className="text-muted-foreground">{formData.description}</p>
                  )}
                  <div className="flex flex-wrap gap-2 pt-2">
                    <Badge variant={formData.urgency as UrgencyLevel}>
                      {URGENCY_LABELS[formData.urgency as UrgencyLevel]}
                    </Badge>
                    <Badge variant="outline">
                      {TRADE_CATEGORY_LABELS[formData.trade_category as TradeCategory]}
                    </Badge>
                  </div>
                  {formData.preferred_date && (
                    <p>
                      Wunschtermin:{" "}
                      {new Date(formData.preferred_date).toLocaleDateString("de-DE")}
                      {formData.preferred_time_window &&
                        ` (${TIME_WINDOW_LABELS[formData.preferred_time_window]})`}
                    </p>
                  )}
                  {formData.access_notes && (
                    <p>Zugang: {formData.access_notes}</p>
                  )}
                  {formData.customer_notes && (
                    <p>Notizen: {formData.customer_notes}</p>
                  )}
                </CardContent>
              </Card>

              {/* Error Display */}
              {createJob.isError && (
                <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                  <p className="font-medium">Fehler beim Erstellen der Aufgabe:</p>
                  <p>{createJob.error?.message || "Unbekannter Fehler"}</p>
                </div>
              )}
            </div>
          )}

          {/* Navigation Buttons */}
          <div className="flex justify-between pt-6 border-t">
            <div>
              {currentStep > 0 && (
                <Button type="button" variant="outline" onClick={handleBack}>
                  <ChevronLeft className="mr-2 h-4 w-4" />
                  Zurück
                </Button>
              )}
              {currentStep === 0 && onCancel && (
                <Button type="button" variant="outline" onClick={onCancel}>
                  Abbrechen
                </Button>
              )}
            </div>

            <div>
              {currentStep < steps.length - 1 ? (
                <Button type="button" onClick={handleNext}>
                  Weiter
                  <ChevronRight className="ml-2 h-4 w-4" />
                </Button>
              ) : (
                <Button
                  type="submit"
                  disabled={isSubmitting || createJob.isPending}
                >
                  {(isSubmitting || createJob.isPending) && (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  )}
                  Aufgabe erstellen
                </Button>
              )}
            </div>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

export default JobForm;
