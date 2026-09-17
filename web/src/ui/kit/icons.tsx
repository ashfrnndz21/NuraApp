import type { JSX } from "preact";
import {
  Activity,
  ArrowRight,
  Bell,
  BookOpen,
  BriefcaseMedical,
  CalendarClock,
  CalendarDays,
  Camera,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleUserRound,
  Clock,
  Droplet,
  FilePlus2,
  FileText,
  Footprints,
  Gauge,
  Globe,
  HandHeart,
  Heart,
  HeartPulse,
  House,
  ListChecks,
  Lock,
  MapPin,
  Menu,
  MessageSquare,
  Mic,
  Moon,
  Palette,
  Phone,
  Pill,
  Play,
  Plus,
  Search,
  ShieldCheck,
  Smile,
  Sparkles,
  Sprout,
  Stethoscope,
  Sun,
  TrendingUp,
  Users,
  UtensilsCrossed,
  Volume2,
  Upload,
  User,
  X,
  type IconNode,
} from "lucide";

/** Thin-line icons: one set, Lucide (ISC licence, `web/THIRD_PARTY.md`), matching the thin
 *  rounded strokes of the owner's reference (docs/design-direction.md, "Icons"). Only the shapes
 *  come from Lucide; the `<svg>` is drawn here, so every icon keeps the design system's own
 *  rules: a 1.5px stroke that stays 1.5px at any size (`vector-effect: non-scaling-stroke`),
 *  24px, 28px in the patient's density, and hidden from the screen reader. An icon never carries
 *  meaning alone: every place that draws one puts a word beside it. */

export const ICONS = {
  // The five tabs, as the approved board draws them (docs/design/nura-concept-board.html).
  home: House,
  health: Heart,
  connect: Users,
  services: BriefcaseMedical,
  profile: User,
  // The Home grid.
  track: Activity,
  medication: Pill,
  activities: BookOpen,
  care: HandHeart,
  resources: FileText,
  upload: Upload,
  // The header and the cards.
  menu: Menu,
  bell: Bell,
  calendar: CalendarDays,
  clock: Clock,
  place: MapPin,
  report: FilePlus2,
  palette: Palette,
  stethoscope: Stethoscope,
  arrow: ArrowRight,
  heart: Heart,
  privacy: ShieldCheck,
  companion: Sparkles,
  trends: TrendingUp,
  easy: Smile,
  growing: Sprout,
  add: Plus,
  check: Check,
  pulse: Activity,
  // The names the screens already use.
  today: Sun,
  medicines: Pill,
  pill: Pill,
  records: FileText,
  visits: CalendarDays,
  timeline: ListChecks,
  plan: ListChecks,
  family: Users,
  speaker: Volume2,
  mic: Mic,
  search: Search,
  camera: Camera,
  close: X,
  play: Play,
  chevron: ChevronRight,
  back: ChevronLeft,
  note: MessageSquare,
  // The Health tab's metric rows and readings (docs/design/nura-concept-board.html).
  steps: Footprints,
  heart_rate: HeartPulse,
  sleep: Moon,
  water: Droplet,
  gauge: Gauge,
  meal: UtensilsCrossed,
  comingUp: CalendarClock,
  phone: Phone,
  // Profile (docs/design/nura-concept-board.html, the Profile screen).
  language: Globe,
  lock: Lock,
} as const satisfies Record<string, IconNode>;

export type IconName = keyof typeof ICONS;

export function Icon({ name }: { name: IconName }): JSX.Element {
  const node: IconNode = ICONS[name];
  return (
    <svg class="icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false" data-icon={name}>
      {node.map(([tag, attrs], at) => {
        const Shape = tag as unknown as "path";
        return <Shape key={at} {...(attrs as Record<string, string | number>)} />;
      })}
    </svg>
  );
}
