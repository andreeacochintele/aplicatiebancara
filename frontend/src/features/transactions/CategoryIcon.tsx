import {
  Bus,
  Clapperboard,
  Dumbbell,
  Film,
  Fuel,
  Gift,
  GraduationCap,
  HeartPulse,
  Plane,
  Receipt,
  RefreshCw,
  ShoppingBag,
  ShoppingCart,
  Sparkles,
  Tag,
  UtensilsCrossed,
  type LucideIcon,
} from "lucide-react";

import { colorForType } from "../analytics/formatters";

/**
 * Categories come from a seeded backend list (migration 0052) shared with
 * the Analytics donut, so this map is keyed by those exact names. Anything
 * unmapped — a category added to the seed later, or a merchant category
 * that predates the unified list — falls back to a neutral tag rather than
 * rendering nothing, so a row never looks broken.
 */
const ICONS: Record<string, LucideIcon> = {
  Food: UtensilsCrossed,
  Groceries: ShoppingCart,
  Entertainment: Clapperboard,
  Fuel: Fuel,
  Transport: Bus,
  Shopping: ShoppingBag,
  Travel: Plane,
  Bills: Receipt,
  Health: HeartPulse,
  Subscriptions: RefreshCw,
  "Sports & Fitness": Dumbbell,
  Education: GraduationCap,
  "Beauty & Personal care": Sparkles,
  "Gifts & Charity": Gift,
  Other: Tag,
  // Retired in migration 0052 (merchants moved to Shopping), but a shared
  // Supabase project that hasn't run it yet still serves merchants on the
  // old name — keep the glyph so those rows don't fall to the generic one.
  Retail: ShoppingBag,
};

// Kept out of the map so an unmapped name still gets a distinct glyph from
// the deliberate "Other".
const FALLBACK: LucideIcon = Film;

export function categoryIcon(category: string): LucideIcon {
  return ICONS[category] ?? FALLBACK;
}

export function CategoryIcon({ category, size = 16 }: { category: string; size?: number }) {
  const Icon = categoryIcon(category);
  // Same hue the donut gives this category, so a slice and a row read as
  // the same thing at a glance.
  return (
    <span
      aria-hidden="true"
      className="category-icon"
      style={{ color: colorForType(category) }}
      title={category}
    >
      <Icon size={size} strokeWidth={2} />
    </span>
  );
}
