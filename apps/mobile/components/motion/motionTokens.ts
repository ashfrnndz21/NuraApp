/**
 * @deprecated Back-compat shim. The single source of truth for these
 * tokens is now `apps/mobile/design/motion.ts` and `apps/mobile/design/colors.ts`
 * (section 35, C0). New code should import from `../../design/motion` /
 * `../../design/colors` directly — this file only re-exports so existing
 * relative imports (`../motion/motionTokens`) keep working.
 */
export * from '../../design/motion';
export { phoneTokens, colorsLight, colorsDark, type ColorTokens } from '../../design/colors';
