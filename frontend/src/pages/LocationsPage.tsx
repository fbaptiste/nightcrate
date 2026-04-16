import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Autocomplete from "@mui/material/Autocomplete";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Snackbar from "@mui/material/Snackbar";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import EditIcon from "@mui/icons-material/Edit";
import MyLocationIcon from "@mui/icons-material/MyLocation";
import SearchIcon from "@mui/icons-material/Search";
import StarIcon from "@mui/icons-material/Star";
import StarOutlineIcon from "@mui/icons-material/StarOutline";
import {
  fetchLocations,
  fetchTimezones,
  fetchGeoTimezone,
  createLocation,
  updateLocation,
  setDefaultLocation,
  deleteLocation,
  type Location,
  type LocationCreate,
} from "@/api/locations";
import { EasterEggWand } from "@/components/EasterEggWand";
import { parseOptionalFloat, parseOptionalInt } from "@/lib/formUtils";

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
  elevation_m: string;
  timezone: string;
  bortle_class: string;
  sqm_reading: string;
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
    elevation_m: "",
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    bortle_class: "",
    sqm_reading: "",
    city: "",
    state_province: "",
    country: "",
    postal_code: "",
    notes: "",
  };
}

function locationToForm(loc: Location): FormState {
  return {
    name: loc.name,
    latitude: String(loc.latitude),
    longitude: String(loc.longitude),
    elevation_m: loc.elevation_m != null ? String(loc.elevation_m) : "",
    timezone: loc.timezone,
    bortle_class: loc.bortle_class != null ? String(loc.bortle_class) : "",
    sqm_reading: loc.sqm_reading != null ? String(loc.sqm_reading) : "",
    city: loc.city ?? "",
    state_province: loc.state_province ?? "",
    country: loc.country ?? "",
    postal_code: loc.postal_code ?? "",
    notes: loc.notes ?? "",
  };
}

