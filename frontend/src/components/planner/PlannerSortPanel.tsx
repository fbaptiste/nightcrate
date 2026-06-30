/**
 * Multi-sort panel for the Target Planner.
 *
 * Collapsible accordion under the imaging sliders. The header shows
 * a compact summary of the active sort; the body exposes two pill
 * containers — ``Available`` (fields the user hasn't added) and
 * ``Sort by`` (the active ordered sort).
 *
 * UX semantics:
 * - CLICK an Available pill to add it to Sort-By (at the end). Four
 *   attempts at cross-container drag-drop with dnd-kit resulted in
 *   state thrash or silent drop failures; click is unambiguous and
 *   matches how established sort-pill UIs work.
 * - DRAG a Sort-By pill within the Sort-By area to reorder.
 * - CLICK the ↑/↓ on a Sort-By pill to flip its direction.
 * - CLICK the X on a Sort-By pill to remove it.
 *
 * Implementation: only Sort-By uses dnd-kit (single ``SortableContext``
 * with ``useSortable`` pills). Available is plain clickable Chips.
 */
import { useState } from "react";
import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import CloseIcon from "@mui/icons-material/Close";
import DragIndicatorIcon from "@mui/icons-material/DragIndicator";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
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
  arrayMove,
  horizontalListSortingStrategy,
  sortableKeyboardCoordinates,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  PLANNER_SORT_FIELDS,
  sortFieldAvailable,
  sortFieldDescription,
  sortFieldLabel,
  type SortDir,
  type SortEntry,
} from "@/lib/plannerSortFields";
import { DEFAULT_SORT } from "@/stores/plannerStore";

interface Props {
  sortBy: SortEntry[];
  onSortChange: (next: SortEntry[]) => void;
  restrictTonight: boolean;
  rigSelected: boolean;
  /** Whether the planner's selected night is today. Gates today-only
   *  fields (now_status). Defaults to true (Full Catalog never sets a date). */
  isToday?: boolean;
}

export default function PlannerSortPanel({
  sortBy,
  onSortChange,
  restrictTonight,
  rigSelected,
  isToday = true,
}: Props) {
  const [expanded, setExpanded] = useState(true);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const used = new Set(sortBy.map((e) => e.field));
  const available = PLANNER_SORT_FIELDS.filter(
    (f) =>
      sortFieldAvailable(f.field, restrictTonight, rigSelected, isToday) &&
      !used.has(f.field),
  );

  const visibleSortBy = sortBy.filter((e) =>
    sortFieldAvailable(e.field, restrictTonight, rigSelected, isToday),
  );
  const sortByIds = visibleSortBy.map((e) => e.field);

  function addEntry(field: string) {
    if (sortBy.some((e) => e.field === field)) return;
    onSortChange([...sortBy, { field, dir: "asc" }]);
  }

  function toggleDirection(field: string) {
    onSortChange(
      sortBy.map((e) =>
        e.field === field ? { ...e, dir: e.dir === "asc" ? "desc" : "asc" } : e,
      ),
    );
  }

  function removeEntry(field: string) {
    onSortChange(sortBy.filter((e) => e.field !== field));
  }

  // Reset button is only shown when the current sort differs from the
  // store-level default.
  const isDefaultSort =
    sortBy.length === DEFAULT_SORT.length &&
    sortBy.every((e, i) => e.field === DEFAULT_SORT[i].field && e.dir === DEFAULT_SORT[i].dir);
  function resetToDefault() {
    onSortChange(DEFAULT_SORT);
  }

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const activeId = String(active.id);
    const overId = String(over.id);
    const oldIdx = sortBy.findIndex((e) => e.field === activeId);
    const newIdx = sortBy.findIndex((e) => e.field === overId);
    if (oldIdx === -1 || newIdx === -1 || oldIdx === newIdx) return;
    onSortChange(arrayMove(sortBy, oldIdx, newIdx));
  }

  const summary = visibleSortBy.length === 0 ? null : (
    <Stack direction="row" gap={0.5} flexWrap="wrap">
      {visibleSortBy.map((e) => (
        <Tooltip key={e.field} title={sortFieldDescription(e.field)}>
          <Chip
            size="small"
            label={
              <Stack direction="row" alignItems="center" gap={0.25} sx={{ fontSize: "0.75rem" }}>
                {sortFieldLabel(e.field)}
                {e.dir === "asc" ? (
                  <ArrowUpwardIcon sx={{ fontSize: "0.85rem" }} />
                ) : (
                  <ArrowDownwardIcon sx={{ fontSize: "0.85rem" }} />
                )}
              </Stack>
            }
            variant="outlined"
            sx={{ borderRadius: 1 }}
          />
        </Tooltip>
      ))}
    </Stack>
  );

  return (
    <Accordion
      expanded={expanded}
      onChange={(_, next) => setExpanded(next)}
      disableGutters
      sx={{ mt: 2, boxShadow: "none", bgcolor: "transparent", backgroundImage: "none", "&::before": { display: "none" } }}
    >
      <AccordionSummary
        expandIcon={<ExpandMoreIcon />}
        sx={{ minHeight: 36, px: 1, borderRadius: 1, bgcolor: "action.hover", "& .MuiAccordionSummary-content": { my: 0.5 } }}
      >
        <Stack direction="row" alignItems="center" gap={1.5} sx={{ width: "100%" }}>
          <Typography variant="body2" fontWeight={500}>
            Sorting
          </Typography>
          {summary ?? (
            <Typography variant="caption" color="text.secondary">
              default
            </Typography>
          )}
        </Stack>
      </AccordionSummary>
      <AccordionDetails sx={{ px: 0 }}>
        <Stack gap={1.5}>
          <Box>
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{
                display: "block",
                textTransform: "uppercase",
                letterSpacing: 0.4,
                mb: 0.5,
              }}
            >
              Sort by (drag pills to reorder)
            </Typography>
            <Box
              sx={{
                minHeight: 44,
                px: 1,
                py: 0.75,
                borderRadius: 1,
                border: 1,
                borderStyle: "dashed",
                borderColor: "divider",
              }}
            >
              {visibleSortBy.length === 0 ? (
                <Typography variant="caption" color="text.disabled">
                  Click a field below to start sorting.
                </Typography>
              ) : (
                <DndContext
                  sensors={sensors}
                  collisionDetection={closestCenter}
                  onDragEnd={handleDragEnd}
                >
                  <SortableContext
                    items={sortByIds}
                    strategy={horizontalListSortingStrategy}
                  >
                    <Stack direction="row" gap={0.75} flexWrap="wrap">
                      {visibleSortBy.map((e) => (
                        <SortByPill
                          key={e.field}
                          field={e.field}
                          dir={e.dir}
                          onToggleDir={() => toggleDirection(e.field)}
                          onRemove={() => removeEntry(e.field)}
                        />
                      ))}
                    </Stack>
                  </SortableContext>
                </DndContext>
              )}
            </Box>
          </Box>

          <Box>
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{
                display: "block",
                textTransform: "uppercase",
                letterSpacing: 0.4,
                mb: 0.5,
              }}
            >
              Available (click to add)
            </Typography>
            <Box
              sx={{
                minHeight: 44,
                px: 1,
                py: 0.75,
                borderRadius: 1,
                border: 1,
                borderStyle: "dashed",
                borderColor: "divider",
              }}
            >
              {available.length === 0 ? (
                <Typography variant="caption" color="text.disabled">
                  (all fields in use)
                </Typography>
              ) : (
                <Stack direction="row" gap={0.75} flexWrap="wrap">
                  {available.map((f) => (
                    <Tooltip key={f.field} title={f.description}>
                      <Chip
                        label={f.label}
                        size="small"
                        variant="outlined"
                        onClick={() => addEntry(f.field)}
                        sx={{
                          borderRadius: 1,
                          cursor: "pointer",
                        }}
                      />
                    </Tooltip>
                  ))}
                </Stack>
              )}
            </Box>
          </Box>

          {!isDefaultSort && (
            <Box sx={{ display: "flex", justifyContent: "flex-end" }}>
              <Button size="small" variant="text" onClick={resetToDefault}>
                Reset sorting
              </Button>
            </Box>
          )}
        </Stack>
      </AccordionDetails>
    </Accordion>
  );
}


