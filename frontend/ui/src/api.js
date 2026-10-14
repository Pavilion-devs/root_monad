export async function api(path, body) {
  const response = await fetch(`/api/${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    credentials: 'same-origin',
    headers: body === undefined ? {} : {'Content-Type': 'application/json'},
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: 'no-store',
  });
  let result;
  try { result = await response.json(); } catch { throw new Error('COMPANION_REQUIRED'); }
  if (!response.ok) throw Object.assign(new Error(result.code || 'SERVICE_UNAVAILABLE'), {status: response.status});
  return result;
}

export const messages = {
  CONNECT_REQUIRED: 'Connect this browser using the private link from your local companion.',
  COMPANION_REQUIRED: 'Start the local companion to connect this workspace. The frontend preview alone cannot access your memory.',
  PAIRING_EXPIRED: 'This connection link has expired or was already used. Restart the local companion for a new link.',
  AUTHORITY_UNAVAILABLE: 'We cannot verify the latest revision right now. Your memory has not been shown as current. Try again shortly.',
  CONTENT_UNAVAILABLE: 'Some memory content is unavailable. We could not verify a complete workspace.',
  BASE_CONFLICT: 'Your project changed while this view was open. Refresh and review the current version.',
  REVIEW_EXPIRED: 'This review expired. For an unsigned change, close it and review again. If you already confirmed, check the pending change first.',
  RESUME_REQUIRED: 'A previously confirmed change needs to be checked before another change can begin.',
  CONFIRMATION_MISMATCH: 'This review no longer matches the saved change. Close it and prepare a fresh review.',
  COMMIT_PENDING: 'Your change was submitted, but acceptance is not verified yet. Check the pending change before trying again.',
  OWNER_BUSY: 'Another owner operation is running on this computer. Try again when it finishes.',
  SCOPE_DENIED: 'This application no longer has permission for that action.',
  ALREADY_RESOLVED: 'This suggestion has already been reviewed. Refresh to see its status.',
  SERVICE_UNAVAILABLE: 'The memory service could not be reached. If you confirmed a change, check its status before trying again.',
};
export const explain = error => messages[error.message] || 'We could not complete this request. Refresh to verify the current state.';
