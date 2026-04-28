/**
 * Wishlist tab content for the Target Planner.
 *
 * Planned targets are organized into user-created sections with
 * cross-container drag-and-drop (dnd-kit Multiple Containers pattern).
 * Items can be dragged between sections or reordered within a section.
 * Sections themselves can be reordered.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  closestCorners,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragOverEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  verticalListSortingStrategy,
  sortableKeyboardCoordinates,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import CalendarMonthIcon from "@mui/icons-material/CalendarMonth";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import DragIndicatorIcon from "@mui/icons-material/DragIndicator";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowUpIcon from "@mui/icons-material/KeyboardArrowUp";
import EditIcon from "@mui/icons-material/Edit";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ListIcon from "@mui/icons-material/List";
import MoveDownIcon from "@mui/icons-material/MoveDown";
import StarIcon from "@mui/icons-material/Star";
import {
  useFavoritesFull,
  useRemoveFavorite,
  useDeletePlan,
  useReorderFavorites,
  useSectionMutations,
  type FavoriteFullItem,
  type PlanSummary,
  type SectionResponse,
  type ReorderItem,
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

const UNSECTIONED_ID = "__unsectioned__";

interface SectionGroup {
  id: string;
  name: string;
  sectionDbId: number | null;
  items: FavoriteFullItem[];
}

function isFullyPlanned(i: FavoriteFullItem): boolean {
  return i.plan_count > 0 && i.plans.some((p) => p.date_ranges.length > 0);
}

function buildSectionGroups(
  items: FavoriteFullItem[],
  sections: SectionResponse[],
): SectionGroup[] {
  const planned = items.filter(isFullyPlanned);
  const bySection = new Map<number | null, FavoriteFullItem[]>();
  for (const item of planned) {
    const key = item.section_id;
    const list = bySection.get(key) ?? [];
    list.push(item);
    bySection.set(key, list);
  }
  const groups: SectionGroup[] = [];
  const general = bySection.get(null) ?? [];
  groups.push({
    id: UNSECTIONED_ID,
    name: "General",
    sectionDbId: null,
    items: general,
  });
  for (const sec of sections) {
    groups.push({
      id: `section-${sec.id}`,
      name: sec.name,
      sectionDbId: sec.id,
      items: bySection.get(sec.id) ?? [],
    });
  }
  return groups;
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
  const sectionMutations = useSectionMutations();

  const items = data?.items ?? [];
  const sections = data?.sections ?? [];
  const unassigned = items.filter((i) => !isFullyPlanned(i));

  const [localGroups, setLocalGroups] = useState<SectionGroup[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [collapsedSections, setCollapsedSections] = useState<Set<string>>(new Set());

  const toggleCollapse = useCallback((groupId: string) => {
    setCollapsedSections((prev) => {
      const next = new Set(prev);
      if (next.has(groupId)) next.delete(groupId);
      else next.add(groupId);
      return next;
    });
  }, []);

  useEffect(() => {
    setLocalGroups(buildSectionGroups(items, sections));
  }, [items, sections]);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const findContainer = useCallback(
    (id: string): string | null => {
      if (id.startsWith("section-") || id === UNSECTIONED_ID) return id;
      for (const g of localGroups) {
        if (g.items.some((i) => `item-${i.dso.dso_id}` === id)) return g.id;
      }
      return null;
    },
    [localGroups],
  );

  const activeItem = useMemo(() => {
    if (!activeId || !activeId.startsWith("item-")) return null;
    const dsoId = Number(activeId.replace("item-", ""));
    for (const g of localGroups) {
      const found = g.items.find((i) => i.dso.dso_id === dsoId);
      if (found) return found;
    }
    return null;
  }, [activeId, localGroups]);

  function handleDragStart(event: DragStartEvent) {
    setActiveId(String(event.active.id));
  }

  function handleDragOver(event: DragOverEvent) {
    const { active, over } = event;
    if (!over) return;
    const activeIdStr = String(active.id);
    const overIdStr = String(over.id);
    if (!activeIdStr.startsWith("item-")) return;

    const activeContainer = findContainer(activeIdStr);
    let overContainer = findContainer(overIdStr);
    if (overIdStr.startsWith("section-") || overIdStr === UNSECTIONED_ID) {
      overContainer = overIdStr;
    }
    if (!activeContainer || !overContainer || activeContainer === overContainer) return;

    setLocalGroups((prev) => {
      const activeGroupIdx = prev.findIndex((g) => g.id === activeContainer);
      const overGroupIdx = prev.findIndex((g) => g.id === overContainer);
      if (activeGroupIdx === -1 || overGroupIdx === -1) return prev;

      const activeItems = [...prev[activeGroupIdx].items];
      const overItems = [...prev[overGroupIdx].items];
      const itemIdx = activeItems.findIndex((i) => `item-${i.dso.dso_id}` === activeIdStr);
      if (itemIdx === -1) return prev;

      const [moved] = activeItems.splice(itemIdx, 1);
      const overItemIdx = overItems.findIndex((i) => `item-${i.dso.dso_id}` === overIdStr);
      overItems.splice(overItemIdx >= 0 ? overItemIdx : overItems.length, 0, moved);

      const next = [...prev];
      next[activeGroupIdx] = { ...next[activeGroupIdx], items: activeItems };
      next[overGroupIdx] = { ...next[overGroupIdx], items: overItems };
      return next;
    });
  }

  function handleMoveSection(sectionDbId: number, direction: "up" | "down") {
    const namedGroups = localGroups.filter((g) => g.sectionDbId !== null);
    const idx = namedGroups.findIndex((g) => g.sectionDbId === sectionDbId);
    if (idx === -1) return;
    const newIdx = direction === "up" ? idx - 1 : idx + 1;
    if (newIdx < 0 || newIdx >= namedGroups.length) return;
    const ids = namedGroups.map((g) => g.sectionDbId!);
    [ids[idx], ids[newIdx]] = [ids[newIdx], ids[idx]];
    sectionMutations.reorder.mutate(ids);
  }

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    setActiveId(null);
    if (!over || active.id === over.id) return;

    const activeIdStr = String(active.id);
    const overIdStr = String(over.id);

    if (activeIdStr.startsWith("item-")) {
      const container = findContainer(activeIdStr);
      const overContainer = findContainer(overIdStr);
      if (container && container === overContainer) {
        setLocalGroups((prev) => {
          const gIdx = prev.findIndex((g) => g.id === container);
          if (gIdx === -1) return prev;
          const items = [...prev[gIdx].items];
          const oldIdx = items.findIndex((i) => `item-${i.dso.dso_id}` === activeIdStr);
          const newIdx = items.findIndex((i) => `item-${i.dso.dso_id}` === overIdStr);
          if (oldIdx === -1 || newIdx === -1) return prev;
          const [moved] = items.splice(oldIdx, 1);
          items.splice(newIdx, 0, moved);
          const next = [...prev];
          next[gIdx] = { ...next[gIdx], items };
          return next;
        });
      }
      persistOrder();
    }
  }

  function persistOrder() {
    setTimeout(() => {
      setLocalGroups((current) => {
        const reorderItems: ReorderItem[] = [];
        for (const group of current) {
          for (let i = 0; i < group.items.length; i++) {
            reorderItems.push({
              dso_id: group.items[i].dso.dso_id,
              section_id: group.sectionDbId,
              sort_order: i,
            });
          }
        }
        if (reorderItems.length > 0) {
          reorderFavorites.mutate(reorderItems);
        }
        return current;
      });
    }, 0);
  }

  function handleAddSection() {
    sectionMutations.create.mutate("New Section");
  }

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
          {/* Unassigned section — no drag */}
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
                    sections={sections}
                    onRemoveFavorite={() => removeFavorite.mutate(fav.dso.dso_id)}
                    onAddPlan={() => setEditorState({ open: true, dsoId: fav.dso.dso_id, planId: null })}
                    onEditPlan={(planId) => setEditorState({ open: true, dsoId: fav.dso.dso_id, planId })}
                    onDeletePlan={(planId) => deletePlan.mutate(planId)}
                    onMoveToSection={(sectionId) => sectionMutations.move.mutate({ dsoId: fav.dso.dso_id, sectionId })}
                  />
                ))}
              </Stack>
            </>
          )}

          {/* Planned sections — cross-container DnD */}
          {localGroups.length > 0 && (
            <>
              {unassigned.length > 0 && <Divider sx={{ my: 1 }} />}
              <Stack direction="row" justifyContent="space-between" alignItems="center">
                <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: 1.5 }}>
                  Planned
                </Typography>
                <Button
                  size="small"
                  startIcon={<AddIcon />}
                  onClick={handleAddSection}
                  sx={{ textTransform: "none" }}
                >
                  Add Section
                </Button>
              </Stack>

              <DndContext
                sensors={sensors}
                collisionDetection={closestCorners}
                onDragStart={handleDragStart}
                onDragOver={handleDragOver}
                onDragEnd={handleDragEnd}
              >
                <Stack gap={2}>
                  {/* General (pinned, not sortable as a section) */}
                  {localGroups.length > 0 && localGroups[0].id === UNSECTIONED_ID && (
                    <DroppableSection
                      key={UNSECTIONED_ID}
                      group={localGroups[0]}
                      sections={sections}
                      collapsed={collapsedSections.has(UNSECTIONED_ID)}
                      onToggleCollapse={() => toggleCollapse(UNSECTIONED_ID)}
                      onRename={() => {}}
                      onDelete={() => {}}
                      onRemoveFavorite={(dsoId) => removeFavorite.mutate(dsoId)}
                      onAddPlan={(dsoId) => setEditorState({ open: true, dsoId, planId: null })}
                      onEditPlan={(dsoId, planId) => setEditorState({ open: true, dsoId, planId })}
                      onDeletePlan={(planId) => deletePlan.mutate(planId)}
                      onMoveToSection={(dsoId, sectionId) => sectionMutations.move.mutate({ dsoId, sectionId })}
                    />
                  )}

                  {/* Named sections — reorder via up/down buttons */}
                  {(() => {
                    const named = localGroups.filter((g) => g.sectionDbId !== null);
                    return named.map((group, idx) => (
                      <DroppableSection
                        key={group.id}
                        group={group}
                        sections={sections}
                        collapsed={collapsedSections.has(group.id)}
                        onToggleCollapse={() => toggleCollapse(group.id)}
                        onRename={(name) => {
                          if (group.sectionDbId) sectionMutations.rename.mutate({ id: group.sectionDbId, name });
                        }}
                        onDelete={() => {
                          if (group.sectionDbId) sectionMutations.remove.mutate(group.sectionDbId);
                        }}
                        onRemoveFavorite={(dsoId) => removeFavorite.mutate(dsoId)}
                        onAddPlan={(dsoId) => setEditorState({ open: true, dsoId, planId: null })}
                        onEditPlan={(dsoId, planId) => setEditorState({ open: true, dsoId, planId })}
                        onDeletePlan={(planId) => deletePlan.mutate(planId)}
                        onMoveToSection={(dsoId, sectionId) => sectionMutations.move.mutate({ dsoId, sectionId })}
                        onMoveUp={idx > 0 ? () => handleMoveSection(group.sectionDbId!, "up") : undefined}
                        onMoveDown={idx < named.length - 1 ? () => handleMoveSection(group.sectionDbId!, "down") : undefined}
                      />
                    ));
                  })()}
                </Stack>

                <DragOverlay>
                  {activeItem && (
                    <Card variant="outlined" sx={{ borderRadius: 2, p: 1.5, opacity: 0.9 }}>
                      <Stack direction="row" gap={1} alignItems="center">
                        <ThumbnailCell dsoId={activeItem.dso.dso_id} size={48} />
                        <Typography variant="body2" fontWeight={600}>
                          {activeItem.dso.primary_designation}
                        </Typography>
                        {activeItem.dso.common_name && (
                          <Typography variant="body2" color="text.secondary">
                            {activeItem.dso.common_name}
                          </Typography>
                        )}
                      </Stack>
                    </Card>
                  )}
                </DragOverlay>
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


