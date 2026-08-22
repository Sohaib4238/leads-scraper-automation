import React from 'react';

export default function StatsBar({ stats, loading }) {
  if (loading || !stats) {
    return (
      <div className="stats-grid">
        <div className="stat-card"><div className="stat-label">Total database leads</div><div className="stat-value">...</div></div>
        <div className="stat-card"><div className="stat-label">Actionable leads</div><div className="stat-value">...</div></div>
        <div className="stat-card"><div className="stat-label">Warm & hot opportunities</div><div className="stat-value">...</div></div>
        <div className="stat-card"><div className="stat-label">Contact coverage</div><div className="stat-value">...</div></div>
      </div>
    );
  }

  const warmHotTotal = (stats.warm_count || 0) + (stats.hot_count || 0);

  return (
    <div className="stats-grid">
      <div className="stat-card">
        <div className="stat-label">Total database leads</div>
        <div className="stat-value">{stats.total_leads?.toLocaleString() ?? 0}</div>
        <div className="stat-subtext">Across {stats.cities?.length || 0} cities & {stats.categories?.length || 0} categories</div>
      </div>

      <div className="stat-card">
        <div className="stat-label">Actionable leads</div>
        <div className="stat-value">{stats.contactable_count?.toLocaleString() ?? 0}</div>
        <div className="stat-subtext">
          {stats.total_leads ? `${Math.round((stats.contactable_count / stats.total_leads) * 100)}% of total leads` : '0%'}
        </div>
      </div>

      <div className="stat-card">
        <div className="stat-label">Warm & hot opportunities</div>
        <div className="stat-value">{warmHotTotal.toLocaleString()}</div>
        <div className="stat-subtext">{stats.hot_count || 0} hot · {stats.warm_count || 0} warm</div>
      </div>

      <div className="stat-card">
        <div className="stat-label">Contact coverage</div>
        <div className="stat-value">{stats.phone_fill_rate ?? 0}%</div>
        <div className="stat-subtext">Phone: {stats.phone_fill_rate ?? 0}% · Email: {stats.email_fill_rate ?? 0}%</div>
      </div>
    </div>
  );
}
