/** Inline stroke icons — no icon dependency, consistent 16px grid. */

type IconProps = { size?: number; className?: string };

const base = (size: number) => ({
  width: size,
  height: size,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
});

export const IconOverview = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <rect x="3" y="3" width="7" height="8" rx="1.5" />
    <rect x="14" y="3" width="7" height="5" rx="1.5" />
    <rect x="14" y="11" width="7" height="10" rx="1.5" />
    <rect x="3" y="14" width="7" height="7" rx="1.5" />
  </svg>
);

export const IconTarget = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <circle cx="12" cy="12" r="8.5" />
    <circle cx="12" cy="12" r="4.5" />
    <circle cx="12" cy="12" r="1" fill="currentColor" />
  </svg>
);

export const IconStore = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M3.5 9.5V19a1.5 1.5 0 0 0 1.5 1.5h14a1.5 1.5 0 0 0 1.5-1.5V9.5" />
    <path d="M2.6 8.2 4.3 4.1A1.5 1.5 0 0 1 5.7 3.2h12.6a1.5 1.5 0 0 1 1.4.9l1.7 4.1a2.7 2.7 0 0 1-4.7 2.5 2.7 2.7 0 0 1-4.7 0 2.7 2.7 0 0 1-4.7 0 2.7 2.7 0 0 1-4.7-2.5Z" />
    <path d="M9.5 20.5v-5h5v5" />
  </svg>
);

export const IconMegaphone = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="m3 11 15-6.5v15L3 13z" />
    <path d="M3 11H2.5A1.5 1.5 0 0 0 1 12.5v0A1.5 1.5 0 0 0 2.5 14H3z" />
    <path d="M7 13.5V19a1.5 1.5 0 0 0 3 0v-4.2" />
    <path d="M21 9.5a2.5 2.5 0 0 1 0 5" />
  </svg>
);

export const IconFunnel = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M3 4.5h18l-7 8v7l-4 2v-9z" />
  </svg>
);

export const IconMap = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="m9 3.5-6 2.5v14l6-2.5 6 2.5 6-2.5v-14L15 6z" />
    <path d="M9 3.5v14M15 6v14.5" />
  </svg>
);

export const IconSearch = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <circle cx="11" cy="11" r="6.5" />
    <path d="m16 16 4.5 4.5" />
  </svg>
);

export const IconX = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="m6 6 12 12M18 6 6 18" />
  </svg>
);

export const IconDownload = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M12 3.5v11" />
    <path d="m7.5 10.5 4.5 4.5 4.5-4.5" />
    <path d="M4 17.5v1.5a1.5 1.5 0 0 0 1.5 1.5h13a1.5 1.5 0 0 0 1.5-1.5v-1.5" />
  </svg>
);

export const IconChevronLeft = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}><path d="m14.5 5.5-7 6.5 7 6.5" /></svg>
);

export const IconChevronRight = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}><path d="m9.5 5.5 7 6.5-7 6.5" /></svg>
);

export const IconArrowUpRight = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M7 17 17 7M9 7h8v8" />
  </svg>
);

export const IconPhone = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M6.5 3.5h3l1.5 4-2 1.5a12 12 0 0 0 6 6l1.5-2 4 1.5v3a1.5 1.5 0 0 1-1.6 1.5A16.5 16.5 0 0 1 5 5.1 1.5 1.5 0 0 1 6.5 3.5Z" />
  </svg>
);

export const IconMail = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <rect x="2.5" y="5" width="19" height="14" rx="2" />
    <path d="m3 6.5 9 6 9-6" />
  </svg>
);

export const IconUsers = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <circle cx="9" cy="8" r="3.5" />
    <path d="M2.5 20a6.5 6.5 0 0 1 13 0" />
    <path d="M16 4.6a3.5 3.5 0 0 1 0 6.8M17.5 14.2a6.5 6.5 0 0 1 4 5.8" />
  </svg>
);

export const IconCalendar = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <rect x="3" y="5" width="18" height="16" rx="2" />
    <path d="M3 10h18M8 3v4M16 3v4" />
  </svg>
);

export const IconInfo = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 11v5.5" />
    <circle cx="12" cy="7.75" r="1" fill="currentColor" stroke="none" />
  </svg>
);

export const IconAlert = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M10.6 3.8 2.4 18a1.6 1.6 0 0 0 1.4 2.4h16.4a1.6 1.6 0 0 0 1.4-2.4L13.4 3.8a1.6 1.6 0 0 0-2.8 0Z" />
    <path d="M12 9.5v4.5" />
    <circle cx="12" cy="17.2" r="1" fill="currentColor" stroke="none" />
  </svg>
);

export const IconSun = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <circle cx="12" cy="12" r="4.2" />
    <path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M19.1 4.9l-1.8 1.8M6.7 17.3l-1.8 1.8" />
  </svg>
);

export const IconMoon = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M20 14.2A8.2 8.2 0 0 1 9.8 4a8.5 8.5 0 1 0 10.2 10.2Z" />
  </svg>
);

export const IconPlus = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}><path d="M12 5v14M5 12h14" /></svg>
);

export const IconCheck = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}><path d="m5 12.5 4.5 4.5L19 7" /></svg>
);

export const IconSparkle = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M12 3.5 13.9 9l5.6 1.9-5.6 1.9L12 18.5 10.1 12.8 4.5 10.9 10.1 9z" />
    <path d="M18.5 3.5v3M20 5h-3" />
  </svg>
);

export const IconTrend = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M3 16.5 9 10l4 4 7.5-8" />
    <path d="M14 6h6.5v6.5" />
  </svg>
);
