# FORESIGHT Planning Dashboard — Design Spec

This is a spec, not a Figma file. Claude can't produce a native `.fig`
binary, but everything below is written so you (or a designer) can
rebuild the frames in Figma quickly, or hand this file to one.

## 1. Purpose & audience

A non-technical operations planner opens this once a week and needs to
answer, unaided: *"What do I reorder, what do I clear, and how much
money is at stake?"* Design for scanning, not for reading.

## 2. Screen inventory (Figma pages/frames)

1. **Overview** — 4 KPI cards + decisioning scatter grid
2. **Action list** — prioritised, filterable table
3. **SKU detail** — single-SKU forecast chart with interval band
4. **Empty / loading states** — for when the pipeline hasn't run yet

## 3. Color system

| Token | Hex | Use |
|---|---|---|
| `bg-base` | `#0F0F1A` (dark) / `#FFFFFF` (light) | App background |
| `surface` | `#1A1A2E` / `#F7F7FB` | Cards, panels |
| `brand-primary` | `#6C5CE7` | Primary actions, links, brand accent |
| `risk-reorder` | `#D1495B` (red) | "Reorder now" quadrant |
| `risk-markdown` | `#6C5CE7` (purple) | "Markdown / clear" quadrant |
| `risk-watch` | `#E1A730` (amber) | "Watch / volatile" quadrant |
| `risk-healthy` | `#2A9D8F` (teal) | "Healthy" quadrant |
| `text-primary` | `#F5F5FA` / `#1A1A2E` | Headings, body |
| `text-muted` | `#9A9AB0` | Captions, helper text |

Keep the four risk colors **consistent everywhere** (KPI cards, scatter
plot, table row tags) — that consistency is what lets a planner scan
fast.

## 4. Typography

- Headings: Inter or system sans-serif, Semibold, 20–28px
- Body/table: Inter Regular, 14px
- KPI numbers: Inter Bold, 32px, tabular figures (numbers must align)

## 5. Layout — Overview frame (desktop, 1440px)

```
┌──────────────────────────────────────────────────────────────┐
│  📦 FORESIGHT — Demand & Inventory Planning     [Sidebar ▸]  │
│  NorthBay Living                                              │
├──────────────────────────────────────────────────────────────┤
│ [KPI: SKUs in view] [KPI: Sales at risk ₹] [KPI: Capital ₹]  │
│ [KPI: Forecast WAPE vs baseline]                              │
├──────────────────────────────────────────────────────────────┤
│  Decisioning view — stockout vs overstock risk                │
│  ┌────────────────────────────────────────────────────────┐  │
│  │   scatter plot, 4 quadrants, bubble size = ₹ at stake   │  │
│  │   dotted lines at x=0.5, y=0.5 dividing quadrants       │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
Sidebar (240px, collapsible): Category multiselect, Quadrant multiselect,
SKU search box.
```

KPI cards: 4-column grid, equal width, 16px gap, each a `surface` card
with 24px padding, a `text-muted` label on top and the bold number below.

## 6. Layout — Action list frame

A single full-width data table below the KPI row, columns in this exact
order (matches the CSV the backend actually produces — don't reorder):

`SKU ID | Category | Quadrant (colored pill) | Recommended action |
Stockout risk | Overstock risk | Sales at risk (₹) | Capital locked (₹) |
On hand | On order | Lead time (days)`

- Sort default: descending by (sales at risk + capital locked).
- "Quadrant" renders as a colored pill using the risk colors above.
- Sticky header row.
- Empty state: teal checkmark icon + "No SKUs currently need action."

## 7. Layout — SKU detail frame

Line chart, 2:1 aspect ratio:
- Solid line: actual historical `units_sold` (last 90 days)
- Solid line, brand-primary: forecast
- Dotted line, muted: seasonal-naive baseline (for comparison)
- Shaded band (brand-primary at 15% opacity): 80% interval
- Vertical dashed marker where history ends and forecast begins

## 8. Components to build as Figma components (for reuse)

- `KPI Card` (label + value + optional delta chip)
- `Risk Pill` (4 color variants: reorder / markdown / watch / healthy)
- `Filter Multiselect`
- `Data Table Row`
- `Empty State` (icon + message + optional CTA)

## 9. Responsive notes

Below ~900px: KPI grid collapses to 2 columns, sidebar becomes a
collapsible drawer, scatter plot and table both scroll horizontally
inside their own container rather than the page scrolling sideways.

## 10. What NOT to design

Per the brief's out-of-scope list: no purchase-order placement UI, no
supplier-selection screens, no price-optimization controls. The
interface's whole job is *show the decision*, not *execute* it.
