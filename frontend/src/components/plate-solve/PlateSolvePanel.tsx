import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocation, useNavigate } from "react-router-dom";
import { useTheme } from "@mui/material/styles";

import { fetchDsos, type DsoListItem } from "@/api/dsos";
import type { HeaderCard } from "@/api/images";
import type {
  PlateSolveRequest,
  PlateSolveResult,
  PlateSolver,
} from "@/api/plateSolve";
import { fetchRigs } from "@/api/rigs";
import { useStarCatalogStatus } from "@/api/starCatalog";
import { useSettingsStore } from "@/stores/settingsStore";
import {
  buildRequest,
  headerHints,
  type AppliedHints,
  type PositionHint,
  type ScaleHint,
} from "./hintModel";
import {
  PanelEditor,
  PanelFailure,
  PanelSolving,
  PanelSummary,
} from "./PlateSolvePanelStates";
import { formatHintNumber, formatPosition, scaleValue } from "./panelHelpers";
import { solveColors } from "./solvePalette";
import { type SolveOutcome, useSolveOperation } from "./useSolveOperation";

export type { SolveOutcome } from "./useSolveOperation";

interface PlateSolvePanelProps {
  image: { path: string; hdu: number; cards: HeaderCard[] };
  scope: { surface: "project"; projectId: number } | { surface: "analyzer" };
  solve: (req: PlateSolveRequest) => Promise<SolveOutcome>;
  primaryLabel: string;
  replacing?: boolean;
  active: boolean;
  onSolved: (result: PlateSolveResult) => void;
  onStale: () => void;
  onChooseImage: () => void;
  dismiss?: { label: string; onClick: () => void };
}

function snapshotKey(scope: PlateSolvePanelProps["scope"], path: string, hdu: number) {
  return scope.surface === "project"
    ? `plate-solve:project:${scope.projectId}:${path}:${hdu}`
    : `plate-solve:analyzer:${path}:${hdu}`;
}

function readSnapshot(key: string): AppliedHints | null {
  try {
    const value = sessionStorage.getItem(key);
    return value ? (JSON.parse(value) as AppliedHints) : null;
  } catch {
    return null;
  }
}

function writeSnapshot(key: string, value: AppliedHints) {
  try {
    sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Session storage may be unavailable in privacy modes.
  }
}

