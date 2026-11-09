import type { SVGProps } from 'react'

const base = { fill: 'none', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, viewBox: '0 0 24 24' }
type P = SVGProps<SVGSVGElement>

export const IconHome = (p: P) => <svg {...base} {...p}><path d="M3 11l9-7 9 7" /><path d="M5 10v10h14V10" /></svg>
export const IconMic = (p: P) => <svg {...base} {...p}><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></svg>
export const IconStop = (p: P) => <svg {...base} {...p}><rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor" /></svg>
export const IconBox = (p: P) => <svg {...base} {...p}><path d="M3 7l9-4 9 4-9 4-9-4z" /><path d="M3 7v10l9 4 9-4V7M12 11v10" /></svg>
export const IconTarget = (p: P) => <svg {...base} {...p}><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="4" /><circle cx="12" cy="12" r="1" fill="currentColor" /></svg>
export const IconMore = (p: P) => <svg {...base} {...p}><path d="M4 6h16M4 12h16M4 18h10" /></svg>
export const IconSend = (p: P) => <svg {...base} {...p}><path d="M4 12l16-8-6 16-2-7-8-1z" /></svg>
export const IconSpeaker = (p: P) => <svg {...base} {...p}><path d="M4 9v6h4l5 4V5L8 9H4z" /><path d="M16 9a4 4 0 0 1 0 6M18.5 6.5a8 8 0 0 1 0 11" /></svg>
export const IconMute = (p: P) => <svg {...base} {...p}><path d="M4 9v6h4l5 4V5L8 9H4z" /><path d="M17 9l4 6M21 9l-4 6" /></svg>
export const IconBack = (p: P) => <svg {...base} {...p}><path d="M15 5l-7 7 7 7" /></svg>
export const IconDoc = (p: P) => <svg {...base} {...p}><path d="M7 3h7l5 5v13H7z" /><path d="M14 3v5h5M10 13h6M10 17h6" /></svg>
export const IconList = (p: P) => <svg {...base} {...p}><path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01" /></svg>
export const IconGear = (p: P) => <svg {...base} {...p}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" /></svg>
export const IconWifiOff = (p: P) => <svg {...base} {...p}><path d="M2 2l20 20M8.5 16.5a5 5 0 0 1 7 0M5 13a10 10 0 0 1 5.2-2.8M19 13a10 10 0 0 0-2.4-1.7M2 8.8a15 15 0 0 1 4.2-2.7M22 8.8A15 15 0 0 0 10.7 5M12 20h.01" /></svg>
export const IconClip = (p: P) => <svg {...base} {...p}><path d="M21 11l-9 9a5 5 0 0 1-7-7l9-9a3.5 3.5 0 0 1 5 5l-9 9a2 2 0 0 1-3-3l8-8" /></svg>
export const IconPlus = (p: P) => <svg {...base} {...p}><path d="M12 5v14M5 12h14" /></svg>
export const IconChat = (p: P) => <svg {...base} {...p}><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.4A8 8 0 1 1 21 12z" /></svg>
export const IconWallet = (p: P) => <svg {...base} {...p}><rect x="3" y="6" width="18" height="13" rx="2" /><path d="M3 10h18M7 15h4" /></svg>
export const IconSpark = (p: P) => <svg {...base} {...p}><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" /></svg>
export const IconArrow = (p: P) => <svg {...base} {...p}><path d="M5 12h14M13 6l6 6-6 6" /></svg>
export const IconSearch = (p: P) => <svg {...base} {...p}><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
export const IconChevron = (p: P) => <svg {...base} {...p}><path d="M9 6l6 6-6 6" /></svg>
export const IconChart = (p: P) => <svg {...base} {...p}><path d="M4 20V10M10 20V4M16 20v-7M22 20H2" /></svg>
