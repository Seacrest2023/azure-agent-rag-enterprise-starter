# Use case: multi-site restaurant groups

A worked example of the baseline applied to one vertical: restaurant groups with many locations. This document holds everything specific to restaurants: the domain research, the data model, the rules and the examples. The machinery is the generic baseline, described in [architecture.md](../architecture.md) and [stack.md](../stack.md): intake, staging, enforcement, access, the agent, search and the security stack.

**Status:** designed, not built. No tables exist and no data is loaded.

## The problem

Restaurant data is messy. Every location runs its own systems, item names don't match, prices differ by channel, and invoices arrive as PDFs and photos. This use case takes operational data in any format (CSV, PDF, image, Word doc, POS feed), turns it into clean, consistent records, and lets an AI agent answer questions about where the business makes and loses money. Every answer is grounded in the data it came from.

## How the design was derived

| Step | Input | What it contributed |
| --- | --- | --- |
| 1 | **Sample operator dataset** | 6 raw tabs (sites, menu/recipes, POS sales, supplier invoices, labour, waste) plus a calculated finance tab. 5 sites, 6 weeks, weekly totals only. A starting point, but too clean to reflect real operations. |
| 2 | **Research: restaurant data and systems landscape** | Every data element restaurants capture, the major systems per category, and which system is the source of truth for each. Exposed gaps: invoice lines, contract prices, promotions, voids, labour detail. |
| 3 | **Research: unit economics and benchmarks** | Realistic ranges for food cost, labour %, discount rate, and prime cost, and dollar sizing for margin leaks. |
| 4 | **Operator domain knowledge** | Item names are inconsistent across locations and channels; locations often run different POS systems; channels (dine-in, drive-thru, online, third-party delivery) carry different prices; loyalty ties to promotions; data arrives in any format; the same term can mean different things at different sites. |
| 5 | **Research: restaurant schema design** | Dimensional model (facts and dimensions), medallion layers, check/line/shift grain instead of weekly, recipes (BOM), stock counts, voids as a flag on order lines, sale vs payout separation, temporal price tables. |
| 6 | **Research: Azure-based restaurant chains** | Confirmed Azure SQL as the operational engine; columnstore, partitioning, duplicate-proof keys, read-only agent identity, ledger tables; added raw intake, term mappings, and an agent audit ledger. |
| 7 | **Reconciliation** | Merged both schema studies and corrected their errors (see [Decisions](#decisions-and-corrections)). Result: 25 tables plus views. |

**Evidence note:** Restaurant chains don't publish their database designs. This structure follows Microsoft's standard patterns and dimensional-modeling practice, and is consistent with what Azure-based chains disclose publicly.

## Domain terms

| Term | Plain meaning |
| --- | --- |
| **Check** | one customer's bill: a header row plus one row per item on it |
| **Channel** | the way an order arrives: dine-in, drive-thru, online, third-party delivery |
| **Void** | an item taken off a check after it was entered, with a reason and a manager's approval |
| **Payout** | what a delivery platform pays the restaurant for its orders, after commissions, fees and clawbacks |
| **BOM (bill of materials)** | the recipe as data: ingredients and quantities per menu item |
| **Theoretical food cost** | what the ingredients should have cost, from sales × recipes; set against actual purchases, counts and waste |

## Data model

25 tables plus views. Tables marked **shared** are the baseline's [shared tables](../architecture.md#5-shared-tables), which every use case has; the rest belong to this use case.

### Dimensions (13): Silver, rowstore

| # | Table | Grain | Unique key (blocks duplicates) |
| --- | --- | --- | --- |
| 1 | sites (shared) | one location | location_code |
| 2 | source_systems (shared) | one POS / platform / system | system_name |
| 3 | channels | one ordering avenue | channel_name |
| 4 | master_items (shared) | one canonical sellable item **or** ingredient | item_sku |
| 5 | item_aliases (shared) | one source name mapped to a master item | source_system + source_item_id |
| 6 | recipe_bom | one ingredient in one recipe | sellable_item + ingredient_item |
| 7 | suppliers | one vendor | supplier_code |
| 8 | promotions | one promo, with dates and funding source | promo_code |
| 9 | employees | one staff member | payroll_id |
| 10 | void_reasons | one standardized void reason | reason_code |
| 11 | term_mappings (shared) | one local term mapped to its standard meaning | raw_term + site + source_system + field |
| 12 | channel_prices *(temporal)* | one item price per channel, history kept | master_item + channel |
| 13 | contract_prices *(temporal)* | one ingredient cost per supplier, history kept | master_item + supplier |

### Facts (9): Silver, columnstore + monthly partitions on the large ones

| # | Table | Grain | Unique key |
| --- | --- | --- | --- |
| 14 | order_headers | one check | source_system + source_order_id |
| 15 | order_lines | one item on a check (voids flagged here, with reason and manager approval) | source_system + source_line_id |
| 16 | order_discounts | one promo applied to one order line | order_line + promo |
| 17 | payout_reconciliations | one third-party delivery payout (commissions, fees, clawbacks) | source_system + platform_payout_id |
| 18 | labor_shifts | one employee shift, clock-in to clock-out | source_system + source_shift_id |
| 19 | supplier_invoice_headers | one invoice | supplier + invoice_number |
| 20 | supplier_invoice_lines | one line on an invoice | invoice + line_number |
| 21 | stock_counts | one ingredient counted at one site on one date | site + master_item + count_date |
| 22 | waste_logs | one waste event, with reason | source_system + source_waste_id |

### Intake and control (3): shared

| # | Table | Grain | Unique key |
| --- | --- | --- | --- |
| 23 | raw_document_intake | one received file or payload | file fingerprint (SHA-256 hash) |
| 24 | staging_extractions | one record the agent extracted, with confidence | intake + target_table + record_index |
| 25 | agent_action_ledger *(Azure SQL ledger table)* | one agent write action | none — append-only |

### Gold views

- **vw_finance_summary** — net sales, theoretical vs actual food cost, variance, labour %, prime cost
- **vw_food_cost_variance** — theoretical usage (sales × recipe) vs actual (purchases + counts + waste)
- **vw_labor_efficiency** — labour cost and hours against sales

## Roles in this use case

The baseline's [roles](../architecture.md#6-roles-and-access) apply as they are. In restaurant terms:

- A **site manager** runs one restaurant and sees only that site's data.
- A **regional or operations lead** sees the restaurants in their region.
- **Finance** sees the finance views, delivery payouts and supplier invoices.
- **Data science** sees the Silver tables with pay masked.

Search filters every query on `site_id` and on the groups allowed to read each document type in full ([decisions](../architecture.md#8-decisions-and-corrections-log)):

| Document type | Groups allowed to read it in full | Masked fields | Indexed for search |
| --- | --- | --- | --- |
| Supplier invoices (PDFs and photos) | site managers, regional leads, finance, data governance | none | yes |
| Delivery payout statements | finance, data governance | none | yes |
| Waste logs | site managers, regional leads, data governance | none | yes |
| Menus and recipes | site managers, regional leads, finance, data governance | none | yes |
| Labour and payroll exports | none in full | pay, and employees' personal details | never |
| POS sales and stock counts | feeds, not documents: their records go to Silver | none | no text to index |

Analytics and data science work from views and tables, not raw documents, so they aren't allowed groups for any document type.

## Decisions and corrections

| Decision | Reason |
| --- | --- |
| Weekly grain replaced with check / line / shift grain | weekly totals hide who voided what and when, and make theoretical food cost inaccurate |
| Voids are a flag on order_lines, not a separate table | a void happens on a line of a check; a separate table disconnects it from the sale |
| Delivery orders replaced by payout_reconciliations | the sale (food out the door) and the payout (cash in, minus fees) are separate events |
| Added recipe_bom and stock_counts | required to calculate theoretical vs actual food cost |
| Dropped kitchen_sensor_events | no sensor data in scope |
| Unique keys include the source system when the source assigns the ID | two POS systems can issue the same ID. Invoices, invoice lines, discounts and stock counts have no source ID, so they use natural keys (supplier + invoice number, invoice + line number, order line + promo, site + item + count date) |

## Through the pipeline

The same path as any use case ([stack.md](../stack.md#how-data-and-questions-flow)), with restaurant data:

1. A manager uploads a photo of a supplier invoice. Intake checks it and sends it to Document Intelligence, and prompt shields screen the text it reads.
2. The extraction agent proposes invoice lines. "Chkn Brst 40#" becomes the master item "chicken breast" through the item aliases. A name the system doesn't know goes to data governance for approval.
3. Enforcement checks each line: the invoice's lines add up to its total, and the unit price matches the contract price for that supplier and date. A line that fails is rejected with its reason, or held for a person.
4. A site manager asks where food cost went wrong in August. The model asks for the food-cost tool for site 12, August; our Python runs it against `vw_food_cost_variance`, and the database returns only site 12's rows.

The agent's tools here include "food-cost variance for this site and month" and "this supplier's invoices for these dates".

## Seed data

Generates sites, menus, POS sales, supplier invoices (as PDFs and photos), labour and waste, with the mess real data has: inconsistent item names, different POS systems, prices by channel, voids. Everything loads through the same ingestion and enforcement path as real data.

## Open items for this use case

- **Menu item naming normalization:** deep research on how online-ordering platforms clean messy restaurant menu data. Plugs into `item_aliases`.
- **Void rate benchmark:** no normal void rate found yet; needed for realistic seed data.
