"use client";

import { useState, useEffect, useRef } from "react";
import FuzzerForm from "@/components/FuzzerForm";
import TestCounter from "@/components/TestCounter";
import TerminalOutput from "@/components/TerminalOutput";
import Dashboard from "@/components/Dashboard";
import { validateTarget, submitFuzzJob, getJobStatus, cancelJob } from "@/lib/api";
import { FuzzRequest, TaskStatus, StatusResponse, CrashResult } from "@/lib/types";

type AppState = "idle" | "running" | "complete" | "error";

export default function Home() {
  const [appState, setAppState] = useState<AppState>("idle");
  const [taskId, setTaskId] = useState<string | null>(null);
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [terminalLines, setTerminalLines] = useState<string[]>([]);
  const [pollInterval, setPollInterval] = useState<NodeJS.Timeout | null>(null);
  // const lastLogCountRef = useRef<number>(0);

  // Submit fuzzing job
  const handleSubmitJob = async (request: FuzzRequest) => {
    try {
      setAppState("running");
      setTerminalLines([]);
      setStatus(null);

      const validation = await validateTarget(request.target_openapi_url);
    
      if (validation.status === "error") {
        throw new Error(validation.message || "Target is unreachable");
      }

      const response = await submitFuzzJob(request);
      setTaskId(response.task_id);

      // Log initial submission
      setTerminalLines((prev) => [
        ...prev,
        `[*] Fuzzing job submitted: ${response.task_id}`,
        `[*] URL: ${request.target_openapi_url}`,
        `[*] Waiting for fuzzing to start...`,
      ]);

      // Start polling
      startPolling(response.task_id);
    } catch (error) {
      setAppState("error");
      const message = error instanceof Error ? error.message : "Unknown error";
      setTerminalLines((prev) => [...prev, `[!] Error: ${message}`]);
    }
  };

  // Poll job status
  const startPolling = (id: string) => {
    const interval = setInterval(() => {
      pollStatus(id);
    }, 3000);
    setPollInterval(interval);
  };

  const pollStatus = async (id: string) => {
    try {
      const response = await getJobStatus(id);
      setStatus(response);

      if (response.logs) {
        const realLogLines = response.logs.split("\n").filter(line => line.trim() !== "");
        
        setTerminalLines([
          `[*] Fuzzing job submitted: ${id}`,
          `[*] Waiting for fuzzing to start...`,
          ...realLogLines
        ]);
      } else {
        // Fallback progress indicator if logs haven't initialized yet
        setTerminalLines((prev) => {
          if (prev.some(l => l.includes("Progress:"))) return prev;
          return [
            ...prev,
            `[*] Progress: ${response.total_tests_run} operations mapped...`
          ];
        });
      } 

      if (response.status === TaskStatus.SUCCESS) {
        setAppState("complete");
        
        if (response.logs) {
          const finalLogLines = response.logs.split("\n").filter(line => line.trim() !== "");
          setTerminalLines([
            `[*] Fuzzing job submitted: ${id}`,
            ...finalLogLines,
            `[✓] Fuzzing complete!`,
            `[✓] Total operations reported: ${response.total_tests_run}`,
            `[✓] Total target crashes found: ${response.total_crashes}`,
          ]);
        }

        if (pollInterval) clearInterval(pollInterval);
      } else if (response.status === TaskStatus.FAILED) {
        setAppState("error");
        setTerminalLines((prev) => [
          ...prev,
          `[!] Fuzzing failed: ${response.error}`,
        ]);
        if (pollInterval) clearInterval(pollInterval);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setTerminalLines((prev) => [...prev, `[!] Error: ${message}`]);
    }
  };

  // Handle cancel
  const handleCancel = async () => {
    if (!taskId) return;

    try {
      await cancelJob(taskId);
      setAppState("idle");
      setTaskId(null);
      setStatus(null);
      setTerminalLines([]);
      if (pollInterval) clearInterval(pollInterval);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setTerminalLines((prev) => [...prev, `[!] Cancel failed: ${message}`]);
    }
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (pollInterval) clearInterval(pollInterval);
    };
  }, [pollInterval]);

  return (
    <main className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="text-center mb-12">
          <h1 className="text-4xl font-bold text-gray-900 mb-2">Black-Box Fuzzer</h1>
          <p className="text-lg text-gray-600">
            Test your staging APIs for 5xx errors via OpenAPI/Swagger
          </p>
        </div>

        {/* Idle State - Form */}
        {appState === "idle" && (
          <div className="bg-white rounded-lg shadow-lg p-8 space-y-6">
            <FuzzerForm onSubmit={handleSubmitJob} />
          </div>
        )}

        {/* Running State - Progress */}
        {appState === "running" && status && (
          <div className="bg-white rounded-lg shadow-lg p-8 space-y-6">
            <div className="flex justify-between items-center">
              <h2 className="text-2xl font-bold text-gray-900">Fuzzing in Progress</h2>
              <button
                onClick={handleCancel}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors text-sm font-medium"
              >
                Cancel
              </button>
            </div>

            <TestCounter
              count={status.total_tests_run}
            />

            <TerminalOutput
              lines={terminalLines}
              isActive={appState === "running"}
            />

            {/* Live Crash Updates */}
            {status.total_crashes > 0 && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                <h3 className="text-sm font-semibold text-red-900 mb-2">
                  ⚠️ Crashes Detected ({status.total_crashes})
                </h3>
                <div className="space-y-2">
                  {status.crashes.slice(-3).map((crash, idx) => (
                    <div key={idx} className="text-sm text-red-700">
                      <strong>{crash.method}</strong> {crash.path} →{" "}
                      <span className="font-mono">{crash.status_code}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Complete State - Results */}
        {appState === "complete" && status && (
          <div className="bg-white rounded-lg shadow-lg p-8 space-y-6">
            <div className="flex justify-between items-center">
              <h2 className="text-2xl font-bold text-gray-900">Fuzzing Complete</h2>
              <button
                onClick={() => {
                  setAppState("idle");
                  setTaskId(null);
                  setStatus(null);
                  setTerminalLines([]);
                }}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
              >
                New Test
              </button>
            </div>

            <Dashboard
              totalTests={status.total_tests_run}
              totalCrashes={status.total_crashes}
              crashes={status.crashes}
              curlCommands={status.curl_commands}
            />
          </div>
        )}

        {/* Error State */}
        {appState === "error" && (
          <div className="bg-white rounded-lg shadow-lg p-8">
            <div className="bg-red-50 border border-red-200 rounded-lg p-6 mb-6">
              <h2 className="text-lg font-semibold text-red-900 mb-2">Fuzzing Failed</h2>
              <p className="text-red-700">{status?.error || "An unknown error occurred"}</p>
            </div>

            {terminalLines.length > 0 && (
              <TerminalOutput lines={terminalLines} isActive={false} />
            )}

            <button
              onClick={() => {
                setAppState("idle");
                setTaskId(null);
                setStatus(null);
                setTerminalLines([]);
              }}
              className="mt-6 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              Back to Home
            </button>
          </div>
        )}

        {/* Footer */}
        <div className="text-center mt-12 text-gray-600 text-sm">
          <p>
            ⚠️ Only use on APIs you own. Fuzzing may cause errors and modify data.
          </p>
        </div>
      </div>
    </main>
  );
}
