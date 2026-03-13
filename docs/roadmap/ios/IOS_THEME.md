# IOS Theme

## Direction

The app should not look “styled.” It should look quiet, precise, and expensive.

Visual character:

- black-first
- low contrast, not flat
- no blue gradients
- no decorative accent color
- white only where emphasis is deserved
- system red only for destructive/error intent

The goal is not “dark mode UI.” The goal is a restrained monochrome product language.

## Monochrome Design Tokens

### Core colors

Use semantic tokens, not raw Color(...) values in views.

Suggested token set:

- bg.app
  - near-black app background
  - example target: #0A0A0A
- bg.surface
  - main card/panel background
  - example: #141414
- bg.surfaceRaised
  - slightly lifted surface for modals / selected cards
  - example: #1A1A1A
- bg.input
  - text field / editable control fill
  - example: #111111
- bg.disabled
  - disabled control fill
  - example: #1E1E1E
- fg.primary
  - primary text
  - example: #F5F5F5
- fg.secondary
  - supporting text
  - example: #B3B3B3
- fg.tertiary
  - low-emphasis labels / hints
  - example: #7A7A7A
- border.default
  - subtle card and input border
  - example: #2A2A2A
- border.strong
  - focused / selected border
  - example: #4A4A4A
- border.subtle
  - dividers
  - example: #202020
- fill.primaryAction
  - primary button fill
  - example: #F2F2F2
- fg.primaryAction
  - text on primary buttons
  - example: #0A0A0A
- fill.secondaryAction
  - secondary button fill
  - example: #1A1A1A
- fg.secondaryAction
  - text on secondary buttons
  - example: #F2F2F2
- state.success
  - use sparingly for completed states
  - recommendation: very muted green-gray, not bright green
- state.warning
  - use sparingly for incomplete-but-recoverable states
  - recommendation: muted warm gray, not orange
- state.error
  - system red
  - do not invent a custom destructive palette

### Color rules

- No gradients in normal surfaces.
- At most one background treatment per screen.
- Cards should separate via surface contrast and border, not glow.
- Status should be communicated first by text, second by icon, only third by color.
- Success/warning colors should never dominate the screen.

## Typography Rules

Use SF only. No custom fonts.

### Type scale

- display
  - onboarding hero / welcome title
  - large, bold, tight line count
- title
  - main section title
- headline
  - card title / important label
- body
  - primary explanatory copy
- subbody
  - dense supportive copy
- caption
  - inline validation, hints, footnotes

### Typography behavior

- Headlines should be short.
- Body copy should rarely exceed 2-3 lines without a break.
- Secondary copy should use fg.secondary, not reduced opacity on white everywhere.
- Avoid too many font weights on one screen.
- Recommended default stack:
  - titles: semibold / bold
  - body: regular
  - secondary labels: medium or regular

## Spacing Tokens

Use a fixed spacing scale.

Suggested:

- space.4
- space.8
- space.12
- space.16
- space.20
- space.24
- space.32
- space.40

Rules:

- Screen horizontal padding: 20
- Card internal padding: 16 or 20
- Section gap: 24
- Tight label-to-copy gap: 6 or 8
- Bottom CTA area should feel anchored and generous, not cramped

## Radius Tokens

Keep corners soft but not playful.

Suggested:

- radius.10 for chips / small controls
- radius.14 for fields / secondary buttons
- radius.18 for cards
- radius.24 for major panels if needed

Rules:

- Do not mix too many corner radii on one screen.
- Primary CTA and text fields should feel related.

## Shadows And Depth

Use almost no shadow.

Rules:

- Prefer border + contrast over drop shadow.
- If any shadow exists, it should be extremely soft and short-range.
- Avoid glassmorphism and blur-heavy panels for this product direction.

## Component Rules

### 1. Screen Container

Every major screen should share a base container:

- app background color
- consistent horizontal padding
- top-aligned content
- optional bottom CTA safe-area inset

