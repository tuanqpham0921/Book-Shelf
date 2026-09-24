import { initializeApp } from 'firebase/app';
import { initializeAppCheck, ReCaptchaEnterpriseProvider, getToken } from 'firebase/app-check';

// Supplied at build time by Vite: .env.development for `npm run dev`,
// .env.production for `npm run build` (both committed — the URL is public).
const BASE_URL = import.meta.env.VITE_API_URL

// Firebase App Check: the backend refuses every route but health without a
// token proving the request came from this site. Only the production build
// carries the reCAPTCHA key, so `npm run dev` sends no token — and the local
// backend, with no APP_FIREBASE_PROJECT_NUMBER, asks for none. These values
// identify the app and are public by design; they are not secrets.
const RECAPTCHA_SITE_KEY = import.meta.env.VITE_RECAPTCHA_SITE_KEY;
const appCheck = RECAPTCHA_SITE_KEY
  ? initializeAppCheck(
      initializeApp({
        apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
        appId: import.meta.env.VITE_FIREBASE_APP_ID,
        projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
      }),
      {
        provider: new ReCaptchaEnterpriseProvider(RECAPTCHA_SITE_KEY),
        isTokenAutoRefreshEnabled: true,
      }
    )
  : null;

async function appCheckHeaders() {
  if (!appCheck) return {};
  // cached by the SDK and refreshed before it expires, so this is usually free
  const { token } = await getToken(appCheck);
  return { 'X-Firebase-AppCheck': token };
}

const DEFAULT_TIMEOUT_MS = 120000; // 2 minutes

async function fetch_api(url, options = {}, timeoutMs = DEFAULT_TIMEOUT_MS) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  // Combine timeout signal with user-provided signal
  const userSignal = options.signal;
  let combinedSignal = controller.signal;

  if (userSignal) {
    // Create a combined signal that aborts when either signal aborts
    const combinedController = new AbortController();
    combinedSignal = combinedController.signal;

    const abort = (reason) => combinedController.abort(reason);

    if (controller.signal.aborted || userSignal.aborted) {
      abort();
    } else {
      controller.signal.addEventListener('abort', () => abort('timeout'));
      userSignal.addEventListener('abort', () => abort('user_cancelled'));
    }
  }

  try {
    const res = await fetch(url, {
      ...options,
      headers: { ...options.headers, ...(await appCheckHeaders()) },
      signal: combinedSignal
    });

    clearTimeout(timeoutId);

    if (!res.ok) {
      const errorData = res.headers.get('content-type')?.includes('application/json')
        ? await res.json()
        : { error: 'Request failed' };
      // reject with a real Error (not a plain object) so callers can rely
      // on instanceof/.name checks (e.g. ChatBot.jsx's AbortError handling)
      return Promise.reject(
        Object.assign(new Error('Request failed'), { status: res.status, data: errorData })
      );
    }

    return res;
  } catch (error) {
    clearTimeout(timeoutId);
    if (error.name === 'AbortError') {
      return Promise.reject(
        Object.assign(new Error('Request timeout or cancelled'), {
          name: 'AbortError',
          status: 408,
          data: { error: 'Request timeout or cancelled' },
        })
      );
    }
    throw error;
  }
}

async function backEndPing() {
  try {
    const res = await fetch_api(BASE_URL + '/ping', { method: 'GET' });
    const data = await res.json();
    return data.status === 'ok';
  } catch {
    return false;
  }
}

async function createSession() {
  const res = await fetch_api(BASE_URL + '/session/new', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  });
  return await res.json();
}

async function sendChatMessage(sessionId, message, abortSignal = null, timeoutMs = DEFAULT_TIMEOUT_MS) {
  const res = await fetch_api(
    BASE_URL + `/session/${sessionId}/message`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
      signal: abortSignal // Pass abort signal to fetch_api
    },
    timeoutMs
  );
  return res.body;
}

// Like or dislike one of this session's own replies; re-sending replaces the
// earlier reaction. The backend 404s a chat run this session didn't produce,
// or one it hasn't finished recording yet.
async function sendFeedback(sessionId, chatId, liked) {
  const res = await fetch_api(BASE_URL + `/session/${sessionId}/message/${chatId}/feedback`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ liked })
  });
  return await res.json();
}


// Fetch recorded chat runs for the review page, in review-queue order
// (least-reviewed first, newest first within a tie), each with its derived
// num_reviews; sessionId optionally narrows to runs whose session_id
// contains the search string.
async function getChatRuns(limit = 200, offset = 0, sessionId = null) {
  const params = new URLSearchParams({ limit, offset });
  if (sessionId) params.set('session_id', sessionId);
  const res = await fetch_api(BASE_URL + `/chat_runs?${params}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' }
  });
  return await res.json();
}

// Fetch all reviews of one chat run, oldest first.
async function getFeedback(chatId) {
  const res = await fetch_api(BASE_URL + `/feedback?chat_id=${chatId}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' }
  });
  return await res.json();
}

// Submit (or replace) this review session's review of one chat run: the
// overall like/dislike plus the full comments list ({title, message,
// positive} each). One review per (chat_id, session_id) — re-submitting
// from the same session replaces the previous version whole.
async function submitReview({ chatId, sessionId, liked = null, comments = [] }) {
  const res = await fetch_api(BASE_URL + '/feedback/review', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: chatId, session_id: sessionId, liked, comments })
  });
  return await res.json();
}

export default {
  createSession, sendChatMessage, sendFeedback, backEndPing,
  getChatRuns, getFeedback, submitReview
};
