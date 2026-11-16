/**
 * Helpers for filesystem paths as the backend returns them: POSIX on macOS
 * and Linux, `C:\…` or `\\server\share\…` on Windows.
 */

export interface PathCrumb {
  name: string;
  path: string;
}

const DRIVE = /^([A-Za-z]:)[\\/]?/;
const UNC = /^\\\\([^\\]+)\\([^\\]+)\\?/;

function windowsCrumbs(root: string, label: string, rest: string): PathCrumb[] {
  const parts = rest.split(/[\\/]/).filter(Boolean);
  return [
    { name: label, path: root },
    ...parts.map((name, i) => ({ name, path: root + parts.slice(0, i + 1).join("\\") })),
  ];
}

/** The path's ancestors, root first, each with the full path to navigate to. */
export function pathCrumbs(path: string): PathCrumb[] {
  const drive = DRIVE.exec(path);
  if (drive) return windowsCrumbs(`${drive[1]}\\`, drive[1], path.slice(drive[0].length));
  const unc = UNC.exec(path);
  if (unc) {
    const share = `\\\\${unc[1]}\\${unc[2]}`;
    return windowsCrumbs(`${share}\\`, share, path.slice(unc[0].length));
  }
  const parts = path.split("/").filter(Boolean);
  return [
    { name: "/", path: "/" },
    ...parts.map((name, i) => ({ name, path: "/" + parts.slice(0, i + 1).join("/") })),
  ];
}

/** The folder containing `path`; a root is its own parent. */
export function parentPath(path: string): string {
  const crumbs = pathCrumbs(path);
  return crumbs[Math.max(crumbs.length - 2, 0)].path;
}

/** The last component of `path`. */
export function baseName(path: string): string {
  const crumbs = pathCrumbs(path);
  return crumbs[crumbs.length - 1].name;
}

/** `name` inside the folder `dir`, with the folder's own separator. */
export function joinPath(dir: string, name: string): string {
  const separator = DRIVE.test(dir) || UNC.test(dir) ? "\\" : "/";
  return /[\\/]$/.test(dir) ? dir + name : dir + separator + name;
}
