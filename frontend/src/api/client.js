/**
 * API Client for FastAPI backend (Phase 4).
 * Uses VITE_API_BASE_URL from environment or defaults to http://localhost:8000.
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export async function fetchStats() {
  const res = await fetch(`${API_BASE_URL}/stats`);
  if (!res.ok) {
    throw new Error(`Failed to load database stats (${res.status} ${res.statusText})`);
  }
  return res.json();
}

export async function startSearch({ country, city, category, count }) {
  const res = await fetch(`${API_BASE_URL}/leads/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      country: country.trim(),
      city: city.trim(),
      category: category.trim(),
      count: Number(count),
    }),
  });

  if (res.status === 409) {
    const errorData = await res.json().catch(() => ({}));
    const err = new Error(errorData.detail || 'A scrape and analysis job is already in progress.');
    err.status = 409;
    throw err;
  }

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    const err = new Error(errorData.detail || `Search request failed with status ${res.status}`);
    err.status = res.status;
    throw err;
  }

  return res.json();
}

export async function getJobStatus(jobId) {
  const res = await fetch(`${API_BASE_URL}/leads/jobs/${jobId}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch job status (${res.status})`);
  }
  return res.json();
}

export async function fetchLeads(filters = {}, page = 1, pageSize = 20) {
  const params = new URLSearchParams();
  params.set('page', page);
  params.set('page_size', pageSize);

  if (filters.priority && filters.priority !== 'ALL') {
    params.set('priority', filters.priority);
  }
  if (filters.service && filters.service !== 'ALL') {
    params.set('service', filters.service);
  }
  if (filters.city && filters.city.trim()) {
    params.set('city', filters.city.trim());
  }
  if (filters.category && filters.category !== 'ALL' && filters.category.trim()) {
    params.set('category', filters.category.trim());
  }
  if (filters.minScore !== undefined && filters.minScore !== '' && Number(filters.minScore) > 0) {
    params.set('min_score', Number(filters.minScore));
  }
  if (filters.contactable !== undefined && filters.contactable !== null && filters.contactable !== 'ALL') {
    params.set('contactable', filters.contactable === 'YES' || filters.contactable === true);
  }
  if (filters.hasEmail) {
    params.set('has_email', true);
  }
  if (filters.hasPhone) {
    params.set('has_phone', true);
  }
  if (filters.noWebsite) {
    params.set('no_website', true);
  }

  const res = await fetch(`${API_BASE_URL}/leads?${params.toString()}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch leads (${res.status})`);
  }
  return res.json();
}

export async function fetchLeadById(id) {
  const res = await fetch(`${API_BASE_URL}/leads/${id}`);
  if (!res.ok) {
    throw new Error(`Lead #${id} not found (${res.status})`);
  }
  return res.json();
}

export function getExportDownloadUrl(format = 'csv', filters = {}) {
  const params = new URLSearchParams();
  params.set('format', format);

  if (filters.priority && filters.priority !== 'ALL') {
    params.set('priority', filters.priority);
  }
  if (filters.service && filters.service !== 'ALL') {
    params.set('service', filters.service);
  }
  if (filters.city && filters.city.trim()) {
    params.set('city', filters.city.trim());
  }
  if (filters.category && filters.category !== 'ALL' && filters.category.trim()) {
    params.set('category', filters.category.trim());
  }
  if (filters.minScore !== undefined && filters.minScore !== '' && Number(filters.minScore) > 0) {
    params.set('min_score', Number(filters.minScore));
  }
  if (filters.contactable !== undefined && filters.contactable !== null && filters.contactable !== 'ALL') {
    params.set('contactable', filters.contactable === 'YES' || filters.contactable === true);
  }
  if (filters.hasEmail) {
    params.set('has_email', true);
  }
  if (filters.hasPhone) {
    params.set('has_phone', true);
  }
  if (filters.noWebsite) {
    params.set('no_website', true);
  }

  return `${API_BASE_URL}/leads/export?${params.toString()}`;
}
