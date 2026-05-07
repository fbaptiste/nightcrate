import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Autocomplete from "@mui/material/Autocomplete";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import FormControlLabel from "@mui/material/FormControlLabel";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import CloseIcon from "@mui/icons-material/Close";
import DeleteIcon from "@mui/icons-material/Delete";
import EditIcon from "@mui/icons-material/Edit";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import MyLocationIcon from "@mui/icons-material/MyLocation";
import RestartAltIcon from "@mui/icons-material/RestartAlt";
import SearchIcon from "@mui/icons-material/Search";
import StarIcon from "@mui/icons-material/Star";
import StarOutlineIcon from "@mui/icons-material/StarOutline";
import {
  fetchLocations,
  fetchTimezones,
  fetchGeoTimezone,
  lookupClearOutside,
  createLocation,
  updateLocation,
  setDefaultLocation,
  deleteLocation,
  type Location,
  type LocationCreate,
} from "@/api/locations";
import { EasterEggWand } from "@/components/EasterEggWand";
import HorizonChart from "@/components/locations/HorizonChart";
import LocationHorizonsSection from "@/components/locations/LocationHorizonsSection";
import { fetchHorizons, replaceLocationHorizons } from "@/api/horizons";
import {
  fromServerRow,
  hasDirtyHorizons,
  seedNewLocationDefault,
  toCreateSeeds,
  toReplaceItems,
  type StagedHorizon,
} from "@/components/locations/horizonStaging";
import { parseOptionalFloat, parseOptionalInt } from "@/lib/formUtils";
import type { WeatherUnits } from "@/api/settings";
import { useSettingsStore } from "@/stores/settingsStore";

function formsDiffer(a: FormState, b: FormState): boolean {
  const keys = Object.keys(a) as (keyof FormState)[];
  for (const k of keys) {
    if (a[k] !== b[k]) return true;
  }
  return false;
}

// ─── Display helpers ────────────────────────────────────────────────────────
// Frontend mirror of backend services/coordinate_format.py for the live
// editor preview. Saved locations use the backend-formatted strings on
// `Location.latitude_display` / `longitude_display`.
const M_TO_FT = 3.28084;
const metersToFeet = (m: number): number => m * M_TO_FT;
const feetToMeters = (ft: number): number => ft / M_TO_FT;

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

function formatDMS(absDeg: number): string {
  const totalSec = Math.round(absDeg * 3600);
  const d = Math.floor(totalSec / 3600);
  const rem = totalSec - d * 3600;
  const m = Math.floor(rem / 60);
  const s = rem - m * 60;
  const dPart = d < 10 ? `0${d}` : String(d);
  return `${dPart}\u00B0${pad2(m)}\u2032${pad2(s)}\u2033`;
}

function formatLatitudeLive(deg: number): string {
  if (isNaN(deg) || deg < -90 || deg > 90) return "";
  return `${formatDMS(Math.abs(deg))} ${deg >= 0 ? "N" : "S"}`;
}

function formatLongitudeLive(deg: number): string {
  if (isNaN(deg) || deg < -180 || deg > 180) return "";
  return `${formatDMS(Math.abs(deg))} ${deg >= 0 ? "E" : "W"}`;
}

/** Render elevation in both units; primary unit is the user's preference.
 *  The secondary (parenthesized) value renders in muted text.secondary. */
function formatElevationBoth(
  meters: number | null,
  units: WeatherUnits,
): React.ReactNode | null {
  if (meters == null) return null;
  const ft = Math.round(metersToFeet(meters));
  const m = Math.round(meters);
  const primary = units === "imperial" ? `${ft} ft` : `${m} m`;
  const secondary = units === "imperial" ? `(${m} m)` : `(${ft} ft)`;
  return (
    <>
      {primary}
      {"  "}
      <Typography component="span" variant="body2" color="text.secondary">
        {secondary}
      </Typography>
    </>
  );
}

/** Return the current UTC offset of an IANA timezone as "UTC-07:00". */
function formatUtcOffset(timezone: string | null | undefined): string {
  if (!timezone) return "";
  try {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: timezone,
      timeZoneName: "longOffset",
    }).formatToParts(new Date());
    const tzPart = parts.find((p) => p.type === "timeZoneName")?.value ?? "";
    // "GMT-07:00" / "GMT+00:00" — Intl uses "GMT" for offsets; prefer "UTC".
    // `formatToParts` returns just "GMT" for UTC itself; show "UTC+00:00" instead.
    if (tzPart === "GMT") return "UTC+00:00";
    return tzPart.replace(/^GMT/, "UTC");
  } catch {
    return "";
  }
}

const INCANTATIONS = [
  "I solemnly swear not to buy any new equipment this month",
  "sudo rm -rf /atmosphere/clouds/*",
  "Have you tried turning the clouds off and on again?",
  "Sacrificing a USB cable to the weather gods...",
  "Dear clouds, I have 10 hours of Ha to capture. Kindly move along.",
  "I promise to finally collimate the SCT if the skies clear",
  "Alexa, set weather to 'photons only'",
  "One does not simply image through clouds",
  "The seeing will be excellent. I have spoken.",
  "Plot twist: the forecast was wrong. It's clear!",
  "I'll polar align by drift if you just give me one clear night",
  "If the sky clears I won't complain about the dew. Much.",
  "Offering my firstborn meridian flip to the weather gods",
  "Clear Outside says 0% cloud. Clear Outside has never lied. Right?",
  "I didn't spend $3,000 on narrowband filters to image clouds",
  "The forecast said clear. My roof says otherwise.",
  "Checking Clear Outside for the 47th time today...",
  "Maybe if I set up all my gear the clouds will part out of spite",
  "I'll even image in LRGB if you just stop raining",
  "The clouds are just nature's flats. Very thick flats.",
  "My scope cost more than my car. The car works in any weather.",
  "I promise to process my backlog before taking new data. Please.",
  "The stars are always there. It's the atmosphere that's broken.",
  "Autoguiding through clouds: the feature no one asked for",
  "The sucker hole giveth, and the sucker hole taketh away",
  "Fun fact: my mount tracks perfectly on cloudy nights",
  "Astronomers don't have bad luck. They have weather.",
  "I just did a star adventurer setup. The universe will respond with clouds.",
  "PixInsight can't process what you can't capture",
  "The Moon is out AND it's cloudy? That's just showing off.",
  "New filter arrived today. Guaranteed 2 weeks of clouds.",
  "My neighbor's light is brighter than the Orion Nebula",
  "FITS header: WEATHER = 'WHY DO I LIVE HERE'",
  "I'm not crying, that's just dew on my corrector plate",
  "Petition to rename 'partly cloudy' to 'entirely useless'",
  "The seeing forecast said 1 arcsec. I think they meant 1 arcminute.",
  "Spent 4 hours setting up. Got 3 subs. Two had airplane trails.",
  "My wife thinks I'm crazy. The clouds agree.",
  "The only guaranteed clear night is the one you don't plan for",
  "Narrowband: because even light pollution needs a $200 solution per channel",
  "I'll take my flats tomorrow. I've been saying that for 6 months.",
  "Cloud sensor reading: YES",
  "Every pixel of this cloud photo cost me $0.47 in equipment depreciation",
  "PHD2 says 'no star selected'. Yes, PHD2, I noticed.",
  "I brought a friend to show them the stars. They saw a parking lot lamp.",
  "Just bought an observatory. Now I can watch it rain from inside.",
  "My dark library has more frames than my light library",
  "N.I.N.A. sequence: 200 subs planned, 0 completed, status: 'waiting for sky'",
  "Roses are red, violets are blue, it's cloudy again, what else is new",
  "Breaking: local man yells at cloud. Cloud does not move.",
  "The telescope is dewed up but my enthusiasm is bone dry",
  "Tonight's imaging target: the inside of a cloud deck",
  "Guiding RMS: N/A. Sky status: also N/A.",
  "Jet stream forecast: directly over your house, specifically",
  "The astronomy club meeting was clear. The actual night was not.",
  "I told my mount to park. It's the only thing that worked tonight.",
  "Step 1: Set up gear. Step 2: Clouds arrive. Step 3: See step 1.",
  "My imaging train is worth more than some people's cars",
  "Humidity: 97%. Dew point: right now. Tears: also right now.",
  "The weatherman and I are no longer on speaking terms",
  "Satellite trail count: still less than my regrets",
  "I've been waiting for clear skies since the last firmware update",
  "Object altitude: 72 degrees. Cloud altitude: all of them.",
  "My goto accuracy is better than the weather forecast accuracy",
  "Flat panel: ready. Bias frames: taken. Sky: personally offended.",
  "Just discovered a new deep sky object. It was a cloud.",
  "I can polar align in 2 minutes. I can't make it stop raining in 2 hours.",
  "My cooling fan works great. The atmosphere's cooling system, not so much.",
  "Tonight's integration time: 0 hours 0 minutes 0 seconds",
  "WiFi signal to the mount: 5 bars. Signal from the universe: 0 bars.",
  "Error: sky.clear() returned FALSE",
  "The only thing darker than a Bortle 1 sky is my mood right now",
  "Meridian flip completed successfully. Into more clouds.",
  "I name this cloud formation: 'The Horsehead of Disappointment'",
  "My filter wheel has 7 positions. Position 8 is for tears.",
  "Astronomer's prayer: give us this night our nightly subs",
];

