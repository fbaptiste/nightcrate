/**
 * Wishlist tab content for the Target Planner.
 *
 * Shows all favorited targets in two sections:
 *   - Unassigned (no plans yet) — at the top to nudge planning
 *   - Planned (>= 1 assignment) — grouped by target with inline plans
 *
 * A List / Calendar toggle switches between the list view and the
 * Gantt-style calendar (added in a later phase).
 */
import { useState } from "react";
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  verticalListSortingStrategy,
  sortableKeyboardCoordinates,
  useSortable,
  arrayMove,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import CalendarMonthIcon from "@mui/icons-material/CalendarMonth";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import DragIndicatorIcon from "@mui/icons-material/DragIndicator";
import EditIcon from "@mui/icons-material/Edit";
import ListIcon from "@mui/icons-material/List";
import StarIcon from "@mui/icons-material/Star";
import {
  useFavoritesFull,
  useRemoveFavorite,
  useDeletePlan,
  useReorderFavorites,
  type FavoriteFullItem,
  type PlanSummary,
} from "@/api/wishlist";
import { displayDsoType, dsoTypeColor } from "@/lib/dsoTypeNames";
import { displayConstellation } from "@/lib/constellations";
import { RIG_ORANGE } from "@/lib/rigColors";
import PlanAssignmentEditor from "./PlanAssignmentEditor";
import PlanSparkline from "./PlanSparkline";
import ThumbnailCell from "./ThumbnailCell";
import WishlistCalendarView from "./WishlistCalendarView";

type SubView = "list" | "calendar";

interface PlanAssignmentEditorState {
  open: boolean;
  dsoId: number | null;
  planId: number | null;
}

