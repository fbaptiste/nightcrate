import { useEffect, useRef, useState, type ReactNode } from "react";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Typography from "@mui/material/Typography";

interface Props<T> {
  items: T[];
  getKey: (item: T) => React.Key;
  renderItem: (item: T) => ReactNode;
  hasMore: boolean;
  fetchingMore: boolean;
  onLoadMore: () => void;
  loading: boolean;
  emptyMessage: string;
}

/** Scrollable, responsive grid of catalog cards with true infinite scroll.
 *  A sentinel below the cards is watched by an IntersectionObserver (scoped to
 *  this scroller) so the next page loads as the user nears the bottom — no MUI X
 *  pagination cap, unlike the DataGrid. */
export default function CatalogCardList<T>({
  items,
  getKey,
  renderItem,
  hasMore,
  fetchingMore,
  onLoadMore,
  loading,
  emptyMessage,
}: Props<T>) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const [intersecting, setIntersecting] = useState(false);

  // Track sentinel visibility as state.
  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;
    const obs = new IntersectionObserver(
      (entries) => setIntersecting(entries[0].isIntersecting),
      { root: scrollRef.current, rootMargin: "600px" },
    );
    obs.observe(sentinel);
    return () => obs.disconnect();
  }, []);

  // Load while the sentinel stays in view. Depending on `fetchingMore` re-runs
  // this after each page settles, so a sentinel that's still visible (its prior
  // intersection never re-fired the observer) keeps pulling pages until the
  // viewport is filled or the data is exhausted.
  useEffect(() => {
    if (intersecting && hasMore && !fetchingMore) onLoadMore();
  }, [intersecting, hasMore, fetchingMore, onLoadMore]);

  return (
    <Box ref={scrollRef} sx={{ flex: 1, minHeight: 0, overflowY: "auto", pr: 0.5 }}>
      {loading && items.length === 0 ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 5 }}>
          <CircularProgress />
        </Box>
      ) : items.length === 0 ? (
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ py: 5, textAlign: "center" }}
        >
          {emptyMessage}
        </Typography>
      ) : (
        <Box
          sx={{
            display: "flex",
            flexDirection: "column",
            gap: 1.5,
            // One card per row; capped so it doesn't stretch across a wide monitor.
            maxWidth: 900,
          }}
        >
          {items.map((it) => (
            <Box key={getKey(it)}>{renderItem(it)}</Box>
          ))}
        </Box>
      )}
      <Box ref={sentinelRef} sx={{ height: "1px" }} />
      {fetchingMore && (
        <Box sx={{ display: "flex", justifyContent: "center", py: 2 }}>
          <CircularProgress size={24} />
        </Box>
      )}
    </Box>
  );
}