interface FormState {
  name: string;
  latitude: string;
  longitude: string;
  // Elevation as typed by the user, in whichever unit they currently prefer
  // (meters or feet). Converted to meters at save time.
  elevation: string;
  timezone: string;
  geo_timezone: string;
  bortle_class: string;
  sqm_reading: string;
  typical_seeing_low_arcsec: string;
  typical_seeing_high_arcsec: string;
  city: string;
  state_province: string;
  country: string;
  postal_code: string;
  notes: string;
}

function emptyForm(): FormState {
  return {
    name: "",
    latitude: "",
    longitude: "",
    elevation: "",
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    geo_timezone: "",
    bortle_class: "",
    sqm_reading: "",
    typical_seeing_low_arcsec: "",
    typical_seeing_high_arcsec: "",
    city: "",
    state_province: "",
    country: "",
    postal_code: "",
    notes: "",
  };
}

/** Map an SQM (mag/arcsec²) reading to its Bortle class using the
 *  standard thresholds shared by the SQM input and Clear Outside lookup. */
function sqmToBortle(sqm: number): number {
  if (sqm >= 21.99) return 1;
  if (sqm >= 21.69) return 2;
  if (sqm >= 21.25) return 3;
  if (sqm >= 20.49) return 4;
  if (sqm >= 19.5) return 5;
  if (sqm >= 18.94) return 6;
  if (sqm >= 18.38) return 7;
  if (sqm >= 17.8) return 8;
  return 9;
}

function locationToForm(loc: Location, units: WeatherUnits): FormState {
  const elevDisplay =
    loc.elevation_m == null
      ? ""
      : units === "imperial"
      ? String(Math.round(metersToFeet(loc.elevation_m)))
      : String(Math.round(loc.elevation_m));
  return {
    name: loc.name,
    latitude: String(loc.latitude),
    longitude: String(loc.longitude),
    elevation: elevDisplay,
    timezone: loc.timezone,
    geo_timezone: loc.geo_timezone ?? "",
    bortle_class: loc.bortle_class != null ? String(loc.bortle_class) : "",
    sqm_reading: loc.sqm_reading != null ? String(loc.sqm_reading) : "",
    typical_seeing_low_arcsec: loc.typical_seeing_low_arcsec != null ? String(loc.typical_seeing_low_arcsec) : "",
    typical_seeing_high_arcsec: loc.typical_seeing_high_arcsec != null ? String(loc.typical_seeing_high_arcsec) : "",
    city: loc.city ?? "",
    state_province: loc.state_province ?? "",
    country: loc.country ?? "",
    postal_code: loc.postal_code ?? "",
    notes: loc.notes ?? "",
  };
}

