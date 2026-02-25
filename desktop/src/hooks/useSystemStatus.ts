/**
 * TanStack Query hook for fetching backend system readiness status.
 *
 * Polls the /system/status endpoint every 10 seconds. System status changes
 * slowly (binary availability, model cache) so a lower frequency is appropriate.
 * Used to display readiness warnings in the UI before the first job is run.
 */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { BACKEND_PORT } from "../lib/backend";

export interface BinaryStatus {
  status: string;
  path: string | null;
  source: string;
}

export interface ModelStatus {
  name: string;
  status: string;
  path: string | null;
}

export interface SystemStatus {
  ready: boolean;
  binaries: Record<string, BinaryStatus>;
  model: ModelStatus;
  issues: string[];
}

async function fetchSystemStatus(): Promise<SystemStatus> {
  const response = await fetch(
    `http://127.0.0.1:${BACKEND_PORT}/system/status`,
  );
  return response.json() as Promise<SystemStatus>;
}

export function useSystemStatus(): UseQueryResult<SystemStatus> {
  return useQuery<SystemStatus>({
    queryKey: ["system-status"],
    queryFn: fetchSystemStatus,
    refetchInterval: 10000,
  });
}
