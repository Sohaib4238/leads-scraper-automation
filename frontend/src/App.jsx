import React, { useEffect, useState, useCallback } from 'react';
import { fetchStats, fetchLeads } from './api/client';
import StatsBar from './components/StatsBar';
import SearchForm from './components/SearchForm';
import FilterSidebar from './components/FilterSidebar';
import LeadsTable from './components/LeadsTable';
import LeadDetailModal from './components/LeadDetailModal';
import ExportButtons from './components/ExportButtons';

export default function App() {
  const [stats, setStats] = useState(null);
  const [statsLoading, setStatsLoading] = useState(true);

  const [filters, setFilters] = useState({
    priority: 'ALL',
    service: 'ALL',
    category: 'ALL',
    city: '',
    minScore: 0,
    contactable: 'ALL',
    hasEmail: false,
    hasPhone: false,
    noWebsite: false,
  });

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const [leadsData, setLeadsData] = useState({ leads: [], total: 0, total_pages: 1 });
  const [leadsLoading, setLeadsLoading] = useState(false);

  const [selectedLeadId, setSelectedLeadId] = useState(null);
  const [appError, setAppError] = useState(null);

  // Load stats from MySQL backend
  const loadStats = useCallback(async () => {
    try {
      setStatsLoading(true);
      const data = await fetchStats();
      setStats(data);
      setStatsLoading(false);
    } catch (err) {
      setAppError(`Failed to connect to backend API: ${err.message}. Ensure FastAPI server is running.`);
      setStatsLoading(false);
    }
  }, []);

  // Load paginated leads from MySQL backend
  const loadLeads = useCallback(async () => {
    try {
      setLeadsLoading(true);
      setAppError(null);
      const data = await fetchLeads(filters, page, pageSize);
      setLeadsData(data);
      setLeadsLoading(false);
    } catch (err) {
      setAppError(`Error loading leads: ${err.message}`);
      setLeadsLoading(false);
    }
  }, [filters, page, pageSize]);

  // Initial load
  useEffect(() => {
    loadStats();
  }, [loadStats]);

  // Load leads when filters or pagination changes
  useEffect(() => {
    loadLeads();
  }, [loadLeads]);

  // Reset page to 1 when filters change
  const handleFilterChange = (newFilters) => {
    setPage(1);
    setFilters(newFilters);
  };

  const handleResetFilters = () => {
    setPage(1);
    setFilters({
      priority: 'ALL',
      service: 'ALL',
      category: 'ALL',
      city: '',
      minScore: 0,
      contactable: 'ALL',
      hasEmail: false,
      hasPhone: false,
      noWebsite: false,
    });
  };

  // Called when background search finishes
  const handleSearchComplete = (jobResult) => {
    loadStats();
    loadLeads();
  };

  return (
    <div className="app-container">
      {/* Header */}
      <header className="app-header">
        <div>
          <h1 className="app-title">Lead scraper & agency qualification engine</h1>
          <p className="app-subtitle">
            Automated multi-source business discovery, deep website auditing, and agency sales qualification
          </p>
        </div>
        <ExportButtons filters={filters} total={leadsData.total} />
      </header>

      {/* Global Error Banner */}
      {appError && (
        <div className="alert-banner alert-error" style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span>{appError}</span>
          <button
            type="button"
            onClick={() => setAppError(null)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#991b1b', fontWeight: 'bold' }}
          >
            ✕
          </button>
        </div>
      )}

      {/* Real-time KPI Stats Cards */}
      <StatsBar stats={stats} loading={statsLoading} />

      {/* Main Content Layout */}
      <div className="main-layout">
        {/* Left Column: Search & Filters */}
        <aside>
          <SearchForm
            categories={stats?.categories || []}
            onSearchComplete={handleSearchComplete}
            onError={(msg) => setAppError(msg)}
          />

          <FilterSidebar
            filters={filters}
            setFilters={handleFilterChange}
            categories={stats?.categories || []}
            onReset={handleResetFilters}
          />
        </aside>

        {/* Right Column: Leads Table */}
        <main>
          <LeadsTable
            leads={leadsData.leads}
            total={leadsData.total}
            page={page}
            pageSize={pageSize}
            totalPages={leadsData.total_pages}
            onPageChange={(newPage) => setPage(newPage)}
            onPageSizeChange={(newSize) => {
              setPageSize(newSize);
              setPage(1);
            }}
            onSelectLead={(id) => setSelectedLeadId(id)}
            loading={leadsLoading}
          />
        </main>
      </div>

      {/* Single Lead Detail Modal */}
      {selectedLeadId && (
        <LeadDetailModal
          leadId={selectedLeadId}
          onClose={() => setSelectedLeadId(null)}
        />
      )}
    </div>
  );
}
