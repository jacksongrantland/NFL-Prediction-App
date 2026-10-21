# Paper entries and virtual credit ledger

This feature uses virtual credits only. It has no payment, real-money account,
sportsbook connection, live odds feed or automatic wagering path. Initialize an
explicitly named local virtual account; 100 integer minor units equal one credit.
Manual line versions record writer-assigned entry time, exact forecast/game/kickoff,
market, selection, point line, typed odds and decimal conversion. They are never
labeled live market data. Source line/forecast history is immutable.

Moneyline is two-way with tied final scores refunded. Spread points are added to
the selected home/away team's score. Total over/under uses the final combined score.
Only integer/half-point lines are supported; quarter/Asian split markets are not.
American odds accept integer >=+100 or <=-100; decimal odds range 1.01-1000.
Conversions and payouts use Decimal; fractional minor-unit payouts round down.
Model EV is a pre-rounding estimate per virtual credit, not a guarantee of payout.

Line/entry cutoff is five minutes before the recorded kickoff, or an earlier
existing official lock. Late, backdated/retrospective, unknown and mismatched line/
forecast/kickoff inputs are rejected. A line version is tied to its exact immutable
forecast. Every stake atomically debits available integer credits; an idempotency
key rejects duplicate submission. Concurrent writes serialize before balance checks.

Win/push/loss and expected net value use the referenced joint game samples. Wilson
win intervals and EV standard-error intervals quantify Monte Carlo sampling only;
they do not quantify the much larger model/role/calibration uncertainty. The
experimental model is not advertised as a wagering advantage. Hypothetical manual
odds are kept separate from any claim about actual available market prices.

Settlement uses the newest versioned settled actual. Provisional results do not
settle. Ties/pushes and cancellation refund the stake. Any recorded kickoff change
after entry voids and refunds it, even if play later resumes. This conservative
postponement policy is permanent for that entry; a new pregame line/entry is needed
for the revised game. Before a changed/cancelled game starts, only void settlement
is possible. Regular win/loss settlement cannot occur before its original kickoff.

Each actual correction appends a settlement revision and compensating ledger event
for the difference in effective return. Earlier entries and balances never mutate.
Duplicate settlement for the same evidence is rejected. A correction can make the
virtual balance negative if prior virtual payouts were already spent; that debt is
shown and new stakes are blocked until available credits cover them. It is not
silently capped or written away. Refunds/returns add no second stake debit.

The dashboard shows manual lines/model estimates, entries with forecast/evidence
IDs, available balance, ordered bankroll chart, append-only events, settled count
and ROI. ROI is net settled return divided by all settled stakes, including refunded
entries; pending debits are excluded from ROI and remain reflected in availability.
Local refresh maintenance can settle/correct existing paper entries, but never
creates a wager. Manual "Settle / check correction" uses the same revision policy.

API: GET/POST /api/paper/accounts/{id}, POST /api/paper/lines,
POST /api/paper/accounts/{id}/entries and POST /api/paper/entries/{id}/settle.
All writes use the loopback client/Host/origin, local-header and JSON-size boundary.
SQLite migration 0004 adds immutable accounts, lines, entries, settlements and ledger.

October 21 verification: five synthetic tests cover conversions, exact rounding,
pushes/ties, stake conservation, overspending, duplicate entries/settlement,
provisional/late rejection, cancellation/reschedule refunds, mutation rejection,
corrected losses and negative correction debt. Browser testing used only the
explicitly named verification-oct21 account: 1,000 virtual credits, 10-credit pending
entry at a hypothetical manually typed -110 line, 990 credits available and no
settled ROI. The default paper account was not initialized. No money was spent.
See paper_verification_2026-10-21.json. No synthetic result was inserted into real
forecast history to make the pending verification entry appear profitable.
