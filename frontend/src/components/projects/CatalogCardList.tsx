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

interface ScrollerProps {
  children: ReactNode;
  itemCount: number;
  hasMore: boolean;
  fetchingMore: boolean;
  onLoadMore: () => void;
  loading: boolean;
  emptyMessage: string;
}

export function CatalogInfiniteScroller({
  children,
  itemCount,
  hasMore,
  fetchingMore,
  onLoadMore,
  loading,
  emptyMessage,
}: ScrollerProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const [intersecting, setIntersecting] = useState(false);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;
    const observer = new IntersectionObserver(
      (entries) => setIntersecting(entries[0].isIntersecting),
      { root: scrollRef.current, rootMargin: "600px" },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (intersecting && hasMore && !fetchingMore) onLoadMore();
  }, [intersecting, hasMore, fetchingMore, onLoadMore]);

  return (
    <Box ref={scrollRef} sx={{ flex: 1, minHeight: 0, overflow: "auto", pr: 0.5 }}>
      {loading && itemCount === 0 ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 5 }}>
          <CircularProgress />
        </Box>
      ) : itemCount === 0 ? (
        <Typography variant="body2" color="text.secondary" sx={{ py: 5, textAlign: "center" }}>
          {emptyMessage}
        </Typography>
      ) : children}
      <Box ref={sentinelRef} sx={{ height: "1px" }} />
      {fetchingMore && (
        <Box sx={{ display: "flex", justifyContent: "center", py: 2 }}>
          <CircularProgress size={24} />
        </Box>
      )}
    </Box>
  );
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
  return (
    <CatalogInfiniteScroller
      itemCount={items.length}
      hasMore={hasMore}
      fetchingMore={fetchingMore}
      onLoadMore={onLoadMore}
      loading={loading}
      emptyMessage={emptyMessage}
    >
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
    </CatalogInfiniteScroller>
  );
}
