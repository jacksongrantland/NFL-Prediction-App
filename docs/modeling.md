# Modeling and feature policy

Feature configuration is versioned in `config/features.json`. Team scoring and
conceding strength use the last 16 eligible games, exponential half-life five
games, shrunk with four equivalent games toward the prior league mean. Player
workload/production use the same scheme and prior position means. With no prior
data at all, team points default to 21 and player counts/yardage to zero; these
are explicit cold-start defaults, not invented career observations. Prior seasons
remain useful. Rest is measured from the last eligible game (default seven days,
capped at 60 across offseasons). Home/away and opponent strength are explicit.

Every season/week shares its earliest scheduled kickoff as its feature cutoff.
Only independently final-reconciled games with kickoff plus a conservative
12-hour delay before that cutoff can contribute. The sources lack observed game
end times: this eligibility is **approximate**, not a guarantee for an unusually
long suspension/resumption. Corrected historical publication timing is also
unknown. Zero historical rows qualify as strict original-version observations.
Week-level freezing deliberately forgoes Thursday outcomes for Sunday features.

Player candidates come from the game's historical weekly roster/team/position,
never today's team and never selected by that game's box score. Weekly rosters
are corrected historical observations and remain approximate; they do not establish
verified active participation. Rookie/sparse players shrink to prior position
means. Trades preserve historical workload and expose prior_team_id separately.
Role uncertainty stays explicit. Injury observations require local observation
and recording by cutoff, without inferred playing probabilities. Missing inputs
remain unknown. Historical roster status is context, not an inactive flag.

All outputs carry source snapshot IDs, configuration, feature-code hash and
artifact checksums. Source/feature changes yield a new artifact. Existing identical
artifacts are checksum-verified before reuse. Artifacts remain ignored by Git.
