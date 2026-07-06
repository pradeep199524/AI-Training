export function getApiUrl() {
  const rawUrl = process.env.NEXT_PUBLIC_API_URL?.trim() || 'http://127.0.0.1:8000/api/v1';
  const trimmed = rawUrl.replace(/\/+$|\s+$/g, '');
  if (trimmed.endsWith('/api/v1')) {
    return trimmed;
  }
  if (trimmed.endsWith('/api')) {
    return `${trimmed}/v1`;
  }
  return `${trimmed}/api/v1`;
}

export function apiPath(path: string) {
  const normalizedPath = path.startsWith('/') ? path.slice(1) : path;
  return `${getApiUrl()}/${normalizedPath}`;
}
