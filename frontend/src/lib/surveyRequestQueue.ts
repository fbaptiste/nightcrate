interface SurveyQueueRequest<T> {
  messierNumber: number;
  distance: () => number;
  signal: AbortSignal;
  run: (signal: AbortSignal) => Promise<T>;
}

interface QueuedRequest {
  messierNumber: number;
  distance: () => number;
  signal: AbortSignal;
  run: (signal: AbortSignal) => Promise<unknown>;
  resolve: (value: unknown) => void;
  reject: (reason: unknown) => void;
  abortController: AbortController | null;
  onAbort: () => void;
  running: boolean;
  settled: boolean;
}

const MAX_IN_FLIGHT = 3;

function abortError() {
  return new DOMException("The survey request was aborted", "AbortError");
}

export class SurveyRequestQueue {
  private waiting: QueuedRequest[] = [];
  private inFlight = 0;

  enqueue<T>(request: SurveyQueueRequest<T>): Promise<T> {
    if (request.signal.aborted) return Promise.reject(abortError());

    return new Promise<T>((resolve, reject) => {
      const queued: QueuedRequest = {
        ...request,
        run: request.run,
        resolve: (value) => resolve(value as T),
        reject,
        abortController: null,
        onAbort: () => this.cancel(queued),
        running: false,
        settled: false,
      };
      request.signal.addEventListener("abort", queued.onAbort, { once: true });
      this.waiting.push(queued);
      this.pump();
    });
  }

  private cancel(request: QueuedRequest) {
    if (request.settled) return;
    if (request.running) {
      request.abortController?.abort();
      return;
    }

    const index = this.waiting.indexOf(request);
    if (index >= 0) this.waiting.splice(index, 1);
    request.settled = true;
    request.signal.removeEventListener("abort", request.onAbort);
    request.reject(abortError());
  }

  private pump() {
    while (this.inFlight < MAX_IN_FLIGHT && this.waiting.length > 0) {
      let bestIndex = 0;
      for (let index = 1; index < this.waiting.length; index += 1) {
        const candidate = this.waiting[index];
        const best = this.waiting[bestIndex];
        const candidateDistance = candidate.distance();
        const bestDistance = best.distance();
        if (
          candidateDistance < bestDistance ||
          (candidateDistance === bestDistance && candidate.messierNumber < best.messierNumber)
        ) {
          bestIndex = index;
        }
      }

      const request = this.waiting.splice(bestIndex, 1)[0];
      request.running = true;
      request.abortController = new AbortController();
      this.inFlight += 1;
      void request.run(request.abortController.signal).then(
        (value) => this.finish(request, true, value),
        (reason) => this.finish(request, false, reason),
      );
    }
  }

  private finish(request: QueuedRequest, succeeded: boolean, result: unknown) {
    if (request.settled) return;
    request.settled = true;
    request.signal.removeEventListener("abort", request.onAbort);
    this.inFlight -= 1;
    if (succeeded) request.resolve(result);
    else request.reject(result);
    this.pump();
  }
}