Do not let each screen invent its own background.

### 2. Cards / Panels

Use one base panel style:

- bg.surface
- border.default
- radius 18
- padding 16 or 20

Use for:

- onboarding explanation blocks
- backend config sections
- readiness summaries
- help sections

Do not:

- stack multiple decorative overlays
- use material blur as the default card style
- use tinted cards

### 3. Buttons

Define 3 button styles only:

- PrimaryButton
  - filled light button on dark background
  - used for main forward action only
- SecondaryButton
  - dark surface button with border
  - used for alternate actions
- DestructiveButton
  - neutral dark fill with red text or bordered red treatment
  - only for disconnect/reset/delete/deactivate

Rules:

- Only one primary button per screen.
- Skip buttons should usually be secondary or text-style, never visually equal to Continue.
- Disabled buttons should be visibly inactive but still readable.

### 4. Inputs

All text fields should share:

- same fill
- same border
- same height
- same label style
- same inline validation position

Rules:

- Labels above fields, not placeholder-only.
- Placeholder text uses tertiary color.
- Inline validation sits below the field, left aligned.
- Secure token entry should visually match URL entry.

### 5. Status Rows

For backend readiness, Meta readiness, wake practice counts:

- use a reusable row component
- left: concise title
- center/body: short status text
- right: small icon or chip if needed

Rules:

- Avoid dashboards.
- Keep rows human-readable first, machine-readable second.
- Replace raw statuses like inactive, configuring, ready with product wording.

### 6. Chips / Badges

Use sparingly.

Allowed uses:

- Connected
- Needs setup
- Skipped
- Ready
- Unavailable

Rules:

- Uppercase is optional, but if used, keep size small and spacing tight.
- Badges must not become the main information carrier.

### 7. Bottom CTA Bar

Use a shared bottom action area for onboarding screens:

- subtle top divider
- same padding everywhere
- one main CTA, optional secondary beneath or beside it

Rules:

- Keep CTA area stable when validation text appears.
- Do not let the bottom bar become visually heavier than the screen content.

### 8. Help Blocks

Help content should use:

- title
- 1-3 short bullets or sentences
- optional icon

Rules:

- No long prose wall.
- No blue info boxes.
- Troubleshooting should be broken into single-purpose sections.

## Screen-Level Rules

### Welcome

- strongest typography in the app
- almost no chrome
- one hero message, one supporting paragraph, one CTA

### Backend Setup

- looks like a serious setup form, not a settings dump
- fields first, explanation second
- validation state should be calm and compact

### Meta Connection

- explain the flow clearly
- use progress rows, not feature marketing
- readiness info should be clearer than current DAT/dev language

### Wake Practice

- treat as a guided exercise
- counters and phrase cards should be visually obvious
- avoid debug labels and internal runtime text

### Home

- should feel nearly empty
- one primary action
- a few concise readiness summaries
- settings/help tucked away, not competing with activation

### Settings

- grouped lists or cards
- no custom visual noise
- advanced settings collapsed or visually separated

## Motion Rules

Use very little animation.

Allowed:

- fade between splash and first routed screen
- subtle slide for onboarding progression
- quick state change on validation success/failure
- counter increment feedback in wake practice

Avoid:

- springy card choreography
- floating glow effects
- large matched-geometry flourishes
- animated gradients

## Accessibility Rules

- Minimum contrast should stay high despite grayscale.
- Do not rely on color alone for readiness/error state.
- Support Dynamic Type from the start.
- All CTA buttons should be true Buttons, not gestures.
- Form labels should remain explicit and persistent.

## What This Means For The Existing UI

Current issues to remove:

- blue gradients in AssistantRuntimeView.swift
- blue/orange emphasis in HomeScreenView.swift
- orange appPrimaryColor asset
- purple-ish destructive palette in assets
- material-heavy card treatment as default visual language

