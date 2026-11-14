import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { SlideshowSeconds } from "@/api/settings";
import { intervalNote, stepInterval } from "./slideshow";

interface Options {
  count: number;
  seconds: SlideshowSeconds;
  onAdvance: () => void;
  onSecondsChange: (seconds: SlideshowSeconds) => void;
}

export function useSlideshow({ count, seconds, onAdvance, onSecondsChange }: Options) {
  const [playing, setPlaying] = useState(false);
  const [pictureShown, setPictureShown] = useState(false);
  const [controlsVisible, setControlsVisible] = useState(true);
  const [note, setNote] = useState<string | null>(null);
  const playingRef = useRef(false);
  const pictureShownRef = useRef(false);
  const hoveringRef = useRef(false);
  const mountedRef = useRef(true);
  const secondsRef = useRef(seconds);
  const countRef = useRef(count);
  const onAdvanceRef = useRef(onAdvance);
  const onSecondsChangeRef = useRef(onSecondsChange);
  const countdownRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hideRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const noteRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wakeLockRef = useRef<WakeLockSentinel | null>(null);

  useLayoutEffect(() => {
    secondsRef.current = seconds;
    countRef.current = count;
    onAdvanceRef.current = onAdvance;
    onSecondsChangeRef.current = onSecondsChange;
  }, [count, onAdvance, onSecondsChange, seconds]);

  const clearCountdown = useCallback(() => {
    if (countdownRef.current != null) clearTimeout(countdownRef.current);
    countdownRef.current = null;
  }, []);

  const startCountdown = useCallback(() => {
    clearCountdown();
    if (!playingRef.current || !pictureShownRef.current || countRef.current <= 1) return;
    countdownRef.current = setTimeout(() => {
      countdownRef.current = null;
      if (playingRef.current && pictureShownRef.current && mountedRef.current) {
        onAdvanceRef.current();
      }
    }, secondsRef.current * 1000);
  }, [clearCountdown]);

  const scheduleHide = useCallback(() => {
    if (hideRef.current != null) clearTimeout(hideRef.current);
    hideRef.current = null;
    if (!playingRef.current || hoveringRef.current) return;
    hideRef.current = setTimeout(() => {
      hideRef.current = null;
      if (playingRef.current && !hoveringRef.current && mountedRef.current) {
        setControlsVisible(false);
      }
    }, 3000);
  }, []);

  const poke = useCallback(() => {
    setControlsVisible(true);
    scheduleHide();
  }, [scheduleHide]);

  const pause = useCallback(() => {
    playingRef.current = false;
    setPlaying(false);
    clearCountdown();
    if (hideRef.current != null) clearTimeout(hideRef.current);
    hideRef.current = null;
    setControlsVisible(true);
  }, [clearCountdown]);

  const toggle = useCallback(() => {
    if (playingRef.current) {
      pause();
      return;
    }
    if (countRef.current <= 1) return;
    playingRef.current = true;
    setPlaying(true);
    setControlsVisible(true);
    startCountdown();
    scheduleHide();
  }, [pause, scheduleHide, startCountdown]);

  const notePictureChanged = useCallback(() => {
    pictureShownRef.current = false;
    setPictureShown(false);
    clearCountdown();
  }, [clearCountdown]);

  const notePictureShown = useCallback(() => {
    pictureShownRef.current = true;
    setPictureShown(true);
    startCountdown();
  }, [startCountdown]);

  const changeInterval = useCallback((delta: 1 | -1) => {
    const result = stepInterval(secondsRef.current, delta);
    secondsRef.current = result.seconds;
    onSecondsChangeRef.current(result.seconds);
    setNote(intervalNote(result.seconds, result.atEnd, delta));
    if (noteRef.current != null) clearTimeout(noteRef.current);
    noteRef.current = setTimeout(() => {
      noteRef.current = null;
      if (mountedRef.current) setNote(null);
    }, 1200);
    startCountdown();
  }, [startCountdown]);

  const hideNow = useCallback(() => {
    if (!playingRef.current) return;
    if (hideRef.current != null) clearTimeout(hideRef.current);
    hideRef.current = null;
    setControlsVisible(false);
  }, []);

  const setHover = useCallback((hovering: boolean) => {
    hoveringRef.current = hovering;
    if (hovering) {
      if (hideRef.current != null) clearTimeout(hideRef.current);
      hideRef.current = null;
      setControlsVisible(true);
    } else {
      scheduleHide();
    }
  }, [scheduleHide]);

  useEffect(() => {
    if (count > 1 || !playingRef.current) return;
    let active = true;
    queueMicrotask(() => {
      if (active) pause();
    });
    return () => { active = false; };
  }, [count, pause]);

  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === "hidden") pause();
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => document.removeEventListener("visibilitychange", handleVisibility);
  }, [pause]);

  useEffect(() => {
    if (!playing) return;
    let active = true;
    void (async () => {
      try {
        const lock = await navigator.wakeLock?.request("screen");
        if (!lock) return;
        if (!active || !playingRef.current || document.visibilityState === "hidden") {
          await lock.release();
          return;
        }
        wakeLockRef.current = lock;
      } catch {
        // Unsupported, insecure or refused wake locks leave normal sleep in place.
      }
    })();
    return () => {
      active = false;
      const lock = wakeLockRef.current;
      wakeLockRef.current = null;
      if (lock) void lock.release().catch(() => undefined);
    };
  }, [playing]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      clearCountdown();
      if (hideRef.current != null) clearTimeout(hideRef.current);
      if (noteRef.current != null) clearTimeout(noteRef.current);
      const lock = wakeLockRef.current;
      wakeLockRef.current = null;
      if (lock) void lock.release().catch(() => undefined);
    };
  }, [clearCountdown]);

  return {
    playing,
    toggle,
    pause,
    pictureShown,
    notePictureShown,
    notePictureChanged,
    changeInterval,
    controlsVisible,
    poke,
    hideNow,
    setHover,
    note,
  };
}
