import {
  BadgePercent,
  Film,
  Fuel,
  Gift,
  Plane,
  Shield,
  ShoppingBag,
  Sofa,
  Store,
  UtensilsCrossed,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";

export interface CategoryStyle {
  icon: LucideIcon;
  key: string;
}

// Style key drives color (aurora.css .category-badge--<key> / .category-pill--<key>).
// Categories from different rewards sections (merchant offer categories like
// "Retail", benefit categories like "RETAIL_DISCOUNT") intentionally share a
// style key where they represent the same real-world concept, so the same
// color/icon language reads consistently across the whole Rewards page.
const CATEGORY_STYLES: Record<string, CategoryStyle> = {
  travel: { icon: Plane, key: "travel" },
  entertainment: { icon: Film, key: "entertainment" },
  retail: { icon: ShoppingBag, key: "retail" },
  retail_discount: { icon: BadgePercent, key: "retail" },
  fuel: { icon: Fuel, key: "fuel" },
  food: { icon: UtensilsCrossed, key: "food" },
  lounge_access: { icon: Sofa, key: "lounge" },
  insurance: { icon: Shield, key: "insurance" },
  other: { icon: Gift, key: "other" },
};

const FALLBACK_STYLE: CategoryStyle = { icon: Store, key: "other" };

export function resolveCategoryStyle(category: string): CategoryStyle {
  return CATEGORY_STYLES[category.toLowerCase()] ?? FALLBACK_STYLE;
}

export function CategoryIconBadge({ category }: { category: string }) {
  const { icon: Icon, key } = resolveCategoryStyle(category);
  return (
    <span className={`category-badge category-badge--${key}`}>
      <Icon size={18} strokeWidth={2} />
    </span>
  );
}

export function CategoryPill({ category, children }: { category: string; children: ReactNode }) {
  const { key } = resolveCategoryStyle(category);
  return <span className={`tag category-pill category-pill--${key}`}>{children}</span>;
}

export function PointsPill({ children }: { children: ReactNode }) {
  return <span className="tag points-pill">{children}</span>;
}
