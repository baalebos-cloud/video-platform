import type { ReactNode } from "react";

export type StudioIconName =
  | "dashboard" | "film" | "chart" | "wallet" | "settings" | "plus"
  | "play" | "pause" | "sparkles" | "layers" | "captions" | "arrow" | "back"
  | "logout" | "folder" | "chevron" | "clock" | "refresh" | "download"
  | "check" | "menu" | "eye" | "audio" | "edit" | "wand" | "search";

const shapes: Record<StudioIconName, ReactNode> = {
  dashboard: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
  film: <><rect x="3" y="3" width="18" height="18" rx="3" /><path d="M7 3v18M17 3v18M3 8h4m10 0h4M3 16h4m10 0h4" /></>,
  chart: <><path d="M3 20h18M6 16v-6M12 16V5M18 16V9" strokeLinecap="round" /></>,
  wallet: <><rect x="3" y="6" width="18" height="15" rx="3" /><path d="M3 10h18M5 6V4a2 2 0 0 1 2-2h10" /><circle cx="17" cy="15" r="1" /></>,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15l1.2 1.1-2 3.4-1.6-.5a8 8 0 0 1-2.3 1.3L14.3 22h-4.6l-.4-1.7A8 8 0 0 1 7 19l-1.6.5-2-3.4L4.6 15a8 8 0 0 1 0-2l-1.2-1.1 2-3.4L7 9a8 8 0 0 1 2.3-1.3L9.7 6h4.6l.4 1.7A8 8 0 0 1 17 9l1.6-.5 2 3.4L19.4 13a8 8 0 0 1 0 2Z" transform="translate(0 -2) scale(1 1.05)" /></>,
  plus: <path d="M12 5v14M5 12h14" strokeLinecap="round" />,
  play: <path d="m8 5 11 7-11 7V5Z" strokeLinejoin="round" />,
  pause: <><path d="M8 5v14M16 5v14" strokeWidth={3} /></>,
  sparkles: <><path d="m12 2 1.8 6.2L20 10l-6.2 1.8L12 18l-1.8-6.2L4 10l6.2-1.8L12 2ZM19 18l.6 1.4L21 20l-1.4.6L19 22l-.6-1.4L17 20l1.4-.6L19 18Z" /></>,
  layers: <><path d="m12 3 9 5-9 5-9-5 9-5ZM3 12l9 5 9-5M3 16l9 5 9-5" strokeLinejoin="round" /></>,
  captions: <><rect x="2" y="4" width="20" height="16" rx="3" /><path d="M9 10a3 3 0 1 0 0 4m10-4a3 3 0 1 0 0 4" /></>,
  arrow: <path d="M5 12h14m-6-6 6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />,
  back: <path d="M19 12H5m6-6-6 6 6 6" strokeLinecap="round" strokeLinejoin="round" />,
  logout: <><path d="M10 4H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h5M15 16l4-4-4-4m4 4H9" /></>,
  folder: <path d="M3 6a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v10H3V6Z" />,
  chevron: <path d="m9 6 6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  refresh: <><path d="M20 10a8 8 0 0 0-14-4L4 8m0-5v5h5M4 14a8 8 0 0 0 14 4l2-2m0 5v-5h-5" /></>,
  download: <><path d="M12 3v13m-5-5 5 5 5-5M4 18v3h16v-3" /></>,
  check: <path d="m4 12 5 5L20 6" strokeLinecap="round" strokeLinejoin="round" />,
  menu: <path d="M4 7h16M4 12h16M4 17h16" strokeLinecap="round" />,
  eye: <><path d="M2 12s4-6 10-6 10 6 10 6-4 6-10 6S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /></>,
  audio: <><path d="M4 10v4m4-8v12m4-15v18m4-14v10m4-7v4" strokeLinecap="round" /></>,
  edit: <><path d="m14 5 5 5-10 10H4v-5L14 5Z" /><path d="m12 7 5 5" /></>,
  wand: <><path d="m4 20 12-12 4 4L8 24M14 3l1 2m5-1-2 1M4 5l2 2" /></>,
  search: <><circle cx="10.5" cy="10.5" r="7" /><path d="m16 16 5 5" strokeLinecap="round" /></>,
};

export function StudioIcon({ name, size = 18, className = "" }: {
  name: StudioIconName; size?: number; className?: string;
}) {
  return (
    <svg aria-hidden="true" xmlns="http://www.w3.org/2000/svg" width={size}
      height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className={className}>
      {shapes[name]}
    </svg>
  );
}
