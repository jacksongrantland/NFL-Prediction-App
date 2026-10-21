import { useState } from 'react'
import { post, RequestState, useResource } from './api'

type Entry = { player_id: string; team_id: string; game_id: string; forecast_id: string; position: string; name: string }
type Roster = { players: Entry[]; slots: Record<string,string[]>; lineup: Record<string,string> }
type Result = { objective: string; risk: string; limitations: string; expected_improvement: number | null; locked_slots: Record<string,string>; recommended: { lineup: Record<string,string>; expected: number; p10: number; p90: number }; current: { expected: number; p10: number; p90: number } | null; comparison: { slot: string; recommended_player: string; previous_player: string | null; expected_points: number; previous_expected_points: number | null; locked: boolean }[] }
const initial: Roster = { players: [], slots: { QB:['QB'], RB1:['RB'], RB2:['RB'], WR1:['WR'], WR2:['WR'], TE:['TE'], FLEX:['RB','WR','TE'] }, lineup:{} }
const points = (value: number | null | undefined) => value === null || value === undefined ? '--' : value.toFixed(2)

export function FantasyPanel({season,week}: {season:number;week:number}) {
  const [identity,setIdentity] = useState(`my-roster-${season}-w${week}`)
  const [roster,setRoster] = useState<Roster>(initial)
  const [search,setSearch] = useState('')
  const [scoring,setScoring] = useState('ppr')
  const [risk,setRisk] = useState('expected')
  const [busy,setBusy] = useState(false)
  const [message,setMessage] = useState('')
  const [result,setResult] = useState<Result>()
  const choices = useResource<{items:Entry[];total:number}>(`/api/fantasy/players?season=${season}&week=${week}&limit=30&search=${encodeURIComponent(search)}`)
  const name = (id: string | null | undefined) => roster.players.find(p=>p.player_id===id)?.name ?? 'Empty slot'
  const change = (next:Roster) => { setRoster(next); setResult(undefined); setMessage('') }
  async function load() {
    setBusy(true); setMessage('')
    try {
      const response = await fetch(`/api/fantasy/rosters/${encodeURIComponent(identity)}`)
      if (!response.ok) throw new Error(response.status===404 ? 'No roster saved under this name yet.' : 'Could not load roster.')
      const record = await response.json() as {roster:Roster}
      change(record.roster); setMessage('Saved roster loaded.')
    } catch(error) { setMessage((error as Error).message) } finally { setBusy(false) }
  }
  async function save(compare=false, next=roster) {
    setBusy(true); setMessage('')
    try {
      await post(`/api/fantasy/rosters/${encodeURIComponent(identity)}`, next)
      setRoster(next)
      if (compare) {
        const computed = await post<Result>('/api/fantasy/compare', {identity,roster:next,scoring:{name:scoring},risk})
        setResult(computed)
      }
      setMessage(compare ? 'Experimental comparison calculated from joint samples.' : 'Roster saved locally.')
    } catch(error) { setMessage((error as Error).message) } finally { setBusy(false) }
  }
  return <section aria-labelledby="fantasy-title"><p className="eyebrow">YOUR ROSTER</p><h2 id="fantasy-title">Fantasy, with the assumptions visible.</h2><p className="notice">Experimental supported offensive points. Player fumbles, two-point bonuses, kicking and defense are excluded. Unknown depth roles can materially change these rankings.</p>
    <div className="filters"><label>Roster name<input value={identity} onChange={e=>setIdentity(e.target.value)} maxLength={64} /></label><button disabled={busy} onClick={load}>Load saved roster</button><button disabled={busy} onClick={()=>{change(initial);setIdentity(`my-roster-${season}-w${week}`)}}>Start new weekly roster</button><label>Scoring<select value={scoring} onChange={e=>{setScoring(e.target.value);setResult(undefined)}}><option value="standard">Standard offensive subtotal</option><option value="half_ppr">Half-PPR offensive subtotal</option><option value="ppr">PPR offensive subtotal</option></select></label><label>Risk preference<select value={risk} onChange={e=>{setRisk(e.target.value);setResult(undefined)}}><option value="expected">Expected points</option><option value="floor">Floor: mean minus 0.25 SD</option><option value="upside">Upside: mean plus 0.25 SD</option></select></label></div>
    <p className="small">Manually add your players from eligible pregame forecasts for season {season}, week {week}. No league account connection. Individual kickoff locks preserve started lineup slots and keep started bench players out.</p>
    <label>Find a player<input type="search" placeholder="Name, team or position" value={search} onChange={e=>setSearch(e.target.value)} /></label><RequestState resource={choices}/>
    <div className="roster-picker">{choices.data?.items.filter(p=>!roster.players.some(r=>r.player_id===p.player_id)).map(player=><button key={player.player_id} onClick={()=>change({...roster,players:[...roster.players.map(p=>p.game_id===player.game_id ? {...p,forecast_id:player.forecast_id}:p),player]})}>{player.name} <span className="small">{player.team_id} · {player.position}</span> +</button>)}</div>
    {choices.data?.total===0 && <p className="small">No eligible player forecasts match. Refresh sources or choose another week; unsupported players are never invented.</p>}
    <h3>Selected players ({roster.players.length})</h3>
    {!roster.players.length && <p className="small">Your roster is empty. Add players above, then compare a complete lineup.</p>}
    <div className="roster-picker">{roster.players.map(player=><button key={player.player_id} aria-label={`Remove ${player.name}`} onClick={()=>change({...roster,players:roster.players.filter(p=>p.player_id!==player.player_id),lineup:Object.fromEntries(Object.entries(roster.lineup).filter(([,p])=>p!==player.player_id))})}>{player.name} · {player.position} ×</button>)}</div>
    <div className="lineup-slots">{Object.entries(roster.slots).map(([slot,positions])=><label key={slot}>{slot}<select value={roster.lineup[slot]??''} onChange={e=>{const lineup={...roster.lineup};if(e.target.value)lineup[slot]=e.target.value;else delete lineup[slot];change({...roster,lineup})}}><option value="">Empty slot</option>{roster.players.filter(p=>positions.includes(p.position)).map(p=><option key={p.player_id} value={p.player_id}>{p.name}</option>)}</select></label>)}</div>
    <div className="actions"><button disabled={busy} onClick={()=>save()}>Save roster locally</button><button className="primary" disabled={busy||!roster.players.length} onClick={()=>save(true)}>{busy?'Working...':'Compare lineups'}</button></div><p role="status" className="small">{message}</p>
    {result && <><h3>{result.objective}</h3><div className="metrics"><div><span>Suggested expected subtotal</span><strong>{points(result.recommended.expected)}</strong></div><div><span>80% sample interval</span><strong>{points(result.recommended.p10)} - {points(result.recommended.p90)}</strong></div><div><span>Expected change vs current</span><strong>{points(result.expected_improvement)}</strong></div></div><p className="small">{result.current ? `Current lineup: ${points(result.current.expected)} expected points, interval ${points(result.current.p10)}-${points(result.current.p90)}.` : 'Fill the current lineup to obtain a numerical alternative comparison.'} Intervals use the same joint draws within each game; risk preferences use the explicitly displayed per-player objective.</p><div className="table-scroll"><table><caption>Numerical lineup comparison</caption><thead><tr><th>Slot</th><th>Suggested player</th><th>Expected</th><th>Current player</th><th>Expected</th><th>Kickoff lock</th></tr></thead><tbody>{result.comparison.map(row=><tr key={row.slot}><th>{row.slot}</th><td>{name(row.recommended_player)}</td><td>{points(row.expected_points)}</td><td>{name(row.previous_player)}</td><td>{points(row.previous_expected_points)}</td><td>{row.locked?'Locked':'Pregame'}</td></tr>)}</tbody></table></div><p className="small">{result.limitations}</p><button onClick={()=>save(false,{...roster,lineup:result.recommended.lineup})} disabled={busy}>Use suggested lineup</button></>}
  </section>
}