// ── Sort-By pill (sortable) ─────────────────────────────────────────────────


function SortByPill({
  field,
  dir,
  onToggleDir,
  onRemove,
}: {
  field: string;
  dir: SortDir;
  onToggleDir: () => void;
  onRemove: () => void;
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    setActivatorNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: field });

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
  };

  return (
    <Stack
      ref={setNodeRef}
      style={style}
      direction="row"
      alignItems="center"
      sx={{
        borderRadius: 999,
        pl: 0.25,
        pr: 0.5,
        py: 0.25,
        bgcolor: "primary.main",
        color: "primary.contrastText",
        fontSize: "0.8rem",
      }}
    >
      <IconButton
        size="small"
        ref={setActivatorNodeRef}
        {...attributes}
        {...listeners}
        sx={{ color: "inherit", cursor: "grab", p: 0.25 }}
        aria-label={`Drag ${sortFieldLabel(field)}`}
      >
        <DragIndicatorIcon fontSize="small" />
      </IconButton>
      <Tooltip title={sortFieldDescription(field)}>
        <Typography variant="body2" sx={{ px: 0.5, fontSize: "0.8rem" }}>
          {sortFieldLabel(field)}
        </Typography>
      </Tooltip>
      <Tooltip
        title={dir === "asc" ? "Ascending (click to flip)" : "Descending (click to flip)"}
      >
        <IconButton
          size="small"
          onClick={onToggleDir}
          sx={{ color: "inherit", p: 0.25 }}
          aria-label="Toggle direction"
        >
          {dir === "asc" ? (
            <ArrowUpwardIcon fontSize="small" />
          ) : (
            <ArrowDownwardIcon fontSize="small" />
          )}
        </IconButton>
      </Tooltip>
      <Tooltip title="Remove from sort">
        <IconButton
          size="small"
          onClick={onRemove}
          sx={{ color: "inherit", p: 0.25 }}
          aria-label="Remove"
        >
          <CloseIcon fontSize="small" />
        </IconButton>
      </Tooltip>
    </Stack>
  );
}
