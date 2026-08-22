import React, { useState } from 'react';
import { startSearch, getJobStatus } from '../api/client';

export default function SearchForm({ categories = [], onSearchComplete, onError }) {
  const [country, setCountry] = useState('US');
  const [city, setCity] = useState('Miami');
  const [categoryOption, setCategoryOption] = useState('real estate');
  const [customCategory, setCustomCategory] = useState('');
  const [count, setCount] = useState(20);

  const [activeJob, setActiveJob] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [jobError, setJobError] = useState(null);

  // Common country presets
  const countries = [
    { code: 'US', name: 'United States (US)' },
    { code: 'CA', name: 'Canada (CA)' },
    { code: 'GB', name: 'United Kingdom (GB)' },
    { code: 'DE', name: 'Germany (DE)' },
    { code: 'AE', name: 'United Arab Emirates (AE)' },
    { code: 'PK', name: 'Pakistan (PK)' },
  ];

  // Combine fetched categories with standard presets
  const standardPresets = ['dentist', 'real estate', 'lawyer', 'cafe', 'clothing store', 'gym', 'car repair', 'hotel'];
  const allCategories = Array.from(new Set([...categories, ...standardPresets])).filter(Boolean).sort();

  const finalCategory = categoryOption === '__custom__' ? customCategory : categoryOption;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!city.trim() || !finalCategory.trim()) {
      onError?.('Please enter both a city and a category.');
      return;
    }

    setIsSubmitting(true);
    setJobError(null);

    try {
      const resp = await startSearch({
        country,
        city: city.trim(),
        category: finalCategory.trim(),
        count: Number(count),
      });

      const jobId = resp.job_id;
      setActiveJob({
        job_id: jobId,
        status: 'pending',
        progress: 'Queued',
        category: finalCategory.trim(),
        city: city.trim(),
      });

      // Start polling
      pollJob(jobId);
    } catch (err) {
      if (err.status === 409) {
        setJobError('A scrape and analysis job is already in progress. Please wait for it to complete.');
      } else {
        setJobError(err.message || 'Failed to start lead search job.');
      }
      setIsSubmitting(false);
    }
  };

  const pollJob = (jobId) => {
    const interval = setInterval(async () => {
      try {
        const statusData = await getJobStatus(jobId);
        setActiveJob(statusData);

        if (statusData.status === 'complete') {
          clearInterval(interval);
          setIsSubmitting(false);
          onSearchComplete?.(statusData);
        } else if (statusData.status === 'failed') {
          clearInterval(interval);
          setIsSubmitting(false);
          setJobError(statusData.error || 'Job failed during execution.');
        }
      } catch (err) {
        clearInterval(interval);
        setIsSubmitting(false);
        setJobError(`Error polling job status: ${err.message}`);
      }
    }, 2000);
  };

  const isJobRunning = isSubmitting || (activeJob && (activeJob.status === 'pending' || activeJob.status === 'running'));

  return (
    <div className="card">
      <div className="card-header">
        <h2 className="card-title">Search & analyze leads</h2>
      </div>

      {jobError && (
        <div className="alert-banner alert-warning">
          {jobError}
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label className="form-label">Country</label>
          <select
            className="form-select"
            value={country}
            onChange={(e) => setCountry(e.target.value)}
            disabled={isJobRunning}
          >
            {countries.map((c) => (
              <option key={c.code} value={c.code}>{c.name}</option>
            ))}
          </select>
        </div>

        <div className="form-group">
          <label className="form-label">City</label>
          <input
            type="text"
            className="form-input"
            value={city}
            onChange={(e) => setCity(e.target.value)}
            placeholder="e.g. Miami, Toronto, Berlin"
            required
            disabled={isJobRunning}
          />
        </div>

        <div className="form-group">
          <label className="form-label">Category / Industry</label>
          <select
            className="form-select"
            value={categoryOption}
            onChange={(e) => setCategoryOption(e.target.value)}
            disabled={isJobRunning}
          >
            {allCategories.map((cat) => (
              <option key={cat} value={cat}>{cat}</option>
            ))}
            <option value="__custom__">+ Enter custom category...</option>
          </select>
        </div>

        {categoryOption === '__custom__' && (
          <div className="form-group">
            <label className="form-label">Custom category name</label>
            <input
              type="text"
              className="form-input"
              value={customCategory}
              onChange={(e) => setCustomCategory(e.target.value)}
              placeholder="e.g. orthodontist, accountant, spa"
              required
              disabled={isJobRunning}
            />
          </div>
        )}

        <div className="form-group">
          <label className="form-label">Total unique leads to scrape</label>
          <input
            type="number"
            className="form-input"
            min="1"
            max="100"
            value={count}
            onChange={(e) => setCount(e.target.value)}
            disabled={isJobRunning}
          />
        </div>

        <button
          type="submit"
          className="btn btn-primary"
          disabled={isJobRunning}
        >
          {isJobRunning ? 'Search in progress...' : 'Search & analyze leads'}
        </button>
      </form>

      {activeJob && (
        <div className="progress-box">
          <div className="progress-header">
            <span>Status: {activeJob.status}</span>
            <span>{activeJob.category} in {activeJob.city}</span>
          </div>
          <div className="progress-message">
            {activeJob.progress || 'Processing request...'}
          </div>
          {activeJob.status === 'complete' && activeJob.result && (
            <div style={{ marginTop: '8px', fontSize: '12px', color: '#166534' }}>
              Completed: {activeJob.result.new_leads_saved} unique leads saved, {activeJob.result.total_analyzed} enriched ({activeJob.result.actionable_leads} actionable).
            </div>
          )}
        </div>
      )}
    </div>
  );
}
