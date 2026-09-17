import type { JSX } from "preact";
import { line, paint } from "./Illo";

/** The two people the illustrations are drawn around: an older woman and an older man, head and
 *  shoulders, each drawn about their own head's centre so a scene places them with one
 *  `transform`. Eyes closed in a smile, round cheeks, soft grey hair — warm, never a cartoon. */

interface Placed {
  transform?: string;
}

/** Her: a grey bob and a bun, round glasses, a lavender cardigan over a pale blouse. */
export function OlderWoman({ transform }: Placed): JSX.Element {
  return (
    <g transform={transform}>
      {/* Cardigan, the blouse's neckline, and two buttons. */}
      <path d="M-50 112C-50 66-32 44 0 44C32 44 50 66 50 112Z" style={paint("illo-cardigan")} />
      <path d="M-18 46C-10 44-4 44 0 44C4 44 10 44 18 46L0 78Z" style={paint("tint-paper")} />
      <path d="M-18 46L0 78L-6 112H-10L-24 50Z" style={paint("illo-cardigan-deep")} opacity="0.35" />
      <circle cx="-4" cy="90" r="2.6" style={paint("illo-cardigan-deep")} />
      <circle cx="-5" cy="102" r="2.6" style={paint("illo-cardigan-deep")} />
      {/* Neck. */}
      <path d="M-9 18H9V44C9 52-9 52-9 44Z" style={paint("illo-skin-shade")} />
      {/* The hair behind her head: the bob, and the bun on top. */}
      <circle cx="0" cy="-36" r="13" style={paint("illo-hair")} />
      <path d="M-5-44C0-47 6-45 8-40" style={line("illo-hair-shade", 2)} />
      <path d="M-31 20C-36-8-24-32 0-32C24-32 36-8 31 20C28 26 22 26 20 20H-20C-22 26-28 26-31 20Z" style={paint("illo-hair")} />
      {/* Ears, face. */}
      <circle cx="-25" cy="5" r="6" style={paint("illo-skin-shade")} />
      <circle cx="25" cy="5" r="6" style={paint("illo-skin-shade")} />
      <circle cx="0" cy="2" r="25" style={paint("illo-skin")} />
      {/* The fringe. */}
      <path d="M-26 0C-27-18-14-28 2-27C17-26 27-17 26-1C20-11 11-15 1-14C-11-13-19-8-26 0Z" style={paint("illo-hair")} />
      <path d="M-12-20C-6-24 4-24 10-21" style={line("illo-hair-shade", 1.6)} />
      {/* Cheeks, glasses, eyes closed in a smile, the smile. */}
      <circle cx="-15" cy="13" r="4.5" style={paint("illo-cheek")} opacity="0.55" />
      <circle cx="15" cy="13" r="4.5" style={paint("illo-cheek")} opacity="0.55" />
      <circle cx="-9.5" cy="4" r="7" style={line("illo-line", 1.8)} />
      <circle cx="9.5" cy="4" r="7" style={line("illo-line", 1.8)} />
      <path d="M-2.5 3.5Q0 2 2.5 3.5" style={line("illo-line", 1.8)} />
      <path d="M-12.5 5.5Q-9.5 2.5-6.5 5.5" style={line("illo-line", 2)} />
      <path d="M6.5 5.5Q9.5 2.5 12.5 5.5" style={line("illo-line", 2)} />
      <path d="M-6 15Q0 20.5 6 15" style={line("illo-line", 2.2)} />
    </g>
  );
}

