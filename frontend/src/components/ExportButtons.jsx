import React from 'react';
import { getExportDownloadUrl } from '../api/client';

export default function ExportButtons({ filters = {}, total = 0 }) {
  const csvUrl = getExportDownloadUrl('csv', filters);
  const xlsxUrl = getExportDownloadUrl('xlsx', filters);

  return (
    <div className="btn-group">
      <a
        href={csvUrl}
        className="btn btn-secondary btn-sm"
        title="Download filtered leads as CSV"
      >
        Export CSV ({total})
      </a>
      <a
        href={xlsxUrl}
        className="btn btn-secondary btn-sm"
        title="Download filtered leads as Excel (.xlsx)"
      >
        Export Excel ({total})
      </a>
    </div>
  );
}
