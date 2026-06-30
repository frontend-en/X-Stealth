# Design Research Notes

## Reddit prompt takeaways

- Do not ask AI for a perfect full app in one pass. Ask for a rough structure, then refine page by page, then polish individual components and states.
- Give hard constraints: product type, target user, data density, existing components, mobile behavior, what to avoid, and what must be visible above the fold.
- For dashboards, require accessibility: chart labels, fallback tables, contrast, keyboard-friendly controls, empty/loading/error states.
- Use style prompts as reusable “design lenses” over the same content instead of changing content and style at the same time.

## Practical prompt template

```text
Design an operational dashboard for [product/persona].
Primary user: [who uses it daily].
Core job: [what decision they need to make fast].
Data shown: [metrics, rows, statuses, charts].
Tone: calm, dense, professional, not a marketing landing page.
Must include: responsive layout, filters, empty/loading/error states, accessible chart labels, table fallback, no text overflow.
Avoid: generic hero sections, decorative gradients, nested cards, low-contrast charts.
First produce the information architecture, then the component layout, then visual styling.
```

## Chart library shortlist

- Recharts: best default for a React dashboard with standard line, area, bar and pie charts. Declarative, easy to maintain, and has responsive containers.
- Apache ECharts: best when data becomes large, highly interactive, or needs advanced chart types and Canvas rendering.
- Nivo: good for polished dataviz with many ready-made chart types, built on D3.
- Visx: best if you want a custom charting system and are comfortable composing low-level primitives.

For this dashboard I used Recharts because the current need is a readable post-performance dashboard, not millions of points or custom visualization primitives.

## Source links

- Reddit search: https://www.reddit.com/search/?q=UI%20design%20prompts%20dashboard%20design
- Reddit search: https://www.reddit.com/search/?q=UX%20design%20ChatGPT%20prompts%20dashboard
- Recharts: https://recharts.org/
- Apache ECharts: https://echarts.apache.org/
- Nivo: https://nivo.rocks/
- Visx: https://airbnb.io/visx/
