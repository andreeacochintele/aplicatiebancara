interface BeeIconProps {
  size?: number;
}

export function BeeIcon({ size = 20 }: BeeIconProps) {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        d="M8.9 11.2C6.2 8 3.2 9.5 3.2 12.2c0 2.1 2.1 3.3 4.8 2.4"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M15.1 11.2c2.7-3.2 5.7-1.7 5.7 1 0 2.1-2.1 3.3-4.8 2.4"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M7.6 14.1c0-3.4 1.8-5.9 4.4-5.9s4.4 2.5 4.4 5.9c0 3.1-1.8 5.6-4.4 5.6s-4.4-2.5-4.4-5.6Z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M9.1 12h5.8M8.4 15h7.2M10 18h4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
      <path d="M9.8 7.2c0-1.2 1-2.2 2.2-2.2s2.2 1 2.2 2.2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M10.6 5.5 8.8 3.7M13.4 5.5l1.8-1.8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}
