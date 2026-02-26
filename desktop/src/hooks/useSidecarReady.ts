/**
 * TanStack Query hook for polling backend health.
 *
 * Polls the /health endpoint every 5 seconds. Components use the returned
 * data to determine whether the backend is reachable and responsive.
 * Returns null when the backend is unreachable (checkHealth swallows
 * network errors and returns null).
 */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { checkHealth, type HealthResponse } from "../lib/backend";

export function useSidecarReady(): UseQueryResult<HealthResponse | null> {
  return useQuery<HealthResponse | null>({
    queryKey: ["health"],
    queryFn: checkHealth,
    refetchInterval: 5000,
    staleTime: 4000,
    // Don't retry health checks — a failed probe is itself useful signal.
    retry: 0,
  });
}
