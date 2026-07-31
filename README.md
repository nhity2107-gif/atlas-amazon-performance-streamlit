# Atlas Amazon Performance Dashboard

Streamlit dashboard for July 2026 Amazon order, Ads and employee KPI reporting.

## Local private database workflow

The production workflow stores raw reports and the SQLite database only under
`D:\Atlas Amazon Performance`. The public repository receives only
`snapshot/dashboard_snapshot.enc`, encrypted with Fernet. The decryption key is
kept in `D:\Atlas Amazon Performance\.secrets\dashboard_data_key.txt` and must
also be configured as the Streamlit secret `DASHBOARD_DATA_KEY`.

Example update:

```powershell
& "D:\Atlas Amazon Performance\update_dashboard.ps1" `
  -Store Wrappiness `
  -Report "D:\Atlas Amazon Performance\reports\orders\new-report.txt" `
  -Scope weekly `
  -Start 2026-07-01 `
  -End 2026-07-30 `
  -Publish
```

Daily imports upsert by `order-item-id`. Weekly and monthly imports replace the
store's complete Pacific-date interval before inserting the new report, ensuring
new late orders are added and cancelled or omitted orders are removed.