export default function LocationsPage() {
  const queryClient = useQueryClient();
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
  const [geoTimezone, setGeoTimezone] = useState<string | null>(null);
  const geoTzTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const { data: timezones = [] } = useQuery({
    queryKey: ["timezones"],
    queryFn: fetchTimezones,
    staleTime: Infinity,
  });

  // Fetch geo_timezone when coordinates change (debounced 500ms)
  useEffect(() => {
    const lat = parseFloat(form.latitude);
    const lon = parseFloat(form.longitude);
    if (isNaN(lat) || isNaN(lon) || lat < -90 || lat > 90 || lon < -180 || lon > 180) {
      setGeoTimezone(null);
      return;
    }
    clearTimeout(geoTzTimerRef.current);
    geoTzTimerRef.current = setTimeout(async () => {
      try {
        const result = await fetchGeoTimezone(lat, lon);
        setGeoTimezone(result.geo_timezone);
        // Auto-populate timezone on new location (not editing)
        if (!editingLocation && form.timezone === Intl.DateTimeFormat().resolvedOptions().timeZone && result.geo_timezone) {
          setForm((prev) => ({ ...prev, timezone: result.geo_timezone! }));
        }
      } catch {
        setGeoTimezone(null);
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
      if (elev != null) set("elevation_m", String(Math.round(elev)));
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

  const openCreate = () => {
    setEditingLocation(null);
    setForm(emptyForm());
    setErrors({});
    setGeoTimezone(null);
    setDialogOpen(true);
  };

  const openEdit = (loc: Location) => {
    setEditingLocation(loc);
    setForm(locationToForm(loc));
    setErrors({});
    setGeoTimezone(loc.geo_timezone);
    setDialogOpen(true);
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
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const handleSave = async () => {
    if (!validate()) return;
    setSaving(true);
    try {
      const payload: LocationCreate = {
        name: form.name.trim(),
        latitude: parseFloat(form.latitude),
        longitude: parseFloat(form.longitude),
        elevation_m: parseOptionalFloat(form.elevation_m),
        timezone: form.timezone.trim(),
        bortle_class: parseOptionalInt(form.bortle_class),
        sqm_reading: parseOptionalFloat(form.sqm_reading),
        city: form.city.trim() || null,
        state_province: form.state_province.trim() || null,
        country: form.country.trim() || null,
        postal_code: form.postal_code.trim() || null,
        notes: form.notes.trim() || null,
      };
      if (editingLocation) {
        await updateLocation(editingLocation.id, payload);
        setSnack({ msg: "Location updated.", severity: "info" });
      } else {
        await createLocation(payload);
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
          <Paper key={loc.id} variant="outlined" sx={{ p: 2 }}>
            <Box sx={{ display: "flex", alignItems: "flex-start", gap: 2 }}>
              {/* Default star */}
              <Tooltip title={loc.is_default ? "Default location" : "Set as default"} arrow>
                <IconButton
                  size="small"
                  onClick={() => !loc.is_default && handleSetDefault(loc)}
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
                  {loc.latitude.toFixed(4)}, {loc.longitude.toFixed(4)}
                  {loc.elevation_m != null && ` · ${loc.elevation_m}m`}
                  {" · "}{loc.timezone}
                </Typography>

                {(loc.city || loc.state_province || loc.country) && (
                  <Typography variant="body2" color="text.secondary">
                    {[loc.city, loc.state_province, loc.country].filter(Boolean).join(", ")}
                    {loc.postal_code && ` ${loc.postal_code}`}
                  </Typography>
                )}

                <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 0.5 }}>
                  {loc.bortle_class != null && (
                    <Chip label={`Bortle ${loc.bortle_class}`} size="small" variant="outlined" />
                  )}
                  {loc.sqm_reading != null && (
                    <Chip label={`SQM ${loc.sqm_reading}`} size="small" variant="outlined" />
                  )}
                  <Typography
                    variant="caption"
                    component="a"
                    href={`https://clearoutside.com/forecast/${loc.latitude.toFixed(2)}/${loc.longitude.toFixed(2)}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    sx={{ color: "primary.main", textDecoration: "none", "&:hover": { textDecoration: "underline" } }}
                  >
                    Clear Outside
                  </Typography>
                  <EasterEggWand lines={INCANTATIONS} tooltip="Cast a clear sky incantation" />
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
                  <IconButton size="small" onClick={() => openEdit(loc)}>
                    <EditIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
                <Tooltip title="Delete" arrow>
                  <IconButton size="small" onClick={() => setDeleteTarget(loc)}>
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              </Box>
            </Box>
          </Paper>
        ))}
      </Box>

      {/* Create / Edit dialog */}
      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="sm" fullWidth>
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
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 2 }}>
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
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 2 }}>
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
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 2 }}>
              <TextField
                label="Latitude"
                type="number"
                value={form.latitude}
                onChange={(e) => set("latitude", e.target.value)}
                required
                error={Boolean(errors.latitude)}
                helperText={errors.latitude || "-90 to 90"}
                slotProps={{ htmlInput: { step: "any", min: -90, max: 90 } }}
              />
              <TextField
                label="Longitude"
                type="number"
                value={form.longitude}
                onChange={(e) => set("longitude", e.target.value)}
                required
                error={Boolean(errors.longitude)}
                helperText={errors.longitude || "-180 to 180"}
                slotProps={{ htmlInput: { step: "any", min: -180, max: 180 } }}
              />
            </Box>

            {/* Map preview when lat/lon are available */}
            {form.latitude && form.longitude && !isNaN(parseFloat(form.latitude)) && !isNaN(parseFloat(form.longitude)) && (
              <Box
                sx={{
                  border: 1,
                  borderColor: "divider",
                  borderRadius: 1,
                  overflow: "hidden",
                  height: 180,
                }}
              >
                <iframe
                  title="Location map preview"
                  src={`https://www.openstreetmap.org/export/embed.html?bbox=${parseFloat(form.longitude) - 0.05},${parseFloat(form.latitude) - 0.03},${parseFloat(form.longitude) + 0.05},${parseFloat(form.latitude) + 0.03}&layer=mapnik&marker=${form.latitude},${form.longitude}`}
                  style={{ width: "100%", height: "100%", border: "none" }}
                />
              </Box>
            )}

            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 2 }}>
              <TextField
                label="Elevation (m)"
                type="number"
                value={form.elevation_m}
                onChange={(e) => set("elevation_m", e.target.value)}
                slotProps={{ htmlInput: { step: "any" } }}
              />
              <Autocomplete
                options={timezones}
                value={timezones.includes(form.timezone) ? form.timezone : null}
                inputValue={form.timezone}
                onInputChange={(_e, value) => set("timezone", value)}
                onChange={(_e, value) => set("timezone", value ?? "")}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label="Timezone"
                    required
                    error={Boolean(errors.timezone)}
                    helperText={errors.timezone}
                  />
                )}
                size="small"
                freeSolo
              />
            </Box>
            {geoTimezone && (
              <Typography variant="caption" color="text.secondary" sx={{ mt: -1 }}>
                Coordinates timezone: <strong>{geoTimezone}</strong>
                {geoTimezone !== form.timezone && " (differs from display timezone)"}
              </Typography>
            )}
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 2 }}>
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
              />
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
                      let b = 9;
                      if (s >= 21.99) b = 1;
                      else if (s >= 21.69) b = 2;
                      else if (s >= 21.25) b = 3;
                      else if (s >= 20.49) b = 4;
                      else if (s >= 19.50) b = 5;
                      else if (s >= 18.94) b = 6;
                      else if (s >= 18.38) b = 7;
                      else if (s >= 17.80) b = 8;
                      set("bortle_class", String(b));
                    }
                  }
                }}
                error={Boolean(errors.sqm_reading)}
                helperText={errors.sqm_reading || "mag/arcsec²"}
                slotProps={{ htmlInput: { step: "any", min: 10, max: 25 } }}
              />
            </Box>
            {form.latitude && form.longitude && !isNaN(parseFloat(form.latitude)) && !isNaN(parseFloat(form.longitude)) && (
              <Typography variant="caption" color="text.secondary" sx={{ mt: -1 }}>
                Don't know your Bortle class?{" "}
                <Typography
                  variant="caption"
                  component="a"
                  href={`https://clearoutside.com/forecast/${parseFloat(form.latitude).toFixed(2)}/${parseFloat(form.longitude).toFixed(2)}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  sx={{ color: "primary.main", textDecoration: "none", "&:hover": { textDecoration: "underline" } }}
                >
                  Look it up on Clear Outside
                </Typography>
                {" "} — Bortle class and SQM are shown at the top of the forecast page.
              </Typography>
            )}
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
          <Button onClick={() => setDialogOpen(false)} disabled={saving}>Cancel</Button>
          <Button onClick={handleSave} variant="contained" disabled={saving}>
            {saving ? "Saving..." : "Save"}
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
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 2 }}>
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
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 2 }}>
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
              <Alert severity="error">{addressError}</Alert>
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
