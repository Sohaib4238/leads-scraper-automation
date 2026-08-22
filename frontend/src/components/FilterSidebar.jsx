import React from 'react';

const CANONICAL_SERVICES = [
  'Web Development',
  'Web App Development',
  'Mobile App Development',
  'SEO',
  'Social Media Marketing',
  'Social Media Management',
  'Google Ads',
  'Google Shopping',
  'AI Automation',
];

export default function FilterSidebar({ filters, setFilters, categories = [], onReset }) {
  const handleChange = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <div className="card">
      <div className="card-header">
        <h2 className="card-title">Filter leads</h2>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={onReset}
        >
          Reset
        </button>
      </div>

      <div className="form-group">
        <label className="form-label">Priority</label>
        <select
          className="form-select"
          value={filters.priority || 'ALL'}
          onChange={(e) => handleChange('priority', e.target.value)}
        >
          <option value="ALL">All priorities</option>
          <option value="HOT">HOT (Score 60–100)</option>
          <option value="WARM">WARM (Score 30–59)</option>
          <option value="COLD">COLD (Score 0–29)</option>
        </select>
      </div>

      <div className="form-group">
        <label className="form-label">Recommended service</label>
        <select
          className="form-select"
          value={filters.service || 'ALL'}
          onChange={(e) => handleChange('service', e.target.value)}
        >
          <option value="ALL">All services</option>
          {CANONICAL_SERVICES.map((svc) => (
            <option key={svc} value={svc}>{svc}</option>
          ))}
        </select>
      </div>

      <div className="form-group">
        <label className="form-label">Category / Industry</label>
        <select
          className="form-select"
          value={filters.category || 'ALL'}
          onChange={(e) => handleChange('category', e.target.value)}
        >
          <option value="ALL">All categories</option>
          {categories.map((cat) => (
            <option key={cat} value={cat}>{cat}</option>
          ))}
        </select>
      </div>

      <div className="form-group">
        <label className="form-label">City name</label>
        <input
          type="text"
          className="form-input"
          value={filters.city || ''}
          onChange={(e) => handleChange('city', e.target.value)}
          placeholder="Filter by city..."
        />
      </div>

      <div className="form-group">
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
          <label className="form-label" style={{ margin: 0 }}>Min opportunity score</label>
          <span style={{ fontSize: '12px', fontWeight: '600', color: 'var(--text-secondary)' }}>
            {filters.minScore || 0}
          </span>
        </div>
        <input
          type="range"
          min="0"
          max="100"
          step="5"
          value={filters.minScore || 0}
          onChange={(e) => handleChange('minScore', Number(e.target.value))}
          style={{ width: '100%' }}
        />
      </div>

      <div className="form-group">
        <label className="form-label">Contact readiness</label>
        <select
          className="form-select"
          value={filters.contactable || 'ALL'}
          onChange={(e) => handleChange('contactable', e.target.value)}
        >
          <option value="ALL">All leads</option>
          <option value="YES">Actionable (Phone or Email)</option>
          <option value="NO">Needs manual lookup</option>
        </select>
      </div>

      <div className="form-group">
        <label className="form-label">Contact & presence flags</label>
        <div className="checkbox-group">
          <label className="checkbox-label">
            <input
              type="checkbox"
              className="checkbox-input"
              checked={Boolean(filters.hasEmail)}
              onChange={(e) => handleChange('hasEmail', e.target.checked)}
            />
            Has email address
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              className="checkbox-input"
              checked={Boolean(filters.hasPhone)}
              onChange={(e) => handleChange('hasPhone', e.target.checked)}
            />
            Has phone number
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              className="checkbox-input"
              checked={Boolean(filters.noWebsite)}
              onChange={(e) => handleChange('noWebsite', e.target.checked)}
            />
            No website
          </label>
        </div>
      </div>
    </div>
  );
}