// ── Droppable Section ───────────────────────────────────────────────────────

interface DroppableSectionProps {
  group: SectionGroup;
  sections: SectionResponse[];
  collapsed: boolean;
  onToggleCollapse: () => void;
  onRename: (name: string) => void;
  onDelete: () => void;
  onRemoveFavorite: (dsoId: number) => void;
  onAddPlan: (dsoId: number) => void;
  onEditPlan: (dsoId: number, planId: number) => void;
  onDeletePlan: (planId: number) => void;
  onMoveToSection: (dsoId: number, sectionId: number | null) => void;
  onMoveUp?: () => void;
  onMoveDown?: () => void;
}

function DroppableSection({
  group,
  sections,
  collapsed,
  onToggleCollapse,
  onRename,
  onDelete,
  onRemoveFavorite,
  onAddPlan,
  onEditPlan,
  onDeletePlan,
  onMoveToSection,
  onMoveUp,
  onMoveDown,
}: DroppableSectionProps) {
  const { setNodeRef, isOver } = useDroppable({ id: group.id });
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState(group.name);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const isUnsectioned = group.sectionDbId === null;

  return (
    <Box
      ref={setNodeRef}
      sx={{
        borderRadius: 1,
        border: 1,
        borderColor: isOver ? "primary.main" : "divider",
        bgcolor: isOver ? "action.hover" : "transparent",
        p: 1,
        minHeight: 40,
        transition: "border-color 0.15s, background-color 0.15s",
      }}
    >
      <Stack direction="row" alignItems="center" gap={0.5}>
        <IconButton size="small" onClick={onToggleCollapse} sx={{ p: 0.25 }}>
          {collapsed ? <ExpandMoreIcon sx={{ fontSize: 18 }} /> : <ExpandLessIcon sx={{ fontSize: 18 }} />}
        </IconButton>
        {!isUnsectioned && editing ? (
          <TextField
            inputRef={inputRef}
            size="small"
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            onBlur={() => { onRename(editName); setEditing(false); }}
            onKeyDown={(e) => {
              if (e.key === "Enter") { onRename(editName); setEditing(false); }
              if (e.key === "Escape") setEditing(false);
            }}
            sx={{ flex: 1 }}
          />
        ) : (
          <Typography
            variant="subtitle2"
            sx={{
              flex: 1,
              cursor: isUnsectioned ? "default" : "pointer",
              color: isUnsectioned ? "text.secondary" : "text.primary",
            }}
            onClick={() => {
              if (!isUnsectioned) { setEditName(group.name); setEditing(true); }
            }}
          >
            {group.name}
            <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 1 }}>
              ({group.items.length})
            </Typography>
          </Typography>
        )}
        {(onMoveUp || onMoveDown) && (
          <Stack direction="row" gap={0}>
            <IconButton
              size="small"
              onClick={onMoveUp}
              disabled={!onMoveUp}
              sx={{ p: 0.25 }}
            >
              <KeyboardArrowUpIcon sx={{ fontSize: 20 }} />
            </IconButton>
            <IconButton
              size="small"
              onClick={onMoveDown}
              disabled={!onMoveDown}
              sx={{ p: 0.25 }}
            >
              <KeyboardArrowDownIcon sx={{ fontSize: 20 }} />
            </IconButton>
          </Stack>
        )}
        {!isUnsectioned && !editing && (
          <Tooltip title="Delete section" arrow>
            <IconButton size="small" onClick={onDelete}>
              <DeleteOutlineIcon sx={{ fontSize: 16 }} />
            </IconButton>
          </Tooltip>
        )}
      </Stack>

      <Collapse in={!collapsed} unmountOnExit>
        <SortableContext
          items={group.items.map((i) => `item-${i.dso.dso_id}`)}
          strategy={verticalListSortingStrategy}
        >
          <Stack gap={1} sx={{ mt: 1 }}>
            {group.items.map((fav) => (
              <SortableFavoriteCard
                key={fav.dso.dso_id}
                item={fav}
                sections={sections}
                onRemoveFavorite={() => onRemoveFavorite(fav.dso.dso_id)}
                onAddPlan={() => onAddPlan(fav.dso.dso_id)}
                onEditPlan={(planId) => onEditPlan(fav.dso.dso_id, planId)}
                onDeletePlan={(planId) => onDeletePlan(planId)}
                onMoveToSection={(sectionId) => onMoveToSection(fav.dso.dso_id, sectionId)}
              />
            ))}
          </Stack>
        </SortableContext>

        {group.items.length === 0 && (
          <Typography variant="caption" color="text.disabled" sx={{ textAlign: "center", display: "block", py: 1 }}>
            Drop targets here
          </Typography>
        )}
      </Collapse>
    </Box>
  );
}


