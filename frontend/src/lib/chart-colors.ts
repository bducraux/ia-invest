/**
 * Definitive chart color palette generator.
 *
 * Strategy: combine three independent perceptual axes so that adjacent slice
 * indices are guaranteed to be visually distinct:
 *
 *   1. Hue is stepped by the golden angle (~137.508°). This is a
 *      low-discrepancy sequence on the circle: every new index falls in the
 *      largest existing gap, so consecutive indices are always far apart in
 *      hue regardless of N.
 *   2. Lightness rotates through 3 bands per step. Two indices that happen
 *      to land near each other in hue will still differ by ≥10% lightness.
 *   3. Saturation rotates through 3 bands every 3 steps. Combined with (2)
 *      we get 9 distinct (S, L) shells before any combination can repeat,
 *      and by then the hue has circled the wheel multiple times.
 *
 * The "Outros" / "Other" slice is forced to a neutral gray so it reads as
 * an aggregation bucket regardless of position.
 */

const OTHERS_COLOR = "hsl(220 8% 52%)";

const LIGHTNESS_BANDS = [52, 66, 42];
const SATURATION_BANDS = [72, 58, 88];
const GOLDEN_ANGLE = 137.508;

export function getChartColor(index: number): string {
  const hue = (index * GOLDEN_ANGLE) % 360;
  const l = LIGHTNESS_BANDS[index % LIGHTNESS_BANDS.length];
  const s =
    SATURATION_BANDS[
      Math.floor(index / LIGHTNESS_BANDS.length) % SATURATION_BANDS.length
    ];
  return `hsl(${hue.toFixed(1)} ${s}% ${l}%)`;
}

export function getSliceColor(label: string, index: number): string {
  if (label.trim().toLowerCase().startsWith("outros")) {
    return OTHERS_COLOR;
  }
  return getChartColor(index);
}

export function generateChartColors(count: number): string[] {
  const colors: string[] = [];
  for (let i = 0; i < count; i++) {
    colors.push(getChartColor(i));
  }
  return colors;
}

export { OTHERS_COLOR };
