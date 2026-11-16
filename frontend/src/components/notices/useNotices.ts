import { useCallback, useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  checkForUpdates,
  dismissNotice,
  fetchUpdates,
  setCheckAutomatically,
  type NoticeAction,
  type NoticeId,
  type UpdateNotice,
} from "@/api/updates";
import { testAutoInstallEnabled } from "@/lib/desktopShell";

export function useNotices(onAutoInstall?: (notice: UpdateNotice) => Promise<boolean>) {
  const queryClient = useQueryClient();
  const checking = useRef(false);
  const autoInstalling = useRef(false);
  const autoAttempts = useRef(0);
  const query = useQuery({ queryKey: ["updates"], queryFn: fetchUpdates });

  const refresh = useCallback(async () => {
    if (checking.current) return;
    checking.current = true;
    try {
      const status = await checkForUpdates();
      queryClient.setQueryData(["updates"], status);
    } finally {
      checking.current = false;
    }
  }, [queryClient]);

  useEffect(() => {
    const checkIfDue = () => {
      const status = queryClient.getQueryData<Awaited<ReturnType<typeof fetchUpdates>>>(["updates"]);
      if (document.visibilityState === "visible" && status?.check_due) void refresh();
    };
    checkIfDue();
    document.addEventListener("visibilitychange", checkIfDue);
    return () => document.removeEventListener("visibilitychange", checkIfDue);
  }, [query.data?.check_due, queryClient, refresh]);

  useEffect(() => {
    if (!onAutoInstall) return;
    let active = true;
    let timer: number | undefined;
    void testAutoInstallEnabled().then(async (enabled) => {
      if (!enabled || !active) return;
      const tick = async () => {
        if (!active || autoInstalling.current || autoAttempts.current >= 3) return;
        await setCheckAutomatically(true);
        const status = await checkForUpdates();
        queryClient.setQueryData(["updates"], status);
        const notice = status.notices.find((item) => item.id === "app" && item.installable);
        if (notice) {
          autoInstalling.current = true;
          const succeeded = await onAutoInstall(notice);
          autoInstalling.current = false;
          if (!succeeded) autoAttempts.current += 1;
          timer = window.setTimeout(tick, succeeded ? 5_000 : 10_000);
        } else {
          timer = window.setTimeout(tick, 5_000);
        }
      };
      await tick();
    });
    return () => {
      active = false;
      if (timer != null) window.clearTimeout(timer);
    };
  }, [onAutoInstall, queryClient]);

  const dismiss = useCallback(async (id: NoticeId, action: NoticeAction) => {
    const status = await dismissNotice(id, action);
    queryClient.setQueryData(["updates"], status);
  }, [queryClient]);

  return { status: query.data, dismiss, refresh };
}
