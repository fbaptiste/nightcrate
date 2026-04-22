/**
 * Display-name map for the 29 designation catalogs defined in the
 * ``dso_designation.catalog`` CHECK constraint (db migration 0015).
 * Codes not in the map fall back to ``code.toUpperCase()``.
 */
const CATALOG_DISPLAY_NAMES: Record<string, string> = {
  ngc: "NGC",
  ic: "IC",
  messier: "Messier",
  caldwell: "Caldwell",
  ugc: "UGC",
  pgc: "PGC",
  mcg: "MCG",
  eso: "ESO",
  arp: "Arp",
  hickson: "Hickson",
  sharpless2: "Sharpless 2",
  barnard: "Barnard",
  ldn: "LDN",
  lbn: "LBN",
  vdb: "vdB",
  cederblad: "Cederblad",
  pk: "PK",
  rcw: "RCW",
  gum: "Gum",
  mrk: "Markarian",
  terzan: "Terzan",
  pal: "Palomar",
  mel: "Melotte",
  cr: "Collinder",
  stock: "Stock",
  ruprecht: "Ruprecht",
  abell: "Abell",
  dolidze: "Dolidze",
  dwb: "DWB",
};

export function displayCatalogName(code: string): string {
  return CATALOG_DISPLAY_NAMES[code] ?? code.toUpperCase();
}
