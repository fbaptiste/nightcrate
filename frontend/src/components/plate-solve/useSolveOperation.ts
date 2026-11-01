import { useCallback, useEffect, useRef, useState } from "react";

import {
  cancelSolve,
  fetchSolveProgress,
  type PlateSolveRequest,
  type PlateSolveResult,
  type PlateSolver,
  type ProgressSnapshot,
  type SolveAttempt,
} from "@/api/plateSolve";

export type SolveOutcome =
  | { kind: "solved"; result: PlateSolveResult }
  | { kind: "failed"; message: string; failureReason: string | null; attempts: SolveAttempt[] };

export interface FailureState {
  message: string;
  failureReason: string | null;
  attempts: SolveAttempt[];
  solver: PlateSolver;
}

interface Options {
  image: { path: string; hdu: number };
  active: boolean;
  solveRequest: (request: PlateSolveRequest) => Promise<SolveOutcome>;
  onSolved: (result: PlateSolveResult) => void;
  onStale: () => void;
}

interface Token {
  id: string;
  path: string;
  hdu: number;
  stale: boolean;
}

export function useSolveOperation({ image, active, solveRequest, onSolved, onStale }: Options) {
  const tokenRef = useRef<Token | null>(null);
  const mountedRef = useRef(true);
  const progressRef = useRef<ProgressSnapshot | null>(null);
  const [status, setStatus] = useState<"idle" | "solving" | "failed">("idle");
  const [progress, setProgress] = useState<ProgressSnapshot | null>(null);
  const [failure, setFailure] = useState<FailureState | null>(null);
  const [lastSolver, setLastSolver] = useState<PlateSolver | null>(null);
  const latestAttempts = useCallback(() => progressRef.current?.attempts ?? [], []);

  const dismissCurrent = useCallback(() => {
    const token = tokenRef.current;
    if (!token) return;
    token.stale = true;
    tokenRef.current = null;
    void cancelSolve(token.id).catch(() => undefined);
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      dismissCurrent();
    };
  }, [dismissCurrent]);

  useEffect(() => {
    dismissCurrent();
    if (mountedRef.current) {
      setStatus("idle");
      setProgress(null);
      progressRef.current = null;
      setFailure(null);
      setLastSolver(null);
    }
  }, [image.path, image.hdu, dismissCurrent]);

  useEffect(() => {
    if (!active) {
      dismissCurrent();
      setStatus("idle");
      setProgress(null);
      progressRef.current = null;
      setFailure(null);
    }
  }, [active, dismissCurrent]);

  const run = useCallback(
    async (request: PlateSolveRequest) => {
      dismissCurrent();
      const operationId = request.operation_id;
      if (!operationId) throw new Error("A plate-solve operation ID is required.");
      const solver = request.solver ?? "native";
      const token: Token = { id: operationId, path: image.path, hdu: image.hdu, stale: false };
      tokenRef.current = token;
      setLastSolver(solver);
      setStatus("solving");
      setFailure(null);
      setProgress(null);
      progressRef.current = null;

      let requestedPoll = 0;
      let appliedPoll = 0;
      const poll = async () => {
        const sequence = ++requestedPoll;
        try {
          const next = await fetchSolveProgress(operationId);
          if (
            sequence > appliedPoll &&
            tokenRef.current === token &&
            !token.stale &&
            mountedRef.current
          ) {
            appliedPoll = sequence;
            progressRef.current = next;
            setProgress(next);
          }
        } catch {
          // A request can reach the progress endpoint before the solve claims its slot.
        }
      };
      void poll();
      const interval = window.setInterval(poll, 1000);
      try {
        const outcome = await solveRequest(request);
        const current = tokenRef.current === token && !token.stale && mountedRef.current;
        if (!current) {
          onStale();
          return;
        }
        if (outcome.kind === "solved") {
          setProgress(null);
          progressRef.current = null;
          setStatus("idle");
          onSolved(outcome.result);
        } else {
          const attempts = outcome.attempts.length
            ? outcome.attempts
            : latestAttempts();
          setProgress(null);
          progressRef.current = null;
          setFailure({ ...outcome, attempts, solver });
          setStatus("failed");
        }
      } catch (error: unknown) {
        if (tokenRef.current !== token || token.stale || !mountedRef.current) {
          onStale();
          return;
        }
        const attempts = latestAttempts();
        setProgress(null);
        progressRef.current = null;
        setFailure({
          message: error instanceof Error ? error.message : String(error),
          failureReason: "error",
          attempts,
          solver,
        });
        setStatus("failed");
      } finally {
        window.clearInterval(interval);
        if (tokenRef.current === token) tokenRef.current = null;
      }
    },
    [dismissCurrent, image.hdu, image.path, latestAttempts, onSolved, onStale, solveRequest],
  );

  const cancel = useCallback(() => {
    const token = tokenRef.current;
    if (token) void cancelSolve(token.id).catch(() => undefined);
  }, []);

  const reset = useCallback(() => {
    setStatus("idle");
    setFailure(null);
    setProgress(null);
    progressRef.current = null;
  }, []);

  return { status, progress, failure, lastSolver, run, cancel, reset };
}
