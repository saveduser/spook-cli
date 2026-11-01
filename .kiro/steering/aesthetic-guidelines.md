# Aesthetic & QSS Steering

When generating Qt QSS or UI components, you MUST conform to the "Haunted Tech-Wear" design system.

1. **The Palette:**
   - Base: Deep Void (`#0B0813`)
   - Panel: Crypt Purple (`#120B1D`)
   - Border: Slate Purple (`#38254A`)
   - Text / Foreground: Soft Off-White (`#F1F5F9`)
   - Muted Text: Ashen Lilac (`#A89CB9`)
   - RAM / Soul Pool: Ectoplasm Green (`#39FF14`)
   - CPU / Core Heat: Neon Orange (`#FF7A00`)
   - Phantom / Selection: Phantom Purple (`#BD00FF`)

2. **The Kiro Mascot:**
   - In gtop, use the local animated `spookcli/assets/blinking_ghost.gif` when present, falling back to `spookcli/assets/ghost-kiro-blink.gif`.
   - If no GIF is available, render a procedural ghost or this ASCII fallback:
   ```text
      .---.
     / ◉ ◉ \
     |  ⌖  |
     \~^~^~/
   ```

3. **Surface Treatment:**
   - gtop uses a frameless translucent window with a glass panel: `background-color: rgba(15, 20, 28, 180);`, 1px `#38254A` border, and 14px radius.
   - Keep scanlines and spiderweb corner accents subtle so text and process rows remain legible.
