# Contribution amounts and values

The shared contribution dialog records the contribution type, description (`gift`),
and numeric pounds amount/value (`amount`, at most two decimal places).

| Type | Amount/value | Description |
| --- | --- | --- |
| Cash | Required, greater than zero | Optional |
| Non-cash | Optional estimated value; zero is allowed | Required |

Blank value means unknown. Gift descriptions are never interpreted as monetary
amounts. Non-cash values are displayed as estimates in internal contribution lists,
history and the contribution board, and are not published on the sponsor wall.

Headliners are the top four confirmed sponsors ranked by cash plus estimated gift
values for the displayed event. Existing alphabetical tie-breaking remains.
Cash indicators, donation email/PDF context, and contribution-board classification
continue to use the cash flag; an estimated gift value does not become cash income.

Migration `0006_contribution_amount` moves valid historical cash amount text into
the numeric field and clears the old amount-only description. Invalid, oversized
or over-precise entries are preserved unchanged for review. Old code writing cash
amount text is supported by `Contributions.monetary_value` until those writers are
updated. The demo sponsor generator now writes numeric cash amounts.
