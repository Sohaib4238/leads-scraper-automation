import React, { useEffect, useState } from 'react';
import { fetchLeadById } from '../api/client';

export default function LeadDetailModal({ leadId, onClose }) {
  const [lead, setLead] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!leadId) return;
    setLoading(true);
    setError(null);

    fetchLeadById(leadId)
      .then((data) => {
        setLead(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message || 'Failed to load lead details.');
        setLoading(false);
      });
  }, [leadId]);

  if (!leadId) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h3 className="modal-title">{lead?.business_name || `Lead #${leadId}`}</h3>
            <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
              {lead?.category} · {lead?.city}, {lead?.country}
            </span>
          </div>
          <button type="button" className="modal-close" onClick={onClose}>
            ✕
          </button>
        </div>

        {loading ? (
          <div style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)' }}>
            Loading lead profile...
          </div>
        ) : error ? (
          <div className="alert-banner alert-error">{error}</div>
        ) : lead ? (
          <div>
            <div className="detail-grid">
              <div className="detail-item">
                <div className="detail-label">Opportunity Score</div>
                <div className="detail-value" style={{ fontWeight: '700', fontSize: '16px' }}>
                  {lead.score ?? '—'}/100 ({lead.priority || 'COLD'})
                </div>
              </div>

              <div className="detail-item">
                <div className="detail-label">Readiness Status</div>
                <div className="detail-value">
                  {lead.contactable ? (
                    <span className="badge badge-ready">Actionable Lead</span>
                  ) : (
                    <span className="badge badge-lookup">Needs Manual Lookup</span>
                  )}
                </div>
              </div>

              <div className="detail-item">
                <div className="detail-label">Phone Number</div>
                <div className="detail-value">
                  {lead.phone ? (
                    <a href={`tel:${lead.phone}`} style={{ color: '#2563eb', textDecoration: 'none' }}>
                      {lead.phone}
                    </a>
                  ) : (
                    'Not found on public tags'
                  )}
                </div>
              </div>

              <div className="detail-item">
                <div className="detail-label">Email Address</div>
                <div className="detail-value">
                  {lead.email ? (
                    <a href={`mailto:${lead.email}`} style={{ color: '#2563eb', textDecoration: 'none' }}>
                      {lead.email}
                    </a>
                  ) : (
                    'Not found'
                  )}
                </div>
              </div>

              <div className="detail-item">
                <div className="detail-label">Website URL</div>
                <div className="detail-value">
                  {lead.website ? (
                    <a href={lead.website.startsWith('http') ? lead.website : `http://${lead.website}`} target="_blank" rel="noreferrer" style={{ color: '#2563eb' }}>
                      {lead.website}
                    </a>
                  ) : (
                    'No active website found'
                  )}
                </div>
              </div>

              <div className="detail-item">
                <div className="detail-label">Physical Address</div>
                <div className="detail-value">{lead.address || 'Address not listed'}</div>
              </div>
            </div>

            {/* Performance Signals */}
            <div className="detail-box">
              <div style={{ fontWeight: '600', marginBottom: '8px', fontSize: '13px' }}>
                Technical Performance Signals
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', fontSize: '12px' }}>
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>Response time: </span>
                  <strong>{lead.response_time_ms ? `${lead.response_time_ms} ms` : '—'}</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>Page size: </span>
                  <strong>{lead.page_size_kb ? `${lead.page_size_kb} KB` : '—'}</strong>
                </div>
              </div>
            </div>

            {/* Recommended Pitch Services */}
            <div className="detail-box">
              <div style={{ fontWeight: '600', marginBottom: '6px', fontSize: '13px' }}>
                Matched Agency Pitch Services
              </div>
              <div style={{ marginBottom: '8px' }}>
                {lead.matched_services && lead.matched_services.length > 0 ? (
                  lead.matched_services.map((s) => (
                    <span key={s} className="tag" style={{ backgroundColor: '#ffffff', borderColor: 'var(--border)' }}>
                      {s}
                    </span>
                  ))
                ) : (
                  <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>No severe service gaps detected.</span>
                )}
              </div>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: '1.4' }}>
                {lead.reason || 'Lead audit completed.'}
              </div>
            </div>

            {/* Social & Provenance */}
            <div style={{ marginTop: '16px', display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: 'var(--text-muted)' }}>
              <div>
                Sources: {lead.discovery_sources?.join(', ') || 'Map discovery'}
              </div>
              <div>
                Created: {lead.created_at ? new Date(lead.created_at).toLocaleDateString() : '—'}
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