Current pieces worth keeping structurally:

- splash screen composition in StartupLoadingView.swift
- reusable button foundation in CustomButton.swift
- reusable info row idea in TipRowView.swift

## Recommended Token Set To Implement First

If we want the minimum viable design system before Phase 1 UI work, I’d start with:

- PWColor.background
- PWColor.surface
- PWColor.surfaceRaised
- PWColor.input
- PWColor.border
- PWColor.textPrimary
- PWColor.textSecondary
- PWColor.textTertiary
- PWColor.primaryButtonFill
- PWColor.primaryButtonText
- PWColor.secondaryButtonFill
- PWColor.secondaryButtonText
- PWColor.destructive

And components:

- PWScreen
- PWCard
- PWPrimaryButton
- PWSecondaryButton
- PWTextFieldRow
- PWStatusRow
- PWBottomActionBar

## Finalized Semantic Token Contract

This section locks the semantic names that implementation should use.

### Color tokens

Use a single `PWColor` namespace or equivalent theme container.

- `PWColor.background`
  - full-screen app background only
- `PWColor.surface`
  - default cards, grouped sections, inset panels
- `PWColor.surfaceRaised`
  - selected cards, emphasized surfaces, modal content
- `PWColor.input`
  - editable field fill
- `PWColor.disabledFill`
  - disabled controls and unavailable states
- `PWColor.border`
  - default card and field outline
- `PWColor.borderStrong`
  - focused or selected outline
- `PWColor.borderSubtle`
  - dividers and low-emphasis separators
- `PWColor.textPrimary`
  - highest-emphasis text
- `PWColor.textSecondary`
  - supporting text and labels
- `PWColor.textTertiary`
  - hints, placeholders, low-emphasis metadata
- `PWColor.primaryButtonFill`
  - the main CTA fill
- `PWColor.primaryButtonText`
  - text and icons on the main CTA
- `PWColor.secondaryButtonFill`
  - secondary action fill
- `PWColor.secondaryButtonText`
  - text and icons on secondary actions
- `PWColor.destructive`
  - destructive text, icon, and border emphasis
- `PWColor.success`
  - completed state accents only
- `PWColor.warning`
  - caution or incomplete-but-recoverable state accents only
- `PWColor.error`
  - failure state accents; may map to system red

Rules:

- Never use `success`, `warning`, or `error` as large fills.
- Never use `primaryButtonFill` as a card background.
- Never use raw `Color.white.opacity(...)` or hardcoded `Color(red:...)` in feature views after the theme layer exists.

### Typography tokens

Use a single `PWTypography` namespace or equivalent style helpers.

- `PWTypography.display`
  - welcome hero and first-line onboarding titles
- `PWTypography.title`
  - screen titles and main section headings
- `PWTypography.headline`
  - card titles and strong labels
- `PWTypography.body`
  - primary copy
- `PWTypography.subbody`
  - supportive copy and dense explanations
- `PWTypography.caption`
  - validation text, hints, and lightweight metadata

Rules:

- `display` should appear on very few screens.
- `caption` should never carry core meaning alone.
- Feature views should choose from this set rather than defining ad hoc font stacks.

### Spacing tokens

Use a single `PWSpace` namespace or equivalent constants.

- `PWSpace.xs = 4`
- `PWSpace.sm = 8`
- `PWSpace.md = 12`
- `PWSpace.lg = 16`
- `PWSpace.xl = 20`
- `PWSpace.section = 24`
- `PWSpace.hero = 32`
- `PWSpace.screen = 20`

Rules:

- Screen horizontal padding defaults to `PWSpace.screen`.
- Card padding defaults to `PWSpace.lg` or `PWSpace.xl`.
- Section spacing defaults to `PWSpace.section`.

### Radius tokens

Use a single `PWRadius` namespace or equivalent constants.

- `PWRadius.chip = 10`
- `PWRadius.field = 14`
- `PWRadius.card = 18`
- `PWRadius.panel = 24`

