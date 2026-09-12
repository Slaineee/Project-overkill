# 火力过载 UI System

## Direction

“Photon Overdrive / 光子过载” is a dense future-weapons interface rather than generic glassmorphism. The screen should feel electrically charged, but every bright element must communicate energy, danger, progress, or interaction.

Design dials: variance 6, motion 5, visual density 7.

## Color tokens

- Foundation `#03050F`: window and arena base.
- Panel `#0A0F1F`: primary opaque reading surface.
- Raised panel `#111930`: controls and cards.
- Electric cyan `#24E2FF`: population, navigation, active rails, focus.
- Hot magenta `#FF30BB`: overload, primary action, reactor energy.
- Signal purple `#B84FFF`: secondary systems and special states.
- Danger red `#EB4E59`: lethal threats and destructive actions only.
- Reward yellow `#FFDD4D`: currency, DPS targets, rewards.
- Success green `#56FFB5`: positive growth and online state.
- Text `#F1F8FF`; muted text `#97AECD`.

## Materials

- The window foundation is always opaque.
- Glass-inspired panels are bounded, dark, and highly legible; they use a thin cool rim and restrained top highlight.
- Do not stack translucent panels or place glass on every card.
- Glow is composited with alpha. Large additive RGB blooms are prohibited because pygame does not attenuate them as expected.
- Dense text regions use opaque or near-opaque surfaces.

## Typography

- Microsoft YaHei/SimHei/Arial fallback for Chinese interface text.
- Cascadia Mono/Consolas for numeric telemetry.
- Large bold Chinese headings pair with compact uppercase English system labels.
- Labels describe the player action directly; avoid decorative sci-fi jargon where it obscures meaning.

## Components

- `draw_ui_panel`: bounded tactical surface with shadow, rim, and corner brackets.
- `draw_menu_button`: left energy rail, explicit ACT/SEL state, press offset, and hover bloom.
- `draw_neon_line`: core line plus two alpha-composited glow widths.
- `draw_step_row`: sixteen-step campaign/endgame sequence or compact progress telemetry.
- `draw_section_title`: compact label with a short semantic energy rail.
- HUD: 64px opaque telemetry strip with stable columns and danger override.

## Motion

- Reactor arcs, scan beams, and step indicators may animate continuously at moderate speed.
- Text, metrics, and primary controls remain stationary.
- Never animate blur radius or large panel geometry.
- Existing glow, spread, feather, and screen-shake settings are the practical reduced-effects controls.

## Layout rules

- Preserve the 1280×720 target and safe margins of at least 18px.
- Use asymmetry: identity/actions on the left, reactor/status systems on the right.
- Combat entities always render above arena decoration.
- Red is reserved for danger/destructive states; magenta is not a synonym for error.
- Critical copy must remain readable over the darkest and brightest point of every animated background.

## Fallback

Normal path: opaque pygame foundation → bounded translucent enhancement → opaque panel fallback. pygame has no DOM forced-colors integration; reduced visual-effect settings and semantic text/shape cues provide the available accessibility fallback.
