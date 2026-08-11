Debt Manager - system edara al-madiuneyat
====================================

Installation:
  1. Copy this folder to the target device
  2. Ensure Python 3.10+, Node.js 18+, and Git are installed
  3. Run install.bat
  4. For desktop mode: double-click web2view.pyw
  5. For browser mode: double-click start.bat

Default login: admin / admin123

  *** SECURITY: Change the default password immediately after first login! ***
  Go to Users page and update the admin password.

WhatsApp: Run install_baileys.bat first, then start_baileys.bat
          Open Settings page to scan QR code.

Backup: Automatic daily backup at 3:00 AM
Debt Manager - Delivery notes
=============================

For a clean release, build the executable and installer, then run:
    python release_check.py

Do not share the dist\DebtManager folder if the check reports local data.
The installer intentionally excludes databases, secret keys, logs, WhatsApp sessions,
and node_modules. End users install WhatsApp dependencies locally only if they need
that optional feature.