export default function PlateSolvePanel({
  image,
  scope,
  solve,
  primaryLabel,
  replacing = false,
  active,
  onSolved,
  onStale,
  onChooseImage,
  dismiss,
}: PlateSolvePanelProps) {
  const theme = useTheme();
  const navigate = useNavigate();
  const location = useLocation();
  const settings = useSettingsStore((state) => state.settings);
  const header = useMemo(() => headerHints(image.cards), [image.cards]);
  const key = snapshotKey(scope, image.path, image.hdu);
  const initial = useMemo<AppliedHints>(
    () =>
      readSnapshot(key) ?? {
        position: { kind: "header" },
        scale: { kind: "header" },
        solver: settings?.default_solver ?? "native",
      },
    [key, settings?.default_solver],
  );
  const [applied, setApplied] = useState<AppliedHints>(initial);
  const [draft, setDraft] = useState<AppliedHints>(initial);
  const [editing, setEditing] = useState(false);
  const [targetInput, setTargetInput] = useState("");
  const [targets, setTargets] = useState<DsoListItem[]>([]);
  const [searching, setSearching] = useState(false);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setApplied(initial);
    setDraft(initial);
    setEditing(false);
  }, [initial]);

  useEffect(
    () => () => {
      if (searchTimer.current) clearTimeout(searchTimer.current);
    },
    [],
  );

  const rigsQuery = useQuery({
    queryKey: ["rigs", "mine"],
    queryFn: () => fetchRigs(true, true),
    enabled: active,
    staleTime: 60_000,
  });
  const starCatalog = useStarCatalogStatus(active);
  const hasBuiltRange =
    starCatalog.data?.ranges.some((range) => range.state === "built") ?? false;
  const appliedHasPosition =
    applied.position.kind === "target" ||
    (applied.position.kind === "header" && header.ra != null && header.dec != null);
  const nativeAvailable =
    !!starCatalog.data?.installed && (appliedHasPosition || hasBuiltRange);
  const astapAvailable = !!settings?.astap_executable_path;
  const solverAvailable =
    applied.solver === "native" ? nativeAvailable : astapAvailable;

  const operation = useSolveOperation({
    image,
    active,
    solveRequest: solve,
    onSolved,
    onStale,
  });

  const persist = useCallback(
    (next: AppliedHints) => {
      setApplied(next);
      setDraft(next);
      writeSnapshot(key, next);
    },
    [key],
  );

  const startSolve = useCallback(
    (solverOverride?: PlateSolver) => {
      const next = solverOverride ? { ...applied, solver: solverOverride } : applied;
      if (solverOverride) persist(next);
      void operation.run(buildRequest(image, next));
    },
    [applied, image, operation, persist],
  );

  const handleTargetSearch = (value: string) => {
    setTargetInput(value);
    if (searchTimer.current) clearTimeout(searchTimer.current);
    if (value.trim().length < 2) {
      setTargets([]);
      setSearching(false);
      return;
    }
    setSearching(true);
    searchTimer.current = setTimeout(async () => {
      try {
        setTargets((await fetchDsos({ q: value.trim(), limit: 10 })).items);
      } catch {
        setTargets([]);
      } finally {
        setSearching(false);
      }
    }, 300);
  };

  const setPositionKind = (kind: PositionHint["kind"]) => {
    setDraft((current) => {
      if (kind !== "target") return { ...current, position: { kind } };
      const position =
        current.position.kind === "target"
          ? current.position
          : { kind: "target" as const, id: 0, label: "", ra: 0, dec: 0 };
      return { ...current, position };
    });
  };

  const setScaleKind = (kind: ScaleHint["kind"]) => {
    setDraft((current) => {
      if (current.scale.kind === kind) return current;
      if (kind === "rig") {
        const rig = rigsQuery.data?.[0];
        return {
          ...current,
          scale: rig
            ? {
                kind,
                rigId: rig.id,
                rigName: rig.name,
                focalLengthMm: rig.effective_focal_length_mm,
                pixelSizeUm: rig.pixel_size_um,
                binning: 1,
              }
            : {
                kind,
                rigId: 0,
                rigName: "",
                focalLengthMm: 0,
                pixelSizeUm: 0,
                binning: 1,
              },
        };
      }
      if (kind === "calc") {
        return {
          ...current,
          scale: {
            kind,
            focalLengthMm: header.focalLengthMm ?? 0,
            pixelSizeUm: header.physicalPixelUm ?? 0,
            binning: header.binning,
          },
        };
      }
      if (kind === "enter") {
        return {
          ...current,
          scale: { kind, scaleArcsec: header.scaleArcsec ?? 0 },
        };
      }
      return { ...current, scale: { kind } };
    });
  };

  const positionSummary =
    applied.position.kind === "header"
      ? ["From the image header", formatPosition(header.ra, header.dec)]
      : applied.position.kind === "target"
        ? ["From a target", applied.position.label]
        : ["None", "The solver searches the whole sky"];
  const scale = scaleValue(applied.scale, header);
  const scaleSummary =
    applied.scale.kind === "header"
      ? [
          "From the image header",
          scale != null
            ? `${formatHintNumber(scale, "scale")}″/px (` +
              `${header.focalLengthMm != null ? formatHintNumber(header.focalLengthMm, "focalLength") : "?"} mm, ` +
              `${header.effectivePixelUm != null ? formatHintNumber(header.effectivePixelUm, "pixelSize") : "?"} µm)`
            : "No scale found",
        ]
      : applied.scale.kind === "rig"
        ? [
            "From a rig",
            `${applied.scale.rigName}, binning ${applied.scale.binning}×, ` +
              `${scale != null ? formatHintNumber(scale, "scale") : "?"}″/px`,
          ]
        : applied.scale.kind === "calc"
          ? ["Calculated", `${scale != null ? formatHintNumber(scale, "scale") : "?"}″/px`]
          : applied.scale.kind === "enter"
            ? ["Entered", `${scale != null ? formatHintNumber(scale, "scale") : "?"}″/px`]
            : ["None", "Every scale is searched"];

  if (operation.status === "solving") {
    return (
      <PanelSolving
        solver={operation.lastSolver}
        progress={operation.progress}
        onCancel={operation.cancel}
      />
    );
  }

  if (operation.status === "failed" && operation.failure) {
    const miss =
      theme.palette.mode === "dark" ? solveColors.miss.dark : solveColors.miss.light;
    return (
      <PanelFailure
        failure={operation.failure}
        progress={operation.progress}
        missColor={miss}
        nativeAvailable={nativeAvailable}
        astapAvailable={astapAvailable}
        onChangeHints={() => {
          operation.reset();
          setDraft(applied);
          setEditing(true);
        }}
        onOtherSolver={startSolve}
        onRetry={() => startSolve()}
        onChooseImage={onChooseImage}
      />
    );
  }

  if (editing) {
    return (
      <PanelEditor
        draft={draft}
        setDraft={setDraft}
        header={header}
        rigs={rigsQuery.data ?? []}
        targets={targets}
        targetInput={targetInput}
        searching={searching}
        nativeAvailable={nativeAvailable}
        astapAvailable={astapAvailable}
        onTargetInput={handleTargetSearch}
        onPositionKind={setPositionKind}
        onScaleKind={setScaleKind}
        onApply={() => {
          persist(draft);
          setEditing(false);
        }}
        onCancel={() => {
          setDraft(applied);
          setEditing(false);
        }}
        onReset={() =>
          setDraft({
            position: { kind: "header" },
            scale: { kind: "header" },
            solver: settings?.default_solver ?? "native",
          })
        }
      />
    );
  }

  const edit = () => {
    setDraft(applied);
    setEditing(true);
  };
  return (
    <PanelSummary
      applied={applied}
      positionSummary={positionSummary}
      scaleSummary={scaleSummary}
      primaryLabel={primaryLabel}
      replacing={replacing}
      solverAvailable={solverAvailable}
      astapAvailable={astapAvailable}
      onEdit={edit}
      onSolve={() => startSolve()}
      onSetup={() =>
        navigate(
          `/admin?returnTo=${encodeURIComponent(location.pathname + location.search)}` +
            "#plate-solving-stars",
        )
      }
      onOpenSettings={() =>
        navigate(
          `/settings?returnTo=${encodeURIComponent(location.pathname + location.search)}`,
        )
      }
      onUseAstap={() => persist({ ...applied, solver: "astap" })}
      dismiss={dismiss}
    />
  );
}