export default function WishlistTab() {
  const [subView, setSubView] = useState<SubView>("list");
  const [editorState, setEditorState] = useState<PlanAssignmentEditorState>({
    open: false,
    dsoId: null,
    planId: null,
  });
  const { data, isLoading } = useFavoritesFull();
  const removeFavorite = useRemoveFavorite();
  const deletePlan = useDeletePlan();
  const reorderFavorites = useReorderFavorites();

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const items = data?.items ?? [];
  const isFullyPlanned = (i: FavoriteFullItem) =>
    i.plan_count > 0 && i.plans.some((p) => p.date_ranges.length > 0);
  const unassigned = items.filter((i) => !isFullyPlanned(i));
  const planned = items.filter(isFullyPlanned);

  if (isLoading) {
    return (
      <Box sx={{ p: 4, textAlign: "center" }}>
        <Typography color="text.secondary">Loading wishlist...</Typography>
      </Box>
    );
  }

  if (items.length === 0) {
    return (
      <Stack alignItems="center" sx={{ p: 6, textAlign: "center" }}>
        <StarIcon sx={{ fontSize: 48, color: "text.disabled", mb: 1 }} />
        <Typography variant="h6" color="text.secondary">
          Your wishlist is empty
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
          Star targets in the Tonight or Full Catalog tabs to add them here.
        </Typography>
      </Stack>
    );
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <Stack
        direction="row"
        justifyContent="space-between"
        alignItems="center"
        sx={{ px: 1.5, pt: 1.5, pb: 1, flexShrink: 0 }}
      >
        <Typography variant="body2" color="text.secondary">
          {items.length} target{items.length !== 1 ? "s" : ""} in wishlist
        </Typography>
        <ToggleButtonGroup
          size="small"
          exclusive
          value={subView}
          onChange={(_, v) => { if (v) setSubView(v); }}
        >
          <ToggleButton value="list" sx={{ textTransform: "none", px: 1.5 }}>
            <ListIcon sx={{ fontSize: 18, mr: 0.5 }} /> List
          </ToggleButton>
          <ToggleButton value="calendar" sx={{ textTransform: "none", px: 1.5 }}>
            <CalendarMonthIcon sx={{ fontSize: 18, mr: 0.5 }} /> Calendar
          </ToggleButton>
        </ToggleButtonGroup>
      </Stack>

      <Box sx={{ flex: 1, minHeight: 0, overflow: "auto", px: 1.5, pb: 1.5 }}>
      {subView === "list" ? (
        <Stack gap={2}>
          {unassigned.length > 0 && (
            <>
              <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: 1.5 }}>
                Unassigned ({unassigned.length})
              </Typography>
              <Stack gap={1}>
                {unassigned.map((fav) => (
                  <FavoriteCard
                    key={fav.dso.dso_id}
                    item={fav}
                    onRemoveFavorite={() => removeFavorite.mutate(fav.dso.dso_id)}
                    onAddPlan={() => setEditorState({ open: true, dsoId: fav.dso.dso_id, planId: null })}
                    onEditPlan={(planId) => setEditorState({ open: true, dsoId: fav.dso.dso_id, planId })}
                    onDeletePlan={(planId) => deletePlan.mutate(planId)}
                  />
                ))}
              </Stack>
            </>
          )}

          {planned.length > 0 && (
            <>
              {unassigned.length > 0 && <Divider sx={{ my: 1 }} />}
              <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: 1.5 }}>
                Planned ({planned.length})
              </Typography>
              <DndContext
                sensors={sensors}
                collisionDetection={closestCenter}
                onDragEnd={(event: DragEndEvent) => {
                  const { active, over } = event;
                  if (!over || active.id === over.id) return;
                  const allDsoIds = items.map((i) => i.dso.dso_id);
                  const oldIdx = allDsoIds.indexOf(Number(active.id));
                  const newIdx = allDsoIds.indexOf(Number(over.id));
                  if (oldIdx === -1 || newIdx === -1) return;
                  reorderFavorites.mutate(arrayMove(allDsoIds, oldIdx, newIdx));
                }}
              >
              <SortableContext
                items={planned.map((i) => i.dso.dso_id)}
                strategy={verticalListSortingStrategy}
              >
              <Stack gap={1}>
                {planned.map((fav) => (
                  <SortableFavoriteCard
                    key={fav.dso.dso_id}
                    item={fav}
                    onRemoveFavorite={() => removeFavorite.mutate(fav.dso.dso_id)}
                    onAddPlan={() => setEditorState({ open: true, dsoId: fav.dso.dso_id, planId: null })}
                    onEditPlan={(planId) => setEditorState({ open: true, dsoId: fav.dso.dso_id, planId })}
                    onDeletePlan={(planId) => deletePlan.mutate(planId)}
                  />
                ))}
              </Stack>
              </SortableContext>
              </DndContext>
            </>
          )}
        </Stack>
      ) : (
        <WishlistCalendarView
          onEditTarget={(dsoId, planId) => setEditorState({ open: true, dsoId, planId })}
        />
      )}
      </Box>

      {editorState.dsoId != null && (() => {
        const fav = items.find((i) => i.dso.dso_id === editorState.dsoId);
        const name = fav
          ? fav.dso.common_name
            ? `${fav.dso.primary_designation} — ${fav.dso.common_name}`
            : fav.dso.primary_designation
          : "";
        return (
          <PlanAssignmentEditor
            open={editorState.open}
            dsoId={editorState.dsoId}
            dsoName={name}
            existingPlan={
              editorState.planId != null
                ? findPlan(items, editorState.planId)
                : null
            }
            onClose={() => setEditorState({ open: false, dsoId: null, planId: null })}
          />
        );
      })()}
    </Box>
  );
}


interface FavoriteCardProps {
  item: FavoriteFullItem;
  onRemoveFavorite: () => void;
  onAddPlan: () => void;
  onEditPlan: (planId: number) => void;
  onDeletePlan: (planId: number) => void;
}

function SortableFavoriteCard(props: FavoriteCardProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: props.item.dso.dso_id });

  return (
    <Box
      ref={setNodeRef}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.5 : 1,
      }}
    >
      <FavoriteCard {...props} dragHandleProps={{ ...attributes, ...listeners }} />
    </Box>
  );
}


