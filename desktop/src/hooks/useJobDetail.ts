/**
 * TanStack Query hook for polling a single job's detail.
 *
 * Only fires when a jobId is provided (enabled: jobId !== null). Polling
 * every 5 seconds keeps stage progress and status current while a job
 * is being viewed in the detail panel.
 */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { getJob, type JobDetail } from "../lib/backend";

export function useJobDetail(jobId: string | null): UseQueryResult<JobDetail> {
  return useQuery<JobDetail>({
    queryKey: ["jobs", jobId],
    queryFn: () => getJob(jobId!),
    enabled: jobId !== null,
    refetchInterval: 5000,
  });
}
