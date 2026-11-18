import type { ProjectRigSetups } from "@/api/projects";

export interface RigProvenanceBadge {
  label: "from files" | "from sessions" | "source unknown";
  title: string;
}

export function rigProvenanceBadge(
  provenance: ProjectRigSetups["provenance"] | undefined,
): RigProvenanceBadge {
  if (provenance === "manual_sessions") {
    return {
      label: "from sessions",
      title: "Sessions you entered by hand in this project use this rig. You didn't add it to the project yourself.",
    };
  }
  if (provenance === "auto_sessions") {
    return {
      label: "from sessions",
      title: "Sessions built from this project's files use this rig, but none of its files do any more. Rebuild the sessions to update them.",
    };
  }
  if (provenance === "files") {
    return {
      label: "from files",
      title: "Your files in this project were taken with this rig, set on their folder in the Files tab. You didn't add it to the project yourself.",
    };
  }
  return {
    label: "source unknown",
    title: "This project uses this rig, but its source couldn't be determined.",
  };
}
