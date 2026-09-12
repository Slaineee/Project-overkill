# Product

<!-- impeccable:product-schema 1 -->

## Platform

Windows desktop game rendered at 1280×720 with pygame-ce.

## Users

Players of fast, session-based roguelite shooters who need to read threats, population, gates, firepower, and build choices in under a second while aiming and moving with keyboard and mouse.

## Product Purpose

火力过载 is a ten-world firepower escalation game. Population functions as survivability and offensive scale; combat rewards accurate movement, target prioritization, temporary gate benefits, and a coherent card build assembled between worlds.

## Positioning

The product fantasy is a weapon system pushed beyond safe operating limits. Its identity comes from escalating population and damage, dense projectile combat, rapid build compilation, and a final two-world endgame challenge—not from a dual-lane narrative.

## Operating Context

Players use WASD, mouse aim, held primary fire, keyboard shortcuts, a between-world equipment compiler, system settings, pause controls, and developer diagnostics. The first eight worlds form the main campaign; worlds nine and ten form the optional endgame protocol.

## Capabilities and Constraints

- Preserve gameplay rules, balance values, save/settings behavior, audio behavior, and test semantics during UI work.
- Preserve the Python, pygame-ce, and Windows executable packaging stack.
- Keep Chinese as the primary player-facing language.
- Prioritize combat readability at 1280×720 and preserve keyboard and mouse operation.
- There is no Tauri, browser, DOM, WebView2, or Windows composition layer. Glass-inspired materials are rendered inside pygame over an opaque foundation.

## Brand Commitments

- Product name: 火力过载 / PHOTON OVERDRIVE.
- Visual theme: near-black weapons terminal, electric cyan energy, hot-magenta overload signals, purple secondary systems, red danger states.
- The repeated visual motifs are reactor orbits, energy rails, scanner fields, sixteen-step world sequencing, and bounded tactical panels.
- Menus, combat HUD, shop, settings, overlays, and pause state must feel like parts of one operating system.

## Evidence on Hand

- Current implementation and visible behavior: `main/main.py`.
- Card data and behavior: `main/cards.py` and `main/data/cards.json`.
- Automated behavior contract: `main/test_*.py`.
- Historical planning documents are explicitly excluded from current product truth.

## Product Principles

- The next threat and useful action should be readable in under a second.
- Light effects create energy and focus; opaque surfaces preserve legibility.
- Population, danger, currency, progression, and interaction use stable semantic colors.
- Visual density may be high, but primary actions and combat entities remain unmistakable.
- UI refactoring must not silently alter gameplay behavior.

## Accessibility & Inclusion

Maintain strong text contrast, large click targets, visible hover/selected states, redundant text and shape cues for danger, screen-shake controls, glow intensity controls, and an opaque base presentation that remains usable when effects are reduced.
