import { useState } from 'react'
import './style.css'
import { useResource, RequestState } from './api'
import { FantasyPanel } from './fantasy'
import { PaperPanel } from './paper'

type Distribution = { mean: number; p10: number; p90: number }
type Game = { game_id: string; season: number; week: number; home_team_id: string; away_team_id: string; kickoff_at: string | null; home_score: number | null; away_score: number | null; result_status: string; forecast_count: number; lock_status: string }
type Page<T> = { items: T[]; total: number; offset: number; limit: number }
type Player = { player_id: string; name: string; position: string | null; team_id: string; offense_participation_probability: number; availability_unknown: boolean; role_unknown: boolean; stats: Record<string, Distribution>; active_conditional: Record<string, Distribution | null> }
type Summary = { home_expected: number; away_expected: number; home_win: number; tie: number; home_p10_p90: number[]; away_p10_p90: number[]; recommended_for_decisions: boolean }
type Version = { id: string; kind: string; generated_at: string; cutoff: string; model_versions: Record<string, string>; input_freshness: Record<string, string>; summary: Summary }
type Revision = { id: string; status: string; recorded_at: string; actual: { home_score: number; away_score: number } }
type Audit = { versions: Version[]; official_forecast_id: string | null; actuals: Revision[]; errors: { forecast_id: string; result_revision_id: string; home_error: number; away_error: number }[] }
type Freshness = { last_refresh: { finished_at: string; elapsed_seconds: number } | null; observations: { kind: string; recorded_at: string }[] }
type Evaluation = { records: { games?: { final_test: { accuracy: number; log_loss: number; margin_mae: number; n: number } }; simulation?: { evaluation: { n: number; brier: number; score_80_interval_coverage: number; reliability: { predicted: number; observed: number; n: number }[] } } }; published_history: { official_locked_forecasts: number } }
const TEAMS = ['ARI','ATL','BAL','BUF','CAR','CHI','CIN','CLE','DAL','DEN','DET','GB','HOU','IND','JAX','KC','LAC','LAR','LV','MIA','MIN','NE','NO','NYG','NYJ','PHI','PIT','SEA','SF','TB','TEN','WAS']
const fmt = (value: number | undefined) => value === undefined ? '--' : value.toFixed(1)
const isStale = (value: string) => Date.now() - new Date(value).getTime() > 36 * 3600000
const pct = (value: number | undefined) => value === undefined ? '--' : `${(value * 100).toFixed(1)}%`
const date = (value: string | null) => value ? new Intl.DateTimeFormat('en-US', { timeZone: 'America/Chicago', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' }).format(new Date(value)) : 'Kickoff TBD'

function ScoreChart({ version, actual, game }: { version: Version; actual?: Revision; game: Game }) {
  const scores = [version.summary.home_expected, version.summary.away_expected]
  const observed = actual && actual.status !== 'cancelled' ? [actual.actual.home_score, actual.actual.away_score] : null
  const scale = Math.max(40, ...scores, ...(observed ?? []))
  return <figure><figcaption>Expected score and actual result</figcaption>
    <svg role="img" aria-label={`Expected scores: ${game.home_team_id} ${fmt(scores[0])}, ${game.away_team_id} ${fmt(scores[1])}. ${observed ? `Actual ${observed.join(' to ')}.` : 'No actual result yet.'}`} viewBox="0 0 500 116">
      {[game.home_team_id, game.away_team_id].map((team, i) => <g key={team} transform={`translate(0 ${i * 56})`}>
        <text x="0" y="21">{team}</text><rect x="52" y="5" width={scores[i] / scale * 330} height="17" rx="4" fill="#7bb9ff" />
        <text x={60 + scores[i] / scale * 330} y="20">{fmt(scores[i])}</text>
        {observed && <><rect x="52" y="27" width={observed[i] / scale * 330} height="11" rx="3" fill="#7de0b2" /><text x={60 + observed[i] / scale * 330} y="38">{observed[i]}</text></>}
      </g>)}
    </svg><p className="small">Blue: expected score. Green: latest actual revision. Means reconcile within joint draws; marginal medians do not add to team totals.</p></figure>
}
function GameDetail({ game }: { game: Game }) {
  const detail = useResource<Audit>(`/api/games/${game.game_id}`)
  const [chosen, setChosen] = useState('')
  const [conditional, setConditional] = useState(false)
  const [position, setPosition] = useState('')
  const [offset, setOffset] = useState(0)
  const audit = detail.data
  const version = audit?.versions.find(v => v.id === chosen) ?? audit?.versions.find(v => v.id === audit.official_forecast_id) ?? audit?.versions[0]
  const projections = useResource<Page<Player>>(version ? `/api/forecasts/${version.id}/players?limit=20&offset=${offset}${position ? `&position=${position}` : ''}` : null)
  const actual = audit?.actuals[0]
  return <section className="detail" aria-labelledby="detail-title">
    <div className="section-heading"><div><p className="eyebrow">GAME DETAIL</p><h2 id="detail-title">{game.away_team_id} at {game.home_team_id}</h2><p className="small">{date(game.kickoff_at)} · Week {game.week}</p></div><span className="tag">{game.lock_status.replaceAll('_', ' ')}</span></div>
    <RequestState resource={detail} />
    {audit && !version && <div className="empty"><h3>No eligible forecast saved</h3><p>This game has no saved prediction. Past games are never filled with a late forecast.</p>{actual && actual.status !== 'cancelled' && <p>Actual: {game.away_team_id} {actual.actual.away_score} - {game.home_team_id} {actual.actual.home_score} ({actual.status})</p>}</div>}
    {version && <>
      <p className="notice">{isStale(version.cutoff) ? "Stale inputs - refresh required. " : ""}Experimental baseline · Unknown depth roles and availability · Prospective accuracy unproven</p>
      <div className="metrics"><div><span>Home win</span><strong>{pct(version.summary.home_win)}</strong></div><div><span>Tie</span><strong>{pct(version.summary.tie)}</strong></div><div><span>Home score 80% interval</span><strong>{version.summary.home_p10_p90.join(' - ')}</strong></div></div>
      <ScoreChart version={version} actual={actual} game={game} />
      <div className="audit-meta"><p>Generated {date(version.generated_at)} · Input cutoff {date(version.cutoff)}</p><p>Schedule: {version.input_freshness.schedule_freshness ?? 'unknown'} · Roster: {version.input_freshness.roster_freshness ?? 'unknown'} · Injury source: {version.input_freshness.injury_source_status ?? 'unknown'}</p><p>Availability can remain unknown even when the injury source was observed. No arbitrary questionable-player penalty is applied.</p></div>
      <details><summary>Forecast versions and model audit</summary><label>Saved version<select value={version.id} onChange={e => { setChosen(e.target.value); setOffset(0) }}>{audit?.versions.map(v => <option key={v.id} value={v.id}>{date(v.generated_at)} · {v.id.slice(0, 8)} {v.id === audit.official_forecast_id ? '(official locked)' : ''}</option>)}</select></label><p className="small">{version.kind.replaceAll('_', ' ')} · Version {version.id}</p>{Object.entries(version.model_versions).map(([key,value]) => <p className="small break" key={key}>{key}: {value}</p>)}</details>
      <div className="section-heading"><h3>Player projections</h3><label>Position<select value={position} onChange={e => { setPosition(e.target.value); setOffset(0) }}><option value="">All positions</option>{['QB','RB','WR','TE'].map(p => <option key={p}>{p}</option>)}</select></label></div>
      <label className="toggle"><input type="checkbox" checked={conditional} onChange={e => setConditional(e.target.checked)} /> Show active-on-offense conditional statistics</label>
      <p className="small">{conditional ? 'Conditional: among draws where this player participated on offense.' : 'Unconditional: includes sampled nonparticipation zeros.'} Brackets show the 10th-90th percentile, a nominal 80% interval. Coverage is not guaranteed; see validation below.</p>
      <RequestState resource={projections} />
      {projections.data && <><div className="table-scroll"><table><caption className="sr-only">Player expected statistics and 80 percent intervals</caption><thead><tr><th>Player</th><th>Team</th><th>Availability / role</th><th>Offense participation</th><th>Pass yards</th><th>Rush yards</th><th>Receive yards</th><th>Receptions</th></tr></thead><tbody>{projections.data.items.map(player => {
        const stats = conditional ? player.active_conditional : player.stats
        const cell = (stat: string) => stats[stat] ? <>{fmt(stats[stat]!.mean)} <span className="interval">[{fmt(stats[stat]!.p10)}, {fmt(stats[stat]!.p90)}]</span></> : 'Unsupported'
        return <tr key={`${player.team_id}-${player.player_id}`}><th scope="row">{player.name}<small>{player.position ?? 'Aggregate'} · {player.player_id === 'other' ? 'Omitted roles' : player.player_id}</small></th><td>{player.team_id}</td><td>{player.availability_unknown ? "Availability unknown" : "Observed status"}<small>{player.role_unknown ? "Depth role unverified" : "Observed role"}</small></td><td>{pct(player.offense_participation_probability)}</td><td>{cell('passing_yards')}</td><td>{cell('rushing_yards')}</td><td>{cell('receiving_yards')}</td><td>{cell('receptions')}</td></tr>
      })}</tbody></table></div>{!projections.data.total && <p>No supported players match this filter.</p>}<Pagination offset={offset} total={projections.data.total} size={20} onChange={setOffset} /></>}
      <p className="small">Individual fumbles, kicking, defense/special teams, other positions and preseason are unsupported. Omitted offensive roles remain in the other-player bucket.</p>
      <h3>Prediction versus actual history</h3>
      {audit?.errors.length ? <div className="table-scroll"><table><thead><tr><th>Actual revision</th><th>Status</th><th>Home error</th><th>Away error</th></tr></thead><tbody>{audit.errors.map(e => <tr key={e.result_revision_id}><td>{e.result_revision_id.slice(0, 10)}</td><td>{audit.actuals.find(a => a.id === e.result_revision_id)?.status}</td><td>{fmt(e.home_error)}</td><td>{fmt(e.away_error)}</td></tr>)}</tbody></table></div> : <p className="small">No scored official pregame forecast yet. Saved upcoming forecasts are not historical performance.</p>}
    </>}
  </section>
}
function Pagination({ offset, total, size, onChange }: { offset: number; total: number; size: number; onChange: (v: number) => void }) {
  return <nav className="pagination" aria-label="Pagination"><span>{total ? offset + 1 : 0}-{Math.min(offset + size, total)} of {total}</span><button disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - size))}>Previous</button><button disabled={offset + size >= total} onClick={() => onChange(offset + size)}>Next</button></nav>
}
function EvaluationPanel() {
  const resource = useResource<Evaluation>('/api/evaluation')
  const game = resource.data?.records.games?.final_test
  const simulation = resource.data?.records.simulation?.evaluation
  return <section><p className="eyebrow">MEASURED PERFORMANCE</p><h2>Backtests, separate from pregame history</h2><RequestState resource={resource} />
    {game && <><p className="small">2025 approximate historical game-model holdout · {game.n} games · October 15, 2026</p><div className="metrics"><div><span>Three-way win accuracy</span><strong>{pct(game.accuracy)}</strong></div><div><span>Log loss</span><strong>{game.log_loss.toFixed(3)}</strong></div><div><span>Margin MAE</span><strong>{fmt(game.margin_mae)} pts</strong></div></div></>}
    {simulation && <><h3>Joint simulation check</h3><p className="small">2024 week 1 · {simulation.n} games · 500 draws/game · Selected validation coverage, not a season-long calibration claim.</p><div className="metrics"><div><span>Three-outcome Brier</span><strong>{simulation.brier.toFixed(3)}</strong></div><div><span>Nominal 80% score coverage</span><strong>{pct(simulation.score_80_interval_coverage)}</strong></div><div><span>Official locked forecasts</span><strong>{resource.data?.published_history.official_locked_forecasts ?? 0}</strong></div></div><div className="table-scroll"><table><caption>Home win calibration on this small validation week</caption><thead><tr><th>Mean probability</th><th>Observed home wins</th><th>Games</th></tr></thead><tbody>{simulation.reliability.map((b,i) => <tr key={i}><td>{pct(b.predicted)}</td><td>{pct(b.observed)}</td><td>{b.n}</td></tr>)}</tbody></table></div></>}
    <p className="small">Corrected historical data lacks original publication histories. Player participation coverage is incomplete. The simpler player baseline was retained because alternatives did not improve earlier validation. These results do not establish a betting advantage.</p>
  </section>
}
export default function App() {
  const [season, setSeason] = useState(2026)
  const [week, setWeek] = useState('7')
  const [team, setTeam] = useState('')
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState<Game>()
  const schedule = useResource<Page<Game>>(`/api/games?season=${season}&limit=28&offset=${offset}${week ? `&week=${week}` : ''}${team ? `&team=${team}` : ''}`)
  const health = useResource<{status: string}>('/api/health')
  const freshness = useResource<Freshness>('/api/freshness')
  const changeFilter = (action: () => void) => { action(); setOffset(0); setSelected(undefined) }
  const current = selected ?? schedule.data?.items[0]
  return <main>
    <header><div className="brand"><span className="brand-mark" aria-hidden="true">N</span><span>NFL / FIELD NOTES</span></div><span className={`connection ${health.data ? 'online' : ''}`}>{health.data ? 'Local API connected' : health.error ? 'API unavailable' : 'Connecting...'}</span></header>
    <div className="hero"><p className="eyebrow">YOUR LOCAL NFL WORKSPACE</p><h1>Game day,<br/><em>with the uncertainty.</em></h1><p>League-wide forecasts, player workload and an honest record of what the model knew before kickoff.</p><span className="tag">Free data · Local CPU · Experimental forecasts</span></div>
    <div className="freshness"><span className="dot" /><span>{freshness.data?.last_refresh ? `${isStale(freshness.data.last_refresh.finished_at) ? "Stale - " : ""}Last refresh ${date(freshness.data.last_refresh.finished_at)} · ${fmt(freshness.data.last_refresh.elapsed_seconds)}s` : 'No completed refresh recorded yet'}</span><span>All times America/Chicago</span></div>
    <section aria-labelledby="schedule-title"><div className="section-heading"><div><p className="eyebrow">THE SCHEDULE</p><h2 id="schedule-title">Every matchup. One view.</h2></div><button onClick={() => changeFilter(() => setTeam(team === 'DAL' ? '' : 'DAL'))} aria-pressed={team === 'DAL'}>Cowboys {team === 'DAL' ? 'selected' : 'quick filter'}</button></div>
      <div className="filters"><label>Season<select value={season} onChange={e => changeFilter(() => setSeason(Number(e.target.value)))}>{[2026,2025,2024,2023,2022,2021,2020].map(s => <option key={s}>{s}</option>)}</select></label><label>Week<select value={week} onChange={e => changeFilter(() => setWeek(e.target.value))}><option value="">All weeks</option>{Array.from({length:22}, (_,i) => i+1).map(w => <option key={w} value={w}>Week {w}</option>)}</select></label><label>Team<select value={team} onChange={e => changeFilter(() => setTeam(e.target.value))}><option value="">Full league</option>{TEAMS.map(t => <option key={t}>{t}</option>)}</select></label></div>
      <RequestState resource={schedule} />
      {schedule.data && <><div className="game-grid">{schedule.data.items.map(game => <button key={game.game_id} className={`game-card ${current?.game_id === game.game_id ? 'selected' : ''}`} onClick={() => setSelected(game)} aria-pressed={current?.game_id === game.game_id}><span className="small">{date(game.kickoff_at)}</span><span className="matchup"><b>{game.away_team_id}</b><span>at</span><b>{game.home_team_id}</b></span><span className="small">{game.result_status === 'final' ? `Final ${game.away_score} - ${game.home_score}` : game.forecast_count ? `${game.forecast_count} saved forecast version${game.forecast_count === 1 ? '' : 's'}` : 'Forecast unavailable'}</span></button>)}</div>{!schedule.data.total && <div className="empty"><h3>No games in this view</h3><p>Try another week or team. Data is never replaced with synthetic history.</p></div>}<Pagination offset={offset} total={schedule.data.total} size={28} onChange={v => { setOffset(v); setSelected(undefined) }} /></>}
    </section>
    {current && <GameDetail key={current.game_id} game={current} />}
    <FantasyPanel season={season} week={Number(week) || 7} />
    <PaperPanel season={season} week={Number(week) || 7} />
    <EvaluationPanel />
    <footer>Local research workspace · No real-money wagering · Unknown is never treated as healthy or as a known zero.</footer>
  </main>
}
