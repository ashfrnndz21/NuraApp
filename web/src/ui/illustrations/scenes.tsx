import type { JSX } from "preact";
import { Illo, line, paint, type IlloProps } from "./Illo";
import { Heart, OlderMan, OlderWoman, Sparkle, Sprig } from "./people";

/** The illustrations the screens use. Each is one scene in the one style (`Illo.tsx`). */

/** Home's greeting: an older couple, close together, on a soft blush shape. */
export function CoupleIllustration(props: IlloProps): JSX.Element {
  return (
    <Illo viewBox="0 0 220 190" name="couple" {...props}>
      <path d="M110 14C162 14 202 54 202 106V190H18V106C18 54 58 14 110 14Z" style={paint("blush")} />
      <circle cx="170" cy="50" r="15" style={paint("illo-sun")} opacity="0.8" />
      <Sprig transform="translate(24 190) scale(1.05)" />
      <Sprig transform="translate(204 190) scale(-0.8 0.8)" />
      <OlderMan transform="translate(140 96)" />
      <OlderWoman transform="translate(84 112) scale(0.94)" />
      <Heart transform="translate(114 46) scale(0.8)" />
      <Sparkle transform="translate(42 60) scale(0.8)" token="illo-plum-soft" />
    </Illo>
  );
}

/** The welcome screen's picture: the couple in a warm arched window, the sun and the hills
 *  behind them, a plant beside them. */
export function WelcomeIllustration(props: IlloProps): JSX.Element {
  return (
    <Illo viewBox="0 0 360 250" name="welcome" {...props}>
      <rect width="360" height="250" style={paint("peach")} />
      <circle cx="40" cy="30" r="60" style={paint("blush")} opacity="0.6" />
      <circle cx="340" cy="220" r="70" style={paint("blush")} opacity="0.5" />
      {/* The window: an arch of sky, the sun, clouds and hills. */}
      <path d="M86 250V128C86 76 128 36 180 36C232 36 274 76 274 128V250Z" style={paint("sky")} />
      <circle cx="226" cy="100" r="24" style={paint("illo-sun")} />
      <path d="M112 110C112 102 120 97 127 100C130 93 142 92 146 100C153 99 158 104 156 110Z" style={paint("illo-cloud")} opacity="0.9" />
      <path d="M196 70C196 65 201 62 206 64C208 59 216 59 218 64C223 64 226 67 225 70Z" style={paint("illo-cloud")} opacity="0.9" />
      <path d="M86 196C118 170 150 176 180 186C210 196 240 178 274 170V250H86Z" style={paint("illo-leaf")} />
      <path d="M86 222C122 206 160 212 196 220C230 228 252 214 274 208V250H86Z" style={paint("illo-leaf-deep")} opacity="0.7" />
      <path d="M86 128C86 76 128 36 180 36C232 36 274 76 274 128" style={line("tint-paper", 8)} />
      {/* The plant beside the window. */}
      <g transform="translate(50 250)">
        <path d="M0-40C-4-66-20-80-30-86C-30-66-18-50 0-40Z" style={paint("illo-leaf")} />
        <path d="M2-44C4-72 18-88 30-92C32-72 20-54 2-44Z" style={paint("illo-leaf-deep")} />
        <path d="M0-42C-10-60-28-62-38-58C-30-46-16-40 0-42Z" style={paint("illo-leaf-deep")} opacity="0.8" />
        <path d="M-22-44H24L18 0H-16Z" style={paint("illo-pot")} />
        <rect x="-25" y="-48" width="52" height="10" rx="5" style={paint("illo-pot-deep")} />
      </g>
      <OlderMan transform="translate(206 150) scale(1.05)" />
      <OlderWoman transform="translate(152 164)" />
      <Heart transform="translate(180 88)" />
      <Sparkle transform="translate(300 60)" token="tint-paper" />
      <Sparkle transform="translate(318 84) scale(0.6)" token="tint-paper" />
    </Illo>
  );
}

