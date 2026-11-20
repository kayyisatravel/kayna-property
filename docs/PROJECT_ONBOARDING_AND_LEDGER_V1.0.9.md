# Project Onboarding & Financial Ledger — PFMS V1.0.9

## Purpose

V1.0.9 adds a separate route for registering a property already acquired, including projects acquired before PFMS was adopted. It does not rerun historical auction underwriting. The project is registered with lifecycle `ACTIVE` and decision status `INCOMPLETE` unless an existing decision status is being preserved; the payload records `project_origin=PROJECT_ONBOARDING`.

## Project onboarding workflow

The user enters property identity, winning/acquisition price and date, current project stage, current condition notes, paid historical transactions, and planned/committed/forecast cost lines.

- Existing prospect with the same lot code can be merged into the existing property record. Existing `latest_analysis` and history are preserved.
- A property already in `WON`, `ACTIVE`, or `SOLD` is not onboarded a second time; use Active Properties instead.
- The price won is descriptive acquisition data. The paid acquisition transaction must be entered in the opening transactions table to be included in actual cash-out. If the deposit is part of the winning price, enter total purchase cost once or split deposit + balance so the sum equals winning price.

## Financial definitions

- `COST_ACTUALS`: payments actually made, not budget and not unpaid obligations.
- `PROJECT_BUDGETS.budget_amount`: total budget for a work item/category.
- `PROJECT_BUDGETS.committed_unpaid`: outstanding amount already agreed/committed but not yet paid.
- `PROJECT_BUDGETS.forecast_remaining`: uncommitted forecast for work/cost still expected.
- `Risk Reserve`: remains separate from actual, committed, and forecast amounts.

`budget_item_id` links paid transactions to budget lines. During opening, PFMS attempts an exact/unique category-subcategory link; ambiguous transactions remain unlinked and are shown as such. In Active Properties, the user may link new payments to a budget line. They choose whether the payment reduces the outstanding commitment, forecast, or is an outside-budget cost. When linked, the corresponding unpaid balance is reduced by the paid amount.

The active project cash position automatically includes `committed_unpaid` amounts from active property budget lines. Do not enter the same commitment again as a manual Cashflow Event. Uncommitted forecast does not automatically reduce cash available.

## Google Sheets compatibility

A new `PROJECT_BUDGETS` worksheet is added. Five trailing fields are appended to `COST_ACTUALS`: `budget_item_id`, `subcategory`, `vendor`, `payment_method`, and `details_json`.

The Google Sheets adapter supports additive trailing-column migration. Existing columns and values are not renamed or reordered. Existing worksheets should gain the new trailing headers when V1.0.9 first connects; the updated XLSX template also includes the new tab/columns.

## Limitations

V1.0.9 does not automatically read bank transactions, receipts, or invoices. The user remains responsible for entering actual cash payments accurately. An actual payment linked to a budget line is assumed to reduce the selected outstanding bucket; select the correct source to avoid misclassification.
