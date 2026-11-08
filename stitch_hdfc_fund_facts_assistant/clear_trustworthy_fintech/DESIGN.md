---
name: Clear & Trustworthy Fintech
colors:
  surface: '#f8f9fb'
  surface-dim: '#d9dadc'
  surface-bright: '#f8f9fb'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f2f4f6'
  surface-container: '#edeef0'
  surface-container-high: '#e7e8ea'
  surface-container-highest: '#e1e2e4'
  on-surface: '#191c1e'
  on-surface-variant: '#3c4a43'
  inverse-surface: '#2e3132'
  inverse-on-surface: '#f0f1f3'
  outline: '#6c7a73'
  outline-variant: '#bbcac1'
  surface-tint: '#006c4f'
  primary: '#006c4f'
  on-primary: '#ffffff'
  primary-container: '#00b386'
  on-primary-container: '#003d2c'
  inverse-primary: '#50ddad'
  secondary: '#5a5d72'
  on-secondary: '#ffffff'
  secondary-container: '#dcdef7'
  on-secondary-container: '#5f6176'
  tertiary: '#585e6f'
  on-tertiary: '#ffffff'
  tertiary-container: '#979daf'
  on-tertiary-container: '#2e3543'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#71fac8'
  primary-fixed-dim: '#50ddad'
  on-primary-fixed: '#002116'
  on-primary-fixed-variant: '#00513b'
  secondary-fixed: '#dfe1fa'
  secondary-fixed-dim: '#c3c5dd'
  on-secondary-fixed: '#171a2c'
  on-secondary-fixed-variant: '#43465a'
  tertiary-fixed: '#dde2f6'
  tertiary-fixed-dim: '#c0c6d9'
  on-tertiary-fixed: '#151b29'
  on-tertiary-fixed-variant: '#414756'
  background: '#f8f9fb'
  on-background: '#191c1e'
  surface-variant: '#e1e2e4'
  surface-card: '#FFFFFF'
  border-subtle: '#E6E8EC'
  alert-refusal: '#EB5350'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 36px
    fontWeight: '600'
    lineHeight: 44px
    letterSpacing: -0.02em
  display-lg-mobile:
    fontFamily: Inter
    fontSize: 28px
    fontWeight: '600'
    lineHeight: 36px
    letterSpacing: -0.01em
  headline-lg:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.015em
  headline-md:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: 0em
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
    letterSpacing: 0em
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 22px
    letterSpacing: 0em
  body-md-medium:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 22px
    letterSpacing: 0em
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 18px
    letterSpacing: 0.01em
  label-md:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 18px
    letterSpacing: 0.01em
  label-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.04em
  code-num:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
    letterSpacing: -0.01em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  gutter: 1.5rem
  gutter-mobile: 1rem
  margin: 2rem
  margin-mobile: 1rem
  space-2xs: 0.25rem
  space-xs: 0.5rem
  space-sm: 0.75rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2rem
  space-2xl: 3rem
---

## Brand & Style

The design system embodies a calm, hyper-focused, and transparent financial technology aesthetic inspired by modern investment platforms. The user experience is built around trust, factual precision, and cognitive ease, avoiding visual clutter, unnecessary gradients, and decorative distractions.

### Visual Aesthetic & Philosophy
- **Style Direction:** Modern Minimalist Fintech. Characterized by pristine white surfaces, crisp high-legibility typography, clear structural borders, and purposeful accent hits.
- **Personality:** Analytical, dependable, calm, and objective. Information is delivered with structured simplicity.
- **Voice & Tone:** Factual and non-speculative. Advisory warnings and objective fund data take center stage without sensory overload.

## Colors

The color system maintains rigorous semantic discipline to preserve visual calm and rapid readability.

### Key Roles & Hierarchy
- **Primary Green (`#00B386`):** The primary visual driver. Reserved for high-value calls-to-action (CTAs), actionable text links, active tabs, focus indicators, and confirmation highlights.
- **Dark Slate (`#44475B`):** The primary text color. Replaces pure black to lower ocular fatigue while maintaining WCAG AAA contrast against white and light grey backgrounds.
- **Secondary Slate (`#6E7485`):** Secondary metadata, supporting labels, tabular captions, timestamp footers, and muted helper copy.
- **Background Light Grey (`#F6F7F9`):** Canvas foundation layer. Provides subtle separation beneath white elevated cards and navigation panels.
- **Surface Card White (`#FFFFFF`):** Base layer for content cards, prompt inputs, modals, and sticky navigation headers.
- **Border Subtle (`#E6E8EC`):** Structural partition color for dividing lines, unselected state outlines, and table headers.
- **Alert / Refusal Red (`#EB5350`):** Semantic accent restricted strictly to the left accent strip, iconography, and critical notices when handling regulatory advisory refusals and high-risk disclosures.

## Typography

Typographic hierarchy relies solely on Inter, optimized for numerical tables, financial disclosures, and assistant conversational streams.

### Principles
- **Weight Restraint:** Limit weights to 400 (Regular), 500 (Medium), and 600 (Semi-Bold). Avoid heavy bold weights (>700) to maintain an airy, understated tone.
- **Tabular Numerals:** All financial figures (NAV, AUM, expense ratios, returns) must use OpenType tabular figure formatting (`font-feature-settings: 'tnum' on, 'cv05' on`) to ensure vertical column alignment across datasets.
- **Line Heights:** Generous line heights are set to preserve scannability in technical prospectus breakdowns and multi-turn response dialogues.