// ── Sortable + plain cards ──────────────────────────────────────────────────

interface FavoriteCardProps {
  item: FavoriteFullItem;
  sections: SectionResponse[];
  onRemoveFavorite: () => void;
  onAddPlan: () => void;
  onEditPlan: (planId: number) => void;
  onDeletePlan: (planId: number) => void;
  onMoveToSection?: (sectionId: number | null) => void;
}

function SortableFavoriteCard(props: FavoriteCardProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: `item-${props.item.dso.dso_id}` });

  return (
    <Box
      ref={setNodeRef}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0 : 1,
      }}
    >
      <FavoriteCard {...props} dragHandleProps={{ ...attributes, ...listeners }} />
    </Box>
  );
}


function FavoriteCard({
  item,
  sections,
  onRemoveFavorite,
  onAddPlan,
  onEditPlan,
  onDeletePlan,
  onMoveToSection,
  dragHandleProps,
}: FavoriteCardProps & {
  dragHandleProps?: Record<string, unknown>;
}) {
  const { dso, plans } = item;
  const [moveAnchor, setMoveAnchor] = useState<HTMLElement | null>(null);

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

        <Stack sx={{ flexShrink: 0 }} gap={0.25}>
          <Tooltip title="Remove from wishlist" arrow>
            <IconButton
              size="small"
              onClick={onRemoveFavorite}
              sx={{ color: RIG_ORANGE }}
            >
              <StarIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          {onMoveToSection && sections.length > 0 && (
            <>
              <Tooltip title="Move to section" arrow>
                <IconButton size="small" onClick={(e) => setMoveAnchor(e.currentTarget)}>
                  <MoveDownIcon sx={{ fontSize: 16 }} />
                </IconButton>
              </Tooltip>
              <Menu
                anchorEl={moveAnchor}
                open={Boolean(moveAnchor)}
                onClose={() => setMoveAnchor(null)}
              >
                <MenuItem
                  onClick={() => { onMoveToSection(null); setMoveAnchor(null); }}
                  selected={item.section_id === null}
                >
                  General
                </MenuItem>
                {sections.map((sec) => (
                  <MenuItem
                    key={sec.id}
                    onClick={() => { onMoveToSection(sec.id); setMoveAnchor(null); }}
                    selected={item.section_id === sec.id}
                  >
                    {sec.name}
                  </MenuItem>
                ))}
              </Menu>
            </>
          )}
        </Stack>
      </Stack>
    </Card>
  );
}


// ── Plan row ────────────────────────────────────────────────────────────────

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
