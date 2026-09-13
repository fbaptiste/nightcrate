/**
 * Drives the frame-quality analysis run from the client (v0.41.3).
 *
 * A full pass over a real library is a couple of hundred gigabytes and several
 * minutes, which is far too long to hold one request open with nothing but a
 * spinner. Rather than introduce the app's first background task, the run is
 * driven from here: fetch the pending ids once, then POST them back in batches.
 * Each batch is an ordinary short request, so progress, cancel and
 * resume-where-it-stopped all fall out for free — a cancelled or abandoned run
 * simply leaves the remaining frames pending, and the next click picks them up.
 *
 * Cancel is checked between batches, so it lands within a few seconds rather
 * than instantly. That's the cost of not being able to abort work already
 * dispatched to the worker pool, and it's the right trade: a half-analyzed
 * batch would otherwise be wasted.
 */
import { useCallback, useRef, useState } from "react";

import {
  analyzeFrames,
  fetchQualityPending,
  type QualityAnalyzeResult,
} from "../api/projectCatalog";

/**
 * Frames per request. Measured on the real library, lights run ~0.16 s/frame in
 * wall clock across the pool (276 analyzed in ~45 s on 12 workers), so a batch is
 * ~10 s — responsive enough for a live progress bar and for cancel to feel
 * prompt, while still amortizing the ~0.3-0.6 s pool spawn each request pays.
 * That spawn is ~10 % of a lights batch and closer to 25 % on the ADU-only
 * calibration path; raising this to 120-240 would cut the churn at the cost of
 * cancel latency. Left at 60 deliberately — cancel responsiveness wins until
 * someone complains about throughput.
 */
const BATCH_SIZE = 60;

/** Batches to average when estimating time remaining. */
const RATE_WINDOW = 5;

export interface AnalyzeProgress {
  running: boolean;
  /** Frames the server accounted for this run (analyzed + unreadable + skipped).
   *  `skipped` is inert in practice — the pending fetch and the analyze POST use
   *  the same `force` flag — but it is counted so the bar can never stall. */
  done: number;
  /** Frames this run set out to process. */
  total: number;
  analyzed: number;
  noStars: number;
  unreadable: number;
  /** Seconds remaining, or null before there's enough data to estimate. */
  etaSeconds: number | null;
  errors: string[];
}

const IDLE: AnalyzeProgress = {
  running: false,
  done: 0,
  total: 0,
  analyzed: 0,
  noStars: 0,
  unreadable: 0,
  etaSeconds: null,
  errors: [],
};

export interface AnalyzeScope {
  frameType: string | null;
  filterName: string | null;
}

export function useAnalyzeRun(
  projectId: number,
  onFinished?: (p: AnalyzeProgress) => void,
) {
  const [progress, setProgress] = useState<AnalyzeProgress>(IDLE);
  const cancelRef = useRef(false);

  const cancel = useCallback(() => {
    cancelRef.current = true;
  }, []);

  const start = useCallback(
    async (scope: AnalyzeScope, force = false) => {
      cancelRef.current = false;
      setProgress({ ...IDLE, running: true });

      let ids: number[];
      try {
        const pending = await fetchQualityPending(
          projectId,
          scope.frameType,
          scope.filterName,
          force,
        );
        ids = pending.frame_ids;
      } catch (e) {
        const p = {
          ...IDLE,
          errors: [e instanceof Error ? e.message : String(e)],
        };
        setProgress(p);
        onFinished?.(p);
        return p;
      }

      const acc: AnalyzeProgress = { ...IDLE, running: true, total: ids.length };
      // Rolling window of (frames, ms) so the ETA reflects recent throughput
      // rather than a run-long average — file sizes and disk speed vary.
      const recent: { frames: number; ms: number }[] = [];

      for (let i = 0; i < ids.length; i += BATCH_SIZE) {
        if (cancelRef.current) break;
        const batch = ids.slice(i, i + BATCH_SIZE);
        const t0 = performance.now();
        let res: QualityAnalyzeResult;
        try {
          res = await analyzeFrames(projectId, batch, force);
        } catch (e) {
          // A whole batch failing (409, backend restart, network) ends the run
          // rather than hammering the remaining thousands of frames.
          acc.errors.push(e instanceof Error ? e.message : String(e));
          break;
        }
        recent.push({ frames: batch.length, ms: performance.now() - t0 });
        if (recent.length > RATE_WINDOW) recent.shift();

        acc.analyzed += res.analyzed;
        acc.noStars += res.no_stars;
        acc.unreadable += res.unreadable;
        acc.done += res.analyzed + res.unreadable + res.skipped;
        if (res.errors.length && acc.errors.length < 20) {
          acc.errors.push(...res.errors.slice(0, 20 - acc.errors.length));
        }

        const totalFrames = recent.reduce((n, r) => n + r.frames, 0);
        const totalMs = recent.reduce((n, r) => n + r.ms, 0);
        acc.etaSeconds =
          totalFrames > 0 && acc.done < acc.total
            ? Math.round(((acc.total - acc.done) * (totalMs / totalFrames)) / 1000)
            : null;
        setProgress({ ...acc });
      }

      const final = { ...acc, running: false, etaSeconds: null };
      setProgress(final);
      onFinished?.(final);
      return final;
    },
    [projectId, onFinished],
  );

  return { progress, start, cancel };
}
