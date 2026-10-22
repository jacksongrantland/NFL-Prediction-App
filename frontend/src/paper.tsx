import { useEffect, useState } from 'react'
import { post, RequestState, useResource } from './api'

type Game = {
  game_id: string
  home_team_id: string
  away_team_id: string
  forecast_count: number
  kickoff_at: string | null
}
type Version = { id: string; generated_at: string; kind: string }
type Event = {
  id: number
  kind: string
  amount_minor: number
  balance_minor: number
  created_at: string
}
type Entry = {
  id: string
  forecast_id: string
  stake_minor: number
  line: {
    game_id: string
    market: string
    selection: string
    points: string | null
    odds: string
    odds_format: string
  }
  settlement: { outcome: string; evidence_id: string } | null
}
type Account = {
  initialized: boolean
  balance_minor: number
  settled_count: number
  roi: number | null
  net_settled_minor: number
  ledger: Event[]
  entries: Entry[]
}
type Preview = {
  line: { id: string; decimal_odds: string; american_odds_rounded: string }
  estimate: {
    draws: number
    win: number
    push: number
    loss: number
    expected_net_per_credit: number
    win_monte_carlo_95: number[]
    ev_monte_carlo_95: number[]
    limitations: string
  }
}
const credit = (value: number) => `${(value / 100).toFixed(2)} cr`
const percent = (value: number) => `${(value * 100).toFixed(1)}%`
function minor(value: string) {
  if (!/^\d+(\.\d{1,2})?$/.test(value))
    throw new Error('Use positive virtual credits with at most two decimals.')
  const [whole, fraction = ''] = value.split('.')
  const result = Number(whole) * 100 + Number(fraction.padEnd(2, '0'))
  if (!Number.isSafeInteger(result) || result <= 0)
    throw new Error('Enter positive virtual credits.')
  return result
}
export function PaperPanel({ season, week }: { season: number; week: number }) {
  const [identity, setIdentity] = useState('paper')
  const [attempt, setAttempt] = useState(0)
  const account = useResource<Account>(
    `/api/paper/accounts/${encodeURIComponent(identity)}?refresh=${attempt}`,
  )
  const games = useResource<{ items: Game[] }>(`/api/games?season=${season}&week=${week}&limit=100`)
  const [gameId, setGameId] = useState('')
  const active =
    games.data?.items.filter(
      (g) => g.forecast_count && g.kickoff_at && new Date(g.kickoff_at).getTime() > Date.now(),
    ) ?? []
  const selected = active.find((g) => g.game_id === gameId) ?? active[0]
  const versions = useResource<{ items: Version[] }>(
    selected ? `/api/games/${selected.game_id}/versions?limit=20` : null,
  )
  const forecast = versions.data?.items.find((v) => v.kind === 'published_pregame')
  const [market, setMarket] = useState('moneyline')
  const [selection, setSelection] = useState('home')
  const [points, setPoints] = useState('-3.5')
  const [odds, setOdds] = useState('-110')
  const [form, setForm] = useState('american')
  const [stake, setStake] = useState('10.00')
  const [seed, setSeed] = useState('1000.00')
  const [preview, setPreview] = useState<Preview>()
  const [key, setKey] = useState(() => crypto.randomUUID())
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  useEffect(() => {
    setPreview(undefined)
  }, [forecast?.id, market, selection, points, odds, form])
  async function action(work: () => Promise<unknown>, success: string) {
    setBusy(true)
    setMessage('')
    try {
      await work()
      setMessage(success)
      setAttempt((v) => v + 1)
    } catch (error) {
      setMessage((error as Error).message)
    } finally {
      setBusy(false)
    }
  }
  const ledger = account.data?.ledger ?? []
  const values = ledger.map((e) => e.balance_minor / 100)
  const low = Math.min(0, ...values),
    high = Math.max(1, ...values)
  const path = values
    .map(
      (v, i) =>
        `${i ? 'L' : 'M'} ${20 + (i / Math.max(1, values.length - 1)) * 660} ${140 - ((v - low) / (high - low)) * 120}`,
    )
    .join(' ')
  return (
    <section aria-labelledby="paper-title">
      <p className="eyebrow">VIRTUAL CREDITS ONLY</p>
      <h2 id="paper-title">Paper entries. A permanent record.</h2>
      <p className="notice">
        No real money, payments, sportsbook connection or automatic wagering. Lines below are
        manually entered and are not live market data.
      </p>
      <div className="filters">
        <label>
          Virtual account
          <input value={identity} onChange={(e) => setIdentity(e.target.value)} maxLength={64} />
        </label>
        {!account.data?.initialized && (
          <>
            <label>
              Starting virtual credits
              <input inputMode="decimal" value={seed} onChange={(e) => setSeed(e.target.value)} />
            </label>
            <button
              disabled={busy}
              onClick={() =>
                action(
                  () =>
                    post(`/api/paper/accounts/${encodeURIComponent(identity)}`, {
                      credits_minor: minor(seed),
                    }),
                  'Virtual account initialized. No real funds involved.',
                )
              }
            >
              Initialize virtual credits
            </button>
          </>
        )}
      </div>
      <RequestState resource={account} />
      {account.data?.initialized && (
        <>
          <div className="metrics">
            <div>
              <span>Available virtual balance</span>
              <strong>{credit(account.data.balance_minor)}</strong>
            </div>
            <div>
              <span>Settled ROI</span>
              <strong>{account.data.roi === null ? '--' : percent(account.data.roi)}</strong>
            </div>
            <div>
              <span>Settled entry count</span>
              <strong>{account.data.settled_count}</strong>
            </div>
          </div>
          {values.length > 0 && (
            <figure>
              <figcaption>Virtual balance history</figcaption>
              <svg
                viewBox="0 0 710 175"
                role="img"
                aria-label={`Virtual balance history, ${values.length} ledger events, current ${credit(account.data.balance_minor)}`}
              >
                <line x1="20" x2="690" y1="145" y2="145" stroke="#40546b" />
                <path d={path} fill="none" stroke="#b5f36f" strokeWidth="3" />
                <text x="20" y="170">
                  Ledger order
                </text>
                <text x="20" y="15">
                  {high.toFixed(2)} credits
                </text>
              </svg>
            </figure>
          )}
        </>
      )}
      <h3>Enter a manual pregame line</h3>
      <RequestState resource={games} />
      <div className="filters">
        <label>
          Game
          <select
            value={selected?.game_id ?? ''}
            onChange={(e) => {
              setGameId(e.target.value)
              setPreview(undefined)
            }}
          >
            {!active.length && <option>No eligible games</option>}
            {active.map((g) => (
              <option key={g.game_id} value={g.game_id}>
                {g.away_team_id} at {g.home_team_id}
              </option>
            ))}
          </select>
        </label>
        <label>
          Market
          <select
            value={market}
            onChange={(e) => {
              setMarket(e.target.value)
              setSelection(e.target.value === 'total' ? 'over' : 'home')
              setPoints(e.target.value === 'total' ? '44.5' : '-3.5')
            }}
          >
            <option value="moneyline">Moneyline - tie pushes</option>
            <option value="spread">Spread</option>
            <option value="total">Total</option>
          </select>
        </label>
        <label>
          Selection
          <select value={selection} onChange={(e) => setSelection(e.target.value)}>
            {(market === 'total' ? ['over', 'under'] : ['home', 'away']).map((value) => (
              <option key={value} value={value}>
                {value === 'home'
                  ? selected?.home_team_id
                  : value === 'away'
                    ? selected?.away_team_id
                    : value}
              </option>
            ))}
          </select>
        </label>
        {market !== 'moneyline' && (
          <label>
            {market === 'spread' ? 'Points added to selected team' : 'Total line'}
            <input inputMode="decimal" value={points} onChange={(e) => setPoints(e.target.value)} />
          </label>
        )}
        <label>
          Odds format
          <select value={form} onChange={(e) => setForm(e.target.value)}>
            <option value="american">American</option>
            <option value="decimal">Decimal</option>
          </select>
        </label>
        <label>
          Manual odds
          <input value={odds} onChange={(e) => setOdds(e.target.value)} />
        </label>
      </div>
      <button
        disabled={busy || !forecast}
        onClick={() =>
          action(async () => {
            const result = await post<Preview>('/api/paper/lines', {
              forecast_id: forecast!.id,
              market,
              selection,
              points: market === 'moneyline' ? null : points,
              odds,
              odds_format: form,
            })
            setPreview(result)
          }, 'Manual line version recorded. Model estimate is experimental.')
        }
      >
        Preview model estimate
      </button>
      {preview && (
        <>
          <div className="metrics">
            <div>
              <span>Model win / push / loss</span>
              <strong className="compact">
                {percent(preview.estimate.win)} / {percent(preview.estimate.push)} /{' '}
                {percent(preview.estimate.loss)}
              </strong>
            </div>
            <div>
              <span>Expected net per virtual credit</span>
              <strong>{preview.estimate.expected_net_per_credit.toFixed(3)}</strong>
            </div>
            <div>
              <span>Joint draws</span>
              <strong>{preview.estimate.draws}</strong>
            </div>
          </div>
          <p className="small">
            Decimal odds {Number(preview.line.decimal_odds).toFixed(3)} · Rounded American{' '}
            {preview.line.american_odds_rounded}. Win Monte Carlo 95% range{' '}
            {preview.estimate.win_monte_carlo_95.map(percent).join(' - ')}; EV range{' '}
            {preview.estimate.ev_monte_carlo_95.map((v) => v.toFixed(3)).join(' - ')}.{' '}
            {preview.estimate.limitations}
          </p>
          <div className="actions">
            <label>
              Virtual stake (credits)
              <input inputMode="decimal" value={stake} onChange={(e) => setStake(e.target.value)} />
            </label>
            <button
              className="primary"
              disabled={busy || !account.data?.initialized}
              onClick={() =>
                action(async () => {
                  await post(`/api/paper/accounts/${encodeURIComponent(identity)}/entries`, {
                    forecast_id: forecast!.id,
                    line_id: preview.line.id,
                    stake_minor: minor(stake),
                    idempotency_key: key,
                  })
                  setKey(crypto.randomUUID())
                }, 'Virtual entry recorded. Available virtual credits debited.')
              }
            >
              Record virtual entry
            </button>
          </div>
        </>
      )}
      <p className="small">
        Entries close five minutes before kickoff. Any reschedule voids the entry.
        Push/tie/cancellation refunds the stake. Corrections append compensating ledger events; no
        balance is silently rewritten. Payouts round down to whole minor credit units. ROI uses net
        return divided by all settled stakes, including refunded entries.
      </p>
      <p role="status" className="small">
        {busy ? 'Working...' : message}
      </p>
      <h3>Entries and settlement audit</h3>
      {!account.data?.entries.length ? (
        <p className="small">
          No virtual entries yet. There is no invented paper performance history.
        </p>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Game / line</th>
                <th>Virtual stake</th>
                <th>Forecast version</th>
                <th>Status / result evidence</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {account.data.entries.map((entry) => (
                <tr key={entry.id}>
                  <th>
                    {entry.line.game_id}
                    <small>
                      {entry.line.market} {entry.line.selection} {entry.line.points ?? ''} · Manual{' '}
                      {entry.line.odds}
                    </small>
                  </th>
                  <td>{credit(entry.stake_minor)}</td>
                  <td>{entry.forecast_id.slice(0, 10)}</td>
                  <td>
                    {entry.settlement?.outcome ?? 'Pending'}
                    <small>{entry.settlement?.evidence_id.slice(0, 12)}</small>
                  </td>
                  <td>
                    <button
                      disabled={busy}
                      onClick={() =>
                        action(
                          () => post(`/api/paper/entries/${entry.id}/settle`, {}),
                          'Latest eligible actual revision applied to the virtual ledger.',
                        )
                      }
                    >
                      Settle / check correction
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <details>
        <summary>Virtual ledger events</summary>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Event</th>
                <th>Change</th>
                <th>Virtual balance</th>
              </tr>
            </thead>
            <tbody>
              {ledger.map((event) => (
                <tr key={event.id}>
                  <td>{event.kind}</td>
                  <td>{credit(event.amount_minor)}</td>
                  <td>{credit(event.balance_minor)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  )
}
