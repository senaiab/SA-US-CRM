# SA-US ERP Branding Setup

The software name is fixed as **SA-US ERP** and the developer branding is **SA Ultimate Solutions**.

## Add the client company's name and logo after installation

On the client PC, in the same folder as `SA_US_ERP_Client.exe`, update:

- `tenant_branding.json`
- `company_logo.png` (replace with the client company's logo file)

Example `tenant_branding.json` values:

```json
{
  "software_name": "SA-US ERP",
  "developer_name": "SA Ultimate Solutions",
  "client_company_name": "Avelon Travel Agency",
  "company_logo_path": "company_logo.png",
  "show_developer_branding": true,
  "app_logo_path": "branding/app_logo.png",
  "developer_logo_path": "branding/sa_ultimate_solutions_logo.png",
  "primary_color": "#1F4E78"
}
```

After editing the file and placing the logo, restart the client app.

## Branding files included

- `branding/app_logo.png` → app logo
- `branding/app_icon.ico` → Windows app icon for EXE build
- `branding/sa_ultimate_solutions_logo.png` → developer logo
