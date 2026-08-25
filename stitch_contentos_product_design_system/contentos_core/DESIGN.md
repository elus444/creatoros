---
name: ContentOS Core
colors:
  surface: '#f9f9ff'
  surface-dim: '#cadaff'
  surface-bright: '#f9f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f1f3ff'
  surface-container: '#e8edff'
  surface-container-high: '#e0e8ff'
  surface-container-highest: '#d7e2ff'
  on-surface: '#041b3c'
  on-surface-variant: '#424754'
  inverse-surface: '#1d3052'
  inverse-on-surface: '#edf0ff'
  outline: '#727785'
  outline-variant: '#c2c6d6'
  surface-tint: '#005ac2'
  primary: '#0058be'
  on-primary: '#ffffff'
  primary-container: '#2170e4'
  on-primary-container: '#fefcff'
  inverse-primary: '#adc6ff'
  secondary: '#0051d5'
  on-secondary: '#ffffff'
  secondary-container: '#316bf3'
  on-secondary-container: '#fefcff'
  tertiary: '#535d66'
  on-tertiary: '#ffffff'
  tertiary-container: '#6c767f'
  on-tertiary-container: '#fcfcff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#d8e2ff'
  primary-fixed-dim: '#adc6ff'
  on-primary-fixed: '#001a42'
  on-primary-fixed-variant: '#004395'
  secondary-fixed: '#dbe1ff'
  secondary-fixed-dim: '#b4c5ff'
  on-secondary-fixed: '#00174b'
  on-secondary-fixed-variant: '#003ea8'
  tertiary-fixed: '#dae4ee'
  tertiary-fixed-dim: '#bec8d2'
  on-tertiary-fixed: '#131d24'
  on-tertiary-fixed-variant: '#3e4851'
  background: '#f9f9ff'
  on-background: '#041b3c'
  surface-variant: '#d7e2ff'
typography:
  display-lg:
    fontFamily: Hanken Grotesk
    fontSize: 48px
    fontWeight: '700'
    lineHeight: 56px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Hanken Grotesk
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Hanken Grotesk
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  headline-sm:
    fontFamily: Hanken Grotesk
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 26px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 22px
  label-md:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.02em
  headline-lg-mobile:
    fontFamily: Hanken Grotesk
    fontSize: 28px
    fontWeight: '600'
    lineHeight: 36px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  base: 4px
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 40px
  gutter: 20px
  container-max: 1440px
---

## Brand & Style
The design system embodies a premium, intelligent, and calm environment tailored for high-performance content operations. The aesthetic draws from high-utility, developer-centric tools while maintaining the approachability of an editorial platform. 

The style is **Modern Corporate with Minimalist influences**, focusing on extreme clarity, high-density information display, and purposeful white space. It prioritizes functional elegance over decorative elements, using subtle depth and a refined blue-scale palette to signal AI sophistication without overwhelming the user. The emotional response should be one of "effortless control" and "creative focus."

## Colors
The palette is rooted in a "Clean Sky" spectrum. The primary background is pure white to ensure a crisp editorial feel, while a very pale blue (#F6F9FC) provides subtle structural contrast for sidebars and secondary regions.

**AI Interactions:** Use the Tertiary blue (#EAF4FF) for surfaces specifically generated or managed by AI agents. This provides a distinct but harmonious visual cue for machine-assisted content.

**Dark Mode:** Avoid pure black. Use a sophisticated deep blue-gray (#0F172A) for the base, with layered surfaces using slightly lighter increments of the same hue to maintain depth and professional sobriety.

## Typography
The typographic system uses **Hanken Grotesk** for headlines to provide a sharp, contemporary "tech-premium" edge. For the body, **Inter** ensures maximum legibility in high-density data views. 

**JetBrains Mono** is utilized sparingly for labels, metadata, and AI status indicators to convey a sense of technical precision and "under-the-hood" intelligence.

Vertical rhythm should be strictly maintained. Use tighter letter-spacing on larger display type to enhance the "polished" editorial feel.

## Layout & Spacing
The design system employs a **12-column fluid grid** for main content areas, but transitions to a **Fixed sidebar + Fluid stage** model for the core application interface.

- **Desktop:** 240px fixed sidebar, 16px or 24px margins depending on content density.
- **Density:** High-density layouts are preferred. Use 8px (sm) and 16px (md) increments for internal component spacing to keep the UI compact and "pro" level.
- **Reflow:** On tablet, the sidebar collapses to an icon-rail; on mobile, it moves to a bottom-nav or hamburger menu with margins reduced to 16px.

## Elevation & Depth
Depth is conveyed primarily through **Tonal Layers** and extremely subtle shadows. 

- **Level 0 (Base):** White (#FFFFFF) or Pale Blue (#F6F9FC).
- **Level 1 (Cards/Floating elements):** White surface with a 1px border (#DCE6F0) and a soft, diffused shadow: `0 2px 4px rgba(23, 43, 77, 0.05)`.
- **Level 2 (Modals/Popovers):** Higher contrast border and a double-layered shadow for distinct separation: `0 10px 25px rgba(23, 43, 77, 0.10)`.

Avoid heavy drop shadows or glows. The goal is a "flat-plus" look where elements feel placed on top of one another rather than floating in 3D space.

## Shapes
The shape language is **Soft (0.25rem / 4px)**. This slight rounding provides a modern, approachable feel while maintaining the professional rigor of a workspace tool. 

- Use **rounded-sm (2px)** for small indicators like checkboxes.
- Use **rounded (4px)** for buttons and input fields.
- Use **rounded-lg (8px)** for cards and larger containers.
- Use **Full (Pill)** only for status badges and AI agent indicators to differentiate them from functional UI buttons.

## Components
### Buttons
- **Primary:** Strong Blue (#2563EB) background, white text. No gradient. 
- **Ghost/Tertiary:** No background, Secondary Text (#5B6B82). On hover, background becomes Soft Blue (#E3F0FC).

### AI Agent Indicators
Status indicators for Research, Strategy, and Content agents must be visually distinct:
- **Research:** Soft Blue tint with a "Search" glyph.
- **Strategy:** Pale Indigo tint with a "Chart" glyph.
- **Content:** Primary Blue tint with a "Pen" glyph.
- All use pill-shaped containers with JetBrains Mono "Label" typography.

### Input Fields
- Border-based (1px #DCE6F0). No background color in default state. 
- Focus state: Border changes to Primary Blue (#3B82F6) with a subtle 2px outer glow of the same color at 10% opacity.

### Cards
- Minimal elevation. Card headers should use Hanken Grotesk (headline-sm) with a subtle bottom divider.
- Content padding should be a consistent 20px (lg) for readability.

### Lists
- High-density. 48px row height. 1px bottom border (#DCE6F0) between items. Hover state uses #F6F9FC.