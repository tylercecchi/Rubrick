/** Rubrick's vendored copy ships no brand artwork (it isn't covered by Stageshow's MIT
 *  license; see ../../NOTICE.md). The registry is empty: BrandMark renders nothing, and a
 *  scene must never draw another company's mark — Rubrick draws the product's own UI. */
export type BrandAsset = {
  name: string
  category: 'Payments' | 'Banks' | 'Apps' | 'Crypto'
  light: string
  dark: string
  tileArtwork?: string
  tileBackground?: string
  proportion: number
  scale: number
}

export const brandMarks = {} as Record<string, BrandAsset>
export type BrandName = string