/** The daily check-in's friendly face: a warm round face, eyes closed in a smile. */
export function CheckInFace(props: IlloProps): JSX.Element {
  return (
    <Illo viewBox="0 0 100 100" name="check-in-face" {...props}>
      <circle cx="50" cy="52" r="44" style={paint("butter")} />
      <circle cx="50" cy="52" r="34" style={paint("illo-sun")} />
      <path d="M36 48Q41 42 46 48" style={line("illo-line", 3)} />
      <path d="M54 48Q59 42 64 48" style={line("illo-line", 3)} />
      <circle cx="33" cy="60" r="5" style={paint("illo-cheek")} opacity="0.6" />
      <circle cx="67" cy="60" r="5" style={paint("illo-cheek")} opacity="0.6" />
      <path d="M40 62Q50 73 60 62" style={line("illo-line", 3)} />
      <Sparkle transform="translate(84 14) scale(0.9)" token="illo-plum-soft" />
    </Illo>
  );
}

/** An empty state, and a place still being made: a seedling in a pot. */
export function SeedlingIllustration(props: IlloProps): JSX.Element {
  return (
    <Illo viewBox="0 0 180 150" name="seedling" {...props}>
      <path d="M92 10C140 8 172 40 172 82C172 124 140 146 92 146C42 146 8 122 8 80C8 38 44 12 92 10Z" style={paint("lavender")} />
      <path d="M90 92C90 74 92 60 96 48" style={line("illo-leaf-deep", 3.5)} />
      <path d="M92 74C72 76 58 64 56 46C76 44 90 56 92 74Z" style={paint("illo-leaf")} />
      <path d="M95 58C110 60 126 50 130 32C112 30 98 40 95 58Z" style={paint("illo-leaf-deep")} />
      <path d="M58 100H122L114 142H66Z" style={paint("illo-pot")} />
      <rect x="52" y="90" width="76" height="16" rx="8" style={paint("illo-pot-deep")} />
      <Sparkle transform="translate(40 40)" token="tint-paper" />
      <Sparkle transform="translate(146 104) scale(0.7)" token="illo-sun" />
      <Heart transform="translate(142 36) scale(0.6)" />
    </Illo>
  );
}

/** A tip's scene: trees in a park, a path, a bench, the sun. */
export function ParkIllustration(props: IlloProps): JSX.Element {
  return (
    <Illo viewBox="0 0 160 120" name="park" {...props}>
      <rect width="160" height="120" rx="20" style={paint("sky")} />
      <circle cx="122" cy="30" r="14" style={paint("illo-sun")} />
      <path d="M0 78C30 64 60 70 84 76C110 82 134 70 160 64V100C160 111 151 120 140 120H20C9 120 0 111 0 100Z" style={paint("illo-leaf")} />
      <path d="M60 120C66 104 84 94 110 88C92 98 88 108 92 120Z" style={paint("ground-warm")} />
      <rect x="36" y="56" width="6" height="30" rx="3" style={paint("illo-trunk")} />
      <circle cx="39" cy="46" r="20" style={paint("illo-leaf-deep")} />
      <circle cx="30" cy="54" r="12" style={paint("illo-leaf-deep")} />
      <rect x="126" y="54" width="5" height="24" rx="2.5" style={paint("illo-trunk")} />
      <circle cx="128.5" cy="46" r="14" style={paint("illo-leaf-deep")} opacity="0.85" />
      <rect x="58" y="80" width="30" height="5" rx="2.5" style={paint("illo-plum-soft")} />
      <rect x="58" y="72" width="30" height="4" rx="2" style={paint("illo-plum-soft")} />
      <rect x="61" y="84" width="3" height="9" rx="1.5" style={paint("illo-plum-soft")} />
      <rect x="82" y="84" width="3" height="9" rx="1.5" style={paint("illo-plum-soft")} />
    </Illo>
  );
}
