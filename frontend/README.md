# LedgerLens Frontend - Spreetail Shared Expenses

This repository contains the frontend assets and presentation layers for **LedgerLens**, an explainable shared-expenses cleanup web application.

## Design Details
- **Theme Support**: Custom dark and light modes styled with HSL custom properties (Midnight/Teal/Rose palette). Persistent user theme storage.
- **Typography**: Google Fonts loaded dynamically (`Outfit` for headers, `Inter` for body text).
- **Glassmorphism**: Visual cards using `backdrop-filter: blur(16px)` with subtle shadows and border highlights.
- **Micro-Animations**: Clean transitions on hover effects, card expansions, and interaction updates.
- **Gauges & Balance Visualizations**: Progress bar visualizations showing credit and debt relative to the maximum account values.
- **Clientside Actions**:
  - Live search filters on the Expense Trace page.
  - Category and status filters on the Data Quality Board/Anomalies page.

## Directory Structure
- `static/styles.css`: Complete styling sheet containing variable definitions, utility classes, and layout rules.
