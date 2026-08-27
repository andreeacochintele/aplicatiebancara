import { useState } from "react";

interface BrandMarkProps {
  className?: string;
  size?: number;
}

/** Static by default; swaps to the animated logo (bee flies across the mark)
 * while hovered/focused, restarting playback each time from frame 0. */
export function BrandMark({ className, size = 46 }: BrandMarkProps) {
  const [animated, setAnimated] = useState(false);

  return (
    <img
      src={animated ? "/logo-animated.webp" : "/logo.svg"}
      alt=""
      className={className}
      style={{ width: size, height: size, objectFit: "contain", flexShrink: 0 }}
      onMouseEnter={() => setAnimated(true)}
      onMouseLeave={() => setAnimated(false)}
      onFocus={() => setAnimated(true)}
      onBlur={() => setAnimated(false)}
    />
  );
}
