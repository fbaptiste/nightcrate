export interface InstallProgress {
  stage: "downloading" | "installing" | "restarting";
  downloaded?: number;
  total?: number;
}

export interface InstallFailure {
  stage: "busy" | "download" | "launch" | "install";
  message: string;
}

type Unlisten = () => void;

declare global {
  interface Window {
    __TAURI__?: {
      core?: { invoke<T>(command: string, args?: Record<string, unknown>): Promise<T> };
      event?: {
        listen<T>(event: string, cb: (event: { payload: T }) => void): Promise<Unlisten>;
      };
    };
  }
}

export function isDesktopShell(): boolean {
  return typeof window !== "undefined" && typeof window.__TAURI__?.core?.invoke === "function";
}

export async function installUpdate(
  version: string,
  token: string,
  onProgress: (progress: InstallProgress) => void,
): Promise<void> {
  const bridge = window.__TAURI__;
  if (!bridge?.core?.invoke || !bridge.event?.listen) {
    throw { stage: "busy", message: "The desktop update bridge is unavailable." } satisfies InstallFailure;
  }
  let unlisten: Unlisten;
  try {
    unlisten = await bridge.event.listen<InstallProgress>("update-progress", (event) => {
      onProgress(event.payload);
    });
  } catch {
    throw { stage: "busy", message: "The desktop update bridge is unavailable." } satisfies InstallFailure;
  }
  try {
    await bridge.core.invoke("install_update", { expectedVersion: version, token });
  } finally {
    unlisten();
  }
}

export function onDownloadSaved(cb: (path: string) => void): () => void {
  let active = true;
  let unlisten: Unlisten | undefined;
  const listener = window.__TAURI__?.event?.listen<string>("download-saved", (event) => cb(event.payload));
  if (listener) {
    void listener.then((stop) => {
      if (active) unlisten = stop;
      else stop();
    }).catch(() => undefined);
  }
  return () => {
    active = false;
    unlisten?.();
  };
}

export async function testAutoInstallEnabled(): Promise<boolean> {
  if (new URLSearchParams(window.location.search).get("nc-test-autoinstall") !== "1") return false;
  try {
    return await window.__TAURI__?.core?.invoke<boolean>("test_auto_install_enabled") === true;
  } catch {
    return false;
  }
}
