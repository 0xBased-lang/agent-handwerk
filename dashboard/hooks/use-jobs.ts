/**
 * IT-Friends Handwerk Dashboard - React Query Hooks for Jobs
 *
 * Custom hooks for job CRUD operations, triage, technician matching, and scheduling.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import {
  Task,
  TaskFilters,
  PaginatedResponse,
  CreateHandwerkJobRequest,
  TriageRequest,
  TriageResponse,
  TechnicianSearchRequest,
  TechnicianMatch,
  TimeSlotSearchRequest,
  TimeSlot,
  BookAppointmentRequest,
  AddJobNoteRequest,
  JobNote,
  TradeCategory,
  TaskStatus,
} from "@/types";

// ============================================================================
// Query Keys
// ============================================================================

export const jobQueryKeys = {
  all: ["jobs"] as const,
  lists: () => [...jobQueryKeys.all, "list"] as const,
  list: (filters?: TaskFilters, page?: number) =>
    [...jobQueryKeys.lists(), { filters, page }] as const,
  details: () => [...jobQueryKeys.all, "detail"] as const,
  detail: (id: string) => [...jobQueryKeys.details(), id] as const,
  notes: (id: string) => [...jobQueryKeys.detail(id), "notes"] as const,
  history: (id: string) => [...jobQueryKeys.detail(id), "history"] as const,
  stats: () => [...jobQueryKeys.all, "stats"] as const,
};

export const technicianQueryKeys = {
  all: ["technicians"] as const,
  search: (request: TechnicianSearchRequest) =>
    [...technicianQueryKeys.all, "search", request] as const,
};

export const schedulingQueryKeys = {
  all: ["scheduling"] as const,
  slots: (request: TimeSlotSearchRequest) =>
    [...schedulingQueryKeys.all, "slots", request] as const,
};

// ============================================================================
// Job Queries
// ============================================================================

/**
 * Fetch paginated list of jobs with filters
 */
export function useJobs(filters?: TaskFilters, page = 1, pageSize = 20) {
  return useQuery({
    queryKey: jobQueryKeys.list(filters, page),
    queryFn: () => apiClient.getTasks(filters, page, pageSize),
    staleTime: 30 * 1000, // Consider data stale after 30 seconds
    refetchInterval: 60 * 1000, // Auto-refetch every minute
  });
}

/**
 * Fetch single job by ID
 */
export function useJob(jobId: string) {
  return useQuery({
    queryKey: jobQueryKeys.detail(jobId),
    queryFn: () => apiClient.getTask(jobId),
    enabled: !!jobId,
  });
}

/**
 * Fetch job statistics for dashboard
 */
export function useJobStats() {
  return useQuery({
    queryKey: jobQueryKeys.stats(),
    queryFn: () => apiClient.getDashboardStats(),
    staleTime: 60 * 1000,
    refetchInterval: 2 * 60 * 1000,
  });
}

/**
 * Fetch job notes
 */
export function useJobNotes(jobId: string) {
  return useQuery({
    queryKey: jobQueryKeys.notes(jobId),
    queryFn: () => apiClient.getJobNotes(jobId),
    enabled: !!jobId,
  });
}

/**
 * Fetch job history/timeline
 */
export function useJobHistory(jobId: string) {
  return useQuery({
    queryKey: jobQueryKeys.history(jobId),
    queryFn: () => apiClient.getJobHistory(jobId),
    enabled: !!jobId,
  });
}

// ============================================================================
// Job Mutations
// ============================================================================

/**
 * Create a new Handwerk job
 */
export function useCreateJob() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: CreateHandwerkJobRequest) =>
      apiClient.createHandwerkJob(request),
    onSuccess: (newJob) => {
      // Invalidate job lists to refetch
      queryClient.invalidateQueries({ queryKey: jobQueryKeys.lists() });
      queryClient.invalidateQueries({ queryKey: jobQueryKeys.stats() });
      // Optionally add to cache
      queryClient.setQueryData(jobQueryKeys.detail(newJob.id), newJob);
    },
  });
}

/**
 * Update job status with optimistic update
 */
