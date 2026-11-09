import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { LINE_NAMES, lineLabel } from "@/lib/lineNames";
import { fetchRigSetups, type Rig } from "@/api/rigs";
import type { Filter } from "@/api/equipment";
import type { ProjectRigSetups } from "@/api/projects";
import type { ProjectSession, SessionCreate } from "@/api/projectSessions";
import { setupLabel } from "./setupLabel";

interface FilterOpt {
  key: string;
  label: string;
  sublabel: string;
  group: string;
  line_name?: string;
  filter_id?: number;
}

interface Props {
  open: boolean;
  onClose: () => void;
  session?: ProjectSession | null;
  rigs: Rig[];
  filters: Filter[];
  // The project's associated rigs — used to default the Rig field when
  // adding a new session.
  projectRigs?: Rig[];
  projectRigSetups: ProjectRigSetups[];
  onSubmit: (body: SessionCreate) => Promise<unknown>;
}

export default function SessionFormDialog({
  open,
  onClose,
  session,
  rigs,
  filters,
  projectRigs,
  projectRigSetups,
  onSubmit,
}: Props) {
  const [rig, setRig] = useState<Rig | null>(() => {
    if (session?.rig_id != null) {
      return rigs.find((candidate) => candidate.id === session.rig_id) ?? null;
    }
    if (!session && projectRigs && projectRigs.length > 0) {
      return projectRigs.find((candidate) => candidate.is_default) ?? projectRigs[0];
    }
    return null;
  });
  const [rigSetupId, setRigSetupId] = useState<number | null>(session?.rig_setup_id ?? null);
  const selectedRigSetups = projectRigSetups.find((history) => history.rig_id === rig?.id);
  const selectedSetup = selectedRigSetups?.setups.find(
    (setup) => setup.rig_setup_id === rigSetupId,
  );
  const { data: rigSetupHistory = [] } = useQuery({
    queryKey: ["rig-setups", rig?.id],
    queryFn: () => fetchRigSetups(rig!.id),
    enabled: rig != null,
  });
  const effectiveFilterIds = useMemo(() => {
    const ids = new Set<number>();
    if (selectedSetup) {
      for (const slot of selectedSetup.parts.filter_slots) ids.add(slot.filter_id);
      if (selectedSetup.parts.single_filter_id != null) ids.add(selectedSetup.parts.single_filter_id);
    } else if (
      selectedRigSetups?.changed_groups.includes("filters") &&
      selectedRigSetups.change
    ) {
      for (const slot of selectedRigSetups.change.filter_slots) ids.add(slot.filter_id);
      if (selectedRigSetups.change.single_filter_id != null) {
        ids.add(selectedRigSetups.change.single_filter_id);
      }
    } else if (rigSetupId != null) {
      const rawSetup = rigSetupHistory.find((setup) => setup.id === rigSetupId);
      if (rawSetup) {
        for (const slot of rawSetup.parts.filter_slots) ids.add(slot.filter_id);
        if (rawSetup.parts.single_filter_id != null) ids.add(rawSetup.parts.single_filter_id);
      }
    } else if (rig) {
      for (const slot of rig.filter_slots) ids.add(slot.filter_id);
      if (rig.single_filter_id != null) ids.add(rig.single_filter_id);
    }
    return ids;
  }, [rig, rigSetupHistory, rigSetupId, selectedRigSetups, selectedSetup]);

  const filterOptions = useMemo<FilterOpt[]>(() => {
    const inRig = (id: number) => effectiveFilterIds.has(id);
    const mkFilter = (f: Filter, group: string): FilterOpt => ({
      key: `filter:${f.id}`,
      label: `${f.manufacturer.name} ${f.model_name}`,
      sublabel:
        f.passbands
          .map((p) => p.line_name)
          .filter((x): x is string => !!x)
          .join(", ") || "—",
      group,
      filter_id: f.id,
    });

    // "My Rig" group first — filters loaded in the project's rigs.
    const myRig: FilterOpt[] = filters
      .filter((f) => inRig(f.id))
      .map((f) => mkFilter(f, "My Rig"))
      .sort((a, b) => a.label.localeCompare(b.label));

    const bands: FilterOpt[] = LINE_NAMES.map((ln) => ({
      key: `line:${ln}`,
      label: ln,
      sublabel: lineLabel(ln),
      group: "Bandpass",
      line_name: ln,
    }));

    // Other equipment filters — sorted by manufacturer so MUI groupBy doesn't
    // emit duplicate headers.
    const others: FilterOpt[] = filters
      .filter((f) => !inRig(f.id))
      .map((f) => mkFilter(f, f.manufacturer.name))
      .sort((a, b) => a.group.localeCompare(b.group) || a.label.localeCompare(b.label));

    return [...myRig, ...bands, ...others];
  }, [filters, effectiveFilterIds]);

  const initialFilter = useMemo<FilterOpt | null>(() => {
    if (!session) return null;
    if (session.filter_id != null) {
      return filterOptions.find((o) => o.filter_id === session.filter_id) ?? null;
    }
    if (session.line_name != null) {
      return filterOptions.find((o) => o.line_name === session.line_name) ?? null;
    }
    return null;
  }, [session, filterOptions]);

  const [filterSel, setFilterSel] = useState<FilterOpt | null>(initialFilter);
  const [exposure, setExposure] = useState(
    session ? String(session.exposure_seconds) : "",
  );
  const [numSubs, setNumSubs] = useState(session ? String(session.num_subs) : "");
  const [gain, setGain] = useState(session?.gain != null ? String(session.gain) : "");
  const [binning, setBinning] = useState(
    session?.binning != null ? String(session.binning) : session ? "" : "1",
  );
  const [date, setDate] = useState(session?.session_date?.slice(0, 10) ?? "");
  const [notes, setNotes] = useState(session?.notes ?? "");
  const [saving, setSaving] = useState(false);

  const exposureNum = Number(exposure);
  const subsNum = Number(numSubs);
  const valid =
    filterSel != null && exposure !== "" && exposureNum > 0 && numSubs !== "" && subsNum > 0;

  const handleSave = async () => {
    if (!valid) return;
    setSaving(true);
    try {
      await onSubmit({
        filter_id: filterSel?.filter_id ?? null,
        line_name: filterSel?.line_name ?? null,
        exposure_seconds: exposureNum,
        num_subs: subsNum,
        gain: gain === "" ? null : Number(gain),
        binning: binning === "" ? null : Number(binning),
        session_date: date || null,
        rig_id: rig?.id ?? null,
        rig_setup_id: rig?.id == null ? null : rigSetupId,
        notes: notes.trim() || null,
      });
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{session ? "Edit session" : "Add session"}</DialogTitle>
      <DialogContent>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2, mt: 1 }}>
          <Autocomplete
            options={filterOptions}
            value={filterSel}
            onChange={(_e, v) => setFilterSel(v)}
            groupBy={(o) => o.group}
            getOptionLabel={(o) => o.label}
            isOptionEqualToValue={(o, v) => o.key === v.key}
            renderOption={(props, option) => {
              const { key, ...optionProps } = props;
              return (
              <li key={key} {...optionProps}>
                <Box>
                  <Typography variant="body2">{option.label}</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {option.sublabel}
                  </Typography>
                </Box>
              </li>
              );
            }}
            renderInput={(params) => (
              <TextField
                {...params}
                label="Filter / bandpass"
                required
                helperText="Pick a specific filter, or a generic bandpass"
                inputProps={{ ...params.inputProps, readOnly: true }}
              />
            )}
          />

          <Box sx={{ display: "flex", gap: 2 }}>
            <TextField
              label="Exposure (s)"
              type="number"
              required
              value={exposure}
              onChange={(e) => setExposure(e.target.value)}
              inputProps={{ min: 0, step: "any" }}
              sx={{ flex: 1 }}
            />
            <TextField
              label="Sub count"
              type="number"
              required
              value={numSubs}
              onChange={(e) => setNumSubs(e.target.value)}
              inputProps={{ min: 1, step: 1 }}
              sx={{ flex: 1 }}
            />
          </Box>

          <Box sx={{ display: "flex", gap: 2 }}>
            <TextField
              label="Gain"
              type="number"
              value={gain}
              onChange={(e) => setGain(e.target.value)}
              inputProps={{ min: 0, step: 1 }}
              sx={{ flex: 1 }}
            />
            <TextField
              select
              label="Binning"
              value={binning}
              onChange={(e) => setBinning(e.target.value)}
              sx={{ flex: 1 }}
            >
              <MenuItem value="">—</MenuItem>
              <MenuItem value="1">1x1</MenuItem>
              <MenuItem value="2">2x2</MenuItem>
              <MenuItem value="3">3x3</MenuItem>
              <MenuItem value="4">4x4</MenuItem>
            </TextField>
            <TextField
              label="Date"
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              InputLabelProps={{ shrink: true }}
              sx={{ flex: 1.4 }}
            />
          </Box>

          <Autocomplete
            options={rigs}
            value={rig}
            onChange={(_e, value) => {
              setRig(value);
              setRigSetupId(null);
            }}
            getOptionLabel={(option) => `${option.name}${option.active ? "" : " (retired)"}`}
            isOptionEqualToValue={(o, v) => o.id === v.id}
            renderInput={(params) => (
              <TextField
                {...params}
                label="Rig (optional)"
                inputProps={{ ...params.inputProps, readOnly: true }}
              />
            )}
          />

          {(selectedRigSetups?.setup_options.length ?? 0) > 1 && (
            <TextField
              select
              label="Setup"
              value={rigSetupId ?? ""}
              onChange={(event) =>
                setRigSetupId(event.target.value === "" ? null : Number(event.target.value))
              }
              InputLabelProps={{ shrink: true }}
              SelectProps={{
                displayEmpty: true,
                renderValue: (value) => {
                  const setupId = value === "" ? null : Number(value);
                  return setupLabel(
                    selectedRigSetups?.setup_options.find(
                      (option) => option.rig_setup_id === setupId,
                    )?.until_at,
                  );
                },
              }}
            >
              {selectedRigSetups?.setup_options.map((setup) => (
                <MenuItem key={setup.rig_setup_id ?? "now"} value={setup.rig_setup_id ?? ""}>
                  <Box>
                    <Typography variant="body2">
                      {setupLabel(setup.until_at)}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {setup.camera_name}, {setup.image_scale_arcsec_per_pixel.toFixed(2)}″/px
                    </Typography>
                  </Box>
                </MenuItem>
              ))}
            </TextField>
          )}

          <TextField
            label="Notes"
            multiline
            minRows={2}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" disabled={!valid || saving} onClick={handleSave}>
          {session ? "Save" : "Add"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
