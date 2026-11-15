import type { UpdateNotice } from "@/api/updates";

const RELEASE_DATE = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "long",
  year: "numeric",
});

export function monthsSince(downloadedAt: string, now = new Date()): number {
  const days = (now.getTime() - new Date(downloadedAt).getTime()) / 86_400_000;
  return Math.max(0, Math.floor(days / 30.4375));
}

export function releaseDate(value: string | null): string | null {
  return value ? RELEASE_DATE.format(new Date(value)) : null;
}

export function noticeTitle(notice: UpdateNotice, now = new Date()): string {
  switch (notice.id) {
    case "app": return `NightCrate ${notice.version} is ready to install`;
    case "openngc": return "OpenNGC has a new release";
    case "mgc50_age": return `The 50 MGC catalog was last downloaded ${monthsSince(notice.downloaded_at!, now)} months ago`;
    case "wikidata_age": return `Wikipedia links were last downloaded ${monthsSince(notice.downloaded_at!, now)} months ago`;
    case "wikidata_query": return "NightCrate now downloads more from Wikidata";
  }
}

export function noticeDescription(notice: UpdateNotice): string {
  switch (notice.id) {
    case "app": {
      const released = releaseDate(notice.published_at);
      return `You have ${notice.current_version}.${released ? ` Released on ${released}.` : ""}`;
    }
    case "openngc": return `Version ${notice.latest_tag} is available. You have ${notice.installed_tag}.`;
    case "mgc50_age": return "Its authors may have updated it since then.";
    case "wikidata_age": return "Wikidata may have added links for more objects since then.";
    case "wikidata_query": return "Download again to get the new links.";
  }
}

export function formatCheckTime(value: string, now = new Date()): string {
  const date = new Date(value);
  const dayKey = (item: Date) => `${item.getFullYear()}-${item.getMonth()}-${item.getDate()}`;
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  const day = dayKey(date) === dayKey(now)
    ? "today"
    : dayKey(date) === dayKey(yesterday)
      ? "yesterday"
      : new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric" }).format(date);
  return `${day} at ${date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false })}`;
}
