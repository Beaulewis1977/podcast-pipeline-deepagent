import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";

import {
  createJob,
  deleteJob,
  listJobs,
  resumeJob,
  runJob,
} from "../desktop/src/lib/backend.ts";

const originalFetch = globalThis.fetch;

type RequestSnapshot = {
  url: string;
  init: RequestInit;
};

let lastRequest: RequestSnapshot | null = null;

function installFetchMock(
  responder: (url: string, init: RequestInit) => Response | Promise<Response>,
): void {
  globalThis.fetch = (async (
    input: RequestInfo | URL,
    init: RequestInit = {},
  ): Promise<Response> => {
    const url = typeof input === "string" ? input : input.toString();
    lastRequest = { url, init };
    return responder(url, init);
  }) as typeof fetch;
}

afterEach(() => {
  globalThis.fetch = originalFetch;
  lastRequest = null;
});

after(() => {
  globalThis.fetch = originalFetch;
});

test("createJob posts video path and name", async () => {
  installFetchMock(() =>
    Response.json({
      job_id: "job-001",
      status: "pending",
      input_file: "input/raw.mp4",
      created_at: "2026-02-13T00:00:00Z",
    }),
  );

  const created = await createJob("/tmp/video.mp4", "episode-1");

  assert.equal(lastRequest?.url.endsWith("/jobs"), true);
  assert.equal(lastRequest?.init.method, "POST");
  assert.deepEqual(JSON.parse(String(lastRequest?.init.body)), {
    video_path: "/tmp/video.mp4",
    name: "episode-1",
  });
  assert.equal(created.job_id, "job-001");
});

test("runJob background targets run/background with stage window payload", async () => {
  installFetchMock(() =>
    Response.json({
      job_id: "job-123",
      accepted: true,
      message: "Background run started",
    }),
  );

  const result = await runJob("job-123", {
    stage: "ingest",
    untilStage: "review",
    background: true,
  });

  assert.equal(lastRequest?.url.endsWith("/jobs/job-123/run/background"), true);
  assert.equal(lastRequest?.init.method, "POST");
  assert.deepEqual(JSON.parse(String(lastRequest?.init.body)), {
    stage: "ingest",
    until_stage: "review",
  });
  assert.equal(result.status, "running");
  assert.equal(result.started, true);
  assert.equal(result.rejected, false);
});

test("resumeJob sends from_stage, until_stage, and background flag", async () => {
  installFetchMock(() =>
    Response.json({
      job_id: "job-resume",
      status: "running",
      message: "Background resume started",
      started: true,
      completed: false,
      rejected: false,
    }),
  );

  const result = await resumeJob("job-resume", {
    fromStage: "analyze",
    untilStage: "render",
    background: true,
  });

  assert.equal(lastRequest?.url.endsWith("/jobs/job-resume/resume"), true);
  assert.equal(lastRequest?.init.method, "POST");
  assert.deepEqual(JSON.parse(String(lastRequest?.init.body)), {
    from_stage: "analyze",
    until_stage: "render",
    background: true,
  });
  assert.equal(result.status, "running");
});

test("deleteJob issues DELETE request and returns response payload", async () => {
  installFetchMock(() =>
    Response.json({
      job_id: "job-delete",
      deleted: true,
      message: "Job deleted",
    }),
  );

  const deleted = await deleteJob("job-delete");

  assert.equal(lastRequest?.url.endsWith("/jobs/job-delete"), true);
  assert.equal(lastRequest?.init.method, "DELETE");
  assert.equal(deleted.deleted, true);
});

test("listJobs returns empty list when jobs payload missing", async () => {
  installFetchMock(() => Response.json({}));

  const jobs = await listJobs();

  assert.deepEqual(jobs, []);
});

test("request errors include backend validation detail text", async () => {
  installFetchMock(
    () =>
      new Response(
        JSON.stringify({
          detail: [
            {
              loc: ["body", "until_stage"],
              msg: "until_stage must be the same as or after stage",
              type: "value_error",
            },
          ],
        }),
        {
          status: 422,
          statusText: "Unprocessable Entity",
          headers: { "Content-Type": "application/json" },
        },
      ),
  );

  await assert.rejects(
    () => runJob("job-err", { stage: "review", untilStage: "ingest" }),
    /until_stage must be the same as or after stage/,
  );
});
