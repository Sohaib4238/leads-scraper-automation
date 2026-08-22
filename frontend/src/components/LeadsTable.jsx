import React, { useState } from 'react';

export default function LeadsTable({
  leads = [],
  total = 0,
  page = 1,
  pageSize = 20,
  totalPages = 1,
  onPageChange,
  onPageSizeChange,
  onSelectLead,
  loading = false,
}) {
  const [sortField, setSortField] = useState('score');
  const [sortDir, setSortDir] = useState('desc');

  const handleSort = (field) => {
    if (sortField === field) {
      setSortDir((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortDir('desc');
    }
  };

  // Sort the current page in-memory
  const sortedLeads = [...leads].sort((a, b) => {
    let valA = a[sortField];
    let valB = b[sortField];

    if (valA === null || valA === undefined) valA = '';
    if (valB === null || valB === undefined) valB = '';

    if (typeof valA === 'string') {
      return sortDir === 'asc'
        ? valA.localeCompare(String(valB))
        : String(valB).localeCompare(valA);
    }

    return sortDir === 'asc' ? valA - valB : valB - valA;
  });

  const getPriorityBadgeClass = (priority) => {
    switch (priority) {
      case 'HOT':
        return 'badge badge-hot';
      case 'WARM':
        return 'badge badge-warm';
      case 'COLD':
        return 'badge badge-cold';
      default:
        return 'badge badge-cold';
    }
  };

  return (
    <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
      <div style={{ padding: '16px 20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border)' }}>
        <div>
          <h2 className="card-title" style={{ margin: 0 }}>Qualified leads</h2>
          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            Showing {leads.length > 0 ? (page - 1) * pageSize + 1 : 0}–{Math.min(page * pageSize, total)} of {total.toLocaleString()} total matching leads
          </span>
        </div>
      </div>

      <div className="table-responsive">
        <table className="leads-table">
          <thead>
            <tr>
              <th onClick={() => handleSort('id')}>ID {sortField === 'id' ? (sortDir === 'asc' ? '▲' : '▼') : ''}</th>
              <th onClick={() => handleSort('business_name')}>Business name {sortField === 'business_name' ? (sortDir === 'asc' ? '▲' : '▼') : ''}</th>
              <th onClick={() => handleSort('category')}>Category {sortField === 'category' ? (sortDir === 'asc' ? '▲' : '▼') : ''}</th>
              <th onClick={() => handleSort('city')}>Location {sortField === 'city' ? (sortDir === 'asc' ? '▲' : '▼') : ''}</th>
              <th>Phone</th>
              <th>Email</th>
              <th>Website</th>
              <th onClick={() => handleSort('score')}>Score {sortField === 'score' ? (sortDir === 'asc' ? '▲' : '▼') : ''}</th>
              <th onClick={() => handleSort('priority')}>Priority {sortField === 'priority' ? (sortDir === 'asc' ? '▲' : '▼') : ''}</th>
              <th>Contact readiness</th>
              <th>Services</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan="12" style={{ textAlign: 'center', padding: '32px', color: 'var(--text-muted)' }}>
                  Loading leads from database...
                </td>
              </tr>
            ) : sortedLeads.length === 0 ? (
              <tr>
                <td colSpan="12" style={{ textAlign: 'center', padding: '32px', color: 'var(--text-muted)' }}>
                  No leads found matching current filter criteria.
                </td>
              </tr>
            ) : (
              sortedLeads.map((lead) => (
                <tr key={lead.id}>
                  <td style={{ color: 'var(--text-muted)', fontSize: '12px' }}>#{lead.id}</td>
                  <td style={{ fontWeight: '600', maxWidth: '200px' }}>{lead.business_name || 'Unnamed Business'}</td>
                  <td><span className="tag">{lead.category || 'General'}</span></td>
                  <td>{lead.city ? `${lead.city}, ${lead.country || ''}` : lead.country || '—'}</td>
                  <td>{lead.phone || <span style={{ color: 'var(--text-muted)' }}>—</span>}</td>
                  <td>
                    {lead.email ? (
                      <a href={`mailto:${lead.email}`} style={{ color: '#2563eb', textDecoration: 'none' }}>
                        {lead.email}
                      </a>
                    ) : (
                      <span style={{ color: 'var(--text-muted)' }}>—</span>
                    )}
                  </td>
                  <td>
                    {lead.website ? (
                      <a
                        href={lead.website.startsWith('http') ? lead.website : `http://${lead.website}`}
                        target="_blank"
                        rel="noreferrer"
                        style={{ color: '#2563eb', textDecoration: 'none', maxWidth: '140px', display: 'inline-block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                      >
                        {lead.website.replace(/^https?:\/\//, '')}
                      </a>
                    ) : (
                      <span style={{ color: 'var(--text-muted)' }}>No website</span>
                    )}
                  </td>
                  <td style={{ fontWeight: '700' }}>{lead.score ?? '—'}</td>
                  <td>
                    <span className={getPriorityBadgeClass(lead.priority)}>
                      {lead.priority || 'COLD'}
                    </span>
                  </td>
                  <td>
                    {lead.contactable ? (
                      <span className="badge badge-ready">Actionable</span>
                    ) : (
                      <span className="badge badge-lookup">Needs lookup</span>
                    )}
                  </td>
                  <td style={{ maxWidth: '220px' }}>
                    {lead.matched_services && lead.matched_services.length > 0 ? (
                      <div>
                        {lead.matched_services.slice(0, 2).map((svc) => (
                          <span key={svc} className="tag">{svc}</span>
                        ))}
                        {lead.matched_services.length > 2 && (
                          <span className="tag" style={{ color: 'var(--text-muted)' }}>
                            +{lead.matched_services.length - 2}
                          </span>
                        )}
                      </div>
                    ) : (
                      <span style={{ color: 'var(--text-muted)' }}>—</span>
                    )}
                  </td>
                  <td>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => onSelectLead?.(lead.id)}
                    >
                      View
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="pagination-bar">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span>Rows per page:</span>
          <select
            className="form-select"
            style={{ width: 'auto', padding: '4px 8px', fontSize: '12px' }}
            value={pageSize}
            onChange={(e) => onPageSizeChange?.(Number(e.target.value))}
          >
            <option value={10}>10</option>
            <option value={20}>20</option>
            <option value={50}>50</option>
            <option value={100}>100</option>
          </select>
        </div>

        <div className="pagination-controls">
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            disabled={page <= 1}
            onClick={() => onPageChange?.(page - 1)}
          >
            Previous
          </button>
          <span>
            Page {page} of {totalPages || 1}
          </span>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            disabled={page >= totalPages}
            onClick={() => onPageChange?.(page + 1)}
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
