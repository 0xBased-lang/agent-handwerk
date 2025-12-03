# Secrets Directory

This directory contains sensitive credentials that should NEVER be committed to version control.

## Files to Place Here

- `google-calendar-credentials.json` - Google Calendar service account credentials
- `ssl/` - SSL certificates (if not using Let's Encrypt)

## Example: Google Calendar Setup

1. Create a service account in Google Cloud Console
2. Download the JSON credentials file
3. Save as `google-calendar-credentials.json` in this directory
4. Set environment variable:
   ```
   ITF_INTEGRATIONS__CALENDAR__GOOGLE__CREDENTIALS_FILE=/app/secrets/google-calendar-credentials.json
   ```

## Security Notes

- All files in this directory are mounted read-only in Docker
- The directory is excluded from git via .gitignore
- Use Docker secrets for production deployments when possible