function FavoriteCard({
  item,
  onRemoveFavorite,
  onAddPlan,
  onEditPlan,
  onDeletePlan,
  dragHandleProps,
}: FavoriteCardProps & {
  dragHandleProps?: Record<string, unknown>;
}) {
  const { dso, plans } = item;

  return (
    <Card variant="outlined" sx={{ borderRadius: 2, p: 1.5 }}>
      <Stack direction="row" gap={2} alignItems="flex-start">
        {dragHandleProps && (
          <Box
            {...dragHandleProps}
            sx={{
              cursor: "grab",
              color: "text.disabled",
              display: "flex",
              alignItems: "center",
              flexShrink: 0,
              mt: 0.5,
            }}
          >
            <DragIndicatorIcon sx={{ fontSize: 20 }} />
          </Box>
        )}
        <Box sx={{ flexShrink: 0 }}>
          <ThumbnailCell dsoId={dso.dso_id} size={72} />
        </Box>

        <Stack spacing={0.75} sx={{ flex: 1, minWidth: 0 }}>
          <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap">
            <Typography variant="body1" fontWeight={600}>
              {dso.primary_designation}
            </Typography>
            {dso.common_name && (
              <Typography variant="body2" color="text.secondary">
                {dso.common_name}
              </Typography>
            )}
            <Chip
              label={displayDsoType(dso.obj_type)}
              size="small"
              sx={{
                bgcolor: dsoTypeColor(dso.obj_type),
                color: "#ffffff",
                fontWeight: 500,
                height: 20,
                "& .MuiChip-label": { px: 0.85, fontSize: "0.72rem" },
              }}
            />
            {dso.constellation && (
              <Typography variant="caption" color="text.secondary">
                in {displayConstellation(dso.constellation)}
              </Typography>
            )}
          </Stack>

          {plans.length > 0 && (
            <Stack gap={0.75} sx={{ mt: 0.5 }}>
              {plans.map((plan) => (
                <PlanRow
                  key={plan.id}
                  dsoId={dso.dso_id}
                  plan={plan}
                  onEdit={() => onEditPlan(plan.id)}
                  onDelete={() => onDeletePlan(plan.id)}
                />
              ))}
            </Stack>
          )}

          <Stack direction="row" gap={1} alignItems="center" sx={{ mt: 0.5 }}>
            <Button
              size="small"
              startIcon={<AddIcon />}
              onClick={onAddPlan}
              sx={{ textTransform: "none" }}
            >
              Add assignment
            </Button>
          </Stack>
        </Stack>

        <Tooltip title="Remove from wishlist" arrow>
          <IconButton
            size="small"
            onClick={onRemoveFavorite}
            sx={{ color: RIG_ORANGE, flexShrink: 0 }}
          >
            <StarIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Stack>
    </Card>
  );
}


function PlanRow({
  dsoId,
  plan,
  onEdit,
  onDelete,
}: {
  dsoId: number;
  plan: PlanSummary;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const fmtShort = (iso: string) => {
    const d = new Date(`${iso}T00:00:00Z`);
    return d.toLocaleDateString("en", { month: "short", day: "numeric", timeZone: "UTC" });
  };

  return (
    <Stack
      direction="row"
      alignItems="center"
      gap={1}
      sx={{
        pl: 1,
        py: 0.5,
        borderLeft: 3,
        borderColor: "primary.main",
        bgcolor: "action.hover",
        borderRadius: "0 4px 4px 0",
      }}
    >
      <Stack spacing={0.5} sx={{ flex: 1, minWidth: 0 }}>
        <Typography variant="body2" sx={{ fontWeight: 500 }}>
          {plan.location_name} / {plan.horizon_name} / {plan.rig_name}
        </Typography>
        {plan.date_ranges.length > 0 && (
          <Stack direction="row" gap={0.5} flexWrap="wrap">
            {plan.date_ranges.map((r, i) => (
              <Chip
                key={i}
                label={`${fmtShort(r.start_date)} – ${fmtShort(r.end_date)}`}
                size="small"
                variant="outlined"
                sx={{
                  height: 20,
                  "& .MuiChip-label": { px: 0.75, fontSize: "0.68rem" },
                }}
              />
            ))}
          </Stack>
        )}
        {plan.notes && (
          <Typography variant="caption" color="text.secondary" noWrap>
            {plan.notes}
          </Typography>
        )}
      </Stack>

      <PlanSparkline
        dsoId={dsoId}
        locationId={plan.location_id}
        horizonId={plan.horizon_id}
        moonSepDeg={plan.moon_sep_deg}
        dateRanges={plan.date_ranges}
      />

      <Tooltip title="Edit" arrow>
        <IconButton size="small" onClick={onEdit}>
          <EditIcon sx={{ fontSize: 16 }} />
        </IconButton>
      </Tooltip>
      <Tooltip title="Delete" arrow>
        <IconButton size="small" onClick={onDelete}>
          <DeleteOutlineIcon sx={{ fontSize: 16 }} />
        </IconButton>
      </Tooltip>
    </Stack>
  );
}


function findPlan(items: FavoriteFullItem[], planId: number): PlanSummary | null {
  for (const item of items) {
    const found = item.plans.find((p) => p.id === planId);
    if (found) return found;
  }
  return null;
}