/** Him: white hair at the sides, a white moustache, a sage jumper over a collared shirt. */
export function OlderMan({ transform }: Placed): JSX.Element {
  return (
    <g transform={transform}>
      {/* Jumper, the shirt's collar in its V. */}
      <path d="M-54 116C-54 68-34 44 0 44C34 44 54 68 54 116Z" style={paint("illo-sweater")} />
      <path d="M-16 45L0 76L16 45C10 43 5 42 0 42C-5 42-10 43-16 45Z" style={paint("tint-paper")} />
      <path d="M-16 45L-6 52L0 64L-10 56Z" style={paint("ground-warm")} />
      <path d="M16 45L6 52L0 64L10 56Z" style={paint("ground-warm")} />
      <path d="M-20 47L0 80L20 47" style={line("illo-sweater-deep", 3)} />
      {/* Neck. */}
      <path d="M-10 18H10V44C10 52-10 52-10 44Z" style={paint("illo-skin-shade")} />
      {/* Ears, face. */}
      <circle cx="-27" cy="4" r="7" style={paint("illo-skin-shade")} />
      <circle cx="27" cy="4" r="7" style={paint("illo-skin-shade")} />
      <ellipse cx="0" cy="0" rx="27" ry="28" style={paint("illo-skin")} />
      {/* White hair at the sides and a little on top. */}
      <path d="M-28 8C-33-8-28-22-17-25C-21-16-22-6-21 6C-23 10-26 11-28 8Z" style={paint("illo-hair")} />
      <path d="M28 8C33-8 28-22 17-25C21-16 22-6 21 6C23 10 26 11 28 8Z" style={paint("illo-hair")} />
      <path d="M-10-26C-4-31 5-31 11-26C5-28-3-28-10-26Z" style={paint("illo-hair")} />
      <path d="M-9-28C-3-32 4-32 9-28" style={line("illo-hair", 3)} />
      {/* Brows, eyes closed in a smile, cheeks, moustache, smile. */}
      <path d="M-16-7Q-11-10-6-7" style={line("illo-hair-shade", 3)} />
      <path d="M6-7Q11-10 16-7" style={line("illo-hair-shade", 3)} />
      <path d="M-15 1Q-11-2.5-7 1" style={line("illo-line", 2.2)} />
      <path d="M7 1Q11-2.5 15 1" style={line("illo-line", 2.2)} />
      <circle cx="-17" cy="10" r="4.5" style={paint("illo-cheek")} opacity="0.5" />
      <circle cx="17" cy="10" r="4.5" style={paint("illo-cheek")} opacity="0.5" />
      <path d="M0 3C-2 7-2 9 1 10" style={line("illo-skin-deep", 1.8)} />
      <path d="M-13 15C-9 10-3 11 0 13C3 11 9 10 13 15C9 18 4 17 0 15C-4 17-9 18-13 15Z" style={paint("illo-hair")} />
      <path d="M-5 20Q0 23.5 5 20" style={line("illo-line", 2.2)} />
    </g>
  );
}

/** A small plum heart: Nura's own mark, floating in a scene. */
export function Heart({ transform, token = "illo-plum-soft" }: Placed & { token?: string }): JSX.Element {
  return <path transform={transform} d="M0 4C-6-2-12-5-12-10C-12-14-9-17-5.5-17C-3-17-1-15.5 0-13.5C1-15.5 3-17 5.5-17C9-17 12-14 12-10C12-5 6-2 0 4Z" style={paint(token)} />;
}

/** A sprig of two soft leaves on a stem. */
export function Sprig({ transform }: Placed): JSX.Element {
  return (
    <g transform={transform}>
      <path d="M0 0C0-14 2-26 8-36" style={line("illo-leaf-deep", 2.4)} />
      <path d="M1-12C-10-12-16-20-16-28C-6-28 1-22 1-12Z" style={paint("illo-leaf")} />
      <path d="M4-24C12-26 18-34 16-42C8-40 3-34 4-24Z" style={paint("illo-leaf-deep")} />
    </g>
  );
}

/** A four-point sparkle. */
export function Sparkle({ transform, token = "illo-sun" }: Placed & { token?: string }): JSX.Element {
  return <path transform={transform} d="M0-8C1-3 3-1 8 0C3 1 1 3 0 8C-1 3-3 1-8 0C-3-1-1-3 0-8Z" style={paint(token)} />;
}
