export type TrackAction = "suggestion_click" | "final_search";

export interface TrackSearchParams {
  prefix: string;
  selected: string;
  action: TrackAction;
}

export interface TrackSearchDeps {
  baseUrl: string;
  fetchImpl?: typeof fetch;
}

export async function trackSearch(deps: TrackSearchDeps, params: TrackSearchParams): Promise<void> {
  const fetchImpl = deps.fetchImpl ?? fetch;
  const response = await fetchImpl(`${deps.baseUrl}/track`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });

  if (!response.ok) {
    throw new Error(`trackSearch failed with status ${response.status}`);
  }
}
