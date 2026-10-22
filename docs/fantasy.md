# Fantasy scoring and manual lineup comparison

The dashboard's roster section accepts manual player selection from eligible
published pregame forecasts. Use a separate roster name for each season/week.
Save/load locally, choose standard/half-PPR/PPR, set a current lineup and compare.
"Use suggested lineup" explicitly saves the suggested assignment. There are no
league logins, external integrations or LLM-generated explanations.

The versioned `offensive-fantasy/1` rules score joint, unrounded player draws:
passing yards 0.04, passing TD 4, interception -2, rushing/receiving yards 0.1,
rushing/receiving TD 6 and receptions 0/0.5/1 by preset. Coefficients are configurable
through the typed local comparison API; unknown fields/nonfinite coefficients are
rejected. These are **supported offensive subtotals**: individual lost fumbles,
two-point bonuses, kicking and defense are excluded because those player targets
are not evaluated/supported. They are not advertised as complete league scores.

One draw index is shared among roster players from the same game/forecast. Different
games use their independent game draws. A single game cannot mix forecast versions;
the common draw count is used without rounding. Lineup means/intervals come from
summing those samples, not adding marginal percentiles.

An exact dynamic program assigns QB/RB/WR/TE/FLEX-compatible slots without duplicate
players. Expected mode maximizes expected supported points. Floor/upside modes
maximize the sum of each player's mean minus/plus 0.25 SD; this is an explicitly
specified per-player preference, not a claim to optimize lineup tail risk. Joint
lineup uncertainty is still reported separately. Numerical per-slot comparisons
show expected points for the current and suggested alternatives.

Each saved roster keeps versioned local history. Started lineup slots cannot move;
started bench players cannot enter; started player game/team/position cannot be
rebound; new started players cannot be added. Slot definitions cannot change once
a roster game starts. After kickoff, samples must come from the immutable official
eligible forecast. A missing official forecast remains unsupported and can block a
complete comparison; no retrospective forecast or zero fantasy total is substituted.
Rescheduled games require an eligible forecast for the revised kickoff. Unknown
availability and unresolved roles are displayed and can materially affect rankings.
The result remains experimental, `recommended_for_decisions=false`.

API: GET /api/fantasy/players, GET/POST /api/fantasy/rosters/{name}, and POST
/api/fantasy/compare. JSON writes require loopback client/Host, a trusted local
origin (or explicit local client), X-NFL-Local: 1 and a bounded JSON body. No CORS
permission is granted to remote sites. HTTP writes never trigger training/downloads.

October 21 verification: synthetic tests check negative/fractional scoring, all
presets, duplicate/eligibility failures, a greedy FLEX trap, risk preference and
started-slot/bench/identity locks. A transient explicitly labeled 11-player real
forecast verification roster improved supported expected points from 36.0886 to
44.6866 with the exact assignment; this is not the user's roster or evidence of
real fantasy performance. See fantasy_verification_2026-10-21.json. Browser testing
saved/loaded the explicitly named `verification-oct21` roster, calculated 56.91
expected supported points and interval 34.18-83.54, applied its lineup, then displayed
0.00 change against that saved identical alternative. No live league was changed.

The final local boundary also rejects untrusted Host headers on read requests to
prevent host rebinding. Comparisons must use the saved roster representation; a
POST cannot bypass saved kickoff locks by supplying an unsaved alternative body.
