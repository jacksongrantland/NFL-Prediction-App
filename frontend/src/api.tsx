import { useEffect, useState } from 'react'

export function useResource<T>(path: string | null) {
  const [data, setData] = useState<T>()
  const [error, setError] = useState(false)
  const [loading, setLoading] = useState(false)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    setData(undefined)
    setError(false)
    if (!path) {
      setLoading(false)
      return
    }
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 10000)
    let disposed = false
    setLoading(true)
    fetch(path, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`Request failed: ${response.status}`)
        return response.json() as Promise<T>
      })
      .then((value) => {
        if (!disposed) setData(value)
      })
      .catch(() => {
        if (!disposed) setError(true)
      })
      .finally(() => {
        clearTimeout(timeout)
        if (!disposed) setLoading(false)
      })
    return () => {
      disposed = true
      clearTimeout(timeout)
      controller.abort()
    }
  }, [path, retry])
  return { data, error, loading, retry: () => setRetry((v) => v + 1) }
}
export function RequestState({
  resource,
}: {
  resource: { loading: boolean; error: boolean; retry: () => void }
}) {
  return (
    <>
      {resource.loading && <p role="status">Loading local data...</p>}
      {resource.error && (
        <div role="alert">
          <p>Could not load data. Check the local backend connection.</p>
          <button onClick={resource.retry}>Retry</button>
        </div>
      )}
    </>
  )
}

export async function post<T>(path: string, value: unknown): Promise<T> {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-NFL-Local': '1' },
    body: JSON.stringify(value),
  })
  const body = await response.json()
  if (!response.ok)
    throw new Error(
      typeof body.detail === 'string' ? body.detail : 'Check the entered values and try again.',
    )
  return body as T
}