export default function LocationsPage() {
  const queryClient = useQueryClient();
  const settings = useSettingsStore((s) => s.settings);
  const units: WeatherUnits = settings?.weather_units ?? "metric";
  const unitIsImperial = units === "imperial";
  const elevationUnitLabel = unitIsImperial ? "ft" : "m";
  const { data: locations = [], isLoading } = useQuery({
    queryKey: ["locations"],
    queryFn: fetchLocations,
  });

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingLocation, setEditingLocation] = useState<Location | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Partial<Record<keyof FormState, string>>>({});
  const [snack, setSnack] = useState<{ msg: string; severity: "info" | "error" } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Location | null>(null);
  const [detecting, setDetecting] = useState(false);
  const [lookingUp, setLookingUp] = useState(false);
  const [lookingUpClearOutside, setLookingUpClearOutside] = useState(false);
  const [seeingGuideOpen, setSeeingGuideOpen] = useState(false);
  const [geoTzEditable, setGeoTzEditable] = useState(false);
  const [geoTzWarningOpen, setGeoTzWarningOpen] = useState(false);
  // The OSM embed iframe picks a zoom to fit the bbox inside its current
  // pixel width at load time and never reflows. If the iframe mounts during
  // the Dialog open transition (which is the case in edit mode, where
  // coordinates are already populated), the tiles get rendered for the
  // pre-grow width and leave a gray gutter. Deferring the iframe mount
  // until `onEntered` fires guarantees it sees the final dialog width.
  const [dialogReady, setDialogReady] = useState(false);
  const [selectedLocationId, setSelectedLocationId] = useState<number | null>(null);
  // Snapshot of the form when the dialog opened, used for the Cancel
  // dirty check. Ref so it doesn't re-render.
  const originalFormRef = useRef<FormState>(emptyForm());
  const [confirmDiscardLocation, setConfirmDiscardLocation] = useState(false);
  // Staged horizons — the full desired horizon state the user sees in
  // the dialog. Mutated locally by LocationHorizonsSection; committed
  // to the server by ``handleSave``; discarded on Cancel. Restores the
  // v0.13.0 "outer Save owns everything" behaviour.
  const [stagedHorizons, setStagedHorizons] = useState<StagedHorizon[]>([]);
  const selectedLocation = selectedLocationId != null
    ? locations.find((l) => l.id === selectedLocationId) ?? null
    : null;
  // Deselect if the location was deleted from the list
  useEffect(() => {
    if (selectedLocationId != null && !locations.some((l) => l.id === selectedLocationId)) {
      setSelectedLocationId(null);
    }
  }, [locations, selectedLocationId]);
  const geoTzTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const { data: timezones = [] } = useQuery({
    queryKey: ["timezones"],
    queryFn: fetchTimezones,
    staleTime: Infinity,
  });

  // Fetch geo_timezone when coordinates change (debounced 500ms). The result
  // populates the Location Timezone field unless the user has explicitly
  // unlocked it — in that case we leave their manual choice alone.
  useEffect(() => {
    const lat = parseFloat(form.latitude);
    const lon = parseFloat(form.longitude);
    if (isNaN(lat) || isNaN(lon) || lat < -90 || lat > 90 || lon < -180 || lon > 180) {
      if (!geoTzEditable) setForm((prev) => ({ ...prev, geo_timezone: "" }));
      return;
    }
    clearTimeout(geoTzTimerRef.current);
    geoTzTimerRef.current = setTimeout(async () => {
      try {
        const result = await fetchGeoTimezone(lat, lon);
        if (geoTzEditable) return;
        setForm((prev) => ({
          ...prev,
          geo_timezone: result.geo_timezone ?? "",
          // Auto-populate display timezone on new location only
          timezone:
            !editingLocation &&
            prev.timezone === Intl.DateTimeFormat().resolvedOptions().timeZone &&
            result.geo_timezone
              ? result.geo_timezone
              : prev.timezone,
        }));
      } catch {
        if (!geoTzEditable) setForm((prev) => ({ ...prev, geo_timezone: "" }));
      }
    }, 500);
    return () => clearTimeout(geoTzTimerRef.current);
  }, [form.latitude, form.longitude]); // eslint-disable-line react-hooks/exhaustive-deps

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["locations"] });

  /** Fetch with retry on 429 (rate limit) and transient errors. */
  async function fetchWithRetry(
    url: string,
    options?: RequestInit,
    maxRetries = 2,
  ): Promise<Response | null> {
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        const res = await fetch(url, options);
        if (res.status === 429 && attempt < maxRetries) {
          await new Promise((r) => setTimeout(r, 1000 * (attempt + 1)));
          continue;
        }
        if (res.ok) return res;
        return null;
      } catch {
        if (attempt < maxRetries) {
          await new Promise((r) => setTimeout(r, 1000 * (attempt + 1)));
          continue;
        }
        return null;
      }
    }
    return null;
  }

  /** Reverse geocode: fill address fields from lat/lon. */
  async function reverseGeocode(lat: number, lon: number) {
    const res = await fetchWithRetry(
      `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lon}&format=json&zoom=14`,
      { headers: { "User-Agent": "NightCrate/1.0" } },
    );
    if (!res) {
      setSnack({ msg: "Address lookup failed — fill in manually", severity: "error" });
      return;
    }
    try {
      const geo = await res.json();
      const addr = geo.address ?? {};
      set("city", addr.city || addr.town || addr.village || addr.hamlet || "");
      set("state_province", addr.state || addr.province || addr.region || "");
      set("country", addr.country || "");
      set("postal_code", addr.postcode || "");
      if (!form.name.trim() && (addr.city || addr.town || addr.village)) {
        set("name", addr.city || addr.town || addr.village || "My Location");
      }
    } catch {
      setSnack({ msg: "Address lookup returned invalid data", severity: "error" });
    }
  }

  /** Fetch elevation from lat/lon. */
  async function fetchElevation(lat: number, lon: number) {
    const res = await fetchWithRetry(
      `https://api.open-meteo.com/v1/elevation?latitude=${lat}&longitude=${lon}`,
    );
    if (!res) {
      setSnack({ msg: "Elevation lookup failed", severity: "error" });
      return;
    }
    try {
      const data = await res.json();
      const elev = data.elevation?.[0];
      if (elev != null) {
        // Open-Meteo returns meters; round in the user's preferred unit.
        const display = unitIsImperial
          ? String(Math.round(metersToFeet(elev)))
          : String(Math.round(elev));
        set("elevation", display);
      }
    } catch {
      setSnack({ msg: "Elevation lookup returned invalid data", severity: "error" });
    }
  }

  /** Use browser geolocation → reverse geocode → elevation. */
  const detectLocation = async () => {
    if (!navigator.geolocation) {
      setSnack({ msg: "Geolocation not supported by this browser", severity: "error" });
      return;
    }
    setDetecting(true);
    try {
      const pos = await new Promise<GeolocationPosition>((resolve, reject) =>
        navigator.geolocation.getCurrentPosition(resolve, reject, {
          enableHighAccuracy: true,
          timeout: 10000,
        }),
      );
      const lat = pos.coords.latitude;
      const lon = pos.coords.longitude;
      set("latitude", String(lat));
      set("longitude", String(lon));
      await Promise.all([reverseGeocode(lat, lon), fetchElevation(lat, lon)]);
    } catch (err) {
      const geoErr = err as GeolocationPositionError;
      const msgs: Record<number, string> = {
        1: "Location access denied",
        2: "Location unavailable",
        3: "Location request timed out",
      };
      setSnack({ msg: msgs[geoErr.code] || "Could not detect location", severity: "error" });
    } finally {
      setDetecting(false);
    }
  };

  // Address lookup dialog state
  const [addressDialogOpen, setAddressDialogOpen] = useState(false);
  const [addressForm, setAddressForm] = useState({
    street: "",
    city: "",
    state_province: "",
    country: "",
    postal_code: "",
  });
  const [addressError, setAddressError] = useState<string | null>(null);

  const openAddressLookup = () => {
    // Pre-populate from the main form if available
    setAddressForm({
      street: "",
      city: form.city,
      state_province: form.state_province,
      country: form.country,
      postal_code: form.postal_code,
    });
    setAddressError(null);
    setAddressDialogOpen(true);
  };

  const handleAddressLookup = async () => {
    const parts = [
      addressForm.street,
      addressForm.city,
      addressForm.state_province,
      addressForm.postal_code,
      addressForm.country,
    ]
      .map((s) => s.trim())
      .filter(Boolean);
    if (parts.length === 0) {
      setAddressError("Enter at least a street, city, or postal code");
      return;
    }
    setLookingUp(true);
    setAddressError(null);
    try {
      const q = encodeURIComponent(parts.join(", "));
      const res = await fetchWithRetry(
        `https://nominatim.openstreetmap.org/search?q=${q}&format=json&limit=1&addressdetails=1`,
        { headers: { "User-Agent": "NightCrate/1.0" } },
      );
      if (!res) {
        setAddressError("Address lookup failed — try a different address");
        return;
      }
      const results = await res.json();
      if (!Array.isArray(results) || results.length === 0) {
        setAddressError("No results found — try adding more detail");
        return;
      }
      const hit = results[0];
      const lat = parseFloat(hit.lat);
      const lon = parseFloat(hit.lon);
      set("latitude", String(lat));
      set("longitude", String(lon));

      // Backfill address fields from the geocode result (not the street)
      const addr = hit.address ?? {};
      set("city", addr.city || addr.town || addr.village || addr.hamlet || form.city);
      set("state_province", addr.state || addr.province || addr.region || form.state_province);
      set("country", addr.country || form.country);
      set("postal_code", addr.postcode || form.postal_code);

      await fetchElevation(lat, lon);
      setAddressDialogOpen(false);
    } catch {
      setAddressError("Address lookup failed");
    } finally {
      setLookingUp(false);
    }
  };

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const handleClearOutsideLookup = async () => {
    const lat = parseFloat(form.latitude);
    const lon = parseFloat(form.longitude);
    if (isNaN(lat) || isNaN(lon)) {
      setSnack({ msg: "Set coordinates first", severity: "error" });
      return;
    }
    setLookingUpClearOutside(true);
    try {
      const data = await lookupClearOutside(lat, lon);
      if (data.sqm == null) {
        setSnack({
          msg: "Could not find SQM on Clear Outside",
          severity: "error",
        });
      } else {
        // Populate SQM and derive Bortle from it. Clear Outside's Bortle
        // value is intentionally ignored — keep a single source of truth.
        const bortle = sqmToBortle(data.sqm);
        setForm((prev) => ({
          ...prev,
          sqm_reading: String(data.sqm),
          bortle_class: String(bortle),
        }));
        setSnack({
          msg: "Populated SQM from Clear Outside; Bortle derived from SQM.",
          severity: "info",
        });
      }
    } catch (err) {
      setSnack({
        msg: err instanceof Error ? err.message : "Clear Outside lookup failed",
        severity: "error",
      });
    } finally {
      setLookingUpClearOutside(false);
    }
  };

  const openCreate = () => {
    setEditingLocation(null);
    const fresh = emptyForm();
    setForm(fresh);
    originalFormRef.current = fresh;
    setErrors({});
    setGeoTzEditable(false);
    // Seed with a 0° flat default — mirrors the server's legacy auto-
    // seed so the user starts with a valid horizon set they can modify
    // or replace before committing.
    setStagedHorizons(seedNewLocationDefault());
    setDialogOpen(true);
  };

  const openEdit = async (loc: Location) => {
    setEditingLocation(loc);
    const snapshot = locationToForm(loc, units);
    setForm(snapshot);
    originalFormRef.current = snapshot;
    setErrors({});
    setGeoTzEditable(false);
    // Populate staged horizons from the server snapshot. Keep the
    // dialog open even if the fetch fails — the horizons section shows
    // an empty list and a fallback error is surfaced via snackbar.
    setStagedHorizons([]);
    setDialogOpen(true);
    try {
      const serverHorizons = await fetchHorizons(loc.id);
      setStagedHorizons(serverHorizons.map(fromServerRow));
    } catch (err) {
      setSnack({
        msg: err instanceof Error ? err.message : "Failed to load horizons",
        severity: "error",
      });
    }
  };

  const hasUnsavedChanges = (): boolean => {
    return formsDiffer(form, originalFormRef.current) || hasDirtyHorizons(stagedHorizons);
  };

  const attemptClose = () => {
    if (hasUnsavedChanges()) {
      setConfirmDiscardLocation(true);
    } else {
      setDialogOpen(false);
    }
  };

  const confirmDiscardAndClose = () => {
    setConfirmDiscardLocation(false);
    setDialogOpen(false);
  };

  const validate = (): boolean => {
    const e: typeof errors = {};
    if (!form.name.trim()) e.name = "Name is required";
    if (!form.latitude.trim() || isNaN(parseFloat(form.latitude))) e.latitude = "Valid latitude required";
    else if (parseFloat(form.latitude) < -90 || parseFloat(form.latitude) > 90) e.latitude = "Must be -90 to 90";
    if (!form.longitude.trim() || isNaN(parseFloat(form.longitude))) e.longitude = "Valid longitude required";
    else if (parseFloat(form.longitude) < -180 || parseFloat(form.longitude) > 180) e.longitude = "Must be -180 to 180";
    if (!form.timezone.trim()) e.timezone = "Timezone is required";
    if (form.bortle_class.trim()) {
      const b = parseInt(form.bortle_class, 10);
      if (isNaN(b) || b < 1 || b > 9) e.bortle_class = "Must be 1-9";
    }
    if (form.sqm_reading.trim()) {
      const s = parseFloat(form.sqm_reading);
      if (isNaN(s) || s < 10 || s > 25) e.sqm_reading = "Must be 10-25";
    }
    if (form.typical_seeing_low_arcsec.trim()) {
      const v = parseFloat(form.typical_seeing_low_arcsec);
      if (isNaN(v) || v <= 0) e.typical_seeing_low_arcsec = "Must be positive";
    }
    if (form.typical_seeing_high_arcsec.trim()) {
      const v = parseFloat(form.typical_seeing_high_arcsec);
      if (isNaN(v) || v <= 0) e.typical_seeing_high_arcsec = "Must be positive";
    }
    if (form.typical_seeing_low_arcsec.trim() && form.typical_seeing_high_arcsec.trim()) {
      const low = parseFloat(form.typical_seeing_low_arcsec);
      const high = parseFloat(form.typical_seeing_high_arcsec);
      if (!isNaN(low) && !isNaN(high) && low > high) {
        e.typical_seeing_high_arcsec = "Must be \u2265 best seeing";
      }
    }
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const handleSave = async () => {
    if (!validate()) return;
    setSaving(true);
    try {
      const elevationInput = parseOptionalFloat(form.elevation);
      const elevationMeters =
        elevationInput != null && unitIsImperial
          ? feetToMeters(elevationInput)
          : elevationInput;
      const payload: LocationCreate = {
        name: form.name.trim(),
        latitude: parseFloat(form.latitude),
        longitude: parseFloat(form.longitude),
        elevation_m: elevationMeters,
        timezone: form.timezone.trim(),
        // Only send an explicit geo_timezone if the user actually unlocked
        // and changed it; otherwise let the backend derive it from coords.
        ...(geoTzEditable && form.geo_timezone.trim()
          ? { geo_timezone: form.geo_timezone.trim() }
          : {}),
        bortle_class: parseOptionalInt(form.bortle_class),
        sqm_reading: parseOptionalFloat(form.sqm_reading),
        typical_seeing_low_arcsec: parseOptionalFloat(form.typical_seeing_low_arcsec),
        typical_seeing_high_arcsec: parseOptionalFloat(form.typical_seeing_high_arcsec),
        city: form.city.trim() || null,
        state_province: form.state_province.trim() || null,
        country: form.country.trim() || null,
        postal_code: form.postal_code.trim() || null,
        notes: form.notes.trim() || null,
      };
      if (editingLocation) {
        await updateLocation(editingLocation.id, payload);
        // Atomic horizon replace — the server diff-applies creates /
        // updates / deletes in one SQL transaction, so partial network
        // failure mid-save can't corrupt the dirty-state invariant.
        // Also handles the "replace custom" pattern (delete old +
        // create new, both customs) that a naïve client-side
        // ordering would hit the at-most-one-custom partial unique
        // with (409).
        if (hasDirtyHorizons(stagedHorizons)) {
          await replaceLocationHorizons(editingLocation.id, toReplaceItems(stagedHorizons));
        }
        setSnack({ msg: "Location updated.", severity: "info" });
      } else {
        // New location — atomic create path. Seed horizons are derived
        // from the staged list, validated client-side by the UI and
        // re-validated by the server (exactly-one-default, ≤1 custom).
        const seeds = toCreateSeeds(stagedHorizons);
        const atomicPayload: LocationCreate = {
          ...payload,
          horizons: seeds,
        };
        await createLocation(atomicPayload);
        setSnack({ msg: "Location added.", severity: "info" });
      }
      invalidate();
      setDialogOpen(false);
    } catch (err) {
      setSnack({ msg: err instanceof Error ? err.message : "Save failed", severity: "error" });
    } finally {
      setSaving(false);
    }
  };

  // NOTE: ``_applyStagedHorizonsToExisting`` — which issued per-row
  // create/update/delete calls client-side — was removed in favour of
  // the atomic ``PUT /api/locations/{id}/horizons`` endpoint above.
  // Client-side ordering (creates → updates → promote → deletes)
  // tripped ``idx_location_horizon_one_custom`` (409) on the
  // "replace-custom" flow (delete old custom + add new one) and
  // couldn't offer true atomicity against mid-save network failures.
  // The server endpoint diff-applies the full desired state in one
  // transaction so neither issue is reachable. See horizonStaging's
  // ``planSaveOps`` for the retired plan-builder (kept for reference
  // + its tests; not used at runtime).

  const handleSetDefault = async (loc: Location) => {
    try {
      await setDefaultLocation(loc.id);
      invalidate();
    } catch (err) {
      setSnack({ msg: err instanceof Error ? err.message : "Failed", severity: "error" });
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteLocation(deleteTarget.id);
      invalidate();
      setDeleteTarget(null);
      setSnack({ msg: "Location deleted.", severity: "info" });
    } catch (err) {
      setSnack({ msg: err instanceof Error ? err.message : "Delete failed", severity: "error" });
    }
  };

  return (
    <Box sx={{ p: 3, maxWidth: 900 }}>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 3 }}>
        <Typography variant="h5">Locations</Typography>
        <Button variant="contained" startIcon={<AddIcon />} onClick={openCreate}>
          Add Location
        </Button>
      </Box>

      {isLoading && <Typography color="text.secondary">Loading...</Typography>}

      {!isLoading && locations.length === 0 && (
        <Typography color="text.secondary">
          No locations defined. Add your imaging locations to enable weather, moon phase, and session planning features.
        </Typography>
      )}

      <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
        {locations.map((loc) => (
          <Paper
            key={loc.id}
            variant="outlined"
            onClick={() =>
              setSelectedLocationId((prev) => (prev === loc.id ? null : loc.id))
            }
            sx={{
              p: 2,
              cursor: "pointer",
              borderColor: selectedLocationId === loc.id ? "primary.main" : undefined,
              bgcolor: selectedLocationId === loc.id ? "action.selected" : undefined,
              "&:hover": { borderColor: "primary.main" },
            }}
          >
            <Box sx={{ display: "flex", alignItems: "flex-start", gap: 2 }}>
              {/* Default star */}
              <Tooltip title={loc.is_default ? "Default location" : "Set as default"} arrow>
                <IconButton
                  size="small"
                  onClick={(e) => {
                    e.stopPropagation();
                    if (!loc.is_default) handleSetDefault(loc);
                  }}
                  sx={{ mt: 0.25, color: loc.is_default ? "warning.main" : "action.disabled" }}
                >
                  {loc.is_default ? <StarIcon /> : <StarOutlineIcon />}
                </IconButton>
              </Tooltip>

              {/* Info */}
              <Box sx={{ flex: 1 }}>
                <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
                  <Typography variant="subtitle1" fontWeight={600}>
                    {loc.name}
                  </Typography>
                  {loc.is_default && <Chip label="Default" size="small" color="warning" variant="outlined" />}
                </Box>

                <Typography variant="body2" color="text.secondary">
                  <strong>Display Timezone:</strong> {loc.timezone}
                  {loc.geo_timezone && (
                    <>
                      {"  \u00B7  "}
                      <strong>Location Timezone:</strong> {loc.geo_timezone}
                    </>
                  )}
                </Typography>

                {(loc.city || loc.state_province || loc.country) && (
                  <Typography variant="body2" color="text.secondary">
                    {[loc.city, loc.state_province, loc.country].filter(Boolean).join(", ")}
                  </Typography>
                )}

                <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 0.5 }}>
                  {loc.bortle_class != null && (
                    <Chip label={`Bortle ${loc.bortle_class}`} size="small" variant="outlined" />
                  )}
                  {loc.sqm_reading != null && (
                    <Chip label={`SQM ${loc.sqm_reading}`} size="small" variant="outlined" />
                  )}
                  <Box onClick={(e) => e.stopPropagation()} sx={{ display: "flex" }}>
                    <EasterEggWand lines={INCANTATIONS} tooltip="Cast a clear sky incantation" />
                  </Box>
                </Box>

                {loc.notes && (
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
                    {loc.notes}
                  </Typography>
                )}
              </Box>

              {/* Actions */}
              <Box sx={{ display: "flex", gap: 0.5 }}>
                <Tooltip title="Edit" arrow>
                  <IconButton
                    size="small"
                    onClick={(e) => {
                      e.stopPropagation();
                      openEdit(loc);
                    }}
                  >
                    <EditIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
                <Tooltip title="Delete" arrow>
                  <IconButton
                    size="small"
                    onClick={(e) => {
                      e.stopPropagation();
                      setDeleteTarget(loc);
                    }}
                  >
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              </Box>
            </Box>
          </Paper>
        ))}
      </Box>

      {/* Slide-up detail panel */}
      <Collapse in={selectedLocation !== null} unmountOnExit>
        {selectedLocation && (
          <LocationDetail
            loc={selectedLocation}
            units={units}
            onClose={() => setSelectedLocationId(null)}
          />
        )}
      </Collapse>

      {/* Create / Edit dialog */}
      <Dialog
        open={dialogOpen}
        onClose={attemptClose}
        maxWidth="md"
        fullWidth
        TransitionProps={{
          onEntered: () => setDialogReady(true),
          onExited: () => setDialogReady(false),
        }}
      >
        <DialogTitle>{editingLocation ? "Edit Location" : "Add Location"}</DialogTitle>
        <DialogContent>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 2, pt: 1 }}>
            <Box sx={{ display: "flex", gap: 2, alignItems: "flex-start" }}>
              <TextField
                label="Name"
                value={form.name}
                onChange={(e) => set("name", e.target.value)}
                required
                error={Boolean(errors.name)}
                helperText={errors.name}
                autoFocus
                sx={{ flex: 1 }}
              />
              <Button
                variant="outlined"
                size="small"
                startIcon={<MyLocationIcon />}
                onClick={detectLocation}
                disabled={detecting}
                sx={{ whiteSpace: "nowrap", mt: 1, height: 40 }}
              >
                {detecting ? "Detecting..." : "Use My Location"}
              </Button>
            </Box>
            {/* Address fields + Lookup from Address */}
            <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" }, gap: 2 }}>
              <TextField
                label="City"
                value={form.city}
                onChange={(e) => set("city", e.target.value)}
              />
              <TextField
                label="State / Province"
                value={form.state_province}
                onChange={(e) => set("state_province", e.target.value)}
              />
            </Box>
            <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" }, gap: 2 }}>
              <TextField
                label="Country"
                value={form.country}
                onChange={(e) => set("country", e.target.value)}
              />
              <TextField
                label="Postal Code"
                value={form.postal_code}
                onChange={(e) => set("postal_code", e.target.value)}
              />
            </Box>
            <Button
              variant="outlined"
              size="small"
              startIcon={<SearchIcon />}
              onClick={openAddressLookup}
              sx={{ alignSelf: "flex-start" }}
            >
              Lookup Coordinates from Address
            </Button>

            {/* Lat/Lon + Map preview */}
            <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" }, gap: 2 }}>
              <TextField
                label="Latitude"
                type="number"
                value={form.latitude}
                onChange={(e) => set("latitude", e.target.value)}
                required
                error={Boolean(errors.latitude)}
                helperText={
                  errors.latitude ||
                  formatLatitudeLive(parseFloat(form.latitude)) ||
                  "-90 to 90"
                }
                slotProps={{ htmlInput: { step: "any", min: -90, max: 90 } }}
              />
              <TextField
                label="Longitude"
                type="number"
                value={form.longitude}
                onChange={(e) => set("longitude", e.target.value)}
                required
                error={Boolean(errors.longitude)}
                helperText={
                  errors.longitude ||
                  formatLongitudeLive(parseFloat(form.longitude)) ||
                  "-180 to 180"
                }
                slotProps={{ htmlInput: { step: "any", min: -180, max: 180 } }}
              />
            </Box>

            {/* Elevation — user types in their preferred unit; helper text
                shows the other unit so both are visible at a glance. */}
            <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" }, gap: 2 }}>
              <TextField
                label={`Elevation (${elevationUnitLabel})`}
                type="number"
                value={form.elevation}
                onChange={(e) => set("elevation", e.target.value)}
                helperText={
                  (() => {
                    const v = parseFloat(form.elevation);
                    if (isNaN(v)) return " ";
                    return unitIsImperial
                      ? `= ${Math.round(feetToMeters(v))} m`
                      : `= ${Math.round(metersToFeet(v))} ft`;
                  })()
                }
                slotProps={{ htmlInput: { step: "any" } }}
              />
            </Box>

            {/* Map preview when lat/lon are available */}
            {dialogReady && form.latitude && form.longitude && !isNaN(parseFloat(form.latitude)) && !isNaN(parseFloat(form.longitude)) && (
              <OsmMap
                latitude={parseFloat(form.latitude)}
                longitude={parseFloat(form.longitude)}
                title="Location map preview"
                height={180}
              />
            )}

            {/* Display / Location Timezone pair. Location Timezone is locked
                by default — clicking the disabled field opens a warning; the
                overlay is absolutely positioned over the Autocomplete so the
                two fields stay the same size and aligned. */}
            <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" }, gap: 2, alignItems: "start" }}>
              <Autocomplete
                options={timezones}
                value={timezones.includes(form.timezone) ? form.timezone : null}
                inputValue={form.timezone}
                onInputChange={(_e, value) => set("timezone", value)}
                onChange={(_e, value) => set("timezone", value ?? "")}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label="Display Timezone"
                    required
                    error={Boolean(errors.timezone)}
                    helperText={
                      errors.timezone ||
                      "Used for showing times in the UI (weather, forecasts, clocks)."
                    }
                  />
                )}
                size="small"
                freeSolo
              />
              <Box sx={{ position: "relative" }}>
                <Autocomplete
                  options={timezones}
                  value={timezones.includes(form.geo_timezone) ? form.geo_timezone : null}
                  inputValue={form.geo_timezone}
                  onInputChange={(_e, value) => set("geo_timezone", value)}
                  onChange={(_e, value) => set("geo_timezone", value ?? "")}
                  disabled={!geoTzEditable}
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      label="Location Timezone"
                      helperText="Used for astronomy (sunset/sunrise, darkness, moon)."
                    />
                  )}
                  size="small"
                  freeSolo
                />
                {!geoTzEditable && (
                  <Box
                    onClick={() => setGeoTzWarningOpen(true)}
                    sx={{
                      position: "absolute",
                      inset: 0,
                      cursor: "pointer",
                      zIndex: 1,
                    }}
                    aria-label="Unlock Location Timezone"
                  />
                )}
              </Box>
            </Box>
            <Stack direction="row" spacing={1} alignItems="center">
              <TextField
                label="Bortle Class"
                type="number"
                value={form.bortle_class}
                onChange={(e) => {
                  const val = e.target.value;
                  set("bortle_class", val);
                  // Auto-estimate SQM from Bortle if SQM is empty
                  if (val && !form.sqm_reading) {
                    const b = parseInt(val, 10);
                    const sqmFromBortle: Record<number, string> = {
                      1: "21.99", 2: "21.69", 3: "21.25", 4: "20.49",
                      5: "19.50", 6: "18.94", 7: "18.38", 8: "17.80", 9: "<17",
                    };
                    if (b >= 1 && b <= 8) set("sqm_reading", sqmFromBortle[b]);
                  }
                }}
                error={Boolean(errors.bortle_class)}
                helperText={errors.bortle_class || "1 (darkest) to 9 (brightest)"}
                slotProps={{ htmlInput: { min: 1, max: 9 } }}
                sx={{ flex: 1 }}
              />
              <Tooltip title="Calculate approximate Bortle from this SQM value">
                <span>
                  <IconButton
                    size="small"
                    disabled={!form.sqm_reading.trim() || isNaN(parseFloat(form.sqm_reading))}
                    onClick={() => {
                      const s = parseFloat(form.sqm_reading);
                      if (!isNaN(s)) set("bortle_class", String(sqmToBortle(s)));
                    }}
                    aria-label="Calculate Bortle from SQM"
                  >
                    <ArrowBackIcon fontSize="small" />
                  </IconButton>
                </span>
              </Tooltip>
              <TextField
                label="SQM Reading"
                type="number"
                value={form.sqm_reading}
                onChange={(e) => {
                  const val = e.target.value;
                  set("sqm_reading", val);
                  // Auto-estimate Bortle from SQM if Bortle is empty
                  if (val && !form.bortle_class) {
                    const s = parseFloat(val);
                    if (!isNaN(s)) {
                      set("bortle_class", String(sqmToBortle(s)));
                    }
                  }
                }}
                error={Boolean(errors.sqm_reading)}
                helperText={errors.sqm_reading || "mag/arcsec²"}
                slotProps={{ htmlInput: { step: "any", min: 10, max: 25 } }}
                sx={{ flex: 1 }}
              />
            </Stack>
            {form.latitude && form.longitude && !isNaN(parseFloat(form.latitude)) && !isNaN(parseFloat(form.longitude)) && (
              <>
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={<SearchIcon />}
                  onClick={handleClearOutsideLookup}
                  disabled={lookingUpClearOutside}
                  sx={{ alignSelf: "flex-start", mt: -1 }}
                >
                  {lookingUpClearOutside ? "Looking up..." : "Lookup Bortle / SQM"}
                </Button>
                <Typography variant="caption" color="text.secondary" sx={{ mt: -1 }}>
                  Scrapes the{" "}
                  <Typography
                    variant="caption"
                    component="a"
                    href={`https://clearoutside.com/forecast/${parseFloat(form.latitude).toFixed(2)}/${parseFloat(form.longitude).toFixed(2)}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    sx={{ color: "primary.main", textDecoration: "none", "&:hover": { textDecoration: "underline" } }}
                  >
                    Clear Outside forecast page
                  </Typography>
                  {" "}to pre-fill Bortle class and SQM.
                </Typography>
              </>
            )}

            {/* Seeing Conditions */}
            <Typography variant="subtitle2" sx={{ mt: 1, mb: -0.5 }}>
              Seeing Conditions
            </Typography>
            <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" }, gap: 2 }}>
              <TextField
                label="Best Typical Seeing"
                type="number"
                value={form.typical_seeing_low_arcsec}
                onChange={(e) => set("typical_seeing_low_arcsec", e.target.value)}
                error={Boolean(errors.typical_seeing_low_arcsec)}
                helperText={errors.typical_seeing_low_arcsec || "FWHM in arcseconds (e.g. 2.0)"}
                slotProps={{ htmlInput: { step: "any", min: 0.1 } }}
              />
              <TextField
                label="Worst Typical Seeing"
                type="number"
                value={form.typical_seeing_high_arcsec}
                onChange={(e) => set("typical_seeing_high_arcsec", e.target.value)}
                error={Boolean(errors.typical_seeing_high_arcsec)}
                helperText={errors.typical_seeing_high_arcsec || "FWHM in arcseconds (e.g. 4.0)"}
                slotProps={{ htmlInput: { step: "any", min: 0.1 } }}
              />
            </Box>
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ mt: -1, cursor: "pointer" }}
              onClick={() => setSeeingGuideOpen((v) => !v)}
            >
              {seeingGuideOpen ? "\u25BE" : "\u25B8"} How to estimate your seeing
            </Typography>
            {seeingGuideOpen && (
              <Box sx={{ ml: 1, mt: 0.5, fontSize: "0.75rem", color: "text.secondary" }}>
                <Typography variant="caption" component="p" sx={{ mb: 0.5 }}>
                  Estimate from the FWHM of stars in your processed subs, or use these guidelines:
                </Typography>
                <Box component="table" sx={{ "& td, & th": { px: 1, py: 0.25, fontSize: "0.75rem" } }}>
                  <thead>
                    <tr><th align="left">Site Type</th><th align="left">Typical Range</th></tr>
                  </thead>
                  <tbody>
                    <tr><td>Mountain observatory (&gt;2000m)</td><td>0.5{"\u2013"}1.5{"\u2033"}</td></tr>
                    <tr><td>Rural dark site</td><td>1.5{"\u2013"}3.0{"\u2033"}</td></tr>
                    <tr><td>Suburban backyard</td><td>2.0{"\u2013"}4.0{"\u2033"}</td></tr>
                    <tr><td>Urban / rooftop</td><td>3.0{"\u2013"}5.0{"\u2033"}</td></tr>
                  </tbody>
                </Box>
                <Typography variant="caption" component="p" sx={{ mt: 0.5 }}>
                  Used by Rig calculators to assess whether your equipment matches your site conditions.
                </Typography>
              </Box>
            )}

            <LocationHorizonsSection
              locationId={editingLocation?.id ?? null}
              locationName={editingLocation?.name ?? (form.name || "New location")}
              staged={stagedHorizons}
              onChange={setStagedHorizons}
            />


            <TextField
              label="Notes"
              value={form.notes}
              onChange={(e) => set("notes", e.target.value)}
              multiline
              rows={2}
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={attemptClose} disabled={saving}>Cancel</Button>
          <Button onClick={handleSave} variant="contained" disabled={saving}>
            {saving ? "Saving..." : "Save"}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Discard-changes confirm on Location editor close */}
      <Dialog
        open={confirmDiscardLocation}
        onClose={() => setConfirmDiscardLocation(false)}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>Discard unsaved changes?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            You have unsaved changes to this location. Close the editor
            and discard them?
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmDiscardLocation(false)}>Keep editing</Button>
          <Button color="warning" onClick={confirmDiscardAndClose}>
            Discard
          </Button>
        </DialogActions>
      </Dialog>

      {/* Location Timezone unlock warning */}
      <Dialog
        open={geoTzWarningOpen}
        onClose={() => setGeoTzWarningOpen(false)}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>Edit Location Timezone?</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 1 }}>
            The Location Timezone is auto-derived from this location's
            coordinates and is used for astronomy calculations — sunset and
            sunrise times, twilight windows, and moon phase/altitude. It
            should always match the timezone of the physical location.
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Change it only if the auto-detected value is wrong (e.g. near a
            timezone boundary where the lookup picks the neighbour).
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setGeoTzWarningOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            color="warning"
            onClick={() => {
              setGeoTzEditable(true);
              setGeoTzWarningOpen(false);
            }}
          >
            Enable Editing
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete confirmation */}
      <Dialog open={deleteTarget !== null} onClose={() => setDeleteTarget(null)} maxWidth="xs">
        <DialogTitle>Delete Location</DialogTitle>
        <DialogContent>
          <Typography>
            Delete <strong>{deleteTarget?.name}</strong>? This cannot be undone.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteTarget(null)}>Cancel</Button>
          <Button onClick={handleDelete} color="warning" variant="contained">Delete</Button>
        </DialogActions>
      </Dialog>

      {/* Address lookup dialog */}
      <Dialog
        open={addressDialogOpen}
        onClose={() => setAddressDialogOpen(false)}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>Lookup Coordinates from Address</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Enter your address for a precise coordinate lookup. The street address is used only for the lookup and is not stored.
          </Typography>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 2, pt: 1 }}>
            <TextField
              label="Street Address"
              value={addressForm.street}
              onChange={(e) => setAddressForm((p) => ({ ...p, street: e.target.value }))}
              autoFocus
              placeholder="e.g. 123 Main St"
            />
            <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" }, gap: 2 }}>
              <TextField
                label="City"
                value={addressForm.city}
                onChange={(e) => setAddressForm((p) => ({ ...p, city: e.target.value }))}
              />
              <TextField
                label="State / Province"
                value={addressForm.state_province}
                onChange={(e) => setAddressForm((p) => ({ ...p, state_province: e.target.value }))}
              />
            </Box>
            <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" }, gap: 2 }}>
              <TextField
                label="Country"
                value={addressForm.country}
                onChange={(e) => setAddressForm((p) => ({ ...p, country: e.target.value }))}
              />
              <TextField
                label="Postal Code"
                value={addressForm.postal_code}
                onChange={(e) => setAddressForm((p) => ({ ...p, postal_code: e.target.value }))}
              />
            </Box>
            {addressError && (
              <Alert severity="warning">{addressError}</Alert>
            )}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddressDialogOpen(false)} disabled={lookingUp}>Cancel</Button>
          <Button onClick={handleAddressLookup} variant="contained" disabled={lookingUp}>
            {lookingUp ? "Looking up..." : "Lookup"}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={snack !== null}
        autoHideDuration={3000}
        onClose={() => setSnack(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert severity={snack?.severity ?? "info"} onClose={() => setSnack(null)}>
          {snack?.msg}
        </Alert>
      </Snackbar>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Detail panel — all location fields + embedded OSM map
// ---------------------------------------------------------------------------

/**
 * OpenStreetMap iframe wrapper that doesn't steal scroll/drag unless
 * the user explicitly activates it. Solves the "scrolling the dialog
 * zooms the map instead" problem. A reset button reloads the iframe
 * to restore the initial view after accidental zooming.
 */
function OsmMap({
  latitude,
  longitude,
  title,
  height,
}: {
  latitude: number;
  longitude: number;
  title: string;
  height: number | string;
}) {
  const [interactive, setInteractive] = useState(false);
  const [mapKey, setMapKey] = useState(0);

  const src = `https://www.openstreetmap.org/export/embed.html?bbox=${longitude - 0.05},${latitude - 0.03},${longitude + 0.05},${latitude + 0.03}&layer=mapnik&marker=${latitude},${longitude}`;

  const reset = () => {
    setMapKey((k) => k + 1);
    setInteractive(false);
  };

  return (
    <Box
      onMouseLeave={() => setInteractive(false)}
      sx={{
        position: "relative",
        border: 1,
        borderColor: "divider",
        borderRadius: 1,
        overflow: "hidden",
        height,
        minHeight: height,
      }}
    >
      <iframe
        key={mapKey}
        title={title}
        src={src}
        style={{
          width: "100%",
          height: "100%",
          border: "none",
          pointerEvents: interactive ? "auto" : "none",
        }}
      />
      {!interactive && (
        <Box
          onClick={() => setInteractive(true)}
          sx={{
            position: "absolute",
            inset: 0,
            cursor: "pointer",
            display: "flex",
            alignItems: "flex-end",
            justifyContent: "center",
            pb: 1,
          }}
        >
          <Chip
            size="small"
            label="Click to interact"
            sx={{
              pointerEvents: "none",
              bgcolor: "background.paper",
              opacity: 0.9,
              boxShadow: 1,
            }}
          />
        </Box>
      )}
      <Tooltip title="Reset map view">
        <IconButton
          onClick={reset}
          size="small"
          sx={{
            position: "absolute",
            bottom: 4,
            right: 4,
            bgcolor: "background.paper",
            boxShadow: 1,
            "&:hover": { bgcolor: "background.paper" },
          }}
        >
          <RestartAltIcon fontSize="small" />
        </IconButton>
      </Tooltip>
    </Box>
  );
}


function DetailField({ label, value }: { label: string; value: React.ReactNode }) {
  if (value == null || value === "") return null;
  return (
    <Box sx={{ display: "flex", gap: 1 }}>
      <Typography variant="body2" color="text.secondary" sx={{ minWidth: 150, flexShrink: 0 }}>
        {label}
      </Typography>
      <Typography variant="body2" component="div">
        {value}
      </Typography>
    </Box>
  );
}

function LocationDetail({
  loc,
  units,
  onClose,
}: {
  loc: Location;
  units: WeatherUnits;
  onClose: () => void;
}) {
  const address = [loc.city, loc.state_province, loc.country]
    .filter(Boolean)
    .join(", ");
  const addressLine = address || null;

  const seeingRange =
    loc.typical_seeing_low_arcsec != null && loc.typical_seeing_high_arcsec != null
      ? `${loc.typical_seeing_low_arcsec}\u2033\u2013${loc.typical_seeing_high_arcsec}\u2033`
      : loc.typical_seeing_low_arcsec != null
      ? `${loc.typical_seeing_low_arcsec}\u2033 (best)`
      : loc.typical_seeing_high_arcsec != null
      ? `${loc.typical_seeing_high_arcsec}\u2033 (worst)`
      : null;

  return (
    <Paper variant="outlined" sx={{ p: 2, mt: 2, position: "relative" }}>
      <IconButton
        size="small"
        onClick={onClose}
        sx={{ position: "absolute", top: 8, right: 8 }}
        aria-label="Close detail"
      >
        <CloseIcon fontSize="small" />
      </IconButton>

      <Typography variant="h6" sx={{ mb: 1.5 }}>
        {loc.name}
        {loc.is_default && (
          <Chip
            label="Default"
            size="small"
            color="warning"
            variant="outlined"
            sx={{ ml: 1, verticalAlign: "middle" }}
          />
        )}
      </Typography>

      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" },
          gap: 3,
        }}
      >
        {/* Left column — details */}
        <Box sx={{ display: "flex", flexDirection: "column", gap: 0.75 }}>
          <DetailField
            label="Latitude"
            value={
              <>
                {loc.latitude_display}
                {"  "}
                <Typography component="span" variant="body2" color="text.secondary">
                  ({loc.latitude.toFixed(6)})
                </Typography>
              </>
            }
          />
          <DetailField
            label="Longitude"
            value={
              <>
                {loc.longitude_display}
                {"  "}
                <Typography component="span" variant="body2" color="text.secondary">
                  ({loc.longitude.toFixed(6)})
                </Typography>
              </>
            }
          />
          <DetailField
            label="Elevation"
            value={formatElevationBoth(loc.elevation_m, units)}
          />
          <DetailField
            label="Display Timezone"
            value={
              <>
                {loc.timezone}
                {formatUtcOffset(loc.timezone) && (
                  <>
                    {"  "}
                    <Typography component="span" variant="body2" color="text.secondary">
                      ({formatUtcOffset(loc.timezone)})
                    </Typography>
                  </>
                )}
              </>
            }
          />
          <DetailField
            label="Location Timezone"
            value={
              loc.geo_timezone ? (
                <>
                  {loc.geo_timezone}
                  {formatUtcOffset(loc.geo_timezone) && (
                    <>
                      {"  "}
                      <Typography component="span" variant="body2" color="text.secondary">
                        ({formatUtcOffset(loc.geo_timezone)})
                      </Typography>
                    </>
                  )}
                </>
              ) : null
            }
          />
          <DetailField label="Address" value={addressLine} />
          <DetailField label="Bortle Class" value={loc.bortle_class} />
          <DetailField
            label="SQM"
            value={
              loc.sqm_reading != null ? `${loc.sqm_reading} mag/arcsec\u00B2` : null
            }
          />
          <DetailField label="Typical Seeing" value={seeingRange} />
          {loc.notes && (
            <Box sx={{ mt: 1 }}>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
                Notes
              </Typography>
              <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
                {loc.notes}
              </Typography>
            </Box>
          )}
        </Box>

        {/* Right column — map */}
        <OsmMap
          latitude={loc.latitude}
          longitude={loc.longitude}
          title={`Map of ${loc.name}`}
          height={260}
        />
      </Box>

      <Box sx={{ mt: 2 }}>
        <LocationHorizonReadonly location={loc} />
      </Box>
    </Paper>
  );
}


