# Taste (Continuously Learned by [CommandCode][cmd])

[cmd]: https://commandcode.ai/

# cli
- Use the Netlify CLI (`netlify deploy --build --prod`) for deploying sites and managing env vars instead of the Netlify UI dashboard. Confidence: 0.65

# backend
- Use AWS SES via boto3 for sending transactional emails (org invitations, notifications). Confidence: 0.65
- After making backend or frontend changes, always align/update the CLI (`backend/integration/cli/`) and MCP (`backend/integration/mcp/`) packages to match the updated API. Confidence: 0.70

