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
 * Frames per request. At roughly 0.5 s/frame across the worker pool this is a
 * few seconds per batch — responsive enough for a live progress bar and for
 * cancel to feel prompt, while still amortizing the pool spawn.
 */
const BATCH_SIZE = 60;

/** Batches to average when estimating time remaining. */
const RATE_WINDOW = 5;

export interface AnalyzeProgress {
  running: boolean;
  /** Frames processed in this run (analyzed + unreadable). */
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
