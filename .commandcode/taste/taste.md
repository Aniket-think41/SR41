# Taste (Continuously Learned by [CommandCode][cmd])

[cmd]: https://commandcode.ai/

# cli
- Use the Netlify CLI (`netlify deploy --build --prod`) for deploying sites and managing env vars instead of the Netlify UI dashboard. Confidence: 0.65

# backend
- Use AWS SES SMTP via `smtplib` (not boto3 SES API) for sending transactional emails — the SMTP credentials are separate from IAM keys. Confidence: 0.85
- After making backend or frontend changes, always align/update the CLI (`backend/integration/cli/`) and MCP (`backend/integration/mcp/`) packages to match the updated API. Confidence: 0.70