Rules:

- Inputs and buttons should mostly use `field`.
- Cards should mostly use `card`.
- Avoid introducing one-off radii in feature views.

## Shared SwiftUI Component Catalog

These are the reusable primitives the new screens should be built from.

### `PWScreen`

Purpose:

- shared full-screen container for major screens

Suggested API:

```swift
struct PWScreen<Content: View>: View {
    let title: String?
    let showsBackButton: Bool
    @ViewBuilder let content: Content
}
```

Responsibilities:

- applies `PWColor.background`
- applies standard horizontal padding
- handles safe area behavior
- optionally hosts a nav title or screen title region

### `PWCard`

Purpose:

- standard panel for grouped content

Suggested API:

```swift
struct PWCard<Content: View>: View {
    let isRaised: Bool
    @ViewBuilder let content: Content
}
```

Responsibilities:

- applies `surface` or `surfaceRaised`
- applies border
- applies standard radius and padding

### `PWPrimaryButton`

Purpose:

- main CTA for a screen

Suggested API:

```swift
struct PWPrimaryButton: View {
    let title: String
    let isDisabled: Bool
    let action: () -> Void
}
```

Rules:

- only one per screen
- should visually dominate secondary actions

### `PWSecondaryButton`

Purpose:

- alternate action without competing with the primary CTA

Suggested API:

```swift
struct PWSecondaryButton: View {
    let title: String
    let isDisabled: Bool
    let action: () -> Void
}
```

### `PWDestructiveButton`

Purpose:

- dangerous or irreversible action

Suggested API:

```swift
struct PWDestructiveButton: View {
    let title: String
    let isDisabled: Bool
    let action: () -> Void
}
```

### `PWTextFieldRow`

Purpose:

- labeled input row used in onboarding and settings

Suggested API:

```swift
struct PWTextFieldRow: View {
    let label: String
    let placeholder: String
    @Binding var text: String
    let message: String?
    let tone: PWFieldTone
    let isSecure: Bool
}
```

Suggested supporting type:

```swift
enum PWFieldTone {
    case normal
    case success
    case warning
    case error
}
```

Responsibilities:

- label above field
- consistent field height
- inline validation below field
- secure and plain text variants share identical visual layout

### `PWStatusRow`

Purpose:

- concise readiness or progress row

Suggested API:

```swift
struct PWStatusRow: View {
    let title: String
    let value: String
    let tone: PWStatusTone
}
```

Suggested supporting type:

```swift
enum PWStatusTone {
    case neutral
    case success
    case warning
    case error
}
```

Responsibilities:

- human-readable status text
- optional icon or subtle tone treatment
- no dashboard-like density

### `PWBadge`

Purpose:

- low-count use for compact state labels

Suggested API:

```swift
struct PWBadge: View {
    let text: String
    let tone: PWStatusTone
}
```

Use cases:

- connected
- skipped
- needs setup
- ready
- unavailable

### `PWBottomActionBar`

Purpose:

- shared bottom CTA area for onboarding

Suggested API:

```swift
struct PWBottomActionBar<Content: View>: View {
    @ViewBuilder let content: Content
}
```

Responsibilities:

- standard padding
- subtle top divider
- stable layout when validation text appears above

### `PWHelpBlock`

Purpose:

- reusable help and troubleshooting section

Suggested API:

```swift
struct PWHelpBlock: View {
    let title: String
    let body: String
    let systemImage: String?
}
```

Responsibilities:

- compact explanatory block
- consistent typography and spacing
- no tinted info-box styling

## Implementation Rules

- Build feature screens by composing these primitives rather than styling raw stacks repeatedly.
- Feature views may pass content and state into shared components, but should not redefine color, spacing, radius, or typography locally without a strong reason.
- If a new screen needs a new primitive, add it to this catalog first rather than inventing it inline.
