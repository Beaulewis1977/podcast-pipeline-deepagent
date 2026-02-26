/**
 * TanStack Query hook for polling the job list.
 *
 * Replaces the manual setInterval pattern in App.tsx with a declarative
 * polling query. Refetches every 5 seconds to keep job statuses current.
 */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { listJobs, type JobSummary } from "../lib/backend";

export function useJobs(): UseQueryResult<JobSummary[]> {
  return useQuery<JobSummary[]>({
    queryKey: ["jobs"],
    queryFn: listJobs,
    refetchInterval: 5000,
    // Consider data fresh for 4 s so rapid component remounts don't fire
    // duplicate requests within the same polling window.
    staleTime: 4000,
    retry: 2,
  });
}