/**
 * Read-only horizon preview for the Locations list detail panel. Shows
 * the location's default horizon — a chart for customs, a plain text
 * line for artificials (there's nothing to draw at a constant
 * altitude besides a flat line).
 */
function LocationHorizonReadonly({ location }: { location: Location }) {
  const [showRaw, setShowRaw] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(720);

  const { data: horizons = [] } = useQuery({
    queryKey: ["horizons", location.id],
    queryFn: () => fetchHorizons(location.id),
  });

  const defaultHorizon = horizons.find((h) => h.is_default) ?? null;

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w) setWidth(Math.max(360, Math.floor(w)));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const showsChart =
    defaultHorizon !== null
    && defaultHorizon.type === "custom"
    && defaultHorizon.points.length >= 2;

  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
        <Typography variant="subtitle1" sx={{ flex: 1 }}>
          Default horizon
          {defaultHorizon && (
            <Typography
              component="span"
              variant="body2"
              color="text.secondary"
              sx={{ ml: 1 }}
            >
              {defaultHorizon.name}
              {defaultHorizon.type === "artificial" &&
                defaultHorizon.flat_altitude_deg != null &&
                ` (${defaultHorizon.flat_altitude_deg.toFixed(0)}°)`}
            </Typography>
          )}
        </Typography>
        {showsChart && (
          <FormControlLabel
            control={
              <Switch
                size="small"
                checked={showRaw}
                onChange={(e) => setShowRaw(e.target.checked)}
              />
            }
            label={
              <Typography variant="caption" color="text.secondary">
                {showRaw ? "Raw" : "Smoothed"}
              </Typography>
            }
            sx={{ mr: 0 }}
          />
        )}
      </Box>

      <Box ref={containerRef} sx={{ width: "100%" }}>
        {showsChart && defaultHorizon ? (
          <HorizonChart
            points={defaultHorizon.points}
            mode="readonly"
            showRawPoints={showRaw}
            width={width}
            height={200}
          />
        ) : (
          <Box
            sx={{
              height: 80,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "text.secondary",
              border: 1,
              borderColor: "divider",
              borderStyle: "dashed",
              borderRadius: 1,
            }}
          >
            <Typography variant="body2">
              {defaultHorizon == null
                ? "No horizons defined."
                : `Flat floor at ${defaultHorizon.flat_altitude_deg?.toFixed(0) ?? "?"}°`}
            </Typography>
          </Box>
        )}
      </Box>
    </Paper>
  );
}

