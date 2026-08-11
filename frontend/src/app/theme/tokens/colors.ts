/** CSS custom-property names used by the theme system.
    Consumer example: `bg-[var(--bg)]` or `<div style={{ background: 'rgb(var(--bg))' }}>` */
export const colorVars = {
  background: '--bg',
  foreground: '--fg',
  surface0: '--surface-0',
  surface1: '--surface-1',
  surface2: '--surface-2',
  surface3: '--surface-3',
  border: '--border',
  borderHover: '--border-hover',
  muted: '--muted',
  accent: '--accent',
  accentHover: '--accent-hover',
  accentSubtle: '--accent-subtle',
  danger: '--danger',
  success: '--success',
  warning: '--warning',
  info: '--info',
} as const