## Layout & Spacing

The structural layout relies on an 8pt grid framework designed around an intentional maximum width constraint suitable for analytical tools and conversational panels.

### Grid & Max Widths
- **Desktop Layout:** Fixed-fluid hybrid system with an optimal central reading and data column capped at `1080px`. On wide canvases, assistant sidebars (history, fund metrics) pin cleanly at `320px` width while the main response flow occupies `760px`.
- **Tablet (768px - 1024px):** Single main container spanning full width with `24px` (`1.5rem`) outer canvas margins and collapsible side sheets.
- **Mobile (< 768px):** Single-column layout with `16px` (`1rem`) edge margins. Floating elements and input boxes lock to the bottom safe area.

### Vertical Rhythm
- Spacing within card internals uses `space-md` (`1rem`) to `space-lg` (`1.5rem`).
- Spacing between independent conversational bubbles or data tables defaults to `space-xl` (`2rem`).

## Elevation & Depth

Visual depth is achieved through flat tonal planes paired with low-contrast structural outlines and subtle ambient drop shadows. Floating layers stay restrained and natural.

### Depth Hierarchy
- **Level 0 (Canvas Base):** Background Light Grey (`#F6F7F9`). Completely flat with zero elevation.
- **Level 1 (Card & Modular Surfaces):** Background White (`#FFFFFF`) with a 1px continuous border of `#E6E8EC`. Accompanied by a whisper-light ambient shadow:
  `box-shadow: 0 1px 3px 0 rgba(68, 71, 91, 0.04), 0 1px 2px -1px rgba(68, 71, 91, 0.04);`
- **Level 2 (Hover States & Dropdowns):** Subtle lift using:
  `box-shadow: 0 4px 12px 0 rgba(68, 71, 91, 0.08);`
  The border remains `#E6E8EC`.
- **Level 3 (Sticky Nav / Overlays / Modals):** Crisp modal containment with:
  `box-shadow: 0 12px 28px -4px rgba(68, 71, 91, 0.12);`
  Zero gradient overlays; modal scrim uses `rgba(68, 71, 91, 0.4)`.

## Shapes

The geometric framework is balanced between soft corners and functional structure.

- **Cards, Panels, and Containers:** Fixed at `12px` border radius (`rounded-lg`), delivering a modern, friendly, yet disciplined appearance.
- **Form Inputs and Assistant Bars:** Use `8px` (`0.5rem`) to `12px` corners to blend with content cards.
- **Pills and Badges:** Filter chips, category tags, and fund status indicators use complete pill radii (`9999px`) to create clear shape contrast against rectangular information cards.
- **Buttons:** Primary and secondary action buttons match input elements at `8px` corner radius.

## Components

### Buttons
- **Primary Button:** Background `#00B386`, text `#FFFFFF`, font weight 500, height 40px (desktop) / 44px (mobile), border radius 8px. Hover state changes background to `#00A37A`. Active state `#00906C`. Focus state has a 2px offset ring of `#00B386`.
- **Secondary Button:** Background transparent, border 1px solid `#E6E8EC`, text `#44475B`. Hover background `#F6F7F9` with border `#DDE0E5`.
- **Tertiary / Text Button:** Background transparent, text `#00B386`, zero padding horizontally, hover underline or text `#00A37A`.

### Fact & Response Cards
- Base surface is `#FFFFFF` with a 1px border of `#E6E8EC` and a 12px border radius.
- Padding is strictly 20px (desktop) or 16px (mobile).
- Internal dividers utilize 1px solid `#E6E8EC`.

### Advisory Refusal Cards
- Used when the assistant must state regulatory boundaries (e.g., SEBI guidelines prohibiting non-registered financial advice).
- Base card matches standard cards (`#FFFFFF`, border `#E6E8EC`, radius 12px).
- Features an integrated 4px vertical accent bar on the flush left edge colored `#EB5350`.
- Headline text uses `#44475B` with a small red informational icon (`#EB5350`), accompanied by clear, non-punitive refusal copy in `#6E7485`.

### Chips & Filter Tags
- **Interactive Chip (Deselected):** Surface `#FFFFFF`, border 1px solid `#E6E8EC`, text `#6E7485`, radius 9999px, height 32px, padding 0 12px.
- **Interactive Chip (Selected):** Surface `rgba(0, 179, 134, 0.08)`, border 1px solid `#00B386`, text `#00B386`, font weight 500.

### Input Fields & Prompt Bar
- **Default State:** Background `#FFFFFF`, border 1px solid `#E6E8EC`, text `#44475B`, placeholder text `#6E7485`, border radius 8px to 12px.
- **Focused State:** Border 1px solid `#00B386`, outline none, shadow `0 0 0 2px rgba(0, 179, 134, 0.15)`.

### Checkboxes & Radios
- **Checkbox:** 18x18px, 4px border radius. Border 1.5px solid `#6E7485` when unselected. Selected state fills with `#00B386` and a white check icon.
- **Radio Button:** 18x18px circle. Border 1.5px solid `#6E7485`. Selected state shows an outer ring of `#00B386` with a solid center dot of `#00B386`.

### Data Display Tables (Fund Metrics)
- Header row uses background `#F6F7F9`, label font size 12px, font weight 600, text `#6E7485`, uppercase tracking +0.04em.
- Cell rows use background `#FFFFFF`, border bottom 1px solid `#E6E8EC`, text `#44475B`, tabular numerals, 48px row height.