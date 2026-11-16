import { isDesktopShell } from "@/lib/desktopShell";

export interface Coordinates {
  latitude: number;
  longitude: number;
}

/** A failed lookup; its message is shown as is, and an empty one isn't shown. */
export class LocationError extends Error {}

const LOOKUP = "use Lookup Coordinates from Address";

// The Mac app asks macOS itself (`packaging/shell/src-tauri/src/location.rs`):
// WebKit in an app window can't fetch a location (Fred, 2026-11-15).
const DESKTOP_MESSAGES: Record<string, string> = {
  denied: `NightCrate isn't allowed to use your location. Allow it in System Settings → Privacy & Security → Location Services, or ${LOOKUP}.`,
  restricted: `Location access is restricted on this Mac. Enter the coordinates, or ${LOOKUP}.`,
  services_off: `Location Services is off. Turn it on in System Settings → Privacy & Security → Location Services, or ${LOOKUP}.`,
  no_answer: `macOS didn't answer the location request. Check NightCrate under System Settings → Privacy & Security → Location Services, or ${LOOKUP}.`,
  timeout: `Finding your location took too long. Try again, or ${LOOKUP}.`,
  unavailable: `Your location isn't available right now. Try again, or ${LOOKUP}.`,
  // A newer request replaced this one; that one reports.
  cancelled: "",
};

const BROWSER_MESSAGES: Record<number, string> = {
  1: `Location access was refused. Allow it in your browser or system settings, or ${LOOKUP}.`,
  2: `Your location isn't available. Check that location services are on, or ${LOOKUP}.`,
  3: `Finding your location took too long. Try again, or ${LOOKUP}.`,
};

function browserLocation(): Promise<Coordinates> {
  if (!navigator.geolocation) {
    return Promise.reject(new LocationError(`This browser can't share your location; ${LOOKUP}.`));
  }
  return new Promise((resolve, reject) =>
    navigator.geolocation.getCurrentPosition(
      (position) =>
        resolve({ latitude: position.coords.latitude, longitude: position.coords.longitude }),
      (error) =>
        reject(new LocationError(BROWSER_MESSAGES[error.code] ?? `Couldn't find your location; ${LOOKUP}.`)),
      { enableHighAccuracy: true, timeout: 10000 },
    ),
  );
}

/**
 * The computer's position. In the Mac app, the app asks macOS (the first
 * time, macOS asks the user); elsewhere, the browser's request.
 */
export async function currentLocation(): Promise<Coordinates> {
  const invoke = isDesktopShell() ? window.__TAURI__?.core?.invoke : undefined;
  if (invoke) {
    try {
      const fix = await invoke<Coordinates>("current_location");
      return { latitude: fix.latitude, longitude: fix.longitude };
    } catch (code) {
      // Windows and Linux answer "unsupported": their window can use the
      // browser's request.
      if (code !== "unsupported") {
        throw new LocationError(DESKTOP_MESSAGES[String(code)] ?? DESKTOP_MESSAGES.unavailable);
      }
    }
  }
  return browserLocation();
}
