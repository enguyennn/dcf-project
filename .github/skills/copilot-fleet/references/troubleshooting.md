# Copilot Fleet — Troubleshooting

## Common Issues

### "copilot: command not found"

The Copilot CLI is not installed or not on PATH.

**Fix:** Install the Copilot CLI:
- Visit https://aka.ms/copilot-cli for installation instructions
- Ensure the install directory is on your PATH
- Restart your terminal after installation

### Authentication failure

Copilot CLI requires an active GitHub Copilot subscription.

**Fix:**
1. Run `copilot` manually and complete authentication
2. Verify with `copilot --version`
3. Ensure your GitHub account has an active Copilot subscription

### Session completes but docs are empty/incomplete

The fleet session ran but produced low-quality output.

**Possible causes:**
- Missing instruction file references in the fleet prompt
- Repository too large for a single session
- Bluebird/code-search not configured

**Fix:**
1. Verify instruction `@` references are correct in the fleet prompt
2. Scope to specific subsystems instead of full repo
3. Configure code-search MCP for better code discovery