export function useUpdateJobStatus() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ jobId, status }: { jobId: string; status: TaskStatus }) =>
      apiClient.updateTaskStatus(jobId, status),
    // Optimistic update
    onMutate: async ({ jobId, status }) => {
      // Cancel any outgoing refetches
      await queryClient.cancelQueries({ queryKey: jobQueryKeys.detail(jobId) });

      // Snapshot previous value
      const previousJob = queryClient.getQueryData<Task>(
        jobQueryKeys.detail(jobId)
      );

      // Optimistically update to new value
      if (previousJob) {
        queryClient.setQueryData(jobQueryKeys.detail(jobId), {
          ...previousJob,
          status,
          updated_at: new Date().toISOString(),
        });
      }

      return { previousJob };
    },
    // Rollback on error
    onError: (_err, { jobId }, context) => {
      if (context?.previousJob) {
        queryClient.setQueryData(jobQueryKeys.detail(jobId), context.previousJob);
      }
    },
    // Always refetch after error or success
    onSettled: (_data, _error, { jobId }) => {
      queryClient.invalidateQueries({ queryKey: jobQueryKeys.detail(jobId) });
      queryClient.invalidateQueries({ queryKey: jobQueryKeys.lists() });
      queryClient.invalidateQueries({ queryKey: jobQueryKeys.stats() });
    },
  });
}

/**
 * Assign technician to job
 */
export function useAssignTechnician() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      jobId,
      technicianId,
    }: {
      jobId: string;
      technicianId: string;
    }) => apiClient.assignTask(jobId, technicianId),
    onSuccess: (_data, { jobId }) => {
      queryClient.invalidateQueries({ queryKey: jobQueryKeys.detail(jobId) });
      queryClient.invalidateQueries({ queryKey: jobQueryKeys.lists() });
    },
  });
}

/**
 * Add note to job
 */
export function useAddJobNote() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ jobId, request }: { jobId: string; request: AddJobNoteRequest }) =>
      apiClient.addJobNote(jobId, request),
    onSuccess: (_data, { jobId }) => {
      queryClient.invalidateQueries({ queryKey: jobQueryKeys.notes(jobId) });
      queryClient.invalidateQueries({ queryKey: jobQueryKeys.history(jobId) });
    },
  });
}

/**
 * Delete job (soft delete)
 */
export function useDeleteJob() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (jobId: string) => apiClient.deleteTask(jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: jobQueryKeys.lists() });
      queryClient.invalidateQueries({ queryKey: jobQueryKeys.stats() });
    },
  });
}

// ============================================================================
// Triage Assessment
// ============================================================================

/**
 * Assess job urgency and trade category via AI triage
 */
export function useAssessTriage() {
  return useMutation({
    mutationFn: (request: TriageRequest) => apiClient.assessTriage(request),
  });
}

// ============================================================================
// Technician Queries
// ============================================================================

/**
 * Search for matching technicians
 */
export function useTechnicianSearch(
  tradeCategory: TradeCategory,
  options?: { enabled?: boolean }
) {
  const request: TechnicianSearchRequest = { trade_category: tradeCategory };

  return useQuery({
    queryKey: technicianQueryKeys.search(request),
    queryFn: () => apiClient.searchTechnicians(request),
    enabled: options?.enabled ?? true,
    staleTime: 5 * 60 * 1000, // Cache for 5 minutes
  });
}

/**
 * Search technicians with full parameters
 */
export function useTechnicianSearchFull(
  request: TechnicianSearchRequest,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: technicianQueryKeys.search(request),
    queryFn: () => apiClient.searchTechnicians(request),
    enabled: options?.enabled ?? true,
    staleTime: 5 * 60 * 1000,
  });
}

// ============================================================================
// Scheduling Queries
// ============================================================================

/**
 * Search available time slots
 */
export function useTimeSlots(
  request: TimeSlotSearchRequest,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: schedulingQueryKeys.slots(request),
    queryFn: () => apiClient.searchTimeSlots(request),
    enabled: options?.enabled ?? true,
    staleTime: 2 * 60 * 1000, // Cache for 2 minutes
  });
}

/**
 * Book an appointment
 */
export function useBookAppointment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: BookAppointmentRequest) =>
      apiClient.bookAppointment(request),
    onSuccess: () => {
      // Invalidate slot queries to refetch availability
      queryClient.invalidateQueries({ queryKey: schedulingQueryKeys.all });
    },
  });
}
