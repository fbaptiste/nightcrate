export function shouldOfferSessionBuild(lightCount: number, automaticCount: number): boolean {
  return lightCount > 0 && automaticCount === 0;
}
